#!/usr/bin/env python3
"""Small diagnostic client for the local AI voice service socket."""

import argparse
import json
import socket
import sys
import time


def read_message(stream, sock, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("timed out waiting for voice service")
    sock.settimeout(remaining)
    line = stream.readline()
    if not line:
        raise ConnectionError("voice service disconnected")
    return json.loads(line.decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="AI voice socket client")
    parser.add_argument("command", choices=("status", "start", "stop", "cancel"))
    parser.add_argument("--socket", default="/tmp/ai-voice.sock")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + args.timeout
    try:
        sock.settimeout(args.timeout)
        sock.connect(args.socket)
        stream = sock.makefile("rwb", buffering=0)
        first = read_message(stream, sock, deadline)
        print(json.dumps(first, ensure_ascii=False))

        payload = json.dumps({"command": args.command}, ensure_ascii=False)
        stream.write((payload + "\n").encode("utf-8"))

        while True:
            message = read_message(stream, sock, deadline)
            print(json.dumps(message, ensure_ascii=False))
            if args.command == "status" and message.get("type") == "snapshot":
                return 0
            if message.get("type") == "ack":
                return 0 if message.get("accepted") else 2
    except (OSError, ValueError, TimeoutError, ConnectionError) as e:
        print(f"voice socket client failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
