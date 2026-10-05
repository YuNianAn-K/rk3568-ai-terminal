"""Test-only bridge fixture: records stdin and never opens UART."""
import json
import os
import sys
import time

path = os.environ["PERSON_BRIDGE_TEST_LOG"]
print(json.dumps(dict(event="ready", track_capable=True, position_ready=True)), flush=True)
with open(path, "a", encoding="ascii") as log:
    for line in sys.stdin:
        log.write(line)
        log.flush()
        if line.strip() == "QUIT":
            break
        if line.startswith("PERSON_START"):
            parts = line.split()
            request_id = parts[1] if len(parts) == 2 else ""
            print(json.dumps(dict(event="tracking", state="searching", request_id=request_id)), flush=True)
            if os.environ.get("PERSON_BRIDGE_TEST_MODE") in ("proof", "bad_ack"):
                time.sleep(.15)
                print(json.dumps(dict(event="tracking", state="active",
                    request_id=request_id if os.environ["PERSON_BRIDGE_TEST_MODE"] == "proof" else "f" * 32)), flush=True)
        if line.startswith("CONTROL_STOP "):
            print(json.dumps(dict(event="stopped", pan="OFF", tilt="OFF",
                                  request_id=line.split()[1])), flush=True)
