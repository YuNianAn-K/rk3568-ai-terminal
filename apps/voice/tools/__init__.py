"""
Tool Registry - Function calling tool system
"""
import re

TOOL_REGISTRY = {}

LOCAL_RESPONSES = {
    "你好": "你好，有什么可以帮你的吗？",
    "你好你好": "你好，有什么可以帮你的吗？",
    "你好你好你好": "你好，有什么可以帮你的吗？",
    "你好呀": "你好，有什么可以帮你的吗？",
    "嗨": "你好，有什么可以帮你的吗？",
    "哈喽": "你好，有什么可以帮你的吗？",
    "哈啰": "你好，有什么可以帮你的吗？",
    "hello": "你好，有什么可以帮你的吗？",
    "hi": "你好，有什么可以帮你的吗？",
}
LOCAL_TIME_HINTS = (
    "几点", "几号", "星期几", "周几", "当前时间", "现在时间",
    "当前日期", "今天日期", "今天是几", "现在是几",
)


def register_tool(name, schema, handler):
    """Register a tool with its JSON schema and handler function"""
    TOOL_REGISTRY[name] = {"schema": schema, "handler": handler}


def get_tools_schema():
    """Return list of tool schemas for LLM API"""
    return [entry["schema"] for entry in TOOL_REGISTRY.values()]


def execute_tool(name, arguments):
    """Execute a registered tool and return result as string"""
    if name not in TOOL_REGISTRY:
        return f"未知工具: {name}"
    handler = TOOL_REGISTRY[name]["handler"]
    return handler(**arguments)


def get_local_response(user_input):
    """Return a deterministic fast response, or empty text for normal routing."""
    normalized = re.sub(r"[\s，。！？,.!?～~]+", "", str(user_input).lower())
    if any(hint in normalized for hint in LOCAL_TIME_HINTS):
        from tools.time_tool import format_spoken_time
        return format_spoken_time(normalized)
    return LOCAL_RESPONSES.get(normalized, "")


# Import tools to trigger registration
from tools import time_tool
from tools import weather_tool
