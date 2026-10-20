#!/usr/bin/env python3
"""Palm-center samples from the same YUYV frames shown by Qt."""

import json
import os
import struct
import sys
import time

PROCESS_STARTED = time.monotonic()

import cv2
import numpy as np
from tflite_runtime.interpreter import Interpreter


WIDTH, HEIGHT = 640, 480
FRAME_BYTES = WIDTH * HEIGHT * 2
INPUT_SIZE = 192
MODEL = os.path.join(os.path.dirname(__file__), "palm_detection_lite.tflite")
TIMING = os.environ.get("GIMBAL_TIMING") == "1"


def anchors():
    result = []
    for stride, count in ((8, 2), (16, 6)):
        size = INPUT_SIZE // stride
        for y in range(size):
            for x in range(size):
                result.extend([((x + 0.5) / size, (y + 0.5) / size)] * count)
    return np.asarray(result, dtype=np.float32)


ANCHORS = anchors()


def read_exact(stream, length):
    result = bytearray()
    while len(result) < length:
        chunk = stream.read(length - len(result))
        if not chunk:
            return None
        result.extend(chunk)
    return result


def detect(interpreter, raw):
    started = time.monotonic()
    yuyv = np.frombuffer(raw, dtype=np.uint8).reshape(HEIGHT, WIDTH, 2)
    rgb = cv2.cvtColor(yuyv, cv2.COLOR_YUV2RGB_YUY2)
    resized = cv2.resize(rgb, (INPUT_SIZE, 144))
    image = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.uint8)
    image[24:168] = resized
    interpreter.set_tensor(interpreter.get_input_details()[0]["index"],
                           image[None].astype(np.float32) / 255.0)
    start = time.monotonic()
    interpreter.invoke()
    invoked = time.monotonic()

    def finish(result):
        finished = time.monotonic()
        result["inference_ms"] = round((invoked - start) * 1000, 3)
        if TIMING:
            result.update(preprocess_ms=round((start - started) * 1000, 3),
                          postprocess_ms=round((finished - invoked) * 1000, 3),
                          detector_total_ms=round((finished - started) * 1000, 3))
        return result

    boxes = interpreter.get_tensor(interpreter.get_output_details()[0]["index"])[0]
    logits = interpreter.get_tensor(interpreter.get_output_details()[1]["index"])[0, :, 0]
    scores = 1.0 / (1.0 + np.exp(-np.clip(logits, -100, 100)))
    best = int(np.argmax(scores))
    score = float(scores[best])
    if score < 0.80:
        return finish({"found": False, "score": round(score, 3)})

    # Decode MediaPipe SSD centers, then map 192x192 letterbox back to 640x480.
    centers = ANCHORS + boxes[:, :2] / INPUT_SIZE
    x = float(centers[best, 0])
    y = float((centers[best, 1] * INPUT_SIZE - 24) / 144)
    width = float(boxes[best, 2] / INPUT_SIZE)
    height = float(boxes[best, 3] / INPUT_SIZE * INPUT_SIZE / 144)
    if not (0.05 < x < 0.95 and 0.05 < y < 0.95 and
            0.08 < width < 0.75 and 0.08 < height < 0.85):
        return finish({"found": False, "score": round(score, 3)})

    # Overlapping anchors describe one palm. A second distant high-score peak
    # means the target is ambiguous, so the controller must not move.
    distant = (np.abs(centers[:, 0] - centers[best, 0]) > max(0.12, width * 0.7)) | (
        np.abs(centers[:, 1] - centers[best, 1]) > max(0.12, height * 0.7))
    ambiguous = bool(np.any((scores > 0.80) & distant))
    return finish({"found": not ambiguous, "ambiguous": ambiguous,
            "x": round(x, 4), "y": round(y, 4),
            "score": round(score, 3)})


def main():
    initialized = time.monotonic()
    interpreter = Interpreter(model_path=MODEL, num_threads=2)
    interpreter.allocate_tensors()
    if TIMING:
        print(json.dumps({"event": "timing", "type": "model_ready",
                          "startup_ms": round((time.monotonic() - PROCESS_STARTED) * 1000, 3),
                          "model_init_ms": round((time.monotonic() - initialized) * 1000, 3)}),
              flush=True)
    stream = sys.stdin.buffer
    while True:
        header = read_exact(stream, 4)
        if header is None:
            break
        length = struct.unpack("<I", header)[0]
        if length != FRAME_BYTES:
            raise ValueError("unexpected video frame size")
        frame = read_exact(stream, length)
        if frame is None:
            break
        print(json.dumps(detect(interpreter, frame)), flush=True)


if __name__ == "__main__":
    main()
