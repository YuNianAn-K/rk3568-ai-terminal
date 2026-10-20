"""Linux PTY: held manual input, retained pose, all edges, release and expiry.

Runs only a simulated UART with a 24 us / 20 ms ramp; never opens hardware.
"""
import json
import os
import pty
import select
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

master, slave = pty.openpty()
position = None
targets = [1500, 1500]
active = [False, False]
armed = False
running = True
commands = []
outputs = []
events = []
faults = []


def firmware():
    global position, armed
    buffer = b""
    ramp = time.monotonic()
    try:
        while running:
            now = time.monotonic()
            if position is not None and now - ramp >= .02:
                for axis in range(2):
                    if active[axis]:
                        gap = targets[axis] - position[axis]
                        position[axis] += max(-24, min(24, gap))
                ramp = now
            if not select.select([master], [], [], .005)[0]:
                continue
            buffer += os.read(master, 4096)
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                command = raw.decode().strip()
                commands.append((command, now))
                if command == "PING":
                    reply = "PONG"
                elif command == "PAN STOP":
                    active[:] = [False, False]
                    armed = False
                    reply = "PAN_PWM=OFF"
                elif command in ("PAN?", "TILT?"):
                    axis = int(command == "TILT?")
                    reply = command[:-1] + "_PWM=" + (
                        "%04dUS" % position[axis] if active[axis] else "OFF")
                elif command == "TRK?":
                    reply = "TRK=ARMED" if armed else "TRK=OFF"
                elif command == "TRK LIMITS?":
                    reply = "TRK_LIMITS=0500,2500,0500,2500"
                elif command == "TRK POS?":
                    reply = "TRK_POS=UNKNOWN" if position is None else (
                        "TRK_POS=%04d,%04d" % tuple(position))
                elif command == "TRK ARM":
                    assert position is not None
                    targets[:] = position
                    armed = True
                    reply = "TRK=ARMED"
                elif command == "TRK KEEP":
                    assert armed
                    reply = "TRK=ARMED"
                elif command in ("TRK P+", "TRK P-", "TRK T+", "TRK T-"):
                    assert armed
                    axis = int(command[4] == "T")
                    if not active[axis]:
                        outputs.append((axis, position[axis]))
                    candidate = max(500, min(2500, targets[axis] +
                                    (80 if command.endswith("+") else -80)))
                    assert abs(candidate - position[axis]) <= 240
                    targets[axis] = candidate
                    active[axis] = True
                    reply = "TRK_%s=%04dUS" % ("TILT" if axis else "PAN", candidate)
                else:
                    raise AssertionError("Unexpected firmware command: " + command)
                os.write(master, (reply + "\r\n").encode())
    except Exception as error:
        faults.append(repr(error))


def wait_for(check, seconds=2):
    deadline = time.monotonic() + seconds
    while not check():
        assert not faults, faults
        assert time.monotonic() < deadline, (commands[-20:], events[-5:])
        time.sleep(.01)


def send(line):
    process.stdin.write((line + "\n").encode())
    process.stdin.flush()


def manual(direction, stamp=None):
    send("MANUAL %s %d" % (direction, int(time.monotonic()*1000) if stamp is None else stamp))


def consume():
    for line in process.stdout:
        events.append(json.loads(line))


with tempfile.TemporaryDirectory() as temp:
    thread = threading.Thread(target=firmware, daemon=True)
    thread.start()
    source = str(Path(__file__).resolve().parents[1])
    code = ("import sys;sys.path.insert(0,%r);import gimbal_worker as w;"
            "w.DEVICE=%r;w.LOCK_PATH=%r;w.main()") % (source, os.ttyname(slave), temp + "/lock")
    process = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    try:
        wait_for(lambda: any(e.get("event") == "ready" for e in events))
        manual("TILT_UP")
        wait_for(lambda: any(e.get("state") == "uninitialized" for e in events))
        assert not outputs and not armed
        position = [1743, 1237]  # Deliberately off-grid: edges must still be reachable.
        for direction, axis, edge in (("PAN_LEFT", 0, 2500), ("PAN_RIGHT", 0, 500),
                                      ("TILT_UP", 1, 500), ("TILT_DOWN", 1, 2500)):
            before = tuple(position)
            count = len(outputs)
            deadline = time.monotonic() + 3.5
            while position[axis] != edge:
                assert time.monotonic() < deadline, (direction, position, targets, faults)
                manual(direction)
                time.sleep(.14)
            assert position[1-axis] == before[1-axis] and not active[1-axis]
            assert outputs[count] == (axis, before[axis]), outputs
            send("STOP")
            wait_for(lambda: not armed)
            count = len(commands)
            time.sleep(.12)
            assert not any(c in ("TRK P+", "TRK P-", "TRK T+", "TRK T-")
                           for c, _ in commands[count:])
        # A single press cannot run forever if the UI or its heartbeat disappears.
        manual("PAN_LEFT")
        wait_for(lambda: armed)
        wait_for(lambda: not armed, 1)
        retained = tuple(position)
        manual("PAN_RIGHT", int(time.monotonic()*1000)-700)
        time.sleep(.12)
        assert not armed and tuple(position) == retained
        # Batched release wins over an immediately preceding held command.
        send("MANUAL PAN_LEFT %d\nSTOP" % int(time.monotonic()*1000))
        time.sleep(.12)
        assert not armed
        assert not any("CENTER" in c for c, _ in commands)
        for axis in ("P", "T"):
            stamps = [t for c, t in commands if c in ("TRK " + axis + "+", "TRK " + axis + "-")]
            assert min(b-a for a,b in zip(stamps, stamps[1:])) >= .055
        send("QUIT")
        process.wait(timeout=2)
        reader.join(timeout=1)
        assert process.returncode == 0, process.stderr.read()
        assert not faults and not any(active)
        assert not any(e.get("event") == "error" for e in events), events
        print("PASS: all four exact edges; no recenter; retained starts; other axis OFF; bounded ramp/lead; release, stale input and missing heartbeat stop")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        running = False
        thread.join(timeout=1)
        os.close(slave)
        os.close(master)
