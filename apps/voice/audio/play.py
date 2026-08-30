"""
Audio Playback Module - Play audio files via ALSA aplay
"""
import os
import subprocess
import wave
import tempfile
import struct


class AudioPlayer:
    """Audio player using ALSA aplay"""

    def __init__(self):
        self.backend = self._detect_backend()

    def _detect_backend(self) -> str:
        """Detect aplay availability"""
        if subprocess.run(['which', 'aplay'], capture_output=True).returncode == 0:
            return 'aplay'
        return 'none'

    @staticmethod
    def _resample_16k(path: str):
        """Resample a WAV to 16 kHz. TTS plays at 24 kHz, but capture runs at
        16 kHz and the rk817 codec locks to DC after a 24 kHz playback.
        Returns the temp path, or the original path if already 16 kHz.
        Falls back to the original file if resampling is unavailable."""
        try:
            import numpy as np
            with open(path, "rb") as f:
                data = f.read()
            if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
                return path
            sr = struct.unpack("<I", data[24:28])[0]
            if sr == 16000:
                return path
            samples = np.frombuffer(data[44:], dtype=np.int16)
            n = len(samples)
            if n < 100:
                return path
            newn = int(n * 16000 / sr)
            idx = np.linspace(0, n - 1, newn)
            y = np.interp(idx, np.arange(n), samples.astype(np.float64)).astype(np.int16)
            out_path = tempfile.mktemp(suffix=".16k.wav")
            wf = wave.open(out_path, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(y.tobytes())
            wf.close()
            return out_path
        except Exception:
            return path

    def play(self, audio_file: str) -> bool:
        """Play audio file; True if successful"""
        if not os.path.exists(audio_file):
            print(f"Audio file not found: {audio_file}")
            return False
        if self.backend != 'aplay':
            print("No audio playback backend available")
            return False

        target = self._resample_16k(audio_file)
        timeout = 60.0
        try:
            try:
                with wave.open(target, "rb") as wf:
                    duration = wf.getnframes() / max(1, wf.getframerate())
                timeout = max(5.0, min(duration + 5.0, 120.0))
            except (OSError, EOFError, wave.Error):
                pass

            result = subprocess.run(
                ["aplay", "-D", "plughw:0,0", target],
                capture_output=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                print(f"aplay error: {result.stderr.decode(errors='replace')}")
                return False
            return True
        except subprocess.TimeoutExpired:
            print(f"aplay timeout after {timeout:.1f}s")
            return False
        except OSError as e:
            print(f"aplay failed: {type(e).__name__}: {e}")
            return False
        finally:
            if target != audio_file and os.path.exists(target):
                try:
                    os.unlink(target)
                except OSError:
                    pass


if __name__ == "__main__":
    player = AudioPlayer()
    print(f"Detected backend: {player.backend}")
