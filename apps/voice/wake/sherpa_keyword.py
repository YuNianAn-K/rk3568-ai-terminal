"""Chinese local KWS. No network, WAV persistence, or English fallback."""
from pathlib import Path
import sys
import threading

from audio.capture import PCMCapture


MODEL_FILES = {
    "encoder": "encoder-epoch-13-avg-2-chunk-16-left-64.int8.onnx",
    "decoder": "decoder-epoch-13-avg-2-chunk-16-left-64.onnx",
    "joiner": "joiner-epoch-13-avg-2-chunk-16-left-64.int8.onnx",
    "tokens": "tokens.txt",
}


class ChineseWakeDetector:
    def __init__(self, model_path, capture_factory=PCMCapture):
        vendor = Path(__file__).resolve().parents[1] / "vendor-wake"
        if vendor.is_dir():
            sys.path.insert(0, str(vendor))
        paths = {name: str(Path(model_path) / file) for name, file in MODEL_FILES.items()}
        if not all(Path(path).is_file() for path in paths.values()):
            raise FileNotFoundError("Chinese KWS model missing")
        keywords = Path(__file__).with_name("keywords-xiaoai.txt")
        tokens = {line.split()[0] for line in Path(paths["tokens"]).read_text(encoding="utf-8").splitlines()}
        phones = keywords.read_text(encoding="utf-8").split("@")[0].split()
        if not set(phones) <= tokens:
            raise ValueError("Chinese KWS token mismatch")
        import numpy as np
        import sherpa_onnx
        self.np = np
        self.model = sherpa_onnx.KeywordSpotter(
            **paths, keywords_file=str(keywords), num_threads=1,
            provider="cpu", keywords_score=1.0, keywords_threshold=0.25,
            num_trailing_blanks=2)
        self.capture_factory = capture_factory
        # Warm the optional tiny VAD before listening so handoff stays fast.
        from audio.vad import prepare_vad
        prepare_vad()
        self.capture = None
        self.stream = None
        self.lock = threading.Lock()

    def poll_keyword(self):
        with self.lock:
            if self.capture is None:
                self.capture = self.capture_factory()
                self.stream = self.model.create_stream()
                print("[VOICE][stage=wake_listen][status=active]", flush=True)
            pcm = self.capture.read()
            if not pcm:
                return False
            samples = self.np.frombuffer(pcm, dtype="<i2").astype(self.np.float32) / 32768
            self.stream.accept_waveform(16000, samples)
            while self.model.is_ready(self.stream):
                self.model.decode_stream(self.stream)
                if self.model.get_result(self.stream) == "小爱同学":
                    self.model.reset_stream(self.stream)
                    return True
            return False

    def pause(self):
        # Returns only after the arecord process exits; formal capture starts later.
        with self.lock:
            if self.capture is not None:
                self.capture.close()
                self.capture = None
            self.stream = None

    close = pause
