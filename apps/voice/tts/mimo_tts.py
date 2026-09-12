"""MiMo TTS: validated 16 kHz PCM, with fallback only before audio escapes."""
import base64
import binascii
import os
import tempfile
import wave

from audio.pcm import AudioFormatError, PCM16Resampler, normalize_wav
from mimo_http import MiMoError, MiMoHTTP, first_choice, retry_pause


class MiMoTTS:
    def __init__(self, api_key=None, http=None):
        from config import MIMO_TTS_VOICE, MIMO_TTS_STREAM
        self.voice = MIMO_TTS_VOICE
        self.streaming_enabled = MIMO_TTS_STREAM
        self.http = http or MiMoHTTP(api_key=api_key)

    def _payload(self, text, stream):
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise MiMoError("invalid_text")
        return {
            "model": "mimo-v2.5-tts",
            "messages": [{"role": "assistant", "content": text}],
            "audio": {"format": "pcm16" if stream else "wav", "voice": self.voice},
            "stream": stream,
        }

    @staticmethod
    def _decode(data):
        if not isinstance(data, str) or not data:
            raise MiMoError("invalid_audio")
        try:
            return base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error):
            raise MiMoError("invalid_audio") from None

    def _blocking_pcm(self, text, retries=2):
        payload = self._payload(text, False)
        for attempt in range(retries):
            try:
                choice = first_choice(self.http.request(payload, budget=25))
                message = choice.get("message")
                audio = message.get("audio") if isinstance(message, dict) else None
                if not isinstance(audio, dict):
                    raise MiMoError("invalid_audio")
                return normalize_wav(self._decode(audio.get("data")))
            except MiMoError as error:
                if not error.retryable or attempt + 1 == retries:
                    raise
                retry_pause(error, attempt)

    def _stream_once(self, text):
        converter = PCM16Resampler(24000)
        complete = False
        has_audio = False
        events = self.http.responses(self._payload(text, True), budget=25)
        try:
            for event in events:
                if event.get("_done"):
                    complete = True
                    break
                if event.get("choices") == [] and "usage" in event:
                    continue
                choice = first_choice(event)
                delta = choice.get("delta")
                if not isinstance(delta, dict):
                    raise MiMoError("invalid_stream")
                audio = delta.get("audio")
                if audio is not None:
                    if complete or not isinstance(audio, dict):
                        raise MiMoError("invalid_audio")
                    if audio.get("data") not in (None, ""):
                        raw = self._decode(audio["data"])
                        if raw.startswith((b"RIFF", b"ID3", b"OggS", b"fLaC")):
                            raise MiMoError("unexpected_audio_container")
                        pcm = converter.feed(raw)
                        if pcm:
                            has_audio = True
                            yield pcm
                if choice.get("finish_reason") == "stop":
                    complete = True
            converter.finish()
            if not complete or not has_audio:
                raise MiMoError("truncated_stream" if has_audio else "empty_audio")
        finally:
            events.close()

    def pcm_stream(self, text):
        """Never replay a sentence after handing any PCM to the player."""
        if not self.streaming_enabled:
            yield self._blocking_pcm(text)
            return
        for attempt in range(2):
            emitted = False
            stream = self._stream_once(text)
            try:
                for pcm in stream:
                    emitted = True
                    yield pcm
                return
            except (MiMoError, AudioFormatError) as error:
                if emitted:
                    raise
                if isinstance(error, MiMoError):
                    if error.kind in ("missing_key", "invalid_text", "invalid_endpoint") or error.status in (401, 403):
                        raise
                    if error.retryable and attempt == 0:
                        retry_pause(error, attempt)
                        continue
                    # Rate limiting is not a stream capability failure.
                    if error.status == 429:
                        raise
                print("[VOICE][provider=mimo][stage=tts_fallback][mode=nonstream]", flush=True)
                yield self._blocking_pcm(text, retries=1)
                return
            finally:
                stream.close()

    def synthesize(self, text, output_file):
        temporary = None
        try:
            pcm = self._blocking_pcm(text)
            directory = os.path.dirname(os.path.abspath(output_file))
            os.makedirs(directory, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".mimo-", suffix=".wav", dir=directory)
            with os.fdopen(fd, "wb") as handle:
                with wave.open(handle, "wb") as target:
                    target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                    target.writeframes(pcm)
            os.replace(temporary, output_file)
            temporary = None
            return True
        except (OSError, MiMoError, AudioFormatError, wave.Error) as error:
            print("[VOICE][provider=mimo][stage=tts_error][kind=%s]" %
                  getattr(error, "kind", type(error).__name__), flush=True)
            return False
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def close(self):
        self.http.close()
