"""
TTS Module - Text to Speech Conversion
Supports Edge TTS, pyttsx3, gTTS, and Volcengine TTS
"""
import os
import json
import uuid
import asyncio
import base64
from abc import ABC, abstractmethod
from config import TTS_ENGINE, TTS_VOICE, TTS_RATE, TTS_VOLUME, AUDIO_FILE
from config import VOLC_API_KEY, VOLC_VOICE_TYPE


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


class VolcengineTTS(BaseTTS):
    """Volcengine TTS - 国内服务，板子独立运行可用"""

    def __init__(self):
        self.api_key = VOLC_API_KEY
        self.voice_type = VOLC_VOICE_TYPE
        self.api_url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

    def synthesize(self, text: str, output_file: str) -> bool:
        """Synthesize using Volcengine TTS V3 API"""
        try:
            import requests
            import struct

            payload = {
                "req_params": {
                    "text": text,
                    "speaker": self.voice_type,
                    "audio_params": {
                        "format": "wav",
                        "sample_rate": 24000
                    }
                }
            }

            headers = {
                "X-Api-Key": self.api_key,
                "X-Api-Resource-Id": "seed-tts-2.0",
                "X-Api-Request-Id": str(uuid.uuid4()),
                "Content-Type": "application/json"
            }

            resp = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()

            raw_chunks = []
            for line in resp.text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                result = json.loads(line)
                code = result.get("code")
                if code == 0 and result.get("data"):
                    raw_chunks.append(base64.b64decode(result["data"]))
                elif code not in (0, 20000000):
                    print(f"Volcengine TTS error: code={code}, message={result.get('message')}")
                    return False

            if not raw_chunks:
                print("Volcengine TTS error: no audio data received")
                return False

            # First chunk may have WAV header (RIFF), strip it to get raw PCM
            pcm_data = raw_chunks[0]
            if pcm_data[:4] == b"RIFF":
                # Find "data" chunk in WAV header
                pos = 12  # skip RIFF header
                while pos < len(pcm_data) - 8:
                    chunk_id = pcm_data[pos:pos + 4]
                    chunk_size = struct.unpack("<I", pcm_data[pos + 4:pos + 8])[0]
                    if chunk_id == b"data":
                        pcm_data = pcm_data[pos + 8:pos + 8 + chunk_size]
                        break
                    pos += 8 + chunk_size
            # Append remaining raw chunks
            pcm_data += b"".join(raw_chunks[1:])

            # Write proper WAV file
            sample_rate = 24000
            channels = 1
            bits_per_sample = 16
            byte_rate = sample_rate * channels * bits_per_sample // 8
            block_align = channels * bits_per_sample // 8
            data_size = len(pcm_data)

            with open(output_file, "wb") as f:
                # RIFF header
                f.write(b"RIFF")
                f.write(struct.pack("<I", 36 + data_size))
                f.write(b"WAVE")
                # fmt chunk
                f.write(b"fmt ")
                f.write(struct.pack("<I", 16))
                f.write(struct.pack("<H", 1))  # PCM
                f.write(struct.pack("<H", channels))
                f.write(struct.pack("<I", sample_rate))
                f.write(struct.pack("<I", byte_rate))
                f.write(struct.pack("<H", block_align))
                f.write(struct.pack("<H", bits_per_sample))
                # data chunk
                f.write(b"data")
                f.write(struct.pack("<I", data_size))
                f.write(pcm_data)

            print(f"Volcengine TTS success: {data_size} bytes PCM, {len(raw_chunks)} chunks")
            return True

        except Exception as e:
            print(f"Volcengine TTS error: {e}")
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
        engines = {
            'edge': EdgeTTS,
            'pyttsx3': Pyttsx3TTS,
            'gtts': GTTSTTS,
            'volcengine': VolcengineTTS
        }

        engine_class = engines.get(self.engine_type)
        if not engine_class:
            print(f"Unknown TTS engine: {self.engine_type}, using Edge TTS")
            engine_class = EdgeTTS

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

        output_file = output_file or AUDIO_FILE

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        print(f"Converting to speech using {self.engine_type}...")
        if self.engine.synthesize(text, output_file):
            print(f"Audio saved to: {output_file}")
            return output_file
        else:
            print("TTS conversion failed")
            return ""


# Test function
if __name__ == "__main__":
    tts = TTSEngine()
    test_text = "你好，我是小米MiMo，很高兴认识你！"
    result = tts.text_to_speech(test_text)
    if result:
        print(f"Test successful! Audio file: {result}")
    else:
        print("Test failed!")