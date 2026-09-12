"""
Audio Playback Module - Play audio files via ALSA aplay
"""
import os
import subprocess
import wave
import tempfile
import struct
import time
import select
import shutil
from audio.pcm import AudioFormatError, normalize_wav, read_wav


class AudioPlayer:
    """Audio player using ALSA aplay"""

    def __init__(self):
        self.backend = self._detect_backend()

    def _detect_backend(self) -> str:
        """Detect aplay availability"""
        if shutil.which('aplay'):
            return 'aplay'
        return 'none'

    @staticmethod
    def _resample_16k(path: str):
        """Reject invalid audio; never fall back to playing at the source rate."""
        with open(path, "rb") as handle:
            data = handle.read(12 * 1024 * 1024 + 1)
        if len(data) > 12 * 1024 * 1024:
            raise AudioFormatError("Audio too large")
        _, rate = read_wav(data)
        if rate == 16000:
            return path
        pcm = normalize_wav(data)
        fd, out_path = tempfile.mkstemp(suffix=".16k.wav")
        try:
            with os.fdopen(fd, "wb") as handle:
                with wave.open(handle, "wb") as target:
                    target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                    target.writeframes(pcm)
            return out_path
        except Exception:
            os.unlink(out_path)
            raise

    def play(self, audio_file: str) -> bool:
        """Play audio file; True if successful"""
        if not os.path.exists(audio_file):
            print(f"Audio file not found: {audio_file}")
            return False
        if self.backend != 'aplay':
            print("No audio playback backend available")
            return False

        target = audio_file
        timeout = 60.0
        try:
            target = self._resample_16k(audio_file)
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
        except (OSError, AudioFormatError) as e:
            print(f"aplay failed: {type(e).__name__}: {e}")
            return False
        finally:
            if target != audio_file and os.path.exists(target):
                try:
                    os.unlink(target)
                except OSError:
                    pass

    def play_pcm_stream(self, chunks, on_start=None, timeout=90.0):
        """Feed 16 kHz PCM through a nonblocking pipe, with bounded drain/exit.

        Network waits are bounded by the adapter. Pipe waits have a separate
        deadline so a wedged aplay cannot strand the voice-round worker.
        """
        proc = None
        started = False
        total_bytes = 0
        deadline = time.monotonic() + timeout
        try:
            if self.backend != "aplay":
                return False
            for chunk in chunks:
                if not chunk:
                    continue
                if not isinstance(chunk, bytes) or len(chunk) % 2:
                    raise AudioFormatError("Unaligned PCM16")
                total_bytes += len(chunk)
                if total_bytes > 16000 * 2 * 120 or time.monotonic() >= deadline:
                    raise TimeoutError("Playback stream limit")
                if proc is None:
                    proc = subprocess.Popen(
                        ["aplay", "-D", "plughw:0,0", "-t", "raw", "-f", "S16_LE",
                         "-r", "16000", "-c", "1"],
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, bufsize=0,
                    )
                    os.set_blocking(proc.stdin.fileno(), False)
                remaining = memoryview(chunk)
                while remaining:
                    wait = deadline - time.monotonic()
                    if wait <= 0 or proc.poll() is not None:
                        raise TimeoutError("Playback stopped or timed out")
                    if not select.select([], [proc.stdin.fileno()], [], min(wait, 0.2))[1]:
                        continue
                    try:
                        written = os.write(proc.stdin.fileno(), remaining[:8192])
                    except BlockingIOError:
                        continue
                    if written <= 0:
                        raise OSError("Playback pipe closed")
                    remaining = remaining[written:]
                    if not started:
                        started = True
                        if on_start:
                            on_start()
            if proc is None:
                return False
            proc.stdin.close()
            proc.wait(timeout=max(0.01, min(10, deadline - time.monotonic())))
            return proc.returncode == 0
        except Exception as error:
            print("[VOICE][stage=playback_error][kind=%s]" %
                  getattr(error, "kind", type(error).__name__), flush=True)
            return False
        finally:
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                try:
                    if proc.stdin and not proc.stdin.closed:
                        proc.stdin.close()
                except OSError:
                    pass
            close = getattr(chunks, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    pass


if __name__ == "__main__":
    player = AudioPlayer()
    print(f"Detected backend: {player.backend}")
