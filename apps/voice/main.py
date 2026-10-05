#!/usr/bin/env python3
"""
AI Voice Terminal - Main Application
RK3568 AI Voice Terminal with voice dialogue support
"""
import sys
import os
import signal
import threading
import subprocess
import tempfile
import select
try:
    import termios
    import tty
except ImportError:
    termios = tty = None  # Windows runs offline tests, not ALSA/TTY interaction.
import time
import queue
import unicodedata

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import HIGH_PASS_ENABLE, HIGH_PASS_CUTOFF, VOICE_LOCAL_RESPONSES
from llm import create_llm
from tts.tts import TTSEngine
from audio.play import AudioPlayer
from audio.record import AudioRecorder
from asr import create_asr
from asr.offline_commands import LocalASRError, OfflineCommandASR
from tools import get_tools_schema, execute_tool, get_local_response
from tools.pc13_led import (
    PC13Led, LedControlError, needs_led_clarification, parse_led_action,
)
from tools.person_tracking import (
    PersonTracking, TrackingControlError, parse_tracking_action,
    needs_tracking_clarification, result_message,
)


class SentenceAccumulator:
    """Accumulate LLM tokens and split into sentences for streaming TTS."""
    SENTENCE_ENDINGS = set('。！？；\n')
    SOFT_BOUNDARY = '，,、'

    def __init__(self, max_len=80):
        self.buffer = ""
        self.max_len = max_len

    def feed(self, token: str) -> list:
        """Feed a token, return list of complete sentences ready for TTS."""
        self.buffer += token
        sentences = []
        while self.buffer:
            # Find earliest sentence ending
            end_pos = -1
            for i, ch in enumerate(self.buffer):
                if ch in self.SENTENCE_ENDINGS:
                    end_pos = i
                    break
            if end_pos >= 0:
                sentence = self.buffer[:end_pos + 1].strip()
                self.buffer = self.buffer[end_pos + 1:]
                if sentence:
                    sentences.append(sentence)
            elif len(self.buffer) >= self.max_len:
                # Force split at soft boundary or just cut
                cut = self._find_soft_split(self.buffer)
                sentence = self.buffer[:cut].strip()
                self.buffer = self.buffer[cut:]
                if sentence:
                    sentences.append(sentence)
            else:
                break
        return sentences

    def flush(self) -> str:
        """Return remaining buffer (called when stream ends)."""
        remaining = self.buffer.strip()
        self.buffer = ""
        return remaining

    def _find_soft_split(self, text: str) -> int:
        """Find best split point at soft boundary, fallback to max_len."""
        best = -1
        for i, ch in enumerate(text):
            if ch in self.SOFT_BOUNDARY and i > len(text) // 3:
                best = i + 1
        return best if best > 0 else min(self.max_len, len(text))


class AIVoiceTerminal:
    TIME_TOOL_HINTS = (
        "几点", "几号", "星期几", "周几", "当前时间", "现在时间",
        "当前日期", "今天日期", "今天是几", "现在是几",
    )
    WEATHER_TOOL_HINTS = (
        "天气", "气温", "温度", "下雨", "下雪", "湿度", "风速",
        "晴天", "天晴", "空气质量",
    )


    def __init__(self, event_callback=None):
        self.event_callback = event_callback
        print("Initializing AI Voice Terminal...")
        self.llm = create_llm()
        self.tts = TTSEngine()
        self.player = AudioPlayer()
        self.recorder = AudioRecorder()
        self.asr = create_asr()
        self.offline_asr = OfflineCommandASR()
        self._cloud_retry_at = 0.0
        self._last_route_up = True
        self.history = []
        self.max_response_chars = 500
        self.high_pass = HIGH_PASS_ENABLE
        self.noise_rms = self._measure_noise()

        # The service owns local wake and microphone handoff. Never load the
        # historical English timer detector or claim it supports Chinese.
        self.wake_detector = None

        print(f"Microphone: {'available' if self.recorder.has_mic else 'not detected (text mode)'}")
        print("Wake word: optional Chinese KWS managed by voice_service")
        print("Initialization complete!\n")

    def _emit_event(self, event_type: str, **payload) -> None:
        """Send a structured, credential-free event to an optional UI adapter."""
        if not self.event_callback:
            return
        try:
            self.event_callback(event_type, payload)
        except Exception as e:
            print(f"Event callback failed: {type(e).__name__}")

    def _emit_timing(self, stage: str) -> None:
        """Emit a monotonic stage marker for the headless service."""
        self._emit_event(
            "timing",
            stage=stage,
            monotonic_ms=int(time.monotonic() * 1000),
            wall_ms=int(time.time() * 1000),
        )

    def process_input(self, user_input: str):
        """Process user input with streaming TTS pipeline"""
        if not user_input or not user_input.strip():
            return

        print(f"\nYou: {user_input}")

        self._reply_has_output = False
        tracking_action = parse_tracking_action(user_input)
        if tracking_action is not None:
            self._handle_tracking_action(tracking_action, offline=False)
            return
        if needs_tracking_clarification(user_input):
            self._speak_blocking(
                "未操作云台。请明确说开始跟踪人物或停止跟踪。", remember=False)
            return
        led_action = parse_led_action(user_input)
        if led_action is not None:
            self._handle_led_action(led_action, offline=False)
            return
        if needs_led_clarification(user_input):
            print("[VOICE][stage=led_intent][status=clarify]", flush=True)
            self._speak_blocking(
                "没有操作指示灯。请明确说打开、关闭或查询指示灯状态。",
                remember=False,
            )
            return

        local_response = get_local_response(user_input) if VOICE_LOCAL_RESPONSES else ""
        if local_response:
            print("Route: local fast response", flush=True)
            self._emit_timing("local_response")
            self._speak_blocking(local_response, user_input)
            return

        # Only explicit tool intents use the slower non-streaming function-call
        # path. Ordinary conversation must stay on the streaming fast path.
        tools_schema = get_tools_schema()
        if tools_schema and self._requires_tools(user_input):
            print("Route: tool-capable blocking", flush=True)
            self._emit_event("state", state="thinking", message="正在生成回答")
            self._emit_timing("llm_request")
            response = self._call_tools_with_retry(user_input, tools_schema)
            if self._is_api_failure(response):
                print(f"AI request failed: {response}")
                self._emit_event("error", message="AI 请求失败，请重试")
                return
            self._emit_timing("llm_first_token")
            self._emit_timing("llm_end")
            self._speak_blocking(response, user_input)
            return

        # Try streaming pipeline
        print("Route: streaming chat", flush=True)
        try:
            self._process_input_streaming(user_input)
        except Exception as e:
            print(f"Streaming failed: {type(e).__name__}")
            if self._reply_has_output:
                self._emit_event("error", message="回答中断，已保留文字，请重试")
            else:
                self._process_input_blocking(user_input)

    def _handle_tracking_action(self, action, offline):
        self._emit_event("state", state="thinking", message="正在核对云台状态")
        self._emit_timing("tracking_request")
        try:
            reply = PersonTracking().execute(action)
            response = result_message(reply)
            print("[VOICE][stage=tracking_result][code=%s][accepted=%s]" %
                  (reply["code"], reply["accepted"]), flush=True)
        except TrackingControlError as error:
            response = ("云台状态未确认，请查看板屏或按立即停止。" if error.kind == "timeout"
                        else "云台连接不可用，请先打开云台摄像页面。")
            print("[VOICE][stage=tracking_result][status=failed][kind=%s]" % error.kind,
                  flush=True)
        self._emit_timing("tracking_result")
        if offline:
            self._emit_event("answer", text=response)
            self._emit_timing("reply_end")
        else:
            self._speak_blocking(response, remember=False)

    def _handle_led_action(self, action, offline):
        """Shared verified PC13 path; offline never waits for cloud TTS."""
        self._emit_event("state", state="thinking", message="正在核对指示灯状态")
        self._emit_timing("led_request")
        try:
            led = PC13Led()
            if action == "query":
                on = led.get_led()
                response = "指示灯当前已打开。" if on else "指示灯当前已关闭。"
            else:
                on = action == "on"
                led.set_led(on)
                response = "指示灯已打开。" if on else "指示灯已关闭。"
            print("[VOICE][stage=led_result][status=verified]", flush=True)
        except LedControlError as error:
            response = ("指示灯查询失败，请检查串口连接和设备状态。"
                        if action == "query" else
                        "指示灯控制失败，请检查串口连接和设备状态。")
            print(f"[VOICE][stage=led_result][status=failed][kind={error.kind}]", flush=True)
        self._emit_timing("led_result")
        if offline:
            self._emit_event("answer", text=response)
            self._emit_timing("reply_end")
        else:
            self._speak_blocking(response, remember=False)

    def _process_input_streaming(self, user_input: str):
        """Streaming pipeline: token -> sentence -> queue -> TTS+play thread"""
        sentence_q = queue.Queue(maxsize=8)
        consumer_failed = threading.Event()
        speech_deadline = time.monotonic() + 90
        full_response = []
        stream_timing = {
            "tts_request": False,
            "tts_ready": False,
            "playback_start": False,
        }

        playback_errors = []
        # Consumer thread: take sentences from queue, TTS + play
        def consumer():
            while True:
                item = sentence_q.get()
                if item is None:  # Sentinel: stream ended
                    break
                speech_item = self._sanitize_tts_text(item)
                if not speech_item:
                    continue
                try:
                    if time.monotonic() >= speech_deadline:
                        raise TimeoutError("Speech round deadline")
                    if not stream_timing["tts_request"]:
                        stream_timing["tts_request"] = True
                        self._emit_timing("tts_request")
                        self._emit_event("state", state="replying", message="正在合成语音")
                    def on_start():
                        if not stream_timing["tts_ready"]:
                            stream_timing["tts_ready"] = True
                            self._emit_timing("tts_ready")
                        if not stream_timing["playback_start"]:
                            stream_timing["playback_start"] = True
                            self._emit_timing("playback_start")
                            self._emit_event("state", state="playing", message="正在播放回答")
                    if not self._play_speech(speech_item, on_start):
                        raise RuntimeError("Speech delivery failed")
                except Exception as e:
                    playback_errors.append("语音合成或播放中断，已保留文字回答")
                    consumer_failed.set()
                    break

        t = threading.Thread(target=consumer, daemon=True)
        t.start()

        # Producer: stream tokens from LLM, accumulate into sentences
        print("Thinking...", end=" ", flush=True)
        self._emit_event("state", state="thinking", message="正在生成回答")
        self._emit_timing("llm_request")
        accum = SentenceAccumulator()
        first_token_seen = False
        token_count = 0
        stream = None

        def enqueue(item):
            while not consumer_failed.is_set():
                if time.monotonic() >= speech_deadline:
                    raise TimeoutError("Speech queue deadline")
                try:
                    sentence_q.put(item, timeout=0.1)
                    return
                except queue.Full:
                    continue

        try:
            stream = self.llm.chat_stream(user_input, self.history)
            for token in stream:
                if not isinstance(token, str) or not token:
                    continue
                if not first_token_seen and self._is_api_failure(token):
                    raise RuntimeError(token)
                if not first_token_seen:
                    first_token_seen = True
                    self._emit_timing("llm_first_token")
                token = token[:max(0, self.max_response_chars - token_count)]
                token_count += len(token)
                self._reply_has_output = True
                full_response.append(token)
                print(token, end="", flush=True)
                self._emit_event("answer_delta", text=token)
                sentences = accum.feed(token)
                for s in sentences:
                    enqueue(s)
                if token_count >= self.max_response_chars:
                    break

            # Flush remaining buffer
            remaining = accum.flush()
            if remaining:
                enqueue(remaining)
            self._emit_timing("llm_end")
        finally:
            close = getattr(stream, "close", None)
            if close:
                try:
                    close()
                except Exception as error:
                    print("Stream cleanup failed: %s" % type(error).__name__)
            # Do not admit another round until the bounded consumer exits.
            while t.is_alive():
                try:
                    sentence_q.put(None, timeout=0.1)
                    break
                except queue.Full:
                    continue
            t.join()

        self._emit_timing("reply_end")

        print()  # Newline after streaming tokens

        response = "".join(full_response)

        if playback_errors:
            self._emit_event("error", message="；".join(dict.fromkeys(playback_errors)))
        if self._is_api_failure(response):
            raise RuntimeError(response)
        if len(response) > self.max_response_chars:
            response = response[:self.max_response_chars] + "..."
        self._emit_event("answer", text=response)

        # Update history
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": response})
        if len(self.history) > 8:
            self.history = self.history[-8:]

    def _process_input_blocking(self, user_input: str):
        """Blocking fallback: generate full response, then TTS + play"""
        print("Thinking...", end=" ", flush=True)
        self._emit_event("state", state="thinking", message="正在生成回答")
        self._emit_timing("llm_request")
        response = self._call_llm_with_retry(user_input)
        if not self._is_api_failure(response):
            self._emit_timing("llm_first_token")
            self._emit_timing("llm_end")
        print("done")
        self._speak_blocking(response, user_input)

    def _speak_blocking(self, response: str, user_input: str = "", remember=True):
        """TTS + play a complete response string"""
        if self._is_api_failure(response):
            self._emit_event("error", message="AI 请求失败，请重试")
            return
        if len(response) > self.max_response_chars:
            response = response[:self.max_response_chars] + "..."

        print(f"\nAI: {response}")
        self._emit_event("answer", text=response)
        self._emit_event("state", state="replying", message="正在合成语音")

        if remember:
            if user_input:
                self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": response})
            if len(self.history) > 8:
                self.history = self.history[-8:]

        print("Synthesizing speech...", end=" ", flush=True)
        self._emit_timing("tts_request")
        speech_text = self._sanitize_tts_text(response)
        def on_start():
            self._emit_timing("tts_ready")
            self._emit_event("state", state="playing", message="正在播放回答")
            self._emit_timing("playback_start")

        try:
            if not self._play_speech(speech_text, on_start):
                self._emit_event("error", message="语音合成或播放失败，已显示文字回答")
        finally:
            self._emit_timing("reply_end")

    def _play_speech(self, text, on_start):
        """Keep the UI protocol independent of file versus PCM transport."""
        if self.tts.supports_pcm_stream:
            return self.player.play_pcm_stream(self.tts.pcm_stream(text), on_start)
        audio_file = self.tts.text_to_speech(text)
        if not audio_file:
            return False
        try:
            on_start()
            return self.player.play(audio_file)
        finally:
            self._safe_unlink(audio_file)

    def _call_llm_with_retry(self, user_input: str, retries: int = 3) -> str:
        """Call MiMo with exponential backoff retry"""
        for attempt in range(retries):
            try:
                response = self.llm.chat(user_input, self.history)
            except Exception as e:
                response = f"API调用失败: {type(e).__name__}"
            if not self._is_api_failure(response):
                return response
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"retry in {wait}s...", end=" ", flush=True)
                time.sleep(wait)
        return response

    def _call_tools_with_retry(self, user_input: str, tools_schema: list,
                               retries: int = 3) -> str:
        """Call the tool-capable LLM path with bounded retries."""
        response = "API调用失败: no response"
        for attempt in range(retries):
            try:
                response = self.llm.chat_with_tools(
                    user_input, self.history,
                    tools_schema=tools_schema,
                    tool_executor=execute_tool,
                )
            except Exception as e:
                response = f"API调用失败: {type(e).__name__}"
            if not self._is_api_failure(response):
                return response
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"retry in {wait}s...", end=" ", flush=True)
                time.sleep(wait)
        return response

    @staticmethod
    def _is_api_failure(response) -> bool:
        return (not isinstance(response, str) or not response.strip() or
                response.startswith("API调用失败") or
                response.startswith("API响应格式错误"))

    def _record_audio(self):
        """Start recording audio"""
        if getattr(self, "_hands_free", False):
            from audio.capture import AutomaticRecording
            proc = AutomaticRecording(max_seconds=self.recorder.max_seconds,
                                      on_first_frame=lambda: self._emit_timing("first_audio_frame"))
            return proc, proc.path
        return self.recorder.record_async()


    @classmethod
    def _requires_tools(cls, user_input: str) -> bool:
        """Conservatively route only supported time/weather intents to tools."""
        normalized = "".join(str(user_input).lower().split())
        hints = cls.TIME_TOOL_HINTS + cls.WEATHER_TOOL_HINTS
        return any(hint in normalized for hint in hints)

    @staticmethod
    def _default_route_available():
        """A missing route is a fast, local signal to skip cloud ASR."""
        try:
            with open("/proc/net/route", encoding="ascii") as handle:
                for line in handle.read().splitlines()[1:]:
                    fields = line.split()
                    if (len(fields) >= 4 and fields[0] != "lo" and
                            fields[1] == "00000000" and
                            int(fields[3], 16) & 0x2):
                        return True
            return False
        except (OSError, ValueError):
            return True

    def _process_offline_command(self, audio_file, reason):
        message = ("网络已断开，正在识别离线固定指令" if reason == "network_down"
                   else "云端识别暂不可用，正在尝试离线指令")
        self._emit_event("state", state="recognizing", message=message)
        self._emit_timing("offline_asr_request")
        try:
            text = self.offline_asr.recognize(audio_file)
        except LocalASRError as error:
            print(f"[VOICE][stage=offline_asr][status=failed][kind={error.kind}]",
                  flush=True)
            self._emit_event("error", message="离线语音识别不可用，请检查本地模型")
            return
        finally:
            self._emit_timing("offline_asr_result")
        tracking_action = parse_tracking_action(text)
        if tracking_action is not None:
            self._emit_event("transcript", text=text)
            self._handle_tracking_action(tracking_action, offline=True)
            return
        action = parse_led_action(text)
        if action is None:
            self._emit_event(
                "answer",
                text=("网络已断开。" if reason == "network_down"
                      else "云端识别暂不可用。") +
                     "离线模式未听清固定指令；支持指示灯开关/查询、开始跟踪人物或停止跟踪。",
            )
            self._emit_timing("reply_end")
            return
        self._emit_event("transcript", text=text)
        self._handle_led_action(action, offline=True)

    def _process_audio(self, audio_file: str):
        """Process recorded audio: quality gate -> (highpass) -> ASR -> LLM -> TTS"""
        source_file = audio_file
        processed_file = audio_file
        try:
            if not os.path.exists(audio_file) or os.path.getsize(audio_file) <= 44:
                print("Recording failed or too short")
                self._emit_event("error", message="录音失败或时间太短")
                return

            # Do not use startup ambient noise as a permanent reject threshold:
            # a nearby voice/video during calibration can otherwise lock out
            # every later round. ASR confidence and PC13 intent checks still
            # decide whether a recording may cause a device action.
            rms = self._audio_rms(audio_file)
            min_rms = 200
            if rms < min_rms:
                print(f"Audio rms={rms:.0f} < {min_rms:.0f} - 声音太轻/没听清，请靠近麦克风再说一遍")
                self._emit_event("error", message="声音太轻或没有听清，请靠近麦克风重试")
                return
            if rms > 8000:
                print(f"Audio rms={rms:.0f} - 录音异常（可能爆音），请重说")
                self._emit_event("error", message="录音音量异常，请重新说一遍")
                return
            print(f"Audio rms={rms:.0f}, quality OK", flush=True)

            if self.high_pass:
                processed_file = self._highpass(audio_file)

            route_up = self._default_route_available()
            if route_up and not self._last_route_up:
                self._cloud_retry_at = 0.0
            self._last_route_up = route_up
            if route_up and time.monotonic() >= self._cloud_retry_at:
                self._emit_event("state", state="recognizing", message="正在识别语音")
                print(f"Recognizing... ({os.path.getsize(processed_file)} bytes)",
                      end=" ", flush=True)
                self._emit_timing("asr_request")
                text, failure = self.asr.recognize_with_status(
                    processed_file, retries=1, budget=8)
                self._emit_timing("asr_result")
                print("done", flush=True)
                if text:
                    self._cloud_retry_at = 0.0
                    self._emit_event("transcript", text=text)
                    self.process_input(text)
                    return
                if failure in ("network", "timeout", "http"):
                    self._cloud_retry_at = time.monotonic() + 15
                self._process_offline_command(processed_file, "cloud_failed")
            else:
                self._process_offline_command(
                    processed_file, "network_down" if not route_up else "cloud_failed")
        except Exception as e:
            print(f"Voice round failed: {type(e).__name__}: {e}")
            self._emit_event("error", message=f"本轮处理失败：{type(e).__name__}")
        finally:
            self._safe_unlink(source_file)
            if processed_file != source_file:
                self._safe_unlink(processed_file)

    @staticmethod
    def _sanitize_tts_text(text: str) -> str:
        """Remove control/symbol characters that cloud TTS cannot speak."""
        cleaned = "".join(
            ch for ch in str(text)
            if not unicodedata.category(ch).startswith(("C", "S"))
        )
        return cleaned.strip()

    @staticmethod
    def _safe_unlink(path: str) -> None:
        if not path:
            return
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError as e:
            print(f"Temp file cleanup failed: {type(e).__name__}")

    @staticmethod
    def _audio_is_constant(path: str, tol: int = 8) -> bool:
        """Detect codec DC lockup: every PCM sample identical (post-playback bug)."""
        try:
            import array
            with open(path, "rb") as f:
                data = f.read()
            pcm = data[44:]
            samples = array.array("h")
            samples.frombytes(pcm[: len(pcm) // 2 * 2])
            if len(samples) < 100:
                return False
            return max(samples) - min(samples) <= tol
        except Exception:
            return False

    def _audio_rms(self, path: str) -> float:
        """Read WAV and compute PCM RMS."""
        import array, math
        with open(path, "rb") as f:
            data = f.read()
        pcm = data[44:]
        samples = array.array("h")
        samples.frombytes(pcm[: len(pcm) // 2 * 2])
        if not samples:
            return 0.0
        return math.sqrt(sum(x * x for x in samples) / len(samples))

    @staticmethod
    def _write_wav(path: str, samples, sr: int = 16000) -> None:
        """Write int16 samples as a standard WAV file."""
        import struct
        data = samples.tobytes()
        data_size = len(data)
        with open(path, "wb") as f:
            f.write(b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE")
            f.write(b"fmt " + struct.pack("<I", 16))
            f.write(struct.pack("<H", 1))
            f.write(struct.pack("<H", 1))
            f.write(struct.pack("<I", sr))
            f.write(struct.pack("<I", sr * 2))
            f.write(struct.pack("<H", 2))
            f.write(struct.pack("<H", 16))
            f.write(b"data" + struct.pack("<I", data_size))
            f.write(data)

    def _highpass(self, path: str) -> str:
        """FFT highpass to cut low-frequency fan vibration; fallback to original if numpy missing."""
        try:
            import numpy as np
            with open(path, "rb") as f:
                data = f.read()
            samples = np.frombuffer(data[44:], dtype=np.int16)
            n = len(samples)
            if n < 1024:
                return path
            spec = np.fft.rfft(samples.astype(np.float64))
            freqs = np.fft.rfftfreq(n, 1.0 / 16000)
            spec[freqs < HIGH_PASS_CUTOFF] = 0
            y = np.clip(np.fft.irfft(spec, n), -32768, 32767).astype(np.int16)
            out_path = path + ".hp.wav"
            self._write_wav(out_path, y)
            return out_path
        except Exception as e:
            print(f"Highpass skipped: {e}")
            return path

    def _measure_noise(self, seconds: float = 1.0) -> float:
        """Sample ambient noise RMS to adaptively set the recording quality gate.
        A median prevents one startup sound from inflating every later round."""
        if not self.recorder.has_mic:
            return 0.0
        from statistics import median
        readings = []
        for _ in range(3):
            path = tempfile.mktemp(suffix=".wav")
            try:
                proc = subprocess.Popen(
                    ["arecord", "-D", "plughw:0,0", "-f", "S16_LE", "-r", "16000",
                     "-c", "1", "-t", "wav", "-d", str(int(seconds)), path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                proc.wait(timeout=seconds + 4)
                if os.path.exists(path) and os.path.getsize(path) > 44:
                    if self._audio_is_constant(path):
                        print("Env noise baseline: constant sample, retry")
                        continue
                    readings.append(self._audio_rms(path))
            finally:
                if os.path.exists(path):
                    os.unlink(path)
        baseline = median(readings) if readings else 0.0
        print(f"Env noise baseline: rms={baseline:.0f} samples={len(readings)}")
        return baseline

    def _start_recording(self, release_delay: float = 0.3) -> bool:
        """Start arecord and verify that the child did not fail immediately."""
        if self._recording:
            return False
        time.sleep(release_delay)
        try:
            proc, audio_file = self._record_audio()
        except Exception as e:
            print(f"Recording start failed: {type(e).__name__}: {e}")
            self._emit_event("error", message="麦克风启动失败")
            return False

        time.sleep(0.05)
        if proc.poll() is not None:
            proc.wait()
            detail = self._read_process_stderr(proc)
            print(f"Recording start failed: arecord exited with {proc.returncode}: {detail}")
            self._safe_unlink(audio_file)
            self._emit_event("error", message="麦克风无法打开，请检查设备占用")
            return False

        self._record_proc = proc
        self._audio_file = audio_file
        self._recording = True
        print("\n[Recording] Press Enter to stop...")
        self._emit_event("state", state="recording", message=(
            "正在聆听，说完会自动结束" if getattr(self, "_hands_free", False)
            else "正在聆听"))
        self._emit_timing("record_start")
        return True

    def _finish_recording(self, automatic: bool = False) -> None:
        """Stop/finalize arecord, recover codec lockups, then process the WAV."""
        proc = self._record_proc
        audio_file = self._audio_file
        self._recording = False
        self._record_proc = None
        self._audio_file = None

        if not proc or not audio_file:
            return

        terminated_by_us = False
        try:
            if proc.poll() is None:
                terminated_by_us = True
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
            else:
                proc.wait()

            if proc.returncode != 0 and not terminated_by_us:
                detail = self._read_process_stderr(proc)
                print(f"arecord exited with {proc.returncode}: {detail}")

            self._emit_timing("record_end")

            if hasattr(proc, "speech_detected"):
                print("[VOICE][stage=auto_endpoint][reason=%s]" %
                      (proc.error or proc.endpoint.reason or "manual_stop"), flush=True)
                if proc.error or not proc.speech_detected:
                    self._safe_unlink(audio_file)
                    if proc.error:
                        self._emit_event("error", message="自动录音失败，请重试或使用按键")
                    else:
                        self._emit_event("answer", text="没有听到指令，本轮未执行操作。")
                    return

            if automatic:
                print("\n[Recording limit reached] Processing captured audio...")

            if self._audio_is_constant(audio_file):
                self._safe_unlink(audio_file)
                print("\n[Mic locked] 检测到麦克风异常，自动重新录音，请再说一遍")
                self._emit_event("error", message="麦克风状态异常，正在自动恢复")
                self._retry_count += 1
                if self._retry_count >= 2:
                    self._retry_count = 0
                    print("连续两次异常，请检查麦克风连接")
                elif not getattr(self, "_hands_free", False) and self._start_recording(release_delay=0.5):
                    print("[Recovery recording started]")
                return

            self._retry_count = 0
            self._process_audio(audio_file)
        except Exception as e:
            self._safe_unlink(audio_file)
            print(f"Recording finalize failed: {type(e).__name__}: {e}")
            self._emit_event("error", message="录音结束处理失败")

    def _discard_active_recording(self) -> None:
        """Best-effort cleanup used during shutdown."""
        proc = self._record_proc
        audio_file = self._audio_file
        self._recording = False
        self._record_proc = None
        self._audio_file = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass
        self._safe_unlink(audio_file)

    @staticmethod
    def _read_process_stderr(proc) -> str:
        try:
            if not proc or not proc.stderr:
                return "no stderr"
            data = proc.stderr.read()
            if isinstance(data, bytes):
                data = data.decode(errors="replace")
            lines = [line.strip() for line in data.splitlines() if line.strip()]
            return lines[-1][:300] if lines else "no stderr"
        except Exception:
            return "stderr unavailable"

    @staticmethod
    def _drain_buffered_input() -> None:
        """Discard keys pressed while a voice round was busy."""
        try:
            while select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.read(1)
        except Exception:
            pass

    def _voice_mode(self):
        """Voice mode: press Enter to start, press Enter again to stop."""
        if not sys.stdin.isatty():
            print("Push-to-talk requires an interactive TTY; no input source available")
            return

        self._recording = False
        self._record_proc = None
        self._audio_file = None
        self._retry_count = 0
        last_key_time = 0.0

        print("=" * 50)
        print("AI Voice Terminal - Push-to-Talk")
        print("Press Enter to START recording")
        print("Press Enter again to STOP and process")
        print("Ctrl+C to exit")
        print("=" * 50)

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())
            while True:
                # arecord exits by itself at RECORD_MAX_SECONDS. Finalize it
                # immediately instead of waiting forever for another key.
                if (self._recording and self._record_proc and
                        self._record_proc.poll() is not None):
                    self._finish_recording(automatic=True)
                    if not self._recording:
                        self._drain_buffered_input()
                        print("\nReady. Press Enter to talk.")
                    continue

                if select.select([sys.stdin], [], [], 0)[0]:
                    ch = sys.stdin.read(1)
                    if ch in ("\r", "\n"):
                        now = time.monotonic()
                        if now - last_key_time < 0.08:
                            continue
                        last_key_time = now

                        if not self._recording:
                            if not self._start_recording():
                                print("\nReady. Press Enter to talk.")
                        else:
                            self._finish_recording()
                            if not self._recording:
                                self._drain_buffered_input()
                                print("\nReady. Press Enter to talk.")
                else:
                    time.sleep(0.02)
        except KeyboardInterrupt:
            pass
        finally:
            self._discard_active_recording()
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def _text_mode(self):
        """Text input mode - fallback when no microphone"""
        print("=" * 50)
        print("AI Voice Terminal - Text Mode")
        print("Type your message and press Enter.")
        print("Type 'quit' to exit.")
        print("=" * 50)

        while True:
            try:
                user_input = input("\nYou: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\nGoodbye!")
                    break
                self.process_input(user_input)
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except EOFError:
                print("\n\nGoodbye!")
                break

    def run(self):
        """Run the terminal - voice or text mode"""
        if self.recorder.has_mic:
            self._voice_mode()
        else:
            self._text_mode()

    def close(self):
        """Release recording state and persistent provider connections."""
        self._discard_active_recording()
        for adapter in (self.asr, self.tts, self.llm):
            close = getattr(adapter, "close", None)
            if close:
                try:
                    close()
                except Exception as error:
                    print("Adapter cleanup failed: %s" % type(error).__name__)


def main():
    """Main entry point"""
    if not sys.stdin.isatty():
        print("Push-to-talk requires an interactive TTY; startup aborted")
        sys.exit(2)

    def signal_handler(sig, frame):
        print("\n\nGoodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    terminal = None
    try:
        terminal = AIVoiceTerminal()
        terminal.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        if terminal:
            terminal.close()


if __name__ == "__main__":
    main()
