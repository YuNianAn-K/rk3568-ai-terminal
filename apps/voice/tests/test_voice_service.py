#!/usr/bin/env python3
"""Offline tests for the Qt voice service state machine."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_service import VoiceService


class FakeRecorder:
    has_mic = True


class FakeTerminal:
    def __init__(self, event_callback):
        self.event_callback = event_callback
        self.recorder = FakeRecorder()
        self._recording = False
        self._record_proc = None
        self._audio_file = None
        self._retry_count = 0

    def _start_recording(self):
        self._recording = True
        self.event_callback("state", {
            "state": "recording",
            "message": "正在聆听",
        })
        self.event_callback("timing", {
            "stage": "record_start",
            "monotonic_ms": int(time.monotonic() * 1000),
        })
        return True

    def _finish_recording(self, automatic=False):
        del automatic
        self._recording = False
        self.event_callback("transcript", {"text": "测试问题"})
        self.event_callback("state", {
            "state": "thinking",
            "message": "正在生成回答",
        })
        self.event_callback("answer", {"text": "测试回答"})

    def _discard_active_recording(self):
        self._recording = False


class VoiceServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = VoiceService(terminal_factory=FakeTerminal)
        self.assertTrue(self.service.initialize_terminal())

    def test_start_stop_round_returns_to_idle(self):
        start = self.service.handle_command({"command": "start"})
        self.assertTrue(start["accepted"])
        self.assertEqual(self.service.state, "recording")

        duplicate = self.service.handle_command({"command": "start"})
        self.assertFalse(duplicate["accepted"])
        self.assertEqual(duplicate["code"], "busy")

        stop = self.service.handle_command({"command": "stop"})
        self.assertTrue(stop["accepted"])
        deadline = time.monotonic() + 2
        while self.service.state != "idle" and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(self.service.state, "idle")
        self.assertEqual(self.service.transcript, "测试问题")
        self.assertEqual(self.service.answer, "测试回答")
        self.assertIn("button_trigger", self.service.timings)
        self.assertIn("record_start", self.service.timings)
        self.assertIn("record_stop_requested", self.service.timings)
        self.assertIn("round_end", self.service.timings)

    def test_snapshot_contains_safe_diagnostics(self):
        snapshot = self.service.snapshot()
        self.assertIn("diagnostics", snapshot)
        self.assertIn("memory_available_mb", snapshot["diagnostics"])
        self.assertIn("service_rss_mb", snapshot["diagnostics"])
        self.assertIn("network", snapshot["diagnostics"])

    def test_cancel_recording_allows_next_round(self):
        self.service.handle_command({"command": "start"})
        cancel = self.service.handle_command({"command": "cancel"})
        self.assertTrue(cancel["accepted"])
        self.assertEqual(self.service.state, "idle")
        self.assertTrue(
            self.service.handle_command({"command": "start"})["accepted"]
        )

    def test_active_worker_blocks_immediate_retry(self):
        self.service.state = "error"
        self.service.round_worker_active = True
        retry = self.service.handle_command({"command": "start"})
        self.assertFalse(retry["accepted"])
        self.assertEqual(retry["code"], "busy")


if __name__ == "__main__":
    unittest.main()
