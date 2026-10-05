"""Exact voice routing and bounded, correlated application control replies."""
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from tools import person_tracking as tracking


class Connection:
    def __init__(self, override=None):
        self.override = override or {}
        self.request = None
        self.first = True
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def settimeout(self, seconds): pass
    def connect(self, path): self.path = path
    def sendall(self, data): self.request = json.loads(data)
    def recv(self, length):
        if self.first:
            self.first = False
            return b'{'
        result = dict(version=1, request_id=self.request["request_id"], accepted=True,
                      code="active" if self.request["command"] == "START_TRACKING" else "off")
        result.update(self.override)
        return (json.dumps(result)[1:] + '\n').encode()


class TrackingTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(tracking.socket, "AF_UNIX", 1, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_only_complete_positive_commands_match(self):
        self.assertEqual(tracking.parse_tracking_action(" 开始 跟踪 人物。"), "START_TRACKING")
        self.assertEqual(tracking.parse_tracking_action("停止跟踪！"), "STOP_TRACKING")
        for text in ("不要开始跟踪人物", "开始跟踪人物吗", "开始跟踪人物?",
                     "请开始跟踪人物", "开始跟踪人物然后停止跟踪", "开始跟踪", "跟随我", ""):
            self.assertIsNone(tracking.parse_tracking_action(text), text)

    def test_correlated_fragmented_reply_and_allowlisted_request(self):
        for command in ("START_TRACKING", "STOP_TRACKING"):
            conn = Connection()
            with mock.patch.object(tracking.socket, "socket", return_value=conn):
                reply = tracking.PersonTracking().execute(command)
            self.assertTrue(reply["accepted"])
            self.assertEqual(conn.request["target"], "PERSON")
            self.assertEqual(conn.request["command"], command)
            self.assertEqual(len(conn.request["request_id"]), 32)
            self.assertGreater(conn.request["issued_ms"], 0)
        with self.assertRaises(ValueError): tracking.PersonTracking().execute("PAN +100")

    def test_wrong_id_unverified_or_oversized_reply_cannot_claim_success(self):
        for override in (dict(request_id="bad"), dict(accepted=1), dict(code="pending"),
                         dict(version=2), dict(code="active\nunsafe"), dict(accepted=False)):
            with mock.patch.object(tracking.socket, "socket", return_value=Connection(override)):
                with self.assertRaises(tracking.TrackingControlError):
                    tracking.PersonTracking().execute("START_TRACKING")
        conn = Connection()
        conn.recv = lambda length: b"x" * 4097
        with mock.patch.object(tracking.socket, "socket", return_value=conn):
            with self.assertRaises(tracking.TrackingControlError):
                tracking.PersonTracking().execute("START_TRACKING")

    def test_unavailable_and_timeout_fail_without_retry(self):
        for failure, kind in ((OSError(), "unavailable"), (socket.timeout(), "timeout")):
            conn = Connection()
            conn.connect = mock.Mock(side_effect=failure)
            with mock.patch.object(tracking.socket, "socket", return_value=conn):
                with self.assertRaises(tracking.TrackingControlError) as caught:
                    tracking.PersonTracking().execute("STOP_TRACKING")
            self.assertEqual(caught.exception.kind, kind)
            conn.connect.assert_called_once()

    def test_voice_routes_to_application_without_llm_or_led_uart(self):
        terminal = object.__new__(main.AIVoiceTerminal)
        terminal.event_callback = mock.Mock()
        terminal._speak_blocking = mock.Mock()
        terminal.llm = mock.Mock()
        with mock.patch.object(main, "PersonTracking") as control, mock.patch.object(main, "PC13Led") as led:
            control.return_value.execute.return_value = dict(accepted=True, code="active")
            terminal.process_input("开始跟踪人物")
            control.return_value.execute.assert_called_once_with("START_TRACKING")
            terminal._speak_blocking.assert_called_once_with("已开始跟踪选中的人物。", remember=False)
            led.assert_not_called()
            terminal.llm.chat_stream.assert_not_called()
        terminal._speak_blocking.reset_mock()
        with mock.patch.object(main, "PersonTracking") as control:
            terminal.process_input("不要开始跟踪人物")
            control.assert_not_called()
        terminal._speak_blocking.assert_called_once_with(
            "未操作云台。请明确说开始跟踪人物或停止跟踪。", remember=False)

    def test_offline_tracking_never_waits_for_cloud_speech(self):
        terminal = object.__new__(main.AIVoiceTerminal)
        terminal.event_callback = mock.Mock()
        terminal.offline_asr = mock.Mock()
        terminal.offline_asr.recognize.return_value = "停止跟踪"
        terminal._speak_blocking = mock.Mock()
        with mock.patch.object(main, "PersonTracking") as control:
            control.return_value.execute.return_value = dict(accepted=True, code="off")
            terminal._process_offline_command("unused.wav", "network_down")
            control.return_value.execute.assert_called_once_with("STOP_TRACKING")
        terminal._speak_blocking.assert_not_called()
        self.assertTrue(any(call.args[0] == "answer" and call.args[1]["text"] == "云台已停止跟踪。"
                            for call in terminal.event_callback.call_args_list))


if __name__ == "__main__": unittest.main()
