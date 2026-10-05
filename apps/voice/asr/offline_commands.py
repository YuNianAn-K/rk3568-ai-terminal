"""Local, fail-closed recognition for fixed PC13 and person tracking phrases."""

import json
import math
import os
from pathlib import Path
import sys
import time

from audio.pcm import AudioFormatError, read_wav


DEFAULT_MODEL_PATH = "/opt/ai-voice-offline/vosk-model-small-cn-0.22"
MIN_WORD_CONFIDENCE = 0.75
MIN_MEAN_CONFIDENCE = 0.85
# Vosk grammar uses model word tokens, not whole unspaced Chinese phrases.
# [unk] prevents unrelated speech from being forced into a command.
COMMAND_GRAMMAR = json.dumps(
    ["打开 指示灯", "关闭 指示灯", "查询 指示灯 状态",
     "开始 跟踪 人物", "停止 跟踪", "停止 跟踪 人物",
     "不要 开始 跟踪 人物", "别 开始 跟踪 人物", "请 开始 跟踪 人物",
     "开始 跟踪 人物 吗", "不要 停止 跟踪", "停止 跟踪 吗", "[unk]"],
    ensure_ascii=False,
)


class LocalASRError(RuntimeError):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


class OfflineCommandASR:
    """Load the small Chinese model on first offline use, then reuse it."""

    def __init__(self, model_path=None):
        self.model_path = model_path or os.getenv(
            "VOICE_OFFLINE_MODEL_PATH", DEFAULT_MODEL_PATH)
        self.model = None
        self.recognizer_class = None

    def _ensure_model(self):
        if self.model is not None:
            return
        if not os.path.isdir(self.model_path):
            raise LocalASRError("model_missing")
        vendor = Path(__file__).resolve().parents[1] / "vendor"
        if vendor.is_dir() and str(vendor) not in sys.path:
            sys.path.insert(0, str(vendor))
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
            SetLogLevel(-1)
            self.model = Model(self.model_path)
            self.recognizer_class = KaldiRecognizer
        except Exception as error:
            raise LocalASRError("model_load") from error

    def recognize(self, audio_file):
        try:
            with open(audio_file, "rb") as handle:
                data = handle.read(7_000_001)
            if len(data) > 7_000_000:
                raise AudioFormatError("Offline ASR input too large")
            pcm, rate = read_wav(data, require_16k=True)
            self._ensure_model()
            recognizer = self.recognizer_class(self.model, rate, COMMAND_GRAMMAR)
            recognizer.SetWords(True)
            fragments = []
            confidences = []
            start = time.monotonic()
            for offset in range(0, len(pcm), 8000):
                if recognizer.AcceptWaveform(pcm[offset:offset + 8000]):
                    self._collect(recognizer.Result(), fragments, confidences)
            self._collect(recognizer.FinalResult(), fragments, confidences)
            text = "".join(fragments).replace(" ", "")
            confidence = (sum(confidences) / len(confidences)
                          if confidences else 0.0)
            accepted = (bool(text) and bool(confidences) and
                        min(confidences) >= MIN_WORD_CONFIDENCE and
                        confidence >= MIN_MEAN_CONFIDENCE)
            print("[VOICE][stage=offline_asr][status=%s][elapsed_ms=%d]"
                  "[confidence=%.2f]" %
                  ("accepted" if accepted else "rejected",
                   int((time.monotonic() - start) * 1000), confidence),
                  flush=True)
            return text if accepted else ""
        except LocalASRError:
            raise
        except (OSError, AudioFormatError, ValueError, KeyError) as error:
            raise LocalASRError("audio_or_decode") from error
        except Exception as error:
            raise LocalASRError("decoder") from error

    @staticmethod
    def _collect(raw, fragments, confidences):
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise LocalASRError("invalid_result") from error
        if not isinstance(data, dict):
            raise LocalASRError("invalid_result")
        text = data.get("text", "")
        if not isinstance(text, str):
            raise LocalASRError("invalid_result")
        if text:
            fragments.append(text)
            words = data.get("result", [])
            if not isinstance(words, list):
                raise LocalASRError("invalid_result")
            for word in words:
                if (not isinstance(word, dict) or
                        not isinstance(word.get("conf"), (int, float)) or
                        not math.isfinite(word["conf"]) or
                        not 0 <= word["conf"] <= 1):
                    raise LocalASRError("invalid_result")
                confidences.append(float(word["conf"]))
