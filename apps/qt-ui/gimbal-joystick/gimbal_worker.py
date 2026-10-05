#!/usr/bin/env python3
"""Bounded UART control for the touch joystick and dual-axis hand tracking."""

import fcntl
from collections import deque
import json
import math
import os
import re
import select
import sys
import termios
import time


DEVICE = "/dev/ttyS9"
LOCK_PATH = "/var/run/ai-voice-pc13.lock"
HOLD_SECONDS = 1.2
SETTLE_SECONDS = 0.25
HAND_LOSS_SECONDS = 1.4
TRACK_INTERVAL_SECONDS = 0.10
TRACK_STEP_US = 80
TRACK_MAX_LEAD_US = 240
TRACK_GAIN_US = 800
TRACK_DEADZONE = 0.08
TIMING = os.environ.get("GIMBAL_TIMING") == "1"
COMMANDS = {
    "PAN_LEFT": ("PAN", "PAN CENTER", "PAN +100", "1600US"),
    "PAN_RIGHT": ("PAN", "PAN CENTER", "PAN -100", "1400US"),
    "TILT_UP": ("TILT", "TILT CENTER", "TILT -100", "1400US"),
    "TILT_DOWN": ("TILT", "TILT CENTER", "TILT +100", "1600US"),
}


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


class SerialFailure(Exception):
    pass


def configure(fd):
    attrs = termios.tcgetattr(fd)
    attrs[0] = attrs[1] = attrs[3] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[4] = attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def exchange(fd, command):
    started = time.monotonic()
    deadline = started + 0.5
    payload = command.encode("ascii") + b"\r\n"
    while payload:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([], [fd], [], remaining)[1]:
            raise SerialFailure("UART 写入超时")
        try:
            payload = payload[os.write(fd, payload):]
        except BlockingIOError:
            continue
    reply = bytearray()
    while b"\n" not in reply:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise SerialFailure("STM32 未回执")
        try:
            reply.extend(os.read(fd, 64 - len(reply)))
        except BlockingIOError:
            continue
        if len(reply) >= 64:
            raise SerialFailure("UART 回执过长")
    result = bytes(reply).decode("ascii", "replace").strip()
    if TIMING:
        finished = time.monotonic()
        emit("timing", type="uart", command=command, reply=result,
             start_ms=round(started * 1000, 3), end_ms=round(finished * 1000, 3),
             duration_ms=round((finished - started) * 1000, 3))
    return result


def require(fd, command, expected):
    if exchange(fd, command) != expected:
        raise SerialFailure("STM32 回执不匹配")


def stop(fd, request_id=""):
    started = time.monotonic()
    require(fd, "PAN STOP", "PAN_PWM=OFF")
    require(fd, "PAN?", "PAN_PWM=OFF")
    require(fd, "TILT?", "TILT_PWM=OFF")
    emit("stopped", pan="OFF", tilt="OFF", request_id=request_id)
    if TIMING:
        emit("timing", type="stop", at_ms=round(time.monotonic() * 1000, 3),
             duration_ms=round((time.monotonic() - started) * 1000, 3))


def saved_position(fd):
    reply = exchange(fd, "TRK POS?")
    if reply == "TRK_POS=UNKNOWN":
        return None
    if not reply.startswith("TRK_POS="):
        raise SerialFailure("固件不支持保留位置，请更新云台固件")
    parts = reply[8:].split(",")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise SerialFailure("保留位置回执不匹配")
    pan, tilt = map(int, parts)
    if not (500 <= pan <= 2500 and 750 <= tilt <= 2250):
        raise SerialFailure("保留位置超出限幅")
    return pan, tilt


def actual_pulse(fd, axis):
    reply = exchange(fd, axis + "?")
    prefix = axis + "_PWM="
    if reply == prefix + "OFF":
        position = saved_position(fd)
        if position is None:
            raise SerialFailure("位置尚未初始化，请先回中位")
        return position[0 if axis == "PAN" else 1]
    if not reply.startswith(prefix) or not reply.endswith("US"):
        raise SerialFailure("舵机位置回执不匹配")
    pulse = reply[len(prefix):-2]
    if not pulse.isdigit():
        raise SerialFailure("舵机位置回执不匹配")
    value = int(pulse)
    minimum, maximum = (500, 2500) if axis == "PAN" else (750, 2250)
    if not minimum <= value <= maximum:
        raise SerialFailure("舵机位置超出限幅")
    return value


def pose_at_capture(history, stamp_ms, current):
    """Interpolate emitted PWM at frame receipt, not physical shaft angle."""
    if not stamp_ms or not history:
        return current
    previous = history[0]
    if stamp_ms <= previous[0]:
        return previous[1:]
    for following in list(history)[1:]:
        if stamp_ms <= following[0]:
            weight = (stamp_ms - previous[0]) / max(1, following[0] - previous[0])
            return tuple(a + weight * (b - a) for a, b in zip(previous[1:], following[1:]))
        previous = following
    return previous[1:]


def frame_target(pulse, error):
    # Do not snap the absolute target to an older camera pose in the deadzone:
    # that would alternate between adjacent PWM steps after delayed frames.
    return pulse + error * TRACK_GAIN_US


def track_axis(fd, axis, actual, target, error, desired_target=None):
    minimum, maximum = (500, 2500) if axis == "PAN" else (750, 2250)
    if abs(error) <= TRACK_DEADZONE:
        error = 0.0
    offset = max(-TRACK_MAX_LEAD_US, min(TRACK_MAX_LEAD_US,
                                          round(error * TRACK_GAIN_US)))
    desired = max(minimum, min(maximum, actual + offset))
    if desired_target is not None:
        # An old image corrects the pose at capture, not the newer pose after
        # the motor has already moved. Otherwise every delayed frame adds lead.
        desired = max(minimum, min(maximum,
            max(actual - TRACK_MAX_LEAD_US, min(actual + TRACK_MAX_LEAD_US, desired_target))))
    prefix = "TRK_" + axis + "="
    letter = "P" if axis == "PAN" else "T"
    moved = False
    threshold = TRACK_STEP_US // 2 if desired_target is None else (
        TRACK_DEADZONE * TRACK_GAIN_US)
    for _ in range(TRACK_MAX_LEAD_US // TRACK_STEP_US):
        if desired >= target + threshold:
            delta, sign = TRACK_STEP_US, "+"
        elif desired <= target - threshold:
            delta, sign = -TRACK_STEP_US, "-"
        else:
            break
        candidate = max(minimum, min(maximum, target + delta))
        if (abs(candidate - actual) > TRACK_MAX_LEAD_US and
                abs(candidate - actual) >= abs(target - actual)):
            break
        reply = exchange(fd, "TRK " + letter + sign)
        if not reply.startswith(prefix) or not reply.endswith("US"):
            raise SerialFailure("跟手位置回执不匹配")
        pulse = reply[len(prefix):-2]
        if not pulse.isdigit():
            raise SerialFailure("跟手位置回执不匹配")
        next_target = int(pulse)
        if next_target != max(minimum, min(maximum, target + delta)):
            raise SerialFailure("跟手目标变化异常")
        target = next_target
        moved = True
    return target, moved


def is_track_start(command):
    return command in ("TRACK_START", "PERSON_START") or command.startswith("PERSON_START ")


class InputReader:
    def __init__(self):
        self.buffer = bytearray()

    def read(self, timeout):
        if b"\n" not in self.buffer:
            if not select.select([sys.stdin], [], [], timeout)[0]:
                return None
            chunk = os.read(sys.stdin.fileno(), 4096)
            if not chunk:
                return "QUIT"
            self.buffer.extend(chunk)
            if len(self.buffer) > 4096:
                raise SerialFailure("摇杆命令过长")
        if b"\n" not in self.buffer:
            return None
        line, _, remainder = self.buffer.partition(b"\n")
        self.buffer = bytearray(remainder)
        return line.decode("ascii", "replace").strip()

    def latest(self, timeout):
        command = self.read(timeout)
        if command is None:
            return None
        if command == "QUIT":
            return "QUIT"
        # Start is a barrier: the next sample may already be queued when a
        # detector is running. Dropping the start would leave the UI waiting
        # while the controller ignores every sample. Start itself cannot ARM.
        if is_track_start(command):
            return command
        commands = [command]
        while True:
            following = self.read(0)
            if following is None:
                break
            if following == "QUIT":
                return "QUIT"
            if is_track_start(following):
                for item in reversed(commands):
                    if item.startswith("CONTROL_STOP "):
                        return item
                if "STOP" in commands or "TRACK_STOP" in commands:
                    return "STOP"
                return following
            commands.append(following)
        if "QUIT" in commands:
            return "QUIT"
        for item in reversed(commands):
            if item.startswith("CONTROL_STOP "):
                return item
        if "STOP" in commands:
            return "STOP"
        if "TRACK_STOP" in commands:
            return "TRACK_STOP"
        return commands[-1]


def main():
    lock_fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    fd = None
    reader = InputReader()
    pending = None
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SerialFailure("串口正被其他程序使用") from None
        fd = os.open(DEVICE, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        configure(fd)
        require(fd, "PING", "PONG")
        stop(fd)
        track_capable = exchange(fd, "TRK?") == "TRK=OFF"
        position = saved_position(fd) if track_capable else None
        emit("ready", track_capable=track_capable, position_ready=position is not None)
        active_until = None
        tracking = False
        person_mode = False
        person_request_id = ""
        armed = False
        recent_hand = deque()
        last_hand = None
        started_at = None
        last_track_command = 0.0
        filtered_x = filtered_y = None
        pose_history = deque(maxlen=32)
        filtered_pan_target = filtered_tilt_target = None
        pan_target = tilt_target = 1500
        while True:
            timeout = 0.05 if active_until is None else max(
                0.0, min(0.05, active_until - time.monotonic()))
            command = pending if pending is not None else reader.latest(timeout)
            pending = None
            now = time.monotonic()
            stop_request_id = ""
            if command and command.startswith(("CONTROL_STOP ", "PERSON_START ")):
                fields = command.split()
                if len(fields) != 2 or not re.fullmatch(r"[a-f0-9]{32}", fields[1]):
                    raise SerialFailure("控制请求编号格式错误")
                if fields[0] == "CONTROL_STOP":
                    stop_request_id = fields[1]
                    command = "STOP"
                else:
                    person_request_id = fields[1]
                    command = "PERSON_START"

            if command not in ("QUIT", "STOP", "TRACK_STOP") and tracking and ((last_hand is None and now - started_at > 6.0) or
                             (armed and last_hand is not None and
                              now - last_hand > (0.6 if person_mode else HAND_LOSS_SECONDS))):
                stop(fd)
                tracking = armed = False
                emit("tracking", state="lost", request_id=person_request_id if person_mode else "")
                continue
            if command == "QUIT":
                break
            if command in ("STOP", "STATUS", "TRACK_STOP"):
                if command == "STATUS" and active_until is not None:
                    continue
                stop(fd, stop_request_id)
                active_until = None
                tracking = armed = False
                if command == "TRACK_STOP":
                    emit("tracking", state="off")
                if track_capable:
                    emit("position", ready=saved_position(fd) is not None)
                continue
            if command == "CENTER":
                stop(fd)
                tracking = armed = False
                require(fd, "TRK CENTER", "TRK=CENTERING")
                emit("centering")
                active_until = time.monotonic() + HOLD_SECONDS
                continue
            if command in ("TRACK_START", "PERSON_START"):
                stop(fd)
                person_mode = command == "PERSON_START"
                position = saved_position(fd) if track_capable else None
                tracking = track_capable and position is not None
                armed = False
                recent_hand.clear()
                last_hand = None
                started_at = now
                active_until = None
                filtered_x = filtered_y = None
                pose_history.clear()
                filtered_pan_target = filtered_tilt_target = None
                if position is not None:
                    pan_target, tilt_target = position
                emit("position", ready=position is not None)
                emit("tracking", state="searching" if tracking else "uninitialized",
                     request_id=person_request_id if person_mode else "")
                if TIMING:
                    emit("timing", type="track_start", at_ms=round(now * 1000, 3))
                continue
            if command and command.startswith(("HAND ", "PERSON ")):
                if not tracking:
                    continue
                parts = command.split()
                if (parts[0] == "PERSON") != person_mode:
                    continue
                if len(parts) not in (5, 7):
                    raise SerialFailure("手部检测数据格式错误")
                try:
                    x, y, score = map(float, parts[1:4])
                except ValueError as error:
                    raise SerialFailure("手部检测数据无效") from error
                probe_ms = result_ms = None
                if len(parts) == 7:
                    try:
                        probe_ms, result_ms = map(int, parts[5:7])
                    except ValueError as error:
                        raise SerialFailure("手部检测计时格式错误") from error
                valid = (parts[4] == "0" and
                         all(math.isfinite(value) for value in (x, y, score)) and
                         (0.55 if person_mode else 0.80) <= score <= 1 and
                         0.05 < x < 0.95 and 0.05 < y < 0.95)
                if person_mode:
                    valid = (valid and probe_ms is not None and result_ms is not None and
                             0 < probe_ms <= result_ms <= now * 1000 and
                             now * 1000 - probe_ms <= 500)
                if TIMING:
                    emit("timing", type="sample", at_ms=round(now * 1000, 3),
                         probe_ms=probe_ms, result_ms=result_ms, valid=valid,
                         queue_ms=round(now * 1000 - result_ms, 3) if result_ms else None,
                         x=x, y=y, score=score, ambiguous=parts[4] != "0")
                if not valid:
                    if person_mode:
                        stop(fd)
                        tracking = armed = False
                        emit("tracking", state="lost", request_id=person_request_id)
                    if parts[4] != "0":
                        recent_hand.clear()
                    continue
                last_hand = now
                filtered_x, filtered_y = x, y
                recent_hand.append(now)
                while recent_hand and now - recent_hand[0] > 1.2:
                    recent_hand.popleft()
                if len(recent_hand) < 3:
                    continue
                if not armed:
                    position = saved_position(fd)
                    if position is None:
                        raise SerialFailure("位置尚未初始化，请先回中位")
                    require(fd, "TRK ARM", "TRK=ARMED")
                    armed = True
                    pan_target, tilt_target = position
                    last_track_command = now - TRACK_INTERVAL_SECONDS
                    emit("tracking", state="active", request_id=person_request_id if person_mode else "")
                    if TIMING:
                        emit("timing", type="armed", at_ms=round(time.monotonic() * 1000, 3),
                             from_start_ms=round((time.monotonic() - started_at) * 1000, 3))
                if now - last_track_command < TRACK_INTERVAL_SECONDS:
                    continue
                dx, dy = filtered_x - 0.5, filtered_y - 0.5
                pan_actual = actual_pulse(fd, "PAN")
                tilt_actual = actual_pulse(fd, "TILT")
                sampled_ms = time.monotonic() * 1000
                if probe_ms and not 0 <= sampled_ms - probe_ms <= 500:
                    raise SerialFailure("手部画面过期，已请求停止")
                pose_history.append((sampled_ms, pan_actual, tilt_actual))
                frame_pan, frame_tilt = pose_at_capture(
                    pose_history, probe_ms, (pan_actual, tilt_actual))
                desired_pan = frame_target(frame_pan, -dx)
                desired_tilt = frame_target(frame_tilt, dy)
                # Smooth absolute targets; smoothing image coordinates across
                # different camera poses would add another feedback delay.
                filtered_pan_target = desired_pan if filtered_pan_target is None else (
                    .25 * filtered_pan_target + .75 * desired_pan)
                filtered_tilt_target = desired_tilt if filtered_tilt_target is None else (
                    .25 * filtered_tilt_target + .75 * desired_tilt)
                pan_target, pan_moved = track_axis(
                    fd, "PAN", pan_actual, pan_target, -dx, filtered_pan_target)
                tilt_target, tilt_moved = track_axis(
                    fd, "TILT", tilt_actual, tilt_target, dy, filtered_tilt_target)
                if not (pan_moved or tilt_moved):
                    require(fd, "TRK KEEP", "TRK=ARMED")
                else:
                    emit("tracking", state="active",
                         pulse=f"PAN={pan_target}US TILT={tilt_target}US",
                         request_id=person_request_id if person_mode else "")
                last_track_command = time.monotonic()
                if TIMING:
                    emit("timing", type="control", begin_ms=round(now * 1000, 3),
                         end_ms=round(last_track_command * 1000, 3),
                         probe_ms=probe_ms, result_ms=result_ms,
                         frame_to_commands_ms=round(last_track_command * 1000 - probe_ms, 3)
                         if probe_ms else None,
                         duration_ms=round((last_track_command - now) * 1000, 3),
                         pan_actual=pan_actual, tilt_actual=tilt_actual,
                         pan_target=pan_target, tilt_target=tilt_target,
                         frame_pan=round(frame_pan, 2), frame_tilt=round(frame_tilt, 2),
                         desired_pan=round(filtered_pan_target, 2),
                         desired_tilt=round(filtered_tilt_target, 2),
                         filtered_x=round(filtered_x, 4), filtered_y=round(filtered_y, 4),
                         moved=pan_moved or tilt_moved)
                continue
            if command in COMMANDS:
                tracking = armed = False
                axis, center, step, pulse = COMMANDS[command]
                stop(fd)
                require(fd, center, f"{axis}_PWM=1500US")
                # A release received during settling prevents the step command.
                interrupted = reader.latest(SETTLE_SECONDS)
                if interrupted is not None:
                    stop(fd)
                    active_until = None
                    if interrupted == "QUIT":
                        break
                    pending = interrupted
                    continue
                require(fd, step, f"{axis}_PWM={pulse}")
                other = "TILT" if axis == "PAN" else "PAN"
                require(fd, other + "?", other + "_PWM=OFF")
                emit("active", axis=axis, pulse=pulse)
                active_until = time.monotonic() + HOLD_SECONDS
                continue
            if active_until is not None and time.monotonic() >= active_until:
                stop(fd)
                active_until = None
                if track_capable:
                    emit("position", ready=saved_position(fd) is not None)
    finally:
        if fd is not None:
            try:
                stop(fd)
            except (OSError, SerialFailure):
                pass
            os.close(fd)
        os.close(lock_fd)


if __name__ == "__main__":
    try:
        main()
    except (OSError, SerialFailure) as error:
        emit("error", message=str(error))
        sys.exit(1)
