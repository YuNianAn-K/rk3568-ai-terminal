"""Stationary world target, delayed camera, gradual PWM plant: no self-sweep."""
import sys
from collections import deque
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gimbal_worker as w

target = {"PAN": 1500, "TILT": 1500}


def exchange(_fd, command):
    axis = "PAN" if command[4] == "P" else "TILT"
    low, high = 500, 2500
    target[axis] = max(low, min(high, target[axis] + (80 if command.endswith("+") else -80)))
    return "TRK_%s=%dUS" % (axis, target[axis])


w.exchange = exchange
for world_pan, world_tilt in ((1750, 1300), (1250, 1750), (1800, 1850)):
    target.update(PAN=1500, TILT=1500)
    actual = [1500, 1500]
    history = deque(maxlen=32)
    physical = [(0, 1500, 1500)]
    smooth = None
    poses = []
    for tick in range(1, 601):
        now = tick * 20
        for axis, key in enumerate(("PAN", "TILT")):
            delta = target[key] - actual[axis]
            actual[axis] += max(-24, min(24, delta))
        physical.append((now, *actual))
        if tick % 5:
            continue
        # The actual image was captured 133 ms before the current PWM read.
        stamp = max(0, now - 133)
        camera = w.pose_at_capture(physical, stamp, actual)
        noise = .004 if tick % 10 else -.004
        dx = (camera[0] - world_pan) / 875 + noise
        dy = -(camera[1] - world_tilt) / 804 + noise
        history.append((now, *actual))
        estimate = w.pose_at_capture(history, stamp, actual)
        desired = [w.frame_target(estimate[0], -dx), w.frame_target(estimate[1], dy)]
        smooth = desired if smooth is None else [
            .25 * old + .75 * new for old, new in zip(smooth, desired)]
        for axis, key, error in ((0, "PAN", -dx), (1, "TILT", dy)):
            w.track_axis(None, key, actual[axis], target[key], error, smooth[axis])
            assert abs(target[key] - actual[axis]) <= 240
        poses.append(tuple(actual))
    for axis, expected in enumerate((world_pan, world_tilt)):
        values = [pose[axis] for pose in poses[-20:]]
        assert max(values) - min(values) <= 24, (world_pan, world_tilt, values)
        assert abs(values[-1] - expected) <= 85, (expected, values[-1])
print("PASS: stationary target converges with 133 ms camera delay and noise; bounded lead; no sustained sweep")

# Person destinations update at 5 Hz, independently of the 60 ms actuator
# cadence. Holding the absolute destination must not integrate old error.
for delay in (150, 300):
    target.update(PAN=1500, TILT=1500)
    actual = [1500, 1500]
    history = deque(maxlen=32)
    physical = [(0, 1500, 1500)]
    smooth = None
    poses = []
    for tick in range(1, 901):
        now = tick * 20
        for axis, key in enumerate(("PAN", "TILT")):
            actual[axis] += max(-24, min(24, target[key] - actual[axis]))
        physical.append((now, *actual))
        history.append((now, *actual))
        if tick % 10 == 0:
            stamp = max(0, now - delay)
            camera = w.pose_at_capture(physical, stamp, actual)
            estimate = w.pose_at_capture(history, stamp, actual)
            desired = [w.frame_target(estimate[0], (1750 - camera[0]) / 875),
                       w.frame_target(estimate[1], (1300 - camera[1]) / 804)]
            smooth = [w.smooth_person_target(None if smooth is None else smooth[i],
                                            desired[i], .20) for i in range(2)]
        if tick % 3 == 0 and smooth is not None:
            for axis, key in enumerate(("PAN", "TILT")):
                before = target[key]
                w.track_axis(None, key, actual[axis], before, 0, smooth[axis], max_steps=1)
                assert abs(target[key] - before) <= 80
                assert abs(target[key] - actual[axis]) <= 240
            poses.append(tuple(actual))
    for axis, expected in enumerate((1750, 1300)):
        values = [pose[axis] for pose in poses[-30:]]
        assert max(values) - min(values) <= 24, (delay, values)
        assert abs(values[-1] - expected) <= 85, (delay, expected, values[-1])
print("PASS: person 60 ms single-step cadence with 5 Hz results and 150/300 ms delay; bounded lead; no sustained sweep")

# Noisy box centres around a stationary world destination must not cause
# alternating PWM commands. Persistent movement still converges promptly.
target.update(PAN=1500, TILT=1500)
smooth = 1500
corrections = []
for tick in range(40):
    desired = 1600 if tick % 2 else 1400
    smooth = w.smooth_person_target(smooth, desired, .20)
    before = target['PAN']
    w.track_axis(None, 'PAN', before, before, 0, smooth, max_steps=1)
    if target['PAN'] != before:
        corrections.append(target['PAN'])
assert not corrections, corrections
for tick in range(3):
    smooth = w.smooth_person_target(smooth, 1750, .20)
assert abs(smooth - 1750) < 20, smooth
assert w.smooth_person_target(None, 1750, .20) == 1750
assert w.smooth_person_target(1500, 1750, 0) == 1500
print('PASS: alternating 100 us destination jitter does not reverse PWM; sustained change settles within three 5 Hz results; pause reset')
