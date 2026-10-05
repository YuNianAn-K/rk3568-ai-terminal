"""Fail-closed offline recognition and cloud/offline routing tests."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from asr.offline_commands import OfflineCommandASR


def wav_file():
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as file:
        path = file.name
    with wave.open(path, "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        output.writeframes(b"\x20\x03" * 8000)
    return path


class FakeRecognizer:
    result = '{"text":"打开 指示灯","result":[{"conf":0.95},{"conf":0.92}]}'
    grammar = ""

    def __init__(self, model, rate, grammar):
        self.rate = rate
        FakeRecognizer.grammar = grammar

    def SetWords(self, enabled):
        self.words = enabled

    def AcceptWaveform(self, chunk):
        return False

    def FinalResult(self):
        return self.result


class LocalASRTests(unittest.TestCase):
    def setUp(self):
        self.path = wav_file()
        self.addCleanup(lambda: Path(self.path).unlink(missing_ok=True))
        self.adapter = OfflineCommandASR()
        self.adapter.model = object()
        self.adapter.recognizer_class = FakeRecognizer

    def test_accepts_only_high_confidence_complete_result(self):
        self.assertEqual(self.adapter.recognize(self.path), "打开指示灯")
        self.assertIn('"关闭 指示灯"', FakeRecognizer.grammar)
        self.assertIn('"[unk]"', FakeRecognizer.grammar)

    def test_low_confidence_is_rejected(self):
        with mock.patch.object(FakeRecognizer, "result",
                               '{"text":"打开 指示灯","result":[{"conf":0.96},{"conf":0.55}]}'):
            self.assertEqual(self.adapter.recognize(self.path), "")

    def test_empty_or_untrusted_word_list_is_rejected(self):
        with mock.patch.object(FakeRecognizer, "result", '{"text":"打开指示灯"}'):
            self.assertEqual(self.adapter.recognize(self.path), "")

    def test_wrong_sample_rate_is_rejected(self):
        with wave.open(self.path, "wb") as output:
            output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            output.writeframes(b"\x20\x03" * 8000)
        with self.assertRaises(Exception):
            self.adapter.recognize(self.path)


class OfflineRoutingTests(unittest.TestCase):
    def setUp(self):
        self.terminal = object.__new__(main.AIVoiceTerminal)
        self.terminal.event_callback = mock.Mock()
        self.terminal.asr = mock.Mock()
        self.terminal.offline_asr = mock.Mock()
        self.terminal.noise_rms = 150
        self.terminal.high_pass = False
        self.terminal._audio_rms = mock.Mock(return_value=1000)
        self.terminal._cloud_retry_at = 0.0
        self.terminal._last_route_up = True
        self.terminal.process_input = mock.Mock()

    def run_round(self, route):
        path = wav_file()
        with mock.patch.object(self.terminal, "_default_route_available", return_value=route):
            self.terminal._process_audio(path)
        self.assertFalse(Path(path).exists())

    def test_disconnected_route_skips_cloud_and_controls_only_exact_intent(self):
        self.terminal.offline_asr.recognize.return_value = "打开指示灯"
        with mock.patch.object(main, "PC13Led") as factory:
            self.run_round(False)
        self.terminal.asr.recognize_with_status.assert_not_called()
        factory.return_value.set_led.assert_called_once_with(True)
        self.assertTrue(any(c.args[0] == "answer" and
                            c.args[1]["text"] == "指示灯已打开。"
                            for c in self.terminal.event_callback.call_args_list))

    def test_noisy_startup_cannot_lock_out_later_online_voice(self):
        self.terminal.noise_rms = 1414
        self.terminal._audio_rms.return_value = 1500
        self.terminal.asr.recognize_with_status.return_value = ("你好", None)
        self.run_round(True)
        self.terminal.asr.recognize_with_status.assert_called_once()
        self.terminal.process_input.assert_called_once_with("你好")

    def test_noisy_startup_cannot_lock_out_offline_command_but_denial_stays_safe(self):
        self.terminal.noise_rms = 1414
        self.terminal._audio_rms.return_value = 1500
        self.terminal.offline_asr.recognize.return_value = "不要打开指示灯"
        with mock.patch.object(main, "PC13Led") as factory:
            self.run_round(False)
        self.terminal.offline_asr.recognize.assert_called_once()
        factory.assert_not_called()

    def test_barely_audible_audio_still_rejected_before_asr(self):
        self.terminal.noise_rms = 1414
        self.terminal._audio_rms.return_value = 100
        self.run_round(True)
        self.terminal.asr.recognize_with_status.assert_not_called()
        self.terminal.offline_asr.recognize.assert_not_called()

    def test_negative_and_conflicting_text_never_reach_uart(self):
        for phrase in ("不要打开指示灯", "打开指示灯关闭指示灯", ""):
            self.terminal.offline_asr.recognize.return_value = phrase
            with mock.patch.object(main, "PC13Led") as factory:
                self.run_round(False)
                factory.assert_not_called()

    def test_cloud_failure_falls_back_then_cooldown_skips_retry(self):
        self.terminal.asr.recognize_with_status.return_value = ("", "timeout")
        self.terminal.offline_asr.recognize.return_value = "查询指示灯状态"
        with mock.patch.object(main, "PC13Led") as factory:
            factory.return_value.get_led.return_value = False
            self.run_round(True)
            self.run_round(True)
            self.assertEqual(factory.return_value.get_led.call_count, 2)
        self.terminal.asr.recognize_with_status.assert_called_once()

    def test_reconnect_resumes_cloud_on_next_round(self):
        self.terminal.offline_asr.recognize.return_value = ""
        self.run_round(False)
        self.terminal.asr.recognize_with_status.return_value = ("你好", None)
        self.run_round(True)
        self.terminal.process_input.assert_called_once_with("你好")
        self.terminal.offline_asr.recognize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
