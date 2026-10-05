#!/usr/bin/env python3
"""Isolated file/synthetic KWS check; never opens mic, cloud or UART."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--wav", help="Local diagnostic WAV, never uploaded")
    args = parser.parse_args()
    from wake.sherpa_keyword import ChineseWakeDetector, MODEL_FILES
    from audio.pcm import read_wav
    start = time.monotonic()
    detector = ChineseWakeDetector(args.model)
    load_ms = int((time.monotonic() - start) * 1000)
    np = detector.np
    if args.wav:
        with open(args.wav, "rb") as source:
            data = source.read(700001)
        if len(data) > 700000:
            raise ValueError("Diagnostic input limited to 20 seconds")
        pcm, _ = read_wav(data, require_16k=True)
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    else:
        samples = np.zeros(32000, dtype=np.float32)
    stream = detector.model.create_stream()
    hits = 0
    decode_start = time.monotonic()
    # Incremental feed also exercises the production streaming API.
    for frame in [samples[i:i+1600] for i in range(0, len(samples), 1600)] + [np.zeros(16000, dtype=np.float32)]:
        stream.accept_waveform(16000, frame)
        while detector.model.is_ready(stream):
            detector.model.decode_stream(stream)
            if detector.model.get_result(stream) == "小爱同学":
                hits += 1
                detector.model.reset_stream(stream)
    rss_kb = None
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                rss_kb = int(line.split()[1])
    except OSError:
        pass
    print(json.dumps(dict(load_ms=load_ms, decode_ms=int((time.monotonic()-decode_start)*1000),
                          input_seconds=len(samples)/16000, wake_hits=hits,
                          model_bytes=sum(Path(args.model, name).stat().st_size for name in MODEL_FILES.values()),
                          rss_kb=rss_kb), ensure_ascii=True))
    if not args.wav and hits:
        raise RuntimeError("Silence unexpectedly triggered wake")


if __name__ == "__main__": main()
