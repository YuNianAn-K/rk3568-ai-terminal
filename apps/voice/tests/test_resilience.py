#!/usr/bin/env python3
"""Offline regression tests for voice pipeline failure handling."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio.play import AudioPlayer
from llm.glm import GLMLLM
from llm.mimo import MiMoLLM


class FakeStreamResponse:
    def raise_for_status(self):
        return None

    def iter_lines(self):
        chunks = [
            {"choices": [{"delta": {"role": "assistant", "content": None}}]},
            {"choices": [{"delta": {"content": "你"}}]},
            {"choices": [{"delta": {"content": None}}]},
            {"choices": [{"delta": {"content": "好"}}]},
        ]
        for chunk in chunks:
            yield ("data: " + json.dumps(chunk, ensure_ascii=False)).encode("utf-8")
        yield b"data: [DONE]"


class VoiceResilienceTests(unittest.TestCase):
    def test_stream_adapters_filter_none_chunks(self):
        for adapter_class in (MiMoLLM, GLMLLM):
            with self.subTest(adapter=adapter_class.__name__):
                adapter = adapter_class()
                if adapter_class is MiMoLLM:
                    events = [
                        {"choices": [{"delta": {"content": None}}]},
                        {"choices": [{"delta": {"content": "你"}}]},
                        {"choices": [{"delta": {"content": "好"}}]},
                        {"_done": True},
                    ]
                    with mock.patch.object(adapter.http, "responses", side_effect=lambda *a, **k: (e for e in events)):
                        self.assertEqual(list(adapter.chat_stream("test", [])), ["你", "好"])
                    adapter.close()
                    continue
                with mock.patch(
                    f"{adapter_class.__module__}.requests.post",
                    return_value=FakeStreamResponse(),
                ):
                    self.assertEqual(list(adapter.chat_stream("test", [])), ["你", "好"])

    def test_player_timeout_returns_false(self):
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            player = object.__new__(AudioPlayer)
            player.backend = "aplay"
            with mock.patch.object(AudioPlayer, "_resample_16k", return_value=path), \
                    mock.patch(
                        "audio.play.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("aplay", 5),
                    ):
                self.assertFalse(player.play(path))
        finally:
            if os.path.exists(path):
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
