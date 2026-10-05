"""Optional local Silero endpoint; never trims or uploads captured PCM."""
import os
from pathlib import Path
import sys
import threading

_engine = None
_load_lock = threading.Lock()
_session_lock = threading.Lock()


def model_path():
    return Path(os.getenv('VOICE_VAD_MODEL_PATH', '/opt/ai-voice-wake/silero_vad.onnx'))


def prepare_vad():
    """Load once before wake listening, not between the cue and first audio."""
    global _engine
    if not model_path().is_file():
        return None
    with _load_lock:
        if _engine is None:
            vendor = Path(__file__).resolve().parents[1] / 'vendor-wake'
            if vendor.is_dir():
                sys.path.insert(0, str(vendor))
            import numpy as np
            import sherpa_onnx
            config = sherpa_onnx.VadModelConfig()
            config.sample_rate = 16000
            config.num_threads = 1
            config.provider = 'cpu'
            config.silero_vad.model = str(model_path())
            config.silero_vad.threshold = 0.5
            config.silero_vad.min_speech_duration = 0.15
            # Keep a pause/tail, rather than racing to end at every short gap.
            config.silero_vad.min_silence_duration = 0.8
            config.silero_vad.max_speech_duration = 20
            _engine = (np, sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=12))
        return _engine


class SileroEndpoint:
    def __init__(self, max_seconds=10, no_speech=4, engine=None):
        self.np, self.vad = engine if engine is not None else prepare_vad()
        if not _session_lock.acquire(blocking=False):
            raise RuntimeError('VAD session already in use')
        self.closed = False
        try:
            self.vad.reset()
        except Exception:
            self.close()
            raise
        self.max_seconds = max_seconds
        self.no_speech = no_speech
        self.seconds = 0
        self.speech_detected = False
        self.reason = ''

    def feed(self, pcm):
        samples = self.np.frombuffer(pcm, dtype='<i2').astype(self.np.float32)
        if not len(samples):
            return False
        self.seconds += len(samples) / 16000
        # Remove codec DC only from detection input. Original WAV is untouched.
        samples = (samples - samples.mean()) / 32768
        self.vad.accept_waveform(samples)
        if self.vad.is_speech_detected():
            self.speech_detected = True
        if not self.vad.empty():
            self.speech_detected = True
            self.reason = 'silence'
            while not self.vad.empty():
                self.vad.pop()
        elif not self.speech_detected and self.seconds >= self.no_speech - 1e-6:
            self.reason = 'no_speech'
        elif self.seconds >= self.max_seconds - 1e-6:
            self.reason = 'max_duration'
        return bool(self.reason)

    def close(self):
        if not self.closed:
            self.closed = True
            _session_lock.release()
