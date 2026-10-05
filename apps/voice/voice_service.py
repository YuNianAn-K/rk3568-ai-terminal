#!/usr/bin/env python3
"""Headless voice service for the Qt AI Voice application."""

import argparse
import json
import os
import signal
import socket
import threading
import time


DEFAULT_SOCKET_PATH = "/tmp/ai-voice.sock"
MAX_MESSAGE_BYTES = 64 * 1024


def create_terminal(event_callback):
    """Import lazily so offline protocol tests also run on Windows."""
    from main import AIVoiceTerminal
    return AIVoiceTerminal(event_callback=event_callback)


class VoiceService:
    """Single-round voice controller exposed through JSON Lines over AF_UNIX."""

    STARTABLE_STATES = {"idle", "error"}

    def __init__(self, socket_path=DEFAULT_SOCKET_PATH,
                 terminal_factory=create_terminal):
        self.socket_path = socket_path
        self.terminal_factory = terminal_factory
        self.terminal = None
        self.server_socket = None
        self.clients = set()
        self.clients_lock = threading.Lock()
        self.command_lock = threading.RLock()
        self.state_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.state = "initializing"
        self.message = "正在初始化语音服务"
        self.transcript = ""
        self.answer = ""
        self.last_error = ""
        self.round_id = 0
        self.round_failed = False
        self.round_worker_active = False
        self.service_started_at = time.monotonic()
        self.round_started_mono_ms = None
        self.timings = {}
        self.wake_detector = None
        self.wake_enabled = False
        self.wake_resume_at = 0.0
        self.wake_thread = None

    def snapshot(self):
        with self.state_lock:
            snapshot = {
                "type": "snapshot",
                "state": self.state,
                "message": self.message,
                "transcript": self.transcript,
                "answer": self.answer,
                "error": self.last_error,
                "round_id": self.round_id,
                "timings": dict(self.timings),
            }
        snapshot["diagnostics"] = self._collect_diagnostics()
        return snapshot

    def initialize_terminal(self):
        """Initialize cloud/audio adapters once while the socket stays responsive."""
        try:
            terminal = self.terminal_factory(self._on_terminal_event)
            terminal._recording = False
            terminal._record_proc = None
            terminal._audio_file = None
            terminal._retry_count = 0
            with self.command_lock:
                if self.stop_event.is_set():
                    terminal.close()
                    return False
                self.terminal = terminal
                if not terminal.recorder.has_mic:
                    self._set_error("没有检测到麦克风")
                    return False
                self._set_state("idle", "语音服务已就绪")
                from config import VOICE_WAKE_ENABLE
                if VOICE_WAKE_ENABLE:
                    self._configure_wake(True)
                return True
        except Exception as e:
            print(f"Voice service initialization failed: {type(e).__name__}: {e}",
                  flush=True)
            self._set_error(f"语音服务初始化失败：{type(e).__name__}")
            return False

    def _on_terminal_event(self, event_type, payload):
        payload = dict(payload or {})
        if event_type == "state":
            self._set_state(payload.get("state", "idle"),
                            payload.get("message", ""))
            return

        if event_type == "transcript":
            text = str(payload.get("text", ""))
            with self.state_lock:
                self.transcript = text
            self._broadcast({"type": "transcript", "text": text,
                             "round_id": self.round_id})
            return

        if event_type == "answer_delta":
            text = str(payload.get("text", ""))
            with self.state_lock:
                self.answer += text
            self._broadcast({"type": "answer_delta", "text": text,
                             "round_id": self.round_id})
            return

        if event_type == "answer":
            text = str(payload.get("text", ""))
            with self.state_lock:
                self.answer = text
            self._broadcast({"type": "answer", "text": text,
                             "round_id": self.round_id})
            return

        if event_type == "timing":
            self._mark_stage(
                str(payload.get("stage", "")),
                monotonic_ms=payload.get("monotonic_ms"),
                wall_ms=payload.get("wall_ms"),
            )
            return

        if event_type == "error":
            self._set_error(str(payload.get("message", "语音处理失败")))

    def _set_state(self, state, message=""):
        with self.state_lock:
            self.state = state
            self.message = message
            round_id = self.round_id
        self._broadcast({"type": "state", "state": state,
                         "message": message, "round_id": round_id})

    def _set_error(self, message):
        with self.state_lock:
            self.state = "error"
            self.message = message
            self.last_error = message
            self.round_failed = True
            round_id = self.round_id
        self._broadcast({"type": "error", "message": message,
                         "round_id": round_id})

    def _mark_stage(self, stage, monotonic_ms=None, wall_ms=None):
        if not stage:
            return
        try:
            mono_ms = int(monotonic_ms)
        except (TypeError, ValueError):
            mono_ms = int(time.monotonic() * 1000)
        try:
            timestamp_ms = int(wall_ms)
        except (TypeError, ValueError):
            timestamp_ms = int(time.time() * 1000)

        with self.state_lock:
            if self.round_started_mono_ms is None:
                self.round_started_mono_ms = mono_ms
            elapsed_ms = max(0, mono_ms - self.round_started_mono_ms)
            self.timings[stage] = elapsed_ms
            round_id = self.round_id
        print(
            f"[VOICE][round={round_id}][stage={stage}]"
            f"[t={timestamp_ms}][elapsed_ms={elapsed_ms}]",
            flush=True,
        )
        self._broadcast({
            "type": "timing",
            "stage": stage,
            "elapsed_ms": elapsed_ms,
            "round_id": round_id,
        })

    def _collect_diagnostics(self):
        mem_available_kb = 0
        service_rss_kb = 0
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemAvailable:"):
                        mem_available_kb = int(line.split()[1])
                        break
        except (OSError, ValueError, IndexError):
            pass
        try:
            with open("/proc/self/status", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        service_rss_kb = int(line.split()[1])
                        break
        except (OSError, ValueError, IndexError):
            pass

        network = "unknown"
        try:
            with open("/proc/net/route", "r", encoding="utf-8") as handle:
                routes = handle.read().splitlines()[1:]
            network = "up" if any(
                len(fields := line.split()) >= 4 and
                fields[0] != "lo" and fields[1] == "00000000" and
                (int(fields[3], 16) & 0x2)
                for line in routes
            ) else "down"
        except (OSError, ValueError):
            pass

        with self.clients_lock:
            client_count = len(self.clients)
        return {
            "memory_available_mb": mem_available_kb // 1024,
            "service_rss_mb": service_rss_kb // 1024,
            "service_uptime_s": int(time.monotonic() - self.service_started_at),
            "network": network,
            "clients": client_count,
        }

    def _send_json(self, conn, message):
        if conn is None:
            return
        data = (json.dumps(message, ensure_ascii=False,
                           separators=(",", ":")) + "\n").encode("utf-8")
        conn.sendall(data)

    def _broadcast(self, message):
        with self.clients_lock:
            clients = list(self.clients)
        dead = []
        for conn in clients:
            try:
                self._send_json(conn, message)
            except OSError:
                dead.append(conn)
        if dead:
            with self.clients_lock:
                for conn in dead:
                    self.clients.discard(conn)
                    try:
                        conn.close()
                    except OSError:
                        pass

    def handle_command(self, command, conn=None):
        """Validate and dispatch one decoded command. Returns the ack payload."""
        if not isinstance(command, dict):
            return self._reply(conn, False, "invalid", "命令格式错误")

        name = command.get("command")
        if name == "status":
            response = self.snapshot()
            self._send_json(conn, response)
            return response
        if name == "start":
            return self._start_round(conn)
        if name == "stop":
            return self._begin_finish(conn, automatic=False)
        if name == "cancel":
            return self._cancel_round(conn)
        if name in ("wake_enable", "wake_disable"):
            with self.command_lock:
                if self.state not in self.STARTABLE_STATES or self.round_worker_active:
                    return self._reply(conn, False, "busy", "请等本轮结束后切换唤醒")
                ok = self._configure_wake(name == "wake_enable")
                return self._reply(conn, ok, "wake_mode" if ok else "wake_unavailable", self.message)
        return self._reply(conn, False, "invalid", "未知命令")

    def _configure_wake(self, enabled):
        if self.stop_event.is_set() or (enabled and self.terminal is None):
            return False
        try:
            if enabled and self.wake_detector is None:
                from config import VOICE_WAKE_MODEL_PATH
                from wake.sherpa_keyword import ChineseWakeDetector
                self.wake_detector = ChineseWakeDetector(VOICE_WAKE_MODEL_PATH)
            if not enabled and self.wake_detector:
                self.wake_detector.pause()
            self.wake_enabled = enabled
            if enabled and (self.wake_thread is None or not self.wake_thread.is_alive()):
                self.wake_thread = threading.Thread(target=self._monitor_wake,
                                                  name="voice-wake", daemon=True)
                self.wake_thread.start()
            self._set_state("idle", "待唤醒：小爱同学 · 也可按键" if enabled else "按键模式，唤醒已关闭")
            return True
        except Exception as error:
            self.wake_enabled = False
            print("[VOICE][stage=wake_init][error=%s]" % type(error).__name__, flush=True)
            self._set_error("中文唤醒不可用，仍可使用按键录音")
            return False

    def _monitor_wake(self):
        while not self.stop_event.wait(0.02):
            try:
                # Serialize polling and handoff with every button command.
                # No callback is invoked while the detector's own lock is held.
                with self.command_lock:
                    if (not self.wake_enabled or self.round_worker_active or
                            self.state not in self.STARTABLE_STATES or
                            time.monotonic() < self.wake_resume_at):
                        continue
                    if self.state == "error":
                        self._set_state("idle", "待唤醒：小爱同学 · 上轮异常可重试")
                    if self.wake_detector.poll_keyword():
                        self._start_round(None, hands_free=True)
            except Exception as error:
                with self.command_lock:
                    try:
                        self.wake_detector.pause()
                    except Exception:
                        # Do not open another capture if release failed.
                        self.wake_enabled = False
                    self.wake_resume_at = time.monotonic() + 5
                    print("[VOICE][stage=wake_capture][error=%s]" % type(error).__name__, flush=True)
                    self._set_error("唤醒监听异常，稍后重试；可使用按键")

    @staticmethod
    def _hello_pcm():
        from pathlib import Path
        from audio.pcm import read_wav
        path = Path(__file__).resolve().parent / "assets" / "wake-hello.wav"
        with path.open("rb") as source:
            data = source.read(50001)
        if len(data) > 50000:
            raise ValueError("Wake greeting too large")
        pcm, _ = read_wav(data, require_16k=True)
        if len(pcm) > 48000:
            raise ValueError("Wake greeting too long")
        return pcm

    @staticmethod
    def _feedback_pcm(kind):
        if kind == "wake":
            return VoiceService._hello_pcm()
        import math
        import struct
        # Distinct local earcons; bounded amplitude and short fades avoid clicks.
        tones = ((1046.5, .11), (0, .025), (784, .14))
        pcm = bytearray()
        for frequency, seconds in tones:
            count = int(16000 * seconds)
            for i in range(count):
                envelope = min(1.0, i / 128, (count - 1 - i) / 128)
                value = int(6000 * envelope * math.sin(2 * math.pi * frequency * i / 16000))
                pcm.extend(struct.pack("<h", value))
        return bytes(pcm)

    def _play_feedback(self, kind):
        try:
            try:
                pcm = self._feedback_pcm(kind)
            except Exception:
                if kind != "wake":
                    raise
                # A missing/corrupt greeting must not force a cloud request.
                pcm = self._feedback_pcm("no_speech")
                print("[VOICE][stage=wake_feedback][kind=fallback_tone]", flush=True)
            ok = self.terminal.player.play_pcm_stream(iter([pcm]), timeout=2)
        except Exception:
            ok = False
        print("[VOICE][stage=%s_feedback][status=%s]" %
              ("wake" if kind == "wake" else "no_speech", "played" if ok else "visual_only"), flush=True)
        return bool(ok)

    def _wake_feedback(self):
        return self._play_feedback("wake")

    def _idle_message(self):
        return "待唤醒：小爱同学 · 也可按键" if self.wake_enabled else "可以开始下一轮"

    def _reply(self, conn, accepted, code, message):
        response = {
            "type": "ack",
            "accepted": bool(accepted),
            "code": code,
            "message": message,
            "round_id": self.round_id,
        }
        try:
            self._send_json(conn, response)
        except OSError:
            pass
        return response

    def _start_round(self, conn, hands_free=False):
        with self.command_lock:
            if self.stop_event.is_set():
                return self._reply(conn, False, "stopped", "语音服务正在退出")
            if self.terminal is None or not self.terminal.recorder.has_mic:
                return self._reply(conn, False, "not_ready", "语音服务尚未就绪")
            if self.state not in self.STARTABLE_STATES or self.round_worker_active:
                return self._reply(conn, False, "busy", "上一轮尚未结束")
            if hands_free and not self.wake_enabled:
                return self._reply(conn, False, "disabled", "唤醒已关闭")
            with self.state_lock:
                self.round_id += 1
                self.round_failed = False
                self.transcript = ""
                self.answer = ""
                self.last_error = ""
                self.round_started_mono_ms = None
                self.timings = {}
            self.terminal._hands_free = hands_free
            self._mark_stage("wake_detected" if hands_free else "button_trigger")
            if self.wake_detector:
                try:
                    self.wake_detector.pause()
                except Exception:
                    self._set_error("麦克风释放失败，请重启语音服务")
                    return self._reply(conn, False, "record_failed", self.message)
            if hands_free:
                self._set_state("starting", "已唤醒，播报你好后请说话")
                try:
                    self._wake_feedback()
                except Exception:
                    print("[VOICE][stage=wake_feedback][status=visual_only]", flush=True)
                self._mark_stage("wake_feedback_end")
            self._set_state("starting", "正在打开麦克风")
            # The listener has already exited: the manual key-release delay
            # would lose an immediate spoken onset after the wake cue.
            started = (self.terminal._start_recording(release_delay=0.0) if hands_free
                       else self.terminal._start_recording())
            if not started:
                if self.state != "error":
                    self._set_error("麦克风启动失败")
                self.wake_resume_at = time.monotonic() + 2
                return self._reply(conn, False, "record_failed", self.message)
            return self._reply(conn, True, "recording", "录音已开始")

    def _begin_finish(self, conn=None, automatic=False):
        with self.command_lock:
            if self.terminal is None or self.state != "recording":
                return self._reply(conn, False, "not_recording", "当前没有录音")
            self._mark_stage("record_stop_requested")
            self._set_state("recognizing", "正在结束录音")
            self.round_worker_active = True
            worker = threading.Thread(
                target=self._finish_round,
                args=(automatic,),
                name="voice-round",
                daemon=True,
            )
            worker.start()
            return self._reply(conn, True, "processing", "录音已结束")

    def _finish_round(self, automatic):
        finished_proc = self.terminal._record_proc
        try:
            self.terminal._finish_recording(automatic=automatic)
        except Exception as e:
            print(f"Voice round worker failed: {type(e).__name__}: {e}",
                  flush=True)
            self._set_error(f"本轮处理失败：{type(e).__name__}")
        finally:
            with self.command_lock:
                self.round_worker_active = False
                if self.terminal and self.terminal._recording:
                    with self.state_lock:
                        self.round_failed = False
                    return
                with self.state_lock:
                    failed = self.round_failed
                if (not failed and not self.stop_event.is_set() and
                        getattr(self.terminal, "_hands_free", False) and
                        getattr(finished_proc, "speech_detected", None) is False and
                        getattr(finished_proc, "error", None) is None and
                        getattr(finished_proc, "returncode", None) == 0 and
                        getattr(getattr(finished_proc, "endpoint", None), "reason", "") == "no_speech"):
                    # Remain busy until playback drains; no button/wake may race it.
                    self.round_worker_active = True
                    self._play_feedback("no_speech")
                    self._mark_stage("no_speech_feedback_end")
                    self.round_worker_active = False
                self._mark_stage("round_end")
                self.wake_resume_at = time.monotonic() + 0.8
                if not failed:
                    self._set_state("idle", self._idle_message())
                self._broadcast({
                    "type": "diagnostics",
                    "diagnostics": self._collect_diagnostics(),
                    "timings": dict(self.timings),
                    "round_id": self.round_id,
                })

    def _cancel_round(self, conn):
        with self.command_lock:
            if self.terminal is None:
                return self._reply(conn, False, "not_ready", "语音服务尚未就绪")
            if self.state == "recording":
                self.terminal._discard_active_recording()
                self._mark_stage("round_end")
                self.wake_resume_at = time.monotonic() + 0.8
                self._set_state("idle", self._idle_message())
                return self._reply(conn, True, "cancelled", "录音已取消")
            if self.state in self.STARTABLE_STATES:
                return self._reply(conn, True, "idle", "当前没有活动轮次")
            return self._reply(conn, False, "busy", "处理阶段暂不支持取消")

    def _monitor_recording(self):
        while not self.stop_event.wait(0.05):
            terminal = self.terminal
            if (terminal and self.state == "recording" and
                    terminal._record_proc and
                    terminal._record_proc.poll() is not None):
                self._begin_finish(automatic=True)

    def _prepare_socket(self):
        if os.path.exists(self.socket_path):
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(0.25)
            try:
                probe.connect(self.socket_path)
            except OSError:
                os.unlink(self.socket_path)
            else:
                raise RuntimeError("voice service is already running")
            finally:
                probe.close()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        server.listen(4)
        server.settimeout(0.5)
        self.server_socket = server

    def _client_loop(self, conn):
        with self.clients_lock:
            self.clients.add(conn)
        try:
            self._send_json(conn, self.snapshot())
            buffer = b""
            while not self.stop_event.is_set():
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data
                if len(buffer) > MAX_MESSAGE_BYTES:
                    self._reply(conn, False, "too_large", "命令过长")
                    break
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        command = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        self._reply(conn, False, "invalid_json", "JSON 格式错误")
                        continue
                    self.handle_command(command, conn)
        except OSError:
            pass
        finally:
            with self.clients_lock:
                self.clients.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    def serve_forever(self):
        self._prepare_socket()
        print(f"Voice service socket: {self.socket_path}", flush=True)
        threading.Thread(target=self.initialize_terminal,
                         name="voice-init", daemon=True).start()
        threading.Thread(target=self._monitor_recording,
                         name="voice-monitor", daemon=True).start()
        try:
            while not self.stop_event.is_set():
                try:
                    conn, _ = self.server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self.stop_event.is_set():
                        break
                    raise
                threading.Thread(target=self._client_loop, args=(conn,),
                                 name="voice-client", daemon=True).start()
        finally:
            self.shutdown()

    def shutdown(self):
        if self.stop_event.is_set() and self.server_socket is None:
            return
        self.stop_event.set()
        with self.command_lock:
            self.wake_enabled = False
            if self.wake_detector:
                try:
                    self.wake_detector.close()
                except Exception as error:
                    print("[VOICE][stage=wake_cleanup][error=%s]" % type(error).__name__, flush=True)
        if self.wake_thread and self.wake_thread is not threading.current_thread():
            self.wake_thread.join(timeout=3)
        if self.terminal:
            close = getattr(self.terminal, "close", None)
            if close:
                close()
            else:
                self.terminal._discard_active_recording()
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None
        with self.clients_lock:
            clients = list(self.clients)
            self.clients.clear()
        for conn in clients:
            try:
                conn.close()
            except OSError:
                pass
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description="Qt voice backend service")
    parser.add_argument("--socket", default=DEFAULT_SOCKET_PATH)
    args = parser.parse_args()
    service = VoiceService(socket_path=args.socket)

    def stop_service(_signum, _frame):
        service.shutdown()

    signal.signal(signal.SIGINT, stop_service)
    signal.signal(signal.SIGTERM, stop_service)
    service.serve_forever()


if __name__ == "__main__":
    main()
