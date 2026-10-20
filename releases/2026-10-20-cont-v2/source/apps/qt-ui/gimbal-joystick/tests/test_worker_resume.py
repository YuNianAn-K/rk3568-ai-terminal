"""Linux PTY regression: unknown startup, explicit center, stop and resume."""
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
commands = []
command_times = []
outputs = []
position = None
targets = [1500, 1500]
active = [False, False]
armed = False
running = True
person_mode = "--person" in sys.argv
control_id = "a" * 32
start_command = "PERSON_START " + control_id if person_mode else "TRACK_START"


def firmware():
    global position, armed
    buffer = b""
    while running:
        if not select.select([master], [], [], .05)[0]:
            continue
        buffer += os.read(master, 4096)
        while b"\n" in buffer:
            raw, buffer = buffer.split(b"\n", 1)
            command = raw.decode().strip()
            commands.append(command)
            command_times.append((command, time.monotonic()))
            if command == "PING":
                reply = "PONG"
            elif command == "PAN STOP":
                active[:] = [False, False]
                armed = False
                reply = "PAN_PWM=OFF"
            elif command in ("PAN?", "TILT?"):
                axis = 0 if command == "PAN?" else 1
                reply = command[:-1] + "_PWM=" + (
                    str(position[axis]) + "US" if active[axis] else "OFF")
            elif command == "TRK?":
                reply = "TRK=ARMED" if armed else "TRK=OFF"
            elif command == "TRK LIMITS?":
                reply = "TRK_LIMITS=0500,2500,0500,2500"
            elif command == "TRK POS?":
                reply = "TRK_POS=UNKNOWN" if position is None else (
                    "TRK_POS=%04d,%04d" % tuple(position))
            elif command == "TRK CENTER":
                position = [1500, 1500]
                targets[:] = position
                active[:] = [True, True]
                armed = True
                reply = "TRK=CENTERING"
            elif command == "TRK ARM":
                assert position is not None
                targets[:] = position
                armed = True
                reply = "TRK=ARMED"
            elif command == "TRK KEEP":
                reply = "TRK=ARMED"
            elif command in ("TRK P+", "TRK P-", "TRK T+", "TRK T-") and armed:
                axis = 0 if command[4] == "P" else 1
                if not active[axis]:
                    outputs.append((axis, position[axis]))
                active[axis] = True
                low, high = (500, 2500)
                targets[axis] = max(low, min(high, targets[axis] + (
                    80 if command.endswith("+") else -80)))
                position[axis] = targets[axis]
                reply = "TRK_" + ("PAN" if axis == 0 else "TILT") + "=%dUS" % targets[axis]
            else:
                reply = "ERR"
            os.write(master, (reply + "\r\n").encode())


def send(text):
    process.stdin.write((text + "\n").encode())
    process.stdin.flush()


def samples():
    if person_mode:
        # Detection is already running when follow is clicked. Exercise a
        # first result queued in the same batch as PERSON_START.
        stamp = int(time.monotonic() * 1000)
        send("PERSON 0.20 0.20 0.72 0 %d %d" % (stamp, stamp))
    time.sleep(.12)
    for _ in range(4):
        if person_mode:
            stamp = int(time.monotonic() * 1000)
            send("PERSON 0.20 0.20 0.72 0 %d %d" % (stamp, stamp))
        else:
            send("HAND 0.20 0.20 0.986 0")
        time.sleep(.15)


def wait_until(check, seconds=3):
    deadline = time.monotonic() + seconds
    while not check():
        assert time.monotonic() < deadline, commands
        time.sleep(.02)


with tempfile.TemporaryDirectory() as temp:
    thread = threading.Thread(target=firmware, daemon=True)
    thread.start()
    source = str(Path(__file__).resolve().parents[1])
    code = ("import sys; sys.path.insert(0,%r); import gimbal_worker as w; "
            "w.DEVICE=%r; w.LOCK_PATH=%r; w.main()") % (
                source, os.ttyname(slave), temp + "/lock")
    process = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_until(lambda: "TRK POS?" in commands)
        send(start_command)
        samples()
        assert "TRK ARM" not in commands and not outputs
        send("CENTER")
        wait_until(lambda: "TRK CENTER" in commands)
        wait_until(lambda: not armed)
        send(start_command)
        samples()
        wait_until(lambda: bool(outputs))
        send("CONTROL_STOP " + control_id if person_mode else "STOP")
        wait_until(lambda: not armed)
        retained = tuple(position)
        assert retained != (1500, 1500), retained
        output_count = len(outputs)
        center_count = commands.count("TRK CENTER")
        send(start_command)
        samples()
        wait_until(lambda: len(outputs) >= output_count + 2)
        assert outputs[output_count:output_count + 2] == [(0, retained[0]), (1, retained[1])], outputs
        assert commands.count("TRK CENTER") == center_count
        if person_mode:
            # Weak confidence continues the same session. A missing box
            # disables PWM, then fresh associated samples resume in place.
            stamp = int(time.monotonic() * 1000)
            arms = commands.count("TRK ARM")
            send("PERSON .2 .2 .45 0 %d %d" % (stamp, stamp))
            time.sleep(.10)
            assert armed and commands.count("TRK ARM") == arms
            send("PERSON_PAUSE")
            wait_until(lambda: not armed)
            paused_commands = len(commands)
            time.sleep(.15)
            assert not any(c.startswith(("TRK P", "TRK T")) and c != "TRK POS?"
                           for c in commands[paused_commands:]), commands
            samples()
            wait_until(lambda: armed)
            assert commands.count("TRK ARM") == arms + 1
            assert commands.count("TRK CENTER") == center_count
            # Recorded user failure: target returns at ~600 ms, but its third
            # confirmation falls past the original 900 ms search deadline.
            arms = commands.count("TRK ARM")
            send("PERSON_PAUSE")
            wait_until(lambda: not armed)
            paused_commands = len(commands)
            time.sleep(.65)
            for index in range(3):
                stamp = int(time.monotonic() * 1000)
                send("PERSON .2 .2 .60 0 %d %d" % (stamp, stamp))
                if index < 2:
                    time.sleep(.17)
                    assert not armed
                    assert not any(command in ("TRK P+", "TRK P-", "TRK T+", "TRK T-")
                                   for command in commands[paused_commands:])
            wait_until(lambda: armed)
            assert commands.count("TRK ARM") == arms + 1
            assert commands.count("TRK CENTER") == center_count
            # Alternating misses and fresh single samples cannot keep a
            # confirmation alive forever or accidentally satisfy three hits.
            arms = commands.count("TRK ARM")
            send("PERSON_PAUSE")
            wait_until(lambda: not armed)
            for _ in range(7):
                stamp = int(time.monotonic() * 1000)
                send("PERSON .2 .2 .60 0 %d %d" % (stamp, stamp))
                time.sleep(.10)
                send("PERSON_PAUSE")
                time.sleep(.04)
            assert not armed and commands.count("TRK ARM") == arms
        # A brief miss keeps the session; sustained loss removes output.
        if not person_mode:
            send("HAND 0.00 0.00 0.000 0")
            time.sleep(.5)
            assert armed
        wait_until(lambda: not armed)
        if person_mode:
            # Timer spreads each axis's corrections instead of bursts.
            for axis in ("P", "T"):
                times = [stamp for command, stamp in command_times
                         if command in ("TRK " + axis + "+", "TRK " + axis + "-")]
                assert len(times) >= 3, times
                assert min(b - a for a, b in zip(times, times[1:])) >= .055, times
            # A stale first result must never ARM; a hand sample cannot steer
            # a person session. Reject malformed/non-finite person data too.
            for invalid in ("PERSON .2 .2 .72 0 1 2",
                            "PERSON .2 .2 .72 1 1 2",
                            "PERSON nan .2 .72 0 1 2",
                            "PERSON .2 .2 .72 0",
                            "PERSON .2 .2 .54 0 1 2"):
                arm_count = commands.count("TRK ARM")
                send(start_command)
                time.sleep(.12)
                send("HAND .2 .2 .986 0")
                time.sleep(.12)
                send(invalid)
                time.sleep(.15)
                assert commands.count("TRK ARM") == arm_count, commands
                assert not armed
        send("QUIT")
        out, err = process.communicate(timeout=3)
        assert process.returncode == 0, (out, err)
        events = [json.loads(line) for line in out.splitlines()]
        assert any(event.get("state") == "uninitialized" for event in events)
        assert any(event.get("state") == "lost" for event in events)
        assert not any(event["event"] == "error" for event in events)
        if person_mode:
            assert any(event.get("state") == "paused" for event in events), events
            assert any(event.get("event") == "stopped" and event.get("request_id") == control_id
                       for event in events), events
            assert any(event.get("state") == "active" and event.get("request_id") == control_id
                       for event in events), events
        assert not any(active)
        print("PASS:", "person" if person_mode else "hand",
              "unknown start; explicit center; retained resume; loss/exit OFF; invalid person samples never ARM")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        running = False
        thread.join(timeout=1)
        os.close(slave)
        os.close(master)
