"""One bounded ALSA PCM owner, shared by local wake and automatic recording."""
import os
import select
import subprocess
import tempfile
import threading
import time
import wave
import array
import math


class PCMCapture:
    def __init__(self):
        self.proc = subprocess.Popen(
            ["arecord", "-q", "-D", "plughw:0,0", "-t", "raw",
             "-f", "S16_LE", "-r", "16000", "-c", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.pending = b""
        self.last_data = time.monotonic()

    def read(self):
        if self.proc.poll() is not None:
            raise OSError("capture exited")
        if not select.select([self.proc.stdout], [], [], 0.1)[0]:
            if time.monotonic() - self.last_data > 2:
                raise TimeoutError("capture stalled")
            return b""
        data = os.read(self.proc.stdout.fileno(), 3200)
        if not data:
            raise OSError("capture EOF")
        self.last_data = time.monotonic()
        data = self.pending + data
        size = len(data) // 2 * 2
        self.pending = data[size:]
        return data[:size]

    def close(self):
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            self.proc.wait(timeout=1)
        finally:
            self.proc.stdout.close()


class SilenceEndpoint:
    """Energy endpoint, not speaker isolation or an action-confidence check.

    Baseline is bounded and per-round: noisy startup cannot lock out later rounds.
    All captured samples are retained, including onset and the 1 s tail.
    """
    def __init__(self, max_seconds=10, no_speech=4, silence=1.0):
        self.max_seconds = max_seconds
        self.no_speech = no_speech
        self.silence = silence
        self.seconds = 0
        self.voiced = 0
        self.quiet = 0
        self.noise = 80
        self.speech_detected = False
        self.reason = ""

    def feed(self, pcm):
        samples = array.array("h", pcm)
        if not samples:
            return False
        mean = sum(samples) / len(samples)
        rms = math.sqrt(sum((x - mean) ** 2 for x in samples) / len(samples))
        duration = len(samples) / 16000
        self.seconds += duration
        threshold = max(200, min(1000, self.noise * 2.5))
        if rms >= threshold:
            self.voiced += duration
            self.quiet = 0
            if self.voiced >= 0.15:
                self.speech_detected = True
        else:
            self.quiet += duration
            if not self.speech_detected:
                self.voiced = 0
                self.noise = 0.9 * self.noise + 0.1 * min(rms, 400)
        if self.speech_detected and self.quiet >= self.silence:
            self.reason = "silence"
        elif not self.speech_detected and self.seconds >= self.no_speech:
            self.reason = "no_speech"
        elif self.seconds >= self.max_seconds:
            self.reason = "max_duration"
        return bool(self.reason)


class AutomaticRecording:
    """Process-like recorder for the existing finalize/cancel contract."""
    stderr = None

    def __init__(self, max_seconds=10, capture_factory=PCMCapture, on_first_frame=None,
                 endpoint_factory=None):
        if endpoint_factory is None:
            from .vad import model_path, SileroEndpoint
            endpoint_factory = SileroEndpoint if model_path().is_file() else SilenceEndpoint
        # Endpoint failures must not open ALSA or leave a temporary recording.
        self.endpoint = endpoint_factory(max_seconds=max_seconds)
        print('[VOICE][stage=auto_vad][engine=%s]' % type(self.endpoint).__name__, flush=True)
        try:
            fd, self.path = tempfile.mkstemp(suffix=".auto.wav")
            os.close(fd)
        except Exception:
            self._close_endpoint()
            raise
        self.stop = threading.Event()
        self.returncode = None
        self.error = None
        self.on_first_frame = on_first_frame
        try:
            self.capture = capture_factory()
        except Exception:
            os.unlink(self.path)
            self._close_endpoint()
            raise
        self.worker = threading.Thread(target=self._run, name="voice-auto-record", daemon=True)
        try:
            self.worker.start()
        except Exception:
            try:
                self.capture.close()
            finally:
                os.unlink(self.path)
                self._close_endpoint()
            raise

    def _close_endpoint(self):
        close = getattr(self.endpoint, 'close', None)
        if close:
            close()

    @property
    def speech_detected(self):
        return self.endpoint.speech_detected

    def _run(self):
        try:
            with wave.open(self.path, "wb") as target:
                target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                deadline = time.monotonic() + self.endpoint.max_seconds + 2
                while not self.stop.is_set():
                    if time.monotonic() > deadline:
                        raise TimeoutError("record deadline")
                    pcm = self.capture.read()
                    if pcm:
                        if self.on_first_frame:
                            callback, self.on_first_frame = self.on_first_frame, None
                            callback()
                        target.writeframesraw(pcm)
                        if self.endpoint.feed(pcm):
                            break
        except Exception as error:
            self.error = type(error).__name__
        finally:
            try:
                self.capture.close()
            except Exception as error:
                self.error = type(error).__name__
            self._close_endpoint()
            self.returncode = 1 if self.error else 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.stop.set()

    kill = terminate

    def wait(self, timeout=None):
        self.worker.join(timeout)
        if self.worker.is_alive():
            raise subprocess.TimeoutExpired("automatic recording", timeout)
        return self.returncode
