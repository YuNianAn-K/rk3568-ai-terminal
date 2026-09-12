"""MiMo ASR adapter preserving recognize(path) -> text/empty semantics."""
import base64

from audio.pcm import AudioFormatError, read_wav
from mimo_http import MiMoError, MiMoHTTP, first_choice, retry_pause


class MiMoASR:
    MAX_AUDIO_BYTES = 7_000_000

    def __init__(self, api_key=None, http=None):
        from config import MIMO_ASR_LANGUAGE
        if MIMO_ASR_LANGUAGE not in ("auto", "zh", "en"):
            raise MiMoError("invalid_language")
        self.language = MIMO_ASR_LANGUAGE
        self.http = http or MiMoHTTP(api_key=api_key)

    def recognize(self, audio_file, retries=2):
        try:
            with open(audio_file, "rb") as handle:
                data = handle.read(self.MAX_AUDIO_BYTES + 1)
            if len(data) > self.MAX_AUDIO_BYTES:
                raise AudioFormatError("ASR input too large")
            read_wav(data, require_16k=True)
            payload = {
                "model": "mimo-v2.5-asr",
                "messages": [{"role": "user", "content": [{
                    "type": "input_audio", "input_audio": {
                        "data": "data:audio/wav;base64," + base64.b64encode(data).decode("ascii")
                    }}]}],
                "asr_options": {"language": self.language},
            }
            for attempt in range(max(1, min(retries, 2))):
                try:
                    choice = first_choice(self.http.request(payload, budget=20))
                    message = choice.get("message")
                    text = message.get("content") if isinstance(message, dict) else None
                    if not isinstance(text, str) or not text.strip():
                        raise MiMoError("empty_transcript")
                    return text.strip()
                except MiMoError as error:
                    if not error.retryable or attempt + 1 >= max(1, min(retries, 2)):
                        raise
                    retry_pause(error, attempt)
        except (OSError, AudioFormatError, MiMoError) as error:
            print("[VOICE][provider=mimo][stage=asr_error][kind=%s]" %
                  getattr(error, "kind", type(error).__name__), flush=True)
        return ""

    def close(self):
        self.http.close()
