"""Validate PCM WAV and keep a continuous 16 kHz resampling state."""
import io
import wave


class AudioFormatError(ValueError):
    pass


def read_wav(data, require_16k=False):
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            rate = source.getframerate()
            if (source.getnchannels() != 1 or source.getsampwidth() != 2 or
                    source.getcomptype() != "NONE" or rate not in (16000, 24000, 48000)):
                raise AudioFormatError("Expected mono PCM16 WAV at 16/24/48 kHz")
            if require_16k and rate != 16000:
                raise AudioFormatError("ASR input must be 16 kHz")
            expected = source.getnframes() * 2
            pcm = source.readframes(source.getnframes())
            if not pcm or len(pcm) != expected or len(pcm) % 2:
                raise AudioFormatError("Empty or truncated WAV")
            return pcm, rate
    except (wave.Error, EOFError, OSError):
        raise AudioFormatError("Invalid WAV") from None


class PCM16Resampler:
    def __init__(self, source_rate):
        if source_rate not in (16000, 24000, 48000):
            raise AudioFormatError("Unsupported sample rate")
        self.rate = source_rate
        self.state = None
        self.pending = b""

    def feed(self, chunk):
        data = self.pending + chunk
        aligned = len(data) // 2 * 2
        self.pending = data[aligned:]
        if not aligned:
            return b""
        data = data[:aligned]
        if self.rate == 16000:
            return data
        try:
            import audioop
        except ImportError:
            raise AudioFormatError("PCM resampling requires Python 3.10-3.12 audioop") from None
        converted, self.state = audioop.ratecv(data, 2, 1, self.rate, 16000, self.state)
        return converted

    def finish(self):
        if self.pending:
            raise AudioFormatError("Truncated PCM sample")


def normalize_wav(data):
    pcm, rate = read_wav(data)
    converter = PCM16Resampler(rate)
    result = converter.feed(pcm)
    converter.finish()
    if not result:
        raise AudioFormatError("No playable PCM")
    return result
