"""Allowlisted, short-lived gimbal actions over the shared UART9 transport."""

import argparse
import json
import time

from tools.pc13_led import LedControlError, PC13Led


# These are camera directions observed with the installed camera, not angles.
MOVES = {
    "pan-left": (b"PAN CENTER", b"PAN_PWM=1500US\r\n",
                 b"PAN +50", b"PAN_PWM=1550US\r\n"),
    "pan-right": (b"PAN CENTER", b"PAN_PWM=1500US\r\n",
                  b"PAN -50", b"PAN_PWM=1450US\r\n"),
    "tilt-up": (b"TILT CENTER", b"TILT_PWM=1500US\r\n",
                b"TILT -50", b"TILT_PWM=1450US\r\n"),
    "tilt-down": (b"TILT CENTER", b"TILT_PWM=1500US\r\n",
                  b"TILT +50", b"TILT_PWM=1550US\r\n"),
    "pan-center": (b"PAN CENTER", b"PAN_PWM=1500US\r\n", None, None),
    "tilt-center": (b"TILT CENTER", b"TILT_PWM=1500US\r\n", None, None),
}
ACTIONS = ("status", "stop", *MOVES)
SETTLE_SECONDS = 0.25
HOLD_SECONDS = 0.6


class GimbalAction(PC13Led):
    """Use PC13's serial transaction and lock; never accept raw UART bytes."""

    def execute(self, action):
        if action not in ACTIONS:
            raise ValueError("unsupported gimbal action")
        return self._transaction(lambda fd: self._execute(fd, action))

    def _expect(self, fd, command, reply):
        if self._exchange(fd, command) != reply:
            raise LedControlError("gimbal_reply_mismatch")

    def _status(self, fd):
        pan = self._exchange(fd, b"PAN?")
        tilt = self._exchange(fd, b"TILT?")
        allowed_pan = {b"PAN_PWM=OFF\r\n"} | {
            f"PAN_PWM={pulse:04d}US\r\n".encode("ascii")
            for pulse in range(500, 2501, 50)
        }
        allowed_tilt = {b"TILT_PWM=OFF\r\n"} | {
            f"TILT_PWM={pulse:04d}US\r\n".encode("ascii")
            for pulse in range(750, 2251, 50)
        }
        if pan not in allowed_pan or tilt not in allowed_tilt:
            raise LedControlError("gimbal_bad_status")
        return {"pan": pan.decode("ascii").strip().split("=", 1)[1],
                "tilt": tilt.decode("ascii").strip().split("=", 1)[1]}

    def _stop_verified(self, fd):
        self._expect(fd, b"PAN STOP", b"PAN_PWM=OFF\r\n")
        state = self._status(fd)
        if state != {"pan": "OFF", "tilt": "OFF"}:
            raise LedControlError("gimbal_stop_mismatch")
        return state

    def _execute(self, fd, action):
        if action == "status":
            return self._status(fd)
        if action == "stop":
            return self._stop_verified(fd)

        # Start from a known idle state. Both axes are stopped by PAN STOP.
        self._stop_verified(fd)
        center, center_reply, step, step_reply = MOVES[action]
        try:
            self._expect(fd, center, center_reply)
            if step is not None:
                time.sleep(SETTLE_SECONDS)
                self._expect(fd, step, step_reply)
            time.sleep(HOLD_SECONDS)
        finally:
            # Firmware also cuts PWM after two seconds if UART is lost.
            self._stop_verified(fd)
        return {"action": action, "pan": "OFF", "tilt": "OFF"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Short, verified gimbal action")
    parser.add_argument("action", choices=ACTIONS)
    args = parser.parse_args(argv)
    try:
        result = GimbalAction().execute(args.action)
    except LedControlError as error:
        parser.exit(1, f"gimbal action failed: {error.kind}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
