"""Deterministic voice-entry tests; no cloud, model, ALSA or device actions."""
import array
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import subprocess
import time
import unittest
from unittest.mock import Mock, patch
import wave
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio.capture import AutomaticRecording, SilenceEndpoint, PCMCapture
from voice_service import VoiceService
from test_voice_service import FakeTerminal
from main import AIVoiceTerminal


def frame(amplitude=0, dc=0):
    return array.array("h", [int(dc + amplitude * math.sin(2 * math.pi * 500 * i / 16000))
                             for i in range(1600)]).tobytes()


class EndpointTests(unittest.TestCase):
    def test_no_speech_and_dc_noise_do_not_count(self):
        endpoint = SilenceEndpoint()
        for _ in range(41):
            endpoint.feed(frame(dc=1400))
        self.assertFalse(endpoint.speech_detected)
        self.assertEqual(endpoint.reason, "no_speech")

    def test_short_noise_impulse_not_speech(self):
        endpoint = SilenceEndpoint()
        endpoint.feed(frame(1000))
        for _ in range(40):
            endpoint.feed(frame())
        self.assertFalse(endpoint.speech_detected)

    def test_speech_pause_tail_and_limit(self):
        endpoint = SilenceEndpoint()
        for _ in range(5): endpoint.feed(frame(1000))
        for _ in range(6): self.assertFalse(endpoint.feed(frame()))
        self.assertFalse(endpoint.feed(frame(1000)))
        for _ in range(11): endpoint.feed(frame())
        self.assertTrue(endpoint.speech_detected)
        self.assertEqual(endpoint.reason, "silence")
        endpoint = SilenceEndpoint(max_seconds=1)
        for _ in range(11): endpoint.feed(frame(1000))
        self.assertEqual(endpoint.reason, "max_duration")

    def test_real_wav_preserves_onset_and_tail_and_releases_capture(self):
        class Capture:
            closed = False
            def __init__(self): self.frames = iter([frame(1000)] * 4 + [frame()] * 11)
            def read(self): return next(self.frames)
            def close(self): self.closed = True
        capture = Capture()
        proc = AutomaticRecording(capture_factory=lambda: capture)
        try:
            self.assertEqual(proc.wait(2), 0)
            self.assertTrue(proc.speech_detected)
            self.assertTrue(capture.closed)
            with wave.open(proc.path) as source:
                self.assertEqual(source.getframerate(), 16000)
                self.assertEqual(source.readframes(1600), frame(1000))
                self.assertGreaterEqual(source.getnframes(), 22400)
        finally:
            os.unlink(proc.path)

    def test_capture_failure_and_constructor_cleanup(self):
        capture = Mock()
        capture.read.side_effect = TimeoutError()
        proc = AutomaticRecording(capture_factory=lambda: capture)
        try:
            self.assertEqual(proc.wait(2), 1)
            self.assertEqual(proc.error, "TimeoutError")
            capture.close.assert_called_once()
        finally: os.unlink(proc.path)
        with tempfile.TemporaryDirectory() as directory:
            with patch("audio.capture.tempfile.tempdir", directory):
                with self.assertRaises(OSError):
                    AutomaticRecording(capture_factory=Mock(side_effect=OSError()))
            self.assertEqual(os.listdir(directory), [])

    def test_capture_stall_and_terminate_kill_cleanup(self):
        proc = Mock()
        proc.poll.return_value = None
        with patch("audio.capture.subprocess.Popen", return_value=proc), \
                patch("audio.capture.select.select", return_value=([], [], [])):
            capture = PCMCapture()
            capture.last_data -= 3
            with self.assertRaises(TimeoutError): capture.read()
            proc.wait.side_effect = [subprocess.TimeoutExpired("arecord", 1), 0]
            capture.close()
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        proc.stdout.close.assert_called_once()

    def test_cancel_joins_capture_and_first_frame_only_once(self):
        capture = Mock()
        def read():
            time.sleep(.005)
            return frame(1000)
        capture.read.side_effect = read
        first = Mock()
        proc = AutomaticRecording(capture_factory=lambda: capture, on_first_frame=first)
        try:
            deadline = time.monotonic() + 1
            while first.call_count == 0 and time.monotonic() < deadline: time.sleep(.01)
            proc.terminate()
            proc.wait(2)
            self.assertFalse(proc.worker.is_alive())
            first.assert_called_once()
            capture.close.assert_called_once()
        finally: os.unlink(proc.path)


class HandsFreeServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = VoiceService(terminal_factory=FakeTerminal)
        with patch("config.VOICE_WAKE_ENABLE", False): self.service.initialize_terminal()
        self.service.wake_detector = Mock()
        self.service.wake_enabled = True
        self.service._wake_feedback = Mock()

    def tearDown(self):
        self.service.stop_event.set()

    def test_wake_handoff_busy_and_button_fallback(self):
        order = []
        self.service.wake_detector.pause.side_effect = lambda: order.append("release")
        self.service._wake_feedback.side_effect = lambda: order.append("feedback")
        start = self.service.terminal._start_recording
        self.service.terminal._start_recording = lambda **kw: (order.append("record") or start(**kw))
        self.assertTrue(self.service._start_round(None, hands_free=True)["accepted"])
        self.assertEqual(order, ["release", "feedback", "record"])
        self.assertIn("wake_detected", self.service.timings)
        self.assertTrue(self.service.terminal._hands_free)
        self.assertFalse(self.service._start_round(None, hands_free=True)["accepted"])
        self.service._cancel_round(None)
        self.assertGreater(self.service.wake_resume_at, time.monotonic())
        self.assertTrue(self.service._start_round(None)["accepted"])
        self.assertFalse(self.service.terminal._hands_free)

    def test_release_failure_never_opens_second_capture(self):
        self.service.wake_detector.pause.side_effect = OSError()
        self.service.terminal._start_recording = Mock()
        self.assertFalse(self.service._start_round(None)["accepted"])
        self.service.terminal._start_recording.assert_not_called()

    def test_simultaneous_button_and_wake_admit_exactly_one_round(self):
        barrier = threading.Barrier(3)
        results = []
        def start(wake):
            barrier.wait()
            results.append(self.service._start_round(None, hands_free=wake)["accepted"])
        workers = [threading.Thread(target=start, args=(wake,)) for wake in (True, False)]
        for worker in workers: worker.start()
        barrier.wait()
        for worker in workers: worker.join(2)
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.service.round_id, 1)

    def test_disabled_and_missing_model_keep_button_mode(self):
        self.assertTrue(self.service.handle_command({"command": "wake_disable"})["accepted"])
        self.assertFalse(self.service._start_round(None, hands_free=True)["accepted"])
        self.assertTrue(self.service._start_round(None)["accepted"])
        self.service._cancel_round(None)
        self.service.wake_detector = None
        with patch("wake.sherpa_keyword.ChineseWakeDetector", side_effect=ImportError()):
            self.assertFalse(self.service.handle_command({"command": "wake_enable"})["accepted"])
        self.assertTrue(self.service._start_round(None)["accepted"])

    def test_busy_disable_refused_and_feedback_failure_safe(self):
        self.service._wake_feedback.side_effect = OSError()
        self.assertTrue(self.service._start_round(None, hands_free=True)["accepted"])
        self.assertFalse(self.service.handle_command({"command": "wake_disable"})["accepted"])

    def test_worker_failure_recovers_without_wake_during_playback(self):
        self.service._start_round(None, hands_free=True)
        def fail(automatic=False):
            self.service.terminal._recording = False
            raise OSError()
        self.service.terminal._finish_recording = fail
        self.service._begin_finish()
        deadline = time.monotonic() + 2
        while self.service.round_worker_active and time.monotonic() < deadline: time.sleep(.01)
        self.assertFalse(self.service.round_worker_active)
        self.assertEqual(self.service.state, "error")
        self.assertGreater(self.service.wake_resume_at, time.monotonic())
        self.assertTrue(self.service._start_round(None)["accepted"])

    def test_silence_never_calls_recognition_or_action(self):
        terminal = object.__new__(AIVoiceTerminal)
        proc = Mock()
        proc.poll.return_value = 0
        proc.returncode = 0
        proc.speech_detected = False
        proc.error = None
        proc.endpoint.reason = "no_speech"
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        terminal._record_proc, terminal._audio_file = proc, path
        terminal.event_callback = Mock()
        terminal._process_audio = Mock()
        terminal._finish_recording(automatic=True)
        terminal._process_audio.assert_not_called()
        self.assertFalse(os.path.exists(path))

    def test_playing_state_never_polls_model(self):
        for state in ("recording", "recognizing", "thinking", "replying", "playing"):
            self.service.state = state
            self.service.wake_detector.poll_keyword.reset_mock()
            with patch.object(self.service.stop_event, "wait", side_effect=[False, True]):
                self.service._monitor_wake()
            self.service.wake_detector.poll_keyword.assert_not_called()

    def test_without_keyword_no_recording_or_action_entry(self):
        self.service.wake_detector.poll_keyword.return_value = False
        self.service.terminal._start_recording = Mock()
        with patch.object(self.service.stop_event, "wait", side_effect=[False, True]):
            self.service._monitor_wake()
        self.service.terminal._start_recording.assert_not_called()
        self.assertEqual(self.service.round_id, 0)

    def test_listener_failure_has_bounded_retry(self):
        self.service.wake_detector.poll_keyword.side_effect = TimeoutError()
        with patch.object(self.service.stop_event, "wait", side_effect=[False, True]):
            self.service._monitor_wake()
        self.service.wake_detector.pause.assert_called_once()
        self.assertGreater(self.service.wake_resume_at, time.monotonic())

    def test_wake_cleanup_error_does_not_skip_socket_cleanup(self):
        self.service.wake_detector.close.side_effect = OSError()
        server = Mock()
        self.service.server_socket = server
        fd, path = tempfile.mkstemp()
        os.close(fd)
        self.service.socket_path = path
        self.service.shutdown()
        server.close.assert_called_once()
        self.assertFalse(self.service.wake_enabled)
        self.assertFalse(os.path.exists(path))

    def test_feedback_pcm_distinct_bounded_16k_with_silent_edges(self):
        with patch.object(VoiceService, '_hello_pcm', return_value=frame(1000)):
            self.assertEqual(self.service._feedback_pcm('wake'), frame(1000))
        timeout = array.array('h', self.service._feedback_pcm('no_speech'))
        self.assertEqual(len(timeout), 4400)
        self.assertEqual(set(timeout[1760:2160]), {0})
        for pcm in (timeout,):
            self.assertEqual(pcm[0], 0)
            self.assertEqual(pcm[-1], 0)
            self.assertLessEqual(max(abs(x) for x in pcm), 6000)
            self.assertGreater(max(abs(x) for x in pcm), 5000)

    def test_feedback_playback_is_bounded_and_failure_does_not_raise(self):
        self.service.terminal.player = Mock()
        self.service.terminal.player.play_pcm_stream.return_value = True
        with patch.object(VoiceService, '_hello_pcm', return_value=frame(1000)):
            self.assertTrue(self.service._play_feedback('wake'))
        call = self.service.terminal.player.play_pcm_stream.call_args
        self.assertEqual(call.kwargs['timeout'], 2)
        self.assertEqual(len(b''.join(call.args[0])), 3200)
        self.service.terminal.player.play_pcm_stream.side_effect = OSError()
        self.assertFalse(self.service._play_feedback('no_speech'))

    def test_missing_hello_uses_local_tone_without_cloud(self):
        self.service.terminal.player = Mock()
        with patch.object(VoiceService, '_hello_pcm', side_effect=ValueError()):
            self.assertTrue(self.service._play_feedback('wake'))
        self.assertEqual(len(b''.join(self.service.terminal.player.play_pcm_stream.call_args.args[0])), 8800)

    def test_hello_wav_checked_for_format_and_length(self):
        import io
        def wav(rate, frames):
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as target:
                target.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
                target.writeframes(b'\0\0' * frames)
            return buffer.getvalue()
        for rate, count, valid in [(16000, 1600, True), (24000, 1600, False), (16000, 25000, False)]:
            handle = Mock()
            handle.__enter__ = Mock(return_value=handle)
            handle.__exit__ = Mock(return_value=False)
            handle.read.return_value = wav(rate, count)
            with patch('pathlib.Path.open', return_value=handle):
                if valid: self.assertEqual(len(VoiceService._hello_pcm()), 3200)
                else:
                    with self.assertRaises(ValueError): VoiceService._hello_pcm()

    def test_no_speech_cue_before_idle_and_listener_recovery(self):
        self.service.terminal._hands_free = True
        self.service.terminal._record_proc = SimpleNamespace(speech_detected=False, error=None,
            returncode=0, endpoint=SimpleNamespace(reason='no_speech'))
        self.service.state = 'recognizing'
        self.service.round_worker_active = True
        self.service.terminal._finish_recording = Mock()
        def cue(kind):
            self.assertEqual(kind, 'no_speech')
            self.assertTrue(self.service.round_worker_active)
            self.assertNotEqual(self.service.state, 'idle')
            self.assertFalse(self.service._start_round(None)['accepted'])
        self.service._play_feedback = Mock(side_effect=cue)
        self.service._finish_round(True)
        self.service._play_feedback.assert_called_once_with('no_speech')
        self.assertEqual(self.service.state, 'idle')
        self.assertFalse(self.service.round_worker_active)
        self.assertGreater(self.service.wake_resume_at, time.monotonic())

    def test_no_timeout_cue_for_manual_speech_error_or_shutdown(self):
        self.service._play_feedback = Mock()
        for manual, speech, error, reason, stop in [
                (True, False, None, 'no_speech', False),
                (False, True, None, 'silence', False),
                (False, False, 'OSError', 'no_speech', False),
                (False, False, None, 'manual_stop', False),
                (False, False, None, 'no_speech', True)]:
            self.service.terminal._hands_free = not manual
            self.service.terminal._record_proc = SimpleNamespace(speech_detected=speech, error=error,
                returncode=1 if error else 0, endpoint=SimpleNamespace(reason=reason))
            self.service.terminal._finish_recording = Mock()
            if stop: self.service.stop_event.set()
            self.service._finish_round(True)
        self.service._play_feedback.assert_not_called()


if __name__ == "__main__": unittest.main()
