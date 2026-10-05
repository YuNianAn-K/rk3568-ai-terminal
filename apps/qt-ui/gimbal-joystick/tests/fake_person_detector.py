"""Test-only process fixture. Never package as the application detector."""
import json
import os
import struct
import sys
import time

mode = os.environ.get("PERSON_TEST_MODE", "ok")
if mode == "crash":
    sys.exit(5)
print(json.dumps(dict(event="ready")), flush=True)
seq = 0
while True:
    header = sys.stdin.buffer.read(4)
    if not header:
        break
    assert len(header) == 4
    length = struct.unpack("<I", header)[0]
    raw = sys.stdin.buffer.read(length)
    assert length == 640 * 480 * 3 and len(raw) == length
    assert raw[:3] == bytes((255, 0, 0)), "Qt must send RGB, not BGR or RGBA"
    time.sleep(1.1 if mode == "late" else .12)
    seq += 1
    print(json.dumps(dict(event="result", seq=seq + (10 if mode == "bad_seq" else 0),
                         boxes=[dict(left=.1, top=.2, right=.4, bottom=.8, score=.9)],
                         inference_ms=120)), flush=True)
