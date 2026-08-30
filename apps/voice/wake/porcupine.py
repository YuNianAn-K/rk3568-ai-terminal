"""
Wake Word Detection Module - openWakeWord + ALSA arecord
"""
import subprocess
import numpy as np
import tempfile
import os


class WakeWordDetector:
    """openWakeWord 唤醒词检测"""

    def __init__(self, keyword: str = None):
        from config import WAKE_WORD
        self.keyword = keyword or WAKE_WORD
        self.model = None
        self.available = self._check_availability()

    def _check_availability(self) -> bool:
        """检查 openWakeWord 和麦克风是否可用"""
        try:
            from openwakeword import Model
            self._Model = Model
        except ImportError:
            print("openwakeword not installed, wake word disabled")
            return False

        # Check microphone via arecord
        try:
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True, text=True, timeout=5
            )
            if "card" not in result.stdout:
                print("No audio capture device, wake word disabled")
                return False
        except Exception:
            print("arecord not available, wake word disabled")
            return False

        return True

    def listen(self, callback):
        """
        持续监听唤醒词，检测到后调用 callback

        Uses arecord to capture 1-second chunks and checks for wake word.
        """
        if not self.available:
            print("Wake word detector not available")
            return

        print(f"Loading wake word model...")
        self.model = self._Model(wakeword_models=["timer"])

        CHUNK_SECONDS = 1
        SAMPLE_RATE = 16000
        SAMPLES_PER_CHUNK = SAMPLE_RATE * CHUNK_SECONDS

        print(f"Listening for wake word...")

        try:
            while True:
                # Record 1 second of audio
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp_path = f.name

                try:
                    subprocess.run(
                        [
                            "arecord", "-D", "default",
                            "-f", "S16_LE", "-r", "16000", "-c", "1",
                            "-d", str(CHUNK_SECONDS),
                            tmp_path
                        ],
                        capture_output=True, timeout=5
                    )

                    # Read WAV file (skip 44-byte header)
                    with open(tmp_path, "rb") as f:
                        f.read(44)  # Skip WAV header
                        raw = f.read()

                    if len(raw) < SAMPLES_PER_CHUNK * 2:
                        continue

                    audio = np.frombuffer(raw[:SAMPLES_PER_CHUNK * 2], dtype=np.int16)
                    prediction = self.model.predict(audio)

                    for model_name, score in prediction.items():
                        if score > 0.5:
                            print(f"Wake word detected! (score: {score:.2f})")
                            self.model.reset()
                            callback()
                            break
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

        except KeyboardInterrupt:
            pass
        finally:
            self.model = None

    def stop(self):
        """停止监听"""
        self.model = None


if __name__ == "__main__":
    detector = WakeWordDetector()
    print(f"Available: {detector.available}")
    if detector.available:
        print("Starting wake word detection (Ctrl+C to stop)...")
        detector.listen(lambda: print("Triggered!"))
