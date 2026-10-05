"""Conservative PC13 voice intent and verified UART text transport."""

import os
import re
import select
import threading
import time

try:
    import fcntl
    import termios
except ImportError:  # Windows runs parser and mocked transport tests.
    fcntl = termios = None


DEVICE = "/dev/ttyS9"
LOCK_PATH = "/var/run/ai-voice-pc13.lock"
_process_lock = threading.Lock()


def _normalize(text):
    return re.sub(r"[\s，。！,.!]+", "", str(text or ""))


def parse_led_intent(text):
    """Accept only complete, affirmative commands for the single LED."""
    normalized = _normalize(text)
    return {"打开指示灯": True, "关闭指示灯": False}.get(normalized)


def parse_led_action(text):
    """Return only one of the three complete PC13 commands."""
    return {"打开指示灯": "on", "关闭指示灯": "off",
            "查询指示灯状态": "query"}.get(_normalize(text))


def needs_led_clarification(text):
    """Keep incomplete device requests away from free-form chat replies."""
    normalized = _normalize(text)
    return (normalized in {"打开", "关闭", "开灯", "关灯", "打开灯", "关闭灯",
                           "开指示灯", "关指示灯", "查询指示灯", "查指示灯",
                           "指示灯状态"} or
            "打开指示灯" in normalized or "关闭指示灯" in normalized or
            "查询指示灯状态" in normalized)


class LedControlError(Exception):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


class PC13Led:
    """One transaction owns UART9 through write, ACK and state readback."""

    def __init__(self, device=DEVICE, lock_path=LOCK_PATH, timeout=2.0):
        self.device = device
        self.lock_path = lock_path
        self.timeout = timeout

    @staticmethod
    def _configure(fd):
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)

    def _exchange(self, fd, command):
        deadline = time.monotonic() + self.timeout
        payload = command + b"\r\n"
        while payload:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LedControlError("timeout")
            _, writable, _ = select.select([], [fd], [], remaining)
            if not writable:
                raise LedControlError("timeout")
            try:
                written = os.write(fd, payload)
                if written == 0:
                    raise LedControlError("serial_io")
                payload = payload[written:]
            except BlockingIOError:
                continue

        reply = bytearray()
        while time.monotonic() < deadline:
            readable, _, _ = select.select([fd], [], [], deadline - time.monotonic())
            if not readable:
                break
            try:
                chunk = os.read(fd, 64 - len(reply))
            except BlockingIOError:
                continue
            if chunk:
                reply.extend(chunk)
                if b"\n" in reply:
                    break
            if len(reply) == 64:
                raise LedControlError("bad_reply")
        if not reply or b"\n" not in reply:
            raise LedControlError("timeout")
        return bytes(reply)

    def set_led(self, on):
        if not isinstance(on, bool):
            raise ValueError("PC13 target must be boolean")
        return self._transaction(lambda fd: self._set_verified(fd, on))

    def _set_verified(self, fd, on):
        if self._exchange(fd, b"LED ON" if on else b"LED OFF") != b"OK\r\n":
            raise LedControlError("bad_ack")
        expected = b"LED=ON\r\n" if on else b"LED=OFF\r\n"
        if self._exchange(fd, b"LED?") != expected:
            raise LedControlError("state_mismatch")
        return True

    def get_led(self):
        """Read actual STM32 state; never infer it from a previous command."""
        return self._transaction(self._read_state)

    def _read_state(self, fd):
        reply = self._exchange(fd, b"LED?")
        if reply == b"LED=ON\r\n":
            return True
        if reply == b"LED=OFF\r\n":
            return False
        raise LedControlError("bad_reply")

    def _transaction(self, operation):
        if termios is None or fcntl is None:
            raise LedControlError("unsupported_platform")
        if not _process_lock.acquire(timeout=self.timeout):
            raise LedControlError("busy")
        lock_fd = fd = None
        try:
            lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LedControlError("busy") from None
            try:
                fd = os.open(
                    self.device,
                    os.O_RDWR | getattr(os, "O_NOCTTY", 0) |
                    getattr(os, "O_NONBLOCK", 0),
                )
                self._configure(fd)
                return operation(fd)
            except OSError as error:
                raise LedControlError("serial_io") from error
        except OSError as error:
            raise LedControlError("serial_io") from error
        finally:
            if fd is not None:
                os.close(fd)
            if lock_fd is not None:
                os.close(lock_fd)
            _process_lock.release()
