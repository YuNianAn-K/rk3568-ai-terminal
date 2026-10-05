"""Exact voice intents and bounded requests to the running gimbal application."""
import json
import re
import socket
import time
import uuid

SOCKET_PATH = "/tmp/gimbal-tracking.sock"
COMMANDS = {"开始跟踪人物": "START_TRACKING", "停止跟踪": "STOP_TRACKING",
            "停止跟踪人物": "STOP_TRACKING"}


def normalize(text):
    if not isinstance(text, str):
        return ""
    return "".join(text.split()).rstrip("。！!，,")


def parse_tracking_action(text):
    return COMMANDS.get(normalize(text))


def needs_tracking_clarification(text):
    value = normalize(text)
    return "跟踪" in value or "跟随" in value


class TrackingControlError(RuntimeError):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


class PersonTracking:
    def __init__(self, socket_path=SOCKET_PATH, timeout=5.0):
        self.socket_path = socket_path
        self.timeout = timeout

    def execute(self, command):
        if command not in {"START_TRACKING", "STOP_TRACKING"}:
            raise ValueError("unsupported tracking action")
        if not hasattr(socket, "AF_UNIX"):
            raise TrackingControlError("unavailable")
        request_id = uuid.uuid4().hex
        request = dict(version=1, request_id=request_id, command=command,
                       target="PERSON", issued_ms=int(time.monotonic() * 1000))
        deadline = time.monotonic() + self.timeout
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(self.timeout)
                conn.connect(self.socket_path)
                conn.sendall((json.dumps(request) + "\n").encode())
                data = b""
                while b"\n" not in data:
                    conn.settimeout(max(.001, deadline - time.monotonic()))
                    if time.monotonic() >= deadline:
                        raise TrackingControlError("timeout")
                    chunk = conn.recv(4096)
                    if not chunk:
                        raise TrackingControlError("disconnected")
                    data += chunk
                    if len(data) > 4096:
                        raise TrackingControlError("bad_reply")
                reply = json.loads(data.split(b"\n", 1)[0])
        except socket.timeout as error:
            raise TrackingControlError("timeout") from error
        except OSError as error:
            raise TrackingControlError("unavailable") from error
        except (ValueError, UnicodeError) as error:
            raise TrackingControlError("bad_reply") from error
        if (not isinstance(reply, dict) or reply.get("version") != 1 or
                reply.get("request_id") != request_id or
                type(reply.get("accepted")) is not bool or
                not isinstance(reply.get("code"), str) or
                not re.fullmatch(r"[a-z_]{1,32}", reply["code"])):
            raise TrackingControlError("bad_reply")
        if reply["accepted"] and reply["code"] != (
                "active" if command == "START_TRACKING" else "off"):
            raise TrackingControlError("bad_reply")
        if not reply["accepted"] and reply["code"] in {"active", "off"}:
            raise TrackingControlError("bad_reply")
        return reply


def result_message(reply):
    return {
        "active": "已开始跟踪选中的人物。",
        "off": "云台已停止跟踪。",
        "select_target": "请先在云台画面开启人物检测，并选择人物框。",
        "position_unknown": "请先在云台画面回中位，再开启人物检测。",
        "camera_unavailable": "摄像头当前不可用，未开始跟踪。",
        "inactive": "请先打开云台摄像页面。",
        "busy": "云台正在处理其他操作，请稍后重试。",
        "lost": "人物目标丢失，未继续跟踪。",
        "timeout": "云台状态未确认，已请求停止，请查看板屏。",
        "controller_unavailable": "云台控制连接不可用，请查看板屏。",
        "cancelled": "跟踪请求已取消。",
    }.get(reply.get("code"), "云台未确认操作，请查看板屏。")
