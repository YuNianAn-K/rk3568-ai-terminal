"""TTS Module - Text to Speech Conversion."""
import os
import asyncio
import tempfile
from abc import ABC, abstractmethod
from config import TTS_ENGINE, TTS_VOICE, TTS_RATE, TTS_VOLUME


class BaseTTS(ABC):
    """Base class for TTS engines"""

    @abstractmethod
    def synthesize(self, text: str, output_file: str) -> bool:
        """
        Convert text to speech

        Args:
            text: Input text
            output_file: Output audio file path

        Returns:
            True if successful, False otherwise
        """
        pass


class EdgeTTS(BaseTTS):
    """Edge TTS engine - free, good quality, requires internet"""

    def __init__(self):
        self.voice = TTS_VOICE
        self.rate = TTS_RATE
        self.volume = TTS_VOLUME

    async def _synthesize_async(self, text: str, output_file: str):
        """Async synthesis using edge-tts"""
        import edge_tts
        communicate = edge_tts.Communicate(
            text,
            self.voice,
            rate=self.rate,
            volume=self.volume
        )
        await communicate.save(output_file)

    def synthesize(self, text: str, output_file: str) -> bool:
        """Synthesize using Edge TTS"""
        try:
            asyncio.run(self._synthesize_async(text, output_file))
            return os.path.exists(output_file)
        except Exception as e:
            print(f"Edge TTS error: {e}")
            return False


class Pyttsx3TTS(BaseTTS):
    """pyttsx3 TTS engine - offline, basic quality"""

    def __init__(self):
        self.rate = 150
        self.volume = 0.9

    def synthesize(self, text: str, output_file: str) -> bool:
        """Synthesize using pyttsx3"""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', self.rate)
            engine.setProperty('volume', self.volume)

            # Try to set Chinese voice
            voices = engine.getProperty('voices')
            for voice in voices:
                if 'chinese' in voice.name.lower() or 'zh' in voice.id.lower():
                    engine.setProperty('voice', voice.id)
                    break

            engine.save_to_file(text, output_file)
            engine.runAndWait()
            return os.path.exists(output_file)
        except Exception as e:
            print(f"pyttsx3 error: {e}")
            return False


class GTTSTTS(BaseTTS):
    """gTTS engine - Google TTS, requires internet"""

    def __init__(self):
        self.lang = 'zh-cn'

    def synthesize(self, text: str, output_file: str) -> bool:
        """Synthesize using gTTS"""
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang=self.lang)
            tts.save(output_file)
            return os.path.exists(output_file)
        except Exception as e:
            print(f"gTTS error: {e}")
            return False


class TTSEngine:
    """TTS Engine Factory"""

    def __init__(self, engine_type: str = None):
        self.engine_type = engine_type or TTS_ENGINE
        self.engine = self._create_engine()

    def _create_engine(self) -> BaseTTS:
        """Create TTS engine based on configuration"""
        if self.engine_type == "mimo":
            from .mimo_tts import MiMoTTS
            return MiMoTTS()
        engines = {
            'edge': EdgeTTS,
            'pyttsx3': Pyttsx3TTS,
            'gtts': GTTSTTS,
        }

        engine_class = engines.get(self.engine_type)
        if not engine_class:
            raise ValueError("Unknown TTS provider")

        return engine_class()

    def text_to_speech(self, text: str, output_file: str = None) -> str:
        """
        Convert text to speech and save to file

        Args:
            text: Input text
            output_file: Output file path (optional)

        Returns:
            Output file path if successful, empty string otherwise
        """
        if not text or not text.strip():
            return ""

        owned = output_file is None
        if owned:
            fd, output_file = tempfile.mkstemp(prefix="voice-tts-", suffix=".wav")
            os.close(fd)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

        print(f"Converting to speech using {self.engine_type}...")
        if self.engine.synthesize(text, output_file):
            print(f"Audio saved to: {output_file}")
            return output_file
        else:
            if owned and os.path.exists(output_file):
                os.unlink(output_file)
            print("TTS conversion failed")
            return ""

    @property
    def supports_pcm_stream(self):
        return hasattr(self.engine, "pcm_stream")

    def pcm_stream(self, text):
        return self.engine.pcm_stream(text)

    def close(self):
        close = getattr(self.engine, "close", None)
        if close:
            close()


# Test function
if __name__ == "__main__":
    tts = TTSEngine()
    test_text = "你好，我是小米MiMo，很高兴认识你！"
    result = tts.text_to_speech(test_text)
    if result:
        print(f"Test successful! Audio file: {result}")
    else:
        print("Test failed!")
