"""Deterministic endpoint policy tests without native inference or microphone."""
import array
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio.capture import AutomaticRecording
from audio.vad import SileroEndpoint


class Samples(list):
    def astype(self, _): return self
    def mean(self): return sum(self) / len(self)
    def __sub__(self, value): return Samples(x - value for x in self)
    def __truediv__(self, value): return Samples(x / value for x in self)


class NP:
    float32 = 'float32'
    @staticmethod
    def frombuffer(pcm, dtype):
        assert dtype == '<i2'
        return Samples(array.array('h', pcm))


PCM = array.array('h', [1000, -1000] * 800).tobytes()


class SileroEndpointTests(unittest.TestCase):
    def setUp(self):
        self.vad = Mock()
        self.vad.empty.return_value = True
        self.vad.is_speech_detected.return_value = False
        self.endpoint = SileroEndpoint(engine=(NP, self.vad))

    def tearDown(self): self.endpoint.close()

    def test_loud_non_speech_exits_without_action_eligibility(self):
        for _ in range(39): self.assertFalse(self.endpoint.feed(PCM))
        self.assertTrue(self.endpoint.feed(PCM))
        self.assertEqual(self.endpoint.reason, 'no_speech')
        self.assertFalse(self.endpoint.speech_detected)

    def test_speech_finishes_despite_background_energy(self):
        self.vad.is_speech_detected.return_value = True
        self.assertFalse(self.endpoint.feed(PCM))
        self.vad.is_speech_detected.return_value = False
        for _ in range(7): self.assertFalse(self.endpoint.feed(PCM))
        self.vad.empty.side_effect = [False, False, True]
        self.assertTrue(self.endpoint.feed(PCM))
        self.assertEqual(self.endpoint.reason, 'silence')
        self.assertTrue(self.endpoint.speech_detected)
        self.vad.pop.assert_called_once()

    def test_brief_pause_does_not_end_and_continuous_speech_is_bounded(self):
        self.vad.is_speech_detected.return_value = True
        self.endpoint.feed(PCM)
        self.vad.is_speech_detected.return_value = False
        for _ in range(6): self.assertFalse(self.endpoint.feed(PCM))
        self.vad.is_speech_detected.return_value = True
        for _ in range(92): self.assertFalse(self.endpoint.feed(PCM))
        self.assertTrue(self.endpoint.feed(PCM))
        self.assertEqual(self.endpoint.reason, 'max_duration')

    def test_dc_removed_only_from_detector_input(self):
        pcm = array.array('h', [1400] * 1600).tobytes()
        self.endpoint.feed(pcm)
        self.assertEqual(set(self.vad.accept_waveform.call_args.args[0]), {0})
        self.endpoint.feed(PCM)
        self.assertAlmostEqual(self.vad.accept_waveform.call_args.args[0][0], 1000/32768)

    def test_empty_input_not_counted(self):
        self.assertFalse(self.endpoint.feed(b''))
        self.assertEqual(self.endpoint.seconds, 0)
        self.vad.accept_waveform.assert_not_called()

    def test_native_failure_is_not_silent_energy_fallback(self):
        self.vad.accept_waveform.side_effect = RuntimeError('native failure')
        with self.assertRaises(RuntimeError): self.endpoint.feed(PCM)
        self.assertFalse(self.endpoint.speech_detected)

    def test_exclusive_lease_released_and_reset_for_next_round(self):
        with self.assertRaises(RuntimeError): SileroEndpoint(engine=(NP, self.vad))
        self.endpoint.close()
        self.endpoint.close()
        endpoint = SileroEndpoint(engine=(NP, self.vad))
        try: self.assertFalse(endpoint.speech_detected)
        finally: endpoint.close()
        self.assertEqual(self.vad.reset.call_count, 2)

    def test_reset_failure_releases_lease(self):
        self.endpoint.close()
        self.vad.reset.side_effect = RuntimeError()
        with self.assertRaises(RuntimeError): SileroEndpoint(engine=(NP, self.vad))
        self.vad.reset.side_effect = None
        endpoint = SileroEndpoint(engine=(NP, self.vad))
        endpoint.close()

    def test_endpoint_failure_never_opens_mic_or_creates_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('audio.capture.tempfile.tempdir', directory):
                capture = Mock()
                with self.assertRaises(RuntimeError):
                    AutomaticRecording(capture_factory=capture, endpoint_factory=Mock(side_effect=RuntimeError()))
                capture.assert_not_called()
            self.assertEqual(os.listdir(directory), [])

    def test_capture_failure_releases_endpoint_and_temp_file(self):
        endpoint = Mock()
        with tempfile.TemporaryDirectory() as directory:
            with patch('audio.capture.tempfile.tempdir', directory):
                with self.assertRaises(OSError):
                    AutomaticRecording(capture_factory=Mock(side_effect=OSError()), endpoint_factory=lambda **_: endpoint)
            self.assertEqual(os.listdir(directory), [])
        endpoint.close.assert_called_once()


if __name__ == '__main__': unittest.main()
