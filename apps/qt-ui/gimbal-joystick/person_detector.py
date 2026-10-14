#!/usr/bin/env python3
"""Person boxes from Qt's RGB preview frames; no camera or UART access."""

import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import zipfile

WIDTH, HEIGHT = 640, 480
FRAME_BYTES = WIDTH * HEIGHT * 3
MODEL = Path(__file__).with_name("person_detection.tflite")
MODEL_SHA256 = "cbdecd08b44c5dea3821f77c5468e2936ecfbf43cde0795a2729fdb43401e58b"
# Weak boxes are only for continuing an already confirmed geometric target.
# Acquisition and visible unselected boxes use the stricter QML threshold.
SCORE_THRESHOLD = 0.40
MAX_BOXES = 10
INFERENCE_THREADS = 3


def box_overlap(a, b):
    intersection = (max(0, min(a['right'], b['right']) - max(a['left'], b['left'])) *
                    max(0, min(a['bottom'], b['bottom']) - max(a['top'], b['top'])))
    area_a = (a['right'] - a['left']) * (a['bottom'] - a['top'])
    area_b = (b['right'] - b['left']) * (b['bottom'] - b['top'])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0, intersection, area_a, area_b


def suppress_duplicates(boxes):
    """Keep strong overlapping people; suppress weak contained fragments only.

    Containment is evidence of a duplicate, not proof of person identity.
    Two reliable nested detections remain available for ambiguity handling.
    """
    kept = []
    for box in sorted(boxes, key=lambda item: item['score'], reverse=True):
        duplicate = False
        for other in kept:
            iou, intersection, area, other_area = box_overlap(box, other)
            weak_fragment = (box['score'] < .55 and other['score'] >= .55 and
                             other['score'] - box['score'] >= .08 and
                             0 < area <= .75 * other_area and intersection / area >= .90)
            if iou >= .65 or weak_fragment:
                duplicate = True
                break
        if not duplicate:
            kept.append(box)
    return kept


class CandidateFilter:
    """Require three consistent sightings for new weak candidates.

    Confirmed candidates survive up to two missed results, but only boxes
    from the current frame are emitted. No predicted boxes steer the gimbal.
    """
    def __init__(self):
        self.tracks = []

    def update(self, boxes):
        previous = self.tracks
        current, result, used = [], [], set()
        for box in boxes:
            matches = sorted(((box_overlap(box, track['box'])[0], i)
                              for i, track in enumerate(previous) if i not in used), reverse=True)
            matched = (matches and matches[0][0] >= .40 and
                       (len(matches) == 1 or matches[0][0] - matches[1][0] >= .15))
            hits, confirmed = 1, box['score'] >= .55
            if matched:
                index = matches[0][1]
                used.add(index)
                track = previous[index]
                hits = track['hits'] + 1 if track['missed'] == 0 else 1
                confirmed = confirmed or track['confirmed'] or hits >= 3
            current.append(dict(box=box, hits=hits, confirmed=confirmed, missed=0))
            if confirmed:
                result.append(box)
        for index, track in enumerate(previous):
            if index not in used and track['missed'] < 2:
                current.append(dict(track, missed=track['missed'] + 1))
        self.tracks = current[:MAX_BOXES * 3]
        return result


def read_exact(stream, length):
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            if data:
                raise ValueError("truncated frame")
            return None
        data.extend(chunk)
    return data


def read_frame(stream):
    header = read_exact(stream, 4)
    if header is None:
        return None
    if struct.unpack("<I", header)[0] != FRAME_BYTES:
        raise ValueError("unexpected RGB frame size")
    data = read_exact(stream, FRAME_BYTES)
    if data is None:
        raise ValueError("missing frame payload")
    return data


def decode_people(boxes, classes, scores, count, suppress=True):
    """The pinned model returns [ymin, xmin, ymax, xmax], person class 0."""
    if not math.isfinite(float(count)) or not 0 <= count <= MAX_BOXES:
        raise ValueError("invalid detection count")
    count = int(count)
    if min(len(boxes), len(classes), len(scores)) < count:
        raise ValueError("incomplete detector output")
    result = []
    for box, label, score in zip(boxes[:count], classes[:count], scores[:count]):
        values = [float(v) for v in box] + [float(label), float(score)]
        if len(box) != 4 or not all(math.isfinite(v) for v in values):
            raise ValueError("non-finite or invalid detector output")
        if float(label) != 0.0 or not SCORE_THRESHOLD <= float(score) <= 1.0:
            continue
        top, left, bottom, right = [max(0.0, min(1.0, float(v))) for v in box]
        if right <= left or bottom <= top:
            continue
        result.append(dict(left=round(left, 5), top=round(top, 5),
                           right=round(right, 5), bottom=round(bottom, 5),
                           score=round(float(score), 4)))
    return suppress_duplicates(result) if suppress else result


def verify_model():
    if hashlib.sha256(MODEL.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError("person model SHA256 mismatch")
    with zipfile.ZipFile(MODEL) as archive:
        labels = archive.read("labelmap.txt").decode("utf-8").splitlines()
    if not labels or labels[0] != "person":
        raise ValueError("person label mapping mismatch")


def rss_kib():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    raise RuntimeError("process RSS unavailable")


def emit(data):
    print(json.dumps(data, allow_nan=False), flush=True)


def main():
    backend = os.environ.get('PERSON_DETECTOR_BACKEND', 'ssd')
    if backend == 'rknn':
        from person_rknn import main as npu_main
        return npu_main(sys.modules[__name__])
    if backend == 'rknn-v8':
        from person_rknn_v8 import main as npu_main
        return npu_main(sys.modules[__name__])
    if backend != 'ssd':
        raise ValueError('unsupported person detector backend')
    started = time.monotonic()
    verify_model()
    import cv2
    import numpy as np
    from tflite_runtime.interpreter import Interpreter

    cv2.setNumThreads(1)
    # Board timing: three threads reduce median/P95 without the four-thread
    # latency spikes. Leave headroom for preview, voice and bounded control.
    interpreter = Interpreter(model_path=str(MODEL), num_threads=INFERENCE_THREADS)
    interpreter.allocate_tensors()
    inputs, outputs = interpreter.get_input_details(), interpreter.get_output_details()
    if (len(inputs) != 1 or list(inputs[0]["shape"]) != [1, 300, 300, 3]
            or inputs[0]["dtype"] != np.uint8):
        raise ValueError("unsupported person model input")
    expected = ["TFLite_Detection_PostProcess" + suffix for suffix in ("", ":1", ":2", ":3")]
    by_name = {item["name"]: item for item in outputs}
    if set(by_name) != set(expected):
        raise ValueError("unsupported person model outputs")
    outputs = [by_name[name] for name in expected]
    for item, shape in zip(outputs, ([1, 10, 4], [1, 10], [1, 10], [1])):
        if list(item["shape"]) != shape or item["dtype"] != np.float32:
            raise ValueError("unsupported person output shape or dtype")
    emit(dict(event="ready", model_sha256=MODEL_SHA256, person_class=0,
              inference_threads=INFERENCE_THREADS,
              startup_ms=round((time.monotonic() - started) * 1000, 3),
              rss_kib=rss_kib()))
    seq = 0
    candidate_filter = CandidateFilter()
    capture = None
    if os.environ.get('PERSON_CAPTURE_DIR'):
        try:
            from person_capture import DiagnosticCapture
            capture = DiagnosticCapture(os.environ['PERSON_CAPTURE_DIR'])
            print('PERSON_CAPTURE_READY ' + str(capture.directory), file=sys.stderr, flush=True)
        except Exception as error:
            print('PERSON_CAPTURE_ERROR ' + str(error), file=sys.stderr, flush=True)
    previous_wall, previous_cpu = time.monotonic(), time.process_time()
    while True:
        raw = read_frame(sys.stdin.buffer)
        if raw is None:
            if capture:
                error = capture.close()
                print('PERSON_CAPTURE_END ' + json.dumps(dict(count=capture.count, error=error)),
                      file=sys.stderr, flush=True)
            return
        begin = time.monotonic()
        rgb = np.frombuffer(raw, dtype=np.uint8).reshape(HEIGHT, WIDTH, 3)
        # Direct resize matches the official SSD sample. Coordinates remain
        # normalized to the original image; Qt applies its preview letterbox.
        image = cv2.resize(rgb, (300, 300), interpolation=cv2.INTER_LINEAR)
        interpreter.set_tensor(inputs[0]["index"], image[None])
        preprocessed = time.monotonic()
        interpreter.invoke()
        invoked = time.monotonic()
        boxes, classes, scores, count = [interpreter.get_tensor(item["index"]) for item in outputs]
        raw_boxes = decode_people(boxes[0], classes[0], scores[0], float(count[0]), suppress=False)
        candidates = suppress_duplicates(raw_boxes)
        people = candidate_filter.update(candidates)
        finished, cpu = time.monotonic(), time.process_time()
        seq += 1
        emit(dict(event="result", seq=seq, boxes=people, candidate_count=len(candidates),
                  preprocess_ms=round((preprocessed - begin) * 1000, 3),
                  inference_ms=round((invoked - preprocessed) * 1000, 3),
                  postprocess_ms=round((finished - invoked) * 1000, 3),
                  detector_total_ms=round((finished - begin) * 1000, 3),
                  worker_cpu_one_core_pct=round(100 * (cpu - previous_cpu) /
                                                max(0.001, finished - previous_wall), 2),
                  worker_rss_kib=rss_kib()))
        if capture:
            capture.observe(raw, dict(seq=seq, model_sha256=MODEL_SHA256,
                inference_threads=INFERENCE_THREADS, raw_boxes=raw_boxes,
                candidates=candidates, boxes=people,
                inference_ms=round((invoked - preprocessed) * 1000, 3)))
            if capture.error:
                print('PERSON_CAPTURE_ERROR ' + capture.error, file=sys.stderr, flush=True)
                capture.close()
                capture = None
        previous_wall, previous_cpu = finished, cpu


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("PERSON_DETECTOR_ERROR: " + str(error), file=sys.stderr, flush=True)
        sys.exit(1)
