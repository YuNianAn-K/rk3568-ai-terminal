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
            self.terminal = terminal
            if not terminal.recorder.has_mic:
                self._set_error("没有检测到麦克风")
                return False
            self._set_state("idle", "语音服务已就绪")
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
        return self._reply(conn, False, "invalid", "未知命令")

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

    def _start_round(self, conn):
        with self.command_lock:
            if self.terminal is None or not self.terminal.recorder.has_mic:
                return self._reply(conn, False, "not_ready", "语音服务尚未就绪")
            if self.state not in self.STARTABLE_STATES or self.round_worker_active:
                return self._reply(conn, False, "busy", "上一轮尚未结束")

            with self.state_lock:
                self.round_id += 1
                self.round_failed = False
                self.transcript = ""
                self.answer = ""
                self.last_error = ""
                self.round_started_mono_ms = None
                self.timings = {}
            self._mark_stage("button_trigger")
            self._set_state("starting", "正在打开麦克风")
            if not self.terminal._start_recording():
                if self.state != "error":
                    self._set_error("麦克风启动失败")
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
                self._mark_stage("round_end")
                if not failed:
                    self._set_state("idle", "可以开始下一轮")
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
                self._set_state("idle", "录音已取消")
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
        if self.terminal:
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
