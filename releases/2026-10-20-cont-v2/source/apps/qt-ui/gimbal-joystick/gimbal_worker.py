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
MANUAL_TICK_SECONDS = 0.06
MANUAL_INPUT_SECONDS = 0.60
HAND_LOSS_SECONDS = 1.4
TRACK_INTERVAL_SECONDS = 0.10
PERSON_TICK_SECONDS = 0.06
PERSON_RECOVERY_SECONDS = 0.9
PERSON_CONFIRM_SECONDS = 0.6
PERSON_FAST_FILTER_TAU = .05
TRACK_STEP_US = 80
TRACK_MAX_LEAD_US = 240
TRACK_GAIN_US = 800
TRACK_DEADZONE = 0.08
TIMING = os.environ.get("GIMBAL_TIMING") == "1"
COMMANDS = {
    "PAN_LEFT": ("PAN", 2500),
    "PAN_RIGHT": ("PAN", 500),
    "TILT_UP": ("TILT", 500),
    "TILT_DOWN": ("TILT", 2500),
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


def stop(fd, request_id="", notify=True):
    started = time.monotonic()
    require(fd, "PAN STOP", "PAN_PWM=OFF")
    require(fd, "PAN?", "PAN_PWM=OFF")
    require(fd, "TILT?", "TILT_PWM=OFF")
    if notify:
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
    if not (500 <= pan <= 2500 and 500 <= tilt <= 2500):
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
    minimum, maximum = 500, 2500
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


def smooth_person_target(previous, desired, interval_seconds):
    """Filter absolute PWM destinations, never integrate held image error.

    A 200 ms time constant damps frame-to-frame box jitter at the measured
    5 Hz rate. Resetting on pause avoids dragging a stale destination forward.
    """
    if previous is None:
        return desired
    alpha = 1 - math.exp(-max(0.0, interval_seconds) / 0.20)
    return previous + alpha * (desired - previous)


def smooth_framing_target(previous, desired, interval_seconds, actual, motion=None):
    # Only called for a new, validated frame. Rate-limit the destination,
    # never refresh timestamps or integrate a held frame's image error.
    interval = max(0.0, min(.25, interval_seconds))
    previous = actual if previous is None else previous
    # A fresh, substantial correction on the opposite side invalidates the
    # old destination's lead. Start the destination filter at the observed
    # current pose, rather than spending new frames chasing the wrong side.
    # Small zero-crossing noise retains the original filter and hysteresis.
    opposed = (previous - actual) * (desired - actual) < 0 and abs(desired - actual) >= 96
    if opposed:
        previous = actual
    fast = False
    if motion is not None and interval > 0:
        error = desired - actual
        direction = 1 if error >= 96 else -1 if error <= -96 else 0
        motion['hits'] = motion.get('hits', 0) + 1 if direction and direction == motion.get('direction') else (1 if direction else 0)
        motion['direction'] = direction
        change = desired-motion.get('last_desired', desired)
        trend = 1 if change >= 12 else -1 if change <= -12 else 0
        motion['trend_hits'] = motion.get('trend_hits', 0)+1 if trend and trend == motion.get('trend') else (1 if trend else 0)
        motion['trend'] = trend
        motion['last_desired'] = desired
        # Require two consecutive destination changes in the error direction.
        # Persistent box bias or two-frame alternating jitter is not velocity.
        fast = direction != 0 and trend == direction and motion['trend_hits'] >= 2
    # The first contradictory observation cancels the old lead but does not
    # launch a reversal. A one-frame large detector outlier must not twitch
    # the opposite way. Subsequent fresh samples use the normal filter.
    if opposed and (motion is None or motion.get('hits', 0) < 2):
        return actual
    tau = PERSON_FAST_FILTER_TAU if fast else .20
    filtered = previous + (1-math.exp(-interval/tau)) * (desired-previous)
    limit = (1200.0 if fast else 600.0) * interval
    return max(previous-limit, min(previous+limit, filtered))


def track_framing_axis(fd, axis, actual, target, desired, direction):
    # Keep firmware 80us steps/ramp. Require a larger fresh destination
    # difference to reverse, so near-boundary noise does not alternate steps.
    delta = desired-target
    if direction and delta*direction < 0 and abs(delta) < 96:
        return target, False, direction
    next_target, moved = track_axis(fd, axis, actual, target, 0, desired, max_steps=1)
    return next_target, moved, (1 if next_target>target else -1) if moved else direction


def track_axis(fd, axis, actual, target, error, desired_target=None, max_steps=3):
    minimum, maximum = 500, 2500
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
    for _ in range(min(max_steps, TRACK_MAX_LEAD_US // TRACK_STEP_US)):
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


def person_recovery_expired(paused_at, confirm_at, now):
    # Confirmation belongs to the current uninterrupted sample streak. Search
    # keeps its original origin; even a late streak has a fixed total cap.
    deadline = paused_at + PERSON_RECOVERY_SECONDS
    if confirm_at is not None:
        deadline = min(paused_at + PERSON_RECOVERY_SECONDS + PERSON_CONFIRM_SECONDS,
                       max(deadline, confirm_at + PERSON_CONFIRM_SECONDS))
    return now >= deadline


def manual_axis(fd, axis, actual, target, destination):
    """Advance a held direction without the visual tracking deadzone."""
    if target == destination:
        return target, False
    delta = TRACK_STEP_US if destination > target else -TRACK_STEP_US
    candidate = max(500, min(2500, target + delta))
    if abs(candidate - actual) > TRACK_MAX_LEAD_US:
        return target, False
    reply = exchange(fd, "TRK " + ("P" if axis == "PAN" else "T") +
                     ("+" if delta > 0 else "-"))
    prefix = "TRK_" + axis + "="
    if not reply.startswith(prefix) or not reply.endswith("US"):
        raise SerialFailure("手动位置回执不匹配")
    pulse = reply[len(prefix):-2]
    if not pulse.isdigit() or int(pulse) != candidate:
        raise SerialFailure("手动目标变化异常")
    return candidate, True


class InputReader:
    def __init__(self):
        self.buffer = bytearray()
        self.deferred = deque()

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
        command = self.deferred.popleft() if self.deferred else self.read(timeout)
        if command is None:
            return None
        if command == "QUIT":
            return "QUIT"
        commands = [command]
        while True:
            following = self.deferred.popleft() if self.deferred else self.read(0)
            if following is None:
                break
            if following == "QUIT":
                return "QUIT"
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
        # STOP was checked across the entire batch, including after START.
        # A start or pause is a barrier, not permission to drop observations
        # that arrived later. Recheck deferred data against new STOP input on
        # the next call; nothing can move directly from this input reader.
        for index, item in enumerate(commands):
            if is_track_start(item):
                self.deferred.extend(commands[index+1:])
                return item
        if "PERSON_PAUSE" in commands:
            index = len(commands)-1-commands[::-1].index("PERSON_PAUSE")
            self.deferred.extend(commands[index+1:])
            return "PERSON_PAUSE"
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
        if track_capable:
            require(fd, "TRK LIMITS?", "TRK_LIMITS=0500,2500,0500,2500")
        position = saved_position(fd) if track_capable else None
        emit("ready", track_capable=track_capable, position_ready=position is not None)
        active_until = None
        manual_direction = None
        manual_last_tick = 0.0
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
        paused_at = None
        recovery_confirm_at = None
        person_probe_ms = None
        framing_mode = False
        framing_directions = [0, 0]
        framing_motion = [{}, {}]
        def pause_person(reason, pause_stamp=None):
            nonlocal armed, paused_at, recovery_confirm_at
            nonlocal filtered_pan_target, filtered_tilt_target
            nonlocal framing_directions, framing_motion
            if paused_at is None:
                origin = time.monotonic() if pause_stamp is None else pause_stamp
                stop(fd)
                armed = False
                paused_at = origin
                emit("tracking", state="paused", reason=reason,
                     request_id=person_request_id)
            # Keep the original search origin and 900+600ms total cap.
            # A miss invalidates confirmation, never refreshes frame age.
            recovery_confirm_at = None
            framing_directions = [0, 0]
            framing_motion = [{}, {}]
            recent_hand.clear()
            filtered_pan_target = filtered_tilt_target = None
            pose_history.clear()
        while True:
            timeout = 0.05 if active_until is None else max(
                0.0, min(0.05, active_until - time.monotonic()))
            if tracking and person_mode and armed:
                timeout = min(timeout, max(0, PERSON_TICK_SECONDS -
                                          (time.monotonic() - last_track_command)))
            if manual_direction is not None:
                timeout = min(timeout, max(0, MANUAL_TICK_SECONDS -
                                          (time.monotonic() - manual_last_tick)))
            command = pending if pending is not None else reader.latest(timeout)
            pending = None
            now = time.monotonic()
            manual_stamp = now
            if command and command.startswith("MANUAL "):
                fields = command.split()
                if len(fields) != 3 or fields[1] not in COMMANDS or not fields[2].isdigit():
                    raise SerialFailure("手动控制数据格式错误")
                if not 0 <= now * 1000 - int(fields[2]) <= 500:
                    stop(fd)
                    tracking = armed = False
                    manual_direction = None
                    active_until = None
                    continue
                manual_stamp = int(fields[2]) / 1000
                command = fields[1]
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
                             (person_mode and paused_at is not None and
                              person_recovery_expired(paused_at, recovery_confirm_at, now)) or
                             (armed and last_hand is not None and
                              not person_mode and now - last_hand > HAND_LOSS_SECONDS)):
                stop(fd)
                tracking = armed = False
                emit("tracking", state="lost", reason="target_timeout",
                     request_id=person_request_id if person_mode else "")
                continue
            if command == "QUIT":
                break
            if command in ("STOP", "STATUS", "TRACK_STOP"):
                if command == "STATUS" and active_until is not None:
                    continue
                stop(fd, stop_request_id)
                active_until = None
                manual_direction = None
                tracking = armed = False
                if command == "TRACK_STOP":
                    emit("tracking", state="off")
                if track_capable:
                    emit("position", ready=saved_position(fd) is not None)
                continue
            # A held target is never extended beyond its original frame age.
            # Missing association and stale frames turn PWM off while retaining
            # the session for a bounded, fresh-sample reacquisition.
            if tracking and person_mode and (command == "PERSON_PAUSE" or
                    (armed and person_probe_ms is not None and now * 1000 - person_probe_ms > 500)):
                pause_person("missing_or_stale", now)
                if command == "PERSON_PAUSE":
                    continue
            if command == "CENTER":
                manual_direction = None
                stop(fd)
                tracking = armed = False
                require(fd, "TRK CENTER", "TRK=CENTERING")
                emit("centering")
                active_until = time.monotonic() + HOLD_SECONDS
                continue
            if command in ("TRACK_START", "PERSON_START"):
                manual_direction = None
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
                paused_at = None
                recovery_confirm_at = None
                person_probe_ms = None
                framing_mode = False
                framing_directions = [0, 0]
                framing_motion = [{}, {}]
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
                if len(parts) not in (5, 7, 9) or (len(parts)==9 and not person_mode):
                    raise SerialFailure("手部检测数据格式错误")
                try:
                    x, y, score = map(float, parts[1:4])
                except ValueError as error:
                    raise SerialFailure("手部检测数据无效") from error
                probe_ms = result_ms = None
                if len(parts) in (7, 9):
                    try:
                        probe_ms, result_ms = map(int, parts[5:7])
                    except ValueError as error:
                        raise SerialFailure("手部检测计时格式错误") from error
                desired_x = desired_y = .5
                sample_framing = len(parts)==9
                if sample_framing:
                    try: desired_x, desired_y = map(float,parts[7:9])
                    except ValueError as error: raise SerialFailure("人物构图数据无效") from error
                valid = (math.isfinite(desired_x) and math.isfinite(desired_y) and
                         .20 <= desired_x <= .80 and .20 <= desired_y <= .85 and
                         parts[4] == "0" and
                         all(math.isfinite(value) for value in (x, y, score)) and
                         (0.40 if person_mode else 0.80) <= score <= 1 and
                         (0 < x < 1 and 0 < y < 1 if person_mode else
                          0.05 < x < 0.95 and 0.05 < y < 0.95))
                if person_mode:
                    valid = (valid and probe_ms is not None and result_ms is not None and
                             0 < probe_ms <= result_ms <= now * 1000)
                    if valid and now * 1000 - probe_ms > 500:
                        pause_person("stale_sample")
                        continue
                if TIMING:
                    emit("timing", type="sample", at_ms=round(now * 1000, 3),
                         probe_ms=probe_ms, result_ms=result_ms, valid=valid,
                         queue_ms=round(now * 1000 - result_ms, 3) if result_ms else None,
                         x=x, y=y, score=score, ambiguous=parts[4] != "0")
                if not valid:
                    if person_mode:
                        stop(fd)
                        tracking = armed = False
                        emit("tracking", state="lost", reason="invalid_sample", request_id=person_request_id)
                    if parts[4] != "0":
                        recent_hand.clear()
                    continue
                if person_mode and person_probe_ms is not None and probe_ms <= person_probe_ms:
                    continue
                sample_interval = now - last_hand if last_hand is not None else 0
                last_hand = now
                if person_mode:
                    person_probe_ms = probe_ms
                    framing_mode = sample_framing
                    if paused_at is not None and recovery_confirm_at is None:
                        # A valid associated target returned within the search
                        # window. Give its three fresh samples their own fixed
                        # budget, with PWM still OFF until ARM is confirmed.
                        recovery_confirm_at = now
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
                    paused_at = None
                    recovery_confirm_at = None
                    pan_target, tilt_target = position
                    last_track_command = now - TRACK_INTERVAL_SECONDS
                    emit("tracking", state="active", request_id=person_request_id if person_mode else "")
                    if TIMING:
                        emit("timing", type="armed", at_ms=round(time.monotonic() * 1000, 3),
                             from_start_ms=round((time.monotonic() - started_at) * 1000, 3))
                if not person_mode and now - last_track_command < TRACK_INTERVAL_SECONDS:
                    continue
                dx, dy = filtered_x - desired_x, filtered_y - desired_y
                pan_actual = actual_pulse(fd, "PAN")
                tilt_actual = actual_pulse(fd, "TILT")
                sampled_ms = time.monotonic() * 1000
                if probe_ms and not 0 <= sampled_ms - probe_ms <= 500:
                    if person_mode:
                        pause_person("stale_after_position_read")
                        continue
                    raise SerialFailure("手部画面过期，已请求停止")
                pose_history.append((sampled_ms, pan_actual, tilt_actual))
                frame_pan, frame_tilt = pose_at_capture(
                    pose_history, probe_ms, (pan_actual, tilt_actual))
                desired_pan = frame_target(frame_pan, -dx)
                desired_tilt = frame_target(frame_tilt, dy)
                # Smooth absolute targets; smoothing image coordinates across
                # different camera poses would add another feedback delay.
                if person_mode:
                    if framing_mode:
                        filtered_pan_target = smooth_framing_target(filtered_pan_target, desired_pan, sample_interval, pan_actual, framing_motion[0])
                        filtered_tilt_target = smooth_framing_target(filtered_tilt_target, desired_tilt, sample_interval, tilt_actual, framing_motion[1])
                        if TIMING:
                            emit("timing", type="framing", at_ms=round(time.monotonic()*1000,3),
                                 probe_ms=probe_ms, result_ms=result_ms, x=x, y=y,
                                 desired_x=desired_x, desired_y=desired_y,
                                 pan_target=round(filtered_pan_target,3), tilt_target=round(filtered_tilt_target,3),
                                 pan_motion_hits=framing_motion[0].get('hits',0),
                                 tilt_motion_hits=framing_motion[1].get('hits',0))
                    else:
                        filtered_pan_target = smooth_person_target(filtered_pan_target, desired_pan, sample_interval)
                        filtered_tilt_target = smooth_person_target(filtered_tilt_target, desired_tilt, sample_interval)
                    # Update the absolute destination once per camera result;
                    # the independent ticker spreads existing 80 us steps.
                    continue
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
            if command is None and tracking and person_mode and armed and \
                    filtered_pan_target is not None and now - last_track_command >= PERSON_TICK_SECONDS:
                pan_actual = actual_pulse(fd, "PAN")
                tilt_actual = actual_pulse(fd, "TILT")
                sampled_ms = time.monotonic() * 1000
                if sampled_ms - person_probe_ms > 500:
                    pause_person("stale_after_position_read")
                    continue
                pose_history.append((sampled_ms, pan_actual, tilt_actual))
                if framing_mode:
                    pan_target, pan_moved, framing_directions[0] = track_framing_axis(
                        fd,"PAN",pan_actual,pan_target,filtered_pan_target,framing_directions[0])
                    tilt_target, tilt_moved, framing_directions[1] = track_framing_axis(
                        fd,"TILT",tilt_actual,tilt_target,filtered_tilt_target,framing_directions[1])
                else:
                    pan_target, pan_moved = track_axis(fd,"PAN",pan_actual,pan_target,0,filtered_pan_target,max_steps=1)
                    tilt_target, tilt_moved = track_axis(fd,"TILT",tilt_actual,tilt_target,0,filtered_tilt_target,max_steps=1)
                if not (pan_moved or tilt_moved):
                    require(fd, "TRK KEEP", "TRK=ARMED")
                last_track_command = time.monotonic()
                if TIMING:
                    emit("timing", type="person_tick", at_ms=round(last_track_command * 1000, 3),
                         probe_ms=person_probe_ms, pan_target=pan_target, tilt_target=tilt_target,
                         moved=pan_moved or tilt_moved)
                continue
            if command in COMMANDS:
                tracking = armed = False
                if manual_direction != command:
                    manual_direction = None
                    stop(fd, notify=False)
                    position = saved_position(fd) if track_capable else None
                    if position is None:
                        active_until = None
                        emit("stopped", pan="OFF", tilt="OFF")
                        emit("position", ready=False)
                        emit("tracking", state="uninitialized")
                        continue
                    require(fd, "TRK ARM", "TRK=ARMED")
                    pan_target, tilt_target = position
                    manual_direction = command
                    manual_last_tick = now - MANUAL_TICK_SECONDS
                    axis, destination = COMMANDS[command]
                    emit("active", axis=axis, pulse=f"目标 {destination}US")
                # Only fresh UI input extends this deadline, never STATUS or ticks.
                active_until = manual_stamp + MANUAL_INPUT_SECONDS
                continue
            if manual_direction is not None and now < active_until and \
                    now - manual_last_tick >= MANUAL_TICK_SECONDS:
                axis, destination = COMMANDS[manual_direction]
                actual = actual_pulse(fd, axis)
                if time.monotonic() >= active_until:
                    stop(fd)
                    manual_direction = None
                    active_until = None
                    continue
                target = pan_target if axis == "PAN" else tilt_target
                target, moved = manual_axis(fd, axis, actual, target, destination)
                if axis == "PAN":
                    pan_target = target
                else:
                    tilt_target = target
                if not moved:
                    require(fd, "TRK KEEP", "TRK=ARMED")
                manual_last_tick = time.monotonic()
                continue
            if active_until is not None and time.monotonic() >= active_until:
                stop(fd)
                active_until = None
                manual_direction = None
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
