"""Offline pipeline recovery and ALSA lifecycle regression tests."""
import io
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from audio.play import AudioPlayer
from mimo_http import MiMoError


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.terminal = object.__new__(main.AIVoiceTerminal)
        self.terminal.llm = mock.Mock()
        self.terminal.history = []
        self.terminal.max_response_chars = 500
        self.terminal.event_callback = mock.Mock()
        self.terminal._play_speech = mock.Mock(return_value=True)
        patcher = mock.patch.object(main, "VOICE_LOCAL_RESPONSES", False)
        patcher.start()
        self.addCleanup(patcher.stop)
        output = mock.patch("sys.stdout", io.StringIO())
        output.start()
        self.addCleanup(output.stop)

    def test_sentence_boundaries_survive_token_splitting(self):
        accum = main.SentenceAccumulator()
        self.assertEqual(accum.feed("第一"), [])
        self.assertEqual(accum.feed("句。第二句！剩"), ["第一句。", "第二句！"])
        self.assertEqual(accum.flush(), "剩")

    def test_partial_llm_failure_never_replays_whole_answer(self):
        def interrupted():
            yield "已经回答。"
            raise MiMoError("network")
        self.terminal.llm.chat_stream.return_value = interrupted()
        self.terminal.process_input("介绍一下你自己")
        self.terminal.llm.chat.assert_not_called()
        self.assertTrue(any(call.args[0] == "error" for call in
                            self.terminal.event_callback.call_args_list))

    def test_synchronous_stream_failure_does_not_leak_consumer(self):
        before = set(threading.enumerate())
        self.terminal.llm.chat_stream.side_effect = MiMoError("network")
        self.terminal.llm.chat.return_value = "恢复成功。"
        self.terminal.process_input("介绍一下你自己")
        self.terminal.llm.chat.assert_called_once()
        self.assertEqual(set(threading.enumerate()), before)

    def test_playback_failure_keeps_text_and_next_round_works(self):
        self.terminal.llm.chat_stream.side_effect = [iter(["第一轮。"]), iter(["第二轮。"])]
        self.terminal._play_speech.side_effect = [False, True]
        self.terminal.process_input("第一次测试")
        self.terminal.process_input("第二次测试")
        self.assertEqual(len(self.terminal.history), 4)
        self.assertEqual(self.terminal.history[-1]["content"], "第二轮。")
        self.terminal.llm.chat.assert_not_called()

    def test_spoken_output_is_bounded(self):
        self.terminal.llm.chat_stream.return_value = iter(["测试。" * 240])
        self.terminal.process_input("介绍一下你自己")
        spoken = "".join(call.args[0] for call in self.terminal._play_speech.call_args_list)
        self.assertLessEqual(len(spoken), 500)
        self.assertEqual(len(self.terminal.history[-1]["content"]), 500)


class PCMPlayerTests(unittest.TestCase):
    def patched(self, *args, **kwargs):
        patcher = mock.patch(*args, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def setUp(self):
        self.player = object.__new__(AudioPlayer)
        self.player.backend = "aplay"
        self.proc = mock.Mock()
        self.proc.poll.return_value = None
        self.proc.returncode = 0
        self.proc.stdin.fileno.return_value = 42
        self.proc.stdin.closed = False
        self.popen = self.patched("audio.play.subprocess.Popen", return_value=self.proc)
        self.patched("audio.play.os.set_blocking")
        self.patched("audio.play.select.select", return_value=([], [42], []))
        self.write = self.patched("audio.play.os.write", side_effect=lambda fd, data: len(data))

    def test_success_uses_fixed_16k_and_closes_source(self):
        closed = []
        def chunks():
            try:
                yield b"\0\0" * 100
                yield b"\1\0" * 100
            finally:
                closed.append(True)
        started = mock.Mock()
        self.assertTrue(self.player.play_pcm_stream(chunks(), started))
        command = self.popen.call_args.args[0]
        self.assertEqual(command, ["aplay", "-D", "plughw:0,0", "-t", "raw",
                                   "-f", "S16_LE", "-r", "16000", "-c", "1"])
        started.assert_called_once()
        self.assertEqual(closed, [True])
        self.proc.stdin.close.assert_called()

    def test_broken_pipe_kills_and_reaps_child(self):
        self.write.side_effect = BrokenPipeError()
        self.assertFalse(self.player.play_pcm_stream(iter([b"\0\0"])))
        self.proc.kill.assert_called_once()
        self.proc.wait.assert_called_once()

    def test_drain_timeout_kills_and_reaps_child(self):
        self.proc.wait.side_effect = [subprocess.TimeoutExpired("aplay", 10), 0]
        self.assertFalse(self.player.play_pcm_stream(iter([b"\0\0"])))
        self.proc.kill.assert_called_once()
        self.assertEqual(self.proc.wait.call_count, 2)

    def test_empty_stream_never_starts_aplay(self):
        self.assertFalse(self.player.play_pcm_stream(iter([])))
        self.popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
