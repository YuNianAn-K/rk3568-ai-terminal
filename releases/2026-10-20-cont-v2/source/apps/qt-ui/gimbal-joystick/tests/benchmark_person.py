"""Offline board benchmark of the real worker; does not open camera or UART."""
import argparse
import json
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import time


def percentile(values, fraction):
    return sorted(values)[round((len(values) - 1) * fraction)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path)
    parser.add_argument("--frames", type=int, default=30)
    args = parser.parse_args()
    if args.frames < 5:
        parser.error("at least five frames required")
    import cv2
    import numpy as np
    if args.image:
        image = cv2.imread(str(args.image))
        if image is None:
            raise ValueError("cannot load benchmark image")
        image = cv2.cvtColor(cv2.resize(image, (640, 480)), cv2.COLOR_BGR2RGB)
    else:
        image = np.zeros((480, 640, 3), dtype=np.uint8)
    raw = image.tobytes()
    packet = struct.pack("<I", len(raw)) + raw
    worker = Path(__file__).resolve().parents[1] / "person_detector.py"
    process = subprocess.Popen([sys.executable, "-B", str(worker)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    samples = []
    try:
        ready = json.loads(process.stdout.readline())
        assert ready["event"] == "ready", ready
        print(json.dumps(ready), flush=True)
        for seq in range(1, args.frames + 1):
            begin = time.monotonic()
            process.stdin.write(packet)
            process.stdin.flush()
            result = json.loads(process.stdout.readline())
            assert result["event"] == "result" and result["seq"] == seq, result
            result["pipe_to_result_ms"] = round((time.monotonic() - begin) * 1000, 3)
            print(json.dumps(result), flush=True)
            samples.append(result)
            time.sleep(max(0, .1 - (time.monotonic() - begin)))
        process.stdin.close()
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    measured = samples[3:]
    summary = dict(event="summary", input="stored_image" if args.image else "black_frame",
                   frames=len(samples), warmup_frames=3, live_camera=False,
                   detected_people=sorted(set(len(item["boxes"]) for item in measured)))
    for key in ("inference_ms", "pipe_to_result_ms", "worker_cpu_one_core_pct", "worker_rss_kib"):
        values = [item[key] for item in measured]
        summary[key + "_median"] = round(statistics.median(values), 3)
        summary[key + "_p95"] = round(percentile(values, .95), 3)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
