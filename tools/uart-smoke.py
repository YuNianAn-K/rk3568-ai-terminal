import os
import select
import sys
import termios
import time


def configure(fd):
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


def exchange(fd, command, timeout=2.0):
    payload = command.encode("ascii") + b"\r\n"
    os.write(fd, payload)
    deadline = time.monotonic() + timeout
    reply = bytearray()
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if not ready:
            continue
        try:
            chunk = os.read(fd, 256)
        except BlockingIOError:
            continue
        if chunk:
            reply.extend(chunk)
            if b"\n" in reply:
                break
    return payload, bytes(reply)


fd = os.open("/dev/ttyS9", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
try:
    configure(fd)
    time.sleep(0.1)
    ping_tx, ping_rx = exchange(fd, "PING")
    led_tx, led_rx = exchange(fd, "LED?")
finally:
    os.close(fd)

print(f"PING_TX={ping_tx!r}")
print(f"PING_RX={ping_rx!r}")
print(f"LED_TX={led_tx!r}")
print(f"LED_RX={led_rx!r}")

ok = ping_rx == b"PONG\r\n" and led_rx in (b"LED=ON\r\n", b"LED=OFF\r\n")
print(f"RESULT={'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 2)
