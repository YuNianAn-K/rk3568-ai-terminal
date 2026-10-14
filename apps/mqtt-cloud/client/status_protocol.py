"""Read-only device status protocol. No MQTT or hardware dependencies."""
import hashlib
import json
import math
import platform
import re
import time
from pathlib import Path

ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
REQUEST_ID = re.compile(r"^[a-f0-9]{24}$")
TTL_MS = 15000
STATUS_MS = 30000


def valid_id(value):
    return isinstance(value, str) and ID.fullmatch(value) is not None


def topics(device_id, controller_id=None):
    if not valid_id(device_id) or (controller_id is not None and not valid_id(controller_id)):
        raise ValueError("invalid identity")
    root = "rk3568/v1/devices/" + device_id
    return {"request": root + "/request/" + (controller_id or "+"), "status": root + "/status",
            "reply": root + "/reply/" + (controller_id or "+")}


def encode(data):
    return json.dumps(data, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")


def decode(payload):
    if len(payload) > 4096:
        raise ValueError("oversized request")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result
    return json.loads(payload.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite number")))


def validate_request(data, device_id, controllers, now):
    keys = {"version", "type", "request_id", "sender", "target", "action", "issued_at", "expires_at"}
    if not isinstance(data, dict) or set(data) != keys:
        return False
    if type(data["version"]) is not int or data["version"] != 1 or data["type"] != "request":
        return False
    if not isinstance(data["request_id"], str) or not REQUEST_ID.fullmatch(data["request_id"]):
        return False
    if not valid_id(data["sender"]) or data["sender"] not in controllers:
        return False
    if data["target"] != device_id or data["action"] != "get_status":
        return False
    issued, expires = data["issued_at"], data["expires_at"]
    return (type(issued) is int and type(expires) is int and issued <= now + 1000
            and now < expires and 0 < expires - issued <= TTL_MS)


def sample_linux(proc=Path("/proc")):
    """Only kernel observations; unavailable fields stay null with an error marker."""
    result = {"source": "linux-proc", "arch": platform.machine(), "uptime_s": None,
              "memory_kib": None, "load_1m": None, "sample_errors": []}
    if platform.system() != "Linux" and proc == Path("/proc"):
        raise RuntimeError("real sampling requires Linux")
    try:
        uptime = float((proc / "uptime").read_text().split()[0])
        if not math.isfinite(uptime) or uptime < 0:
            raise ValueError()
        result["uptime_s"] = round(uptime, 2)
    except (OSError, ValueError, IndexError):
        result["sample_errors"].append("uptime_unavailable")
    try:
        memory = {}
        for line in (proc / "meminfo").read_text().splitlines():
            fields = line.split()
            if fields[0] in ("MemTotal:", "MemAvailable:") and len(fields) == 3 and fields[2] == "kB":
                memory[fields[0][:-1]] = int(fields[1])
        total, available = memory["MemTotal"], memory["MemAvailable"]
        if not 0 <= available <= total or total <= 0:
            raise ValueError()
        result["memory_kib"] = {"total": total, "available": available}
    except (OSError, ValueError, KeyError, IndexError):
        result["sample_errors"].append("memory_unavailable")
    try:
        load = float((proc / "loadavg").read_text().split()[0])
        if not math.isfinite(load) or load < 0:
            raise ValueError()
        result["load_1m"] = load
    except (OSError, ValueError, IndexError):
        result["sample_errors"].append("load_unavailable")
    return result


def status(device_id, session_id, now, sampler=sample_linux):
    return {"version": 1, "type": "status", "device_id": device_id,
            "session_id": session_id, "online": True, "simulated": False,
            "updated_at": now, "expires_at": now + STATUS_MS,
            "capabilities": ["get_status"], "system": sampler()}


def offline(device_id, session_id):
    # A Will is prepared at CONNECT, so its actual disconnect time is unknown.
    return {"version": 1, "type": "status", "device_id": device_id,
            "session_id": session_id, "online": False, "simulated": False,
            "updated_at": None, "expires_at": None}


class RequestHandler:
    def __init__(self, device_id, controllers, session_id, sampler=sample_linux,
                 clock=lambda: int(time.time() * 1000), monotonic=time.monotonic, capacity=100):
        if not valid_id(device_id) or not controllers or not all(valid_id(x) for x in controllers):
            raise ValueError("invalid identities")
        self.device_id, self.controllers, self.session_id = device_id, set(controllers), session_id
        self.sampler, self.clock, self.monotonic, self.capacity = sampler, clock, monotonic, capacity
        self.cache = {}

    def handle(self, topic, payload, retained=False):
        if retained:
            return None
        try:
            request = decode(payload)
        except (ValueError, UnicodeError, TypeError):
            return None
        now = self.clock()
        if not validate_request(request, self.device_id, self.controllers, now):
            return None
        if topic != topics(self.device_id, request["sender"])["request"]:
            return None
        tick = self.monotonic()
        self.cache = {key: entry for key, entry in self.cache.items() if entry[0] > tick}
        key = (request["sender"], request["request_id"])
        digest = hashlib.sha256(encode(request)).digest()
        previous = self.cache.get(key)
        if previous:
            # A connection's cached snapshot must not revive that connection after its Will.
            saved_reply = json.loads(previous[2][1])
            if saved_reply.get("data", {}).get("session_id", self.session_id) != self.session_id:
                return None
            return previous[2] if previous[1] == digest else None
        # Do not evict live IDs: overflow must not allow repeat sampling.
        if len(self.cache) >= self.capacity:
            return None
        try:
            snapshot = status(self.device_id, self.session_id, now, self.sampler)
            reply = {"version": 1, "type": "reply", "request_id": request["request_id"],
                     "sender": self.device_id, "target": request["sender"], "action": "get_status",
                     "simulated": False, "status": "success", "updated_at": now,
                     "expires_at": request["expires_at"], "data": snapshot}
        except (OSError, RuntimeError, ValueError):
            reply = {"version": 1, "type": "reply", "request_id": request["request_id"],
                     "sender": self.device_id, "target": request["sender"], "action": "get_status",
                     "simulated": False, "status": "failed", "reason": "sample_unavailable",
                     "updated_at": now, "expires_at": request["expires_at"]}
        result = (topics(self.device_id, request["sender"])["reply"], encode(reply))
        self.cache[key] = (tick + 60, digest, result)
        return result
