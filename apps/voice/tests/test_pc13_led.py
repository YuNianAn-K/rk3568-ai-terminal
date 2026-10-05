"""PC13 intent, UART acknowledgement and voice routing regression tests."""

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from tools import pc13_led


class IntentTests(unittest.TestCase):
    def test_three_action_whitelist_rejects_ambiguous_or_negative_text(self):
        self.assertEqual(pc13_led.parse_led_action("查询指示灯状态。"), "query")
        self.assertEqual(pc13_led.parse_led_action("打开指示灯"), "on")
        self.assertEqual(pc13_led.parse_led_action("关闭指示灯"), "off")
        for text in ("不要打开指示灯", "打开指示灯然后关闭指示灯",
                     "请打开指示灯", "指示灯状态", "打开灯", "你好",
                     "查询指示灯状态吗"):
            with self.subTest(text=text):
                self.assertIsNone(pc13_led.parse_led_action(text))

    def test_only_explicit_complete_commands_match(self):
        for text in ("打开指示灯", " 打开 指示灯。", "打开指示灯！"):
            self.assertIs(pc13_led.parse_led_intent(text), True)
        for text in ("关闭指示灯", "关闭 指示灯。"):
            self.assertIs(pc13_led.parse_led_intent(text), False)
        for text in (
            "不要打开指示灯", "别关闭指示灯", "打开指示灯吗", "我想打开指示灯",
            "打开灯", "打开指示灯然后关闭", "打开指示灯和风扇", "今天天气如何",
            "", "打开指示灯?",  # A question must not control hardware.
        ):
            with self.subTest(text=text):
                self.assertIsNone(pc13_led.parse_led_intent(text))

    def test_incomplete_device_phrases_require_clarification(self):
        for text in ("关闭。", "打开", "关灯", "开指示灯", "不要打开指示灯",
                     "打开指示灯吗", "请关闭指示灯", "查询指示灯",
                     "查询指示灯状态吗"):
            self.assertTrue(pc13_led.needs_led_clarification(text))
        for text in ("你好", "关闭吃。", "指示灯是什么"):
            self.assertFalse(pc13_led.needs_led_clarification(text))


class SerialTests(unittest.TestCase):
    def setUp(self):
        self.led = pc13_led.PC13Led(timeout=0.1)
        self.patchers = [
            mock.patch.object(pc13_led, "termios", mock.Mock()),
            mock.patch.object(pc13_led, "fcntl", mock.Mock(LOCK_EX=2, LOCK_NB=4)),
            mock.patch.object(pc13_led.os, "open", side_effect=[11, 12]),
            mock.patch.object(pc13_led.os, "close"),
            mock.patch.object(self.led, "_configure"),
            mock.patch.object(self.led, "_exchange"),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_on_requires_ok_then_matching_readback(self):
        self.led._exchange.side_effect = [b"OK\r\n", b"LED=ON\r\n"]
        self.assertTrue(self.led.set_led(True))
        self.assertEqual(self.led._exchange.call_args_list, [
            mock.call(12, b"LED ON"), mock.call(12, b"LED?"),
        ])

    def test_off_requires_ok_then_matching_readback(self):
        self.led._exchange.side_effect = [b"OK\r\n", b"LED=OFF\r\n"]
        self.assertTrue(self.led.set_led(False))
        self.assertEqual(self.led._exchange.call_args_list, [
            mock.call(12, b"LED OFF"), mock.call(12, b"LED?"),
        ])

    def test_bad_ack_never_queries_or_reports_success(self):
        self.led._exchange.return_value = b"ERR\r\n"
        with self.assertRaises(pc13_led.LedControlError) as caught:
            self.led.set_led(True)
        self.assertEqual(caught.exception.kind, "bad_ack")
        self.led._exchange.assert_called_once_with(12, b"LED ON")

    def test_state_mismatch_rejects_acknowledged_action(self):
        self.led._exchange.side_effect = [b"OK\r\n", b"LED=OFF\r\n"]
        with self.assertRaises(pc13_led.LedControlError) as caught:
            self.led.set_led(True)
        self.assertEqual(caught.exception.kind, "state_mismatch")

    def test_timeout_is_failure(self):
        self.led._exchange.side_effect = pc13_led.LedControlError("timeout")
        with self.assertRaises(pc13_led.LedControlError) as caught:
            self.led.set_led(True)
        self.assertEqual(caught.exception.kind, "timeout")

    def test_missing_serial_is_failure(self):
        pc13_led.os.open.side_effect = [11, FileNotFoundError()]
        with self.assertRaises(pc13_led.LedControlError) as caught:
            self.led.set_led(True)
        self.assertEqual(caught.exception.kind, "serial_io")

    def test_query_requires_exact_state_reply(self):
        self.led._exchange.return_value = b"LED=ON\r\n"
        self.assertTrue(self.led.get_led())
        self.led._exchange.assert_called_once_with(12, b"LED?")

    def test_query_bad_reply_and_timeout_fail(self):
        for reply in (b"OK\r\n", b"LED=ON\n"):
            pc13_led.os.open.side_effect = [11, 12]
            self.led._exchange.return_value = reply
            with self.assertRaises(pc13_led.LedControlError):
                self.led.get_led()
        pc13_led.os.open.side_effect = [11, 12]
        self.led._exchange.side_effect = pc13_led.LedControlError("timeout")
        with self.assertRaises(pc13_led.LedControlError):
            self.led.get_led()


class VoiceRoutingTests(unittest.TestCase):
    def setUp(self):
        self.terminal = object.__new__(main.AIVoiceTerminal)
        self.terminal.event_callback = mock.Mock()
        self.terminal.history = []
        self.terminal._speak_blocking = mock.Mock()
        self.terminal.llm = mock.Mock()

    def test_control_bypasses_llm_only_after_verified_uart(self):
        with mock.patch.object(main, "PC13Led") as factory:
            self.terminal.process_input("打开指示灯")
            factory.return_value.set_led.assert_called_once_with(True)
        self.terminal._speak_blocking.assert_called_once_with(
            "指示灯已打开。", remember=False)
        self.terminal.llm.chat_stream.assert_not_called()

    def test_uart_failure_never_claims_success(self):
        with mock.patch.object(main, "PC13Led") as factory:
            factory.return_value.set_led.side_effect = pc13_led.LedControlError("timeout")
            self.terminal.process_input("关闭指示灯")
        self.terminal._speak_blocking.assert_called_once_with(
            "指示灯控制失败，请检查串口连接和设备状态。", remember=False)
        self.terminal.llm.chat_stream.assert_not_called()

    def test_incomplete_command_cannot_get_false_llm_success(self):
        with mock.patch.object(main, "PC13Led") as factory:
            self.terminal.process_input("关闭。")
        factory.assert_not_called()
        self.terminal.llm.chat_stream.assert_not_called()
        self.terminal._speak_blocking.assert_called_once_with(
            "没有操作指示灯。请明确说打开、关闭或查询指示灯状态。",
            remember=False)

    def test_online_query_uses_real_readback(self):
        with mock.patch.object(main, "PC13Led") as factory:
            factory.return_value.get_led.return_value = False
            self.terminal.process_input("查询指示灯状态")
        factory.return_value.get_led.assert_called_once()
        self.terminal._speak_blocking.assert_called_once_with(
            "指示灯当前已关闭。", remember=False)


if __name__ == "__main__":
    unittest.main()
