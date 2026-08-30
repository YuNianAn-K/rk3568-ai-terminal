"""
Audio Recording Module - ALSA recording via arecord
"""
import os
import subprocess
import tempfile


class AudioRecorder:
    """ALSA recording; mic detection + async record via Popen"""

    def __init__(self, sample_rate=16000, channels=1, max_seconds=10):
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_seconds = max_seconds
        self.has_mic = self._check_microphone()

    def _check_microphone(self) -> bool:
        """Detect microphone availability"""
        try:
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True, timeout=5
            )
            return b"card" in result.stdout
        except Exception:
            return False

    def record_async(self):
        """Start recording in background; returns (arecord_proc, wav_path)"""
        audio_file = tempfile.mktemp(suffix=".wav")
        proc = subprocess.Popen(
            ["arecord", "-D", "plughw:0,0",
             "-f", "S16_LE", "-r", str(self.sample_rate),
             "-c", str(self.channels), "-t", "wav", "-d", str(self.max_seconds),
             audio_file],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        return proc, audio_file


if __name__ == "__main__":
    recorder = AudioRecorder()
    print(f"Microphone available: {recorder.has_mic}")
