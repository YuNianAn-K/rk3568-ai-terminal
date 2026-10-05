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
SCORE_THRESHOLD = 0.55
MAX_BOXES = 10


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


def decode_people(boxes, classes, scores, count):
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
    return sorted(result, key=lambda item: item["score"], reverse=True)


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
    started = time.monotonic()
    verify_model()
    import cv2
    import numpy as np
    from tflite_runtime.interpreter import Interpreter

    cv2.setNumThreads(1)
    interpreter = Interpreter(model_path=str(MODEL), num_threads=2)
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
              startup_ms=round((time.monotonic() - started) * 1000, 3),
              rss_kib=rss_kib()))
    seq = 0
    previous_wall, previous_cpu = time.monotonic(), time.process_time()
    while True:
        raw = read_frame(sys.stdin.buffer)
        if raw is None:
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
        people = decode_people(boxes[0], classes[0], scores[0], float(count[0]))
        finished, cpu = time.monotonic(), time.process_time()
        seq += 1
        emit(dict(event="result", seq=seq, boxes=people,
                  preprocess_ms=round((preprocessed - begin) * 1000, 3),
                  inference_ms=round((invoked - preprocessed) * 1000, 3),
                  postprocess_ms=round((finished - invoked) * 1000, 3),
                  detector_total_ms=round((finished - begin) * 1000, 3),
                  worker_cpu_one_core_pct=round(100 * (cpu - previous_cpu) /
                                                max(0.001, finished - previous_wall), 2),
                  worker_rss_kib=rss_kib()))
        previous_wall, previous_cpu = finished, cpu


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("PERSON_DETECTOR_ERROR: " + str(error), file=sys.stderr, flush=True)
        sys.exit(1)
