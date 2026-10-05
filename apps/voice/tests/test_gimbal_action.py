"""Regression checks for bounded gimbal actions and UART failures."""

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import gimbal_action
from tools.pc13_led import LedControlError


class GimbalActionTests(unittest.TestCase):
    def setUp(self):
        self.gimbal = gimbal_action.GimbalAction()
        transaction = mock.patch.object(
            self.gimbal, "_transaction", side_effect=lambda operation: operation(12))
        exchange = mock.patch.object(self.gimbal, "_exchange")
        sleep = mock.patch.object(gimbal_action.time, "sleep")
        self.transaction = transaction.start()
        self.exchange = exchange.start()
        self.sleep = sleep.start()
        self.addCleanup(transaction.stop)
        self.addCleanup(exchange.stop)
        self.addCleanup(sleep.stop)

    def test_rejects_raw_uart_and_unknown_actions_before_opening_serial(self):
        for action in ("PAN +100", "pan-left; LED ON", b"PAN CENTER", "45"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.gimbal.execute(action)
        self.transaction.assert_not_called()

    def test_pan_left_centers_steps_and_stops_both_axes(self):
        self.exchange.side_effect = [
            b"PAN_PWM=OFF\r\n", b"PAN_PWM=OFF\r\n", b"TILT_PWM=OFF\r\n",
            b"PAN_PWM=1500US\r\n", b"PAN_PWM=1550US\r\n",
            b"PAN_PWM=OFF\r\n", b"PAN_PWM=OFF\r\n", b"TILT_PWM=OFF\r\n",
        ]
        self.assertEqual(self.gimbal.execute("pan-left"),
                         {"action": "pan-left", "pan": "OFF", "tilt": "OFF"})
        self.assertEqual([call.args[1] for call in self.exchange.call_args_list], [
            b"PAN STOP", b"PAN?", b"TILT?", b"PAN CENTER", b"PAN +50",
            b"PAN STOP", b"PAN?", b"TILT?",
        ])
        self.sleep.assert_has_calls([mock.call(0.25), mock.call(0.6)])

    def test_bad_step_reply_still_sends_stop(self):
        self.exchange.side_effect = [
            b"PAN_PWM=OFF\r\n", b"PAN_PWM=OFF\r\n", b"TILT_PWM=OFF\r\n",
            b"TILT_PWM=1500US\r\n", b"ERR TILT_CENTER_FIRST\r\n",
            b"PAN_PWM=OFF\r\n", b"PAN_PWM=OFF\r\n", b"TILT_PWM=OFF\r\n",
        ]
        with self.assertRaises(LedControlError) as caught:
            self.gimbal.execute("tilt-up")
        self.assertEqual(caught.exception.kind, "gimbal_reply_mismatch")
        self.assertEqual(self.exchange.call_args_list[-3:], [
            mock.call(12, b"PAN STOP"), mock.call(12, b"PAN?"),
            mock.call(12, b"TILT?"),
        ])

    def test_stop_requires_both_axes_off(self):
        self.exchange.side_effect = [b"PAN_PWM=OFF\r\n",
                                     b"PAN_PWM=OFF\r\n", b"TILT_PWM=1500US\r\n"]
        with self.assertRaises(LedControlError) as caught:
            self.gimbal.execute("stop")
        self.assertEqual(caught.exception.kind, "gimbal_stop_mismatch")

    def test_status_rejects_unrecognized_reply(self):
        self.exchange.side_effect = [b"PAN_PWM=2550US\r\n", b"TILT_PWM=OFF\r\n"]
        with self.assertRaises(LedControlError) as caught:
            self.gimbal.execute("status")
        self.assertEqual(caught.exception.kind, "gimbal_bad_status")

    def test_status_accepts_new_firmware_diagnostic_positions(self):
        self.exchange.side_effect = [b"PAN_PWM=2500US\r\n",
                                     b"TILT_PWM=OFF\r\n"]
        self.assertEqual(self.gimbal.execute("status"),
                         {"pan": "2500US", "tilt": "OFF"})
        self.exchange.side_effect = [b"PAN_PWM=OFF\r\n",
                                     b"TILT_PWM=1100US\r\n"]
        self.assertEqual(self.gimbal.execute("status"),
                         {"pan": "OFF", "tilt": "1100US"})
        self.exchange.side_effect = [b"PAN_PWM=0950US\r\n",
                                     b"TILT_PWM=0750US\r\n"]
        self.assertEqual(self.gimbal.execute("status"),
                         {"pan": "0950US", "tilt": "0750US"})


if __name__ == "__main__":
    unittest.main()
