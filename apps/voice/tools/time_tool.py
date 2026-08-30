"""
Time Tool - Get current date and time
"""
from datetime import datetime, timedelta, timezone as datetime_timezone
from tools import register_tool


CHINA_STANDARD_TIME = datetime_timezone(timedelta(hours=8), "CST")
WEEKDAY_NAMES = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def get_time(timezone: str = "local") -> str:
    """Get current UTC or China Standard Time."""
    selected_timezone = (
        datetime_timezone.utc if timezone == "utc" else CHINA_STANDARD_TIME
    )
    now = datetime.now(selected_timezone)
    return now.strftime("%Y-%m-%d %H:%M:%S")


def format_spoken_time(user_input: str, now=None) -> str:
    """Format a short local answer for explicit time/date voice queries."""
    current = now or datetime.now(CHINA_STANDARD_TIME)
    normalized = "".join(str(user_input).lower().split())

    if "星期几" in normalized or "周几" in normalized:
        return f"今天是{WEEKDAY_NAMES[current.weekday()]}。"
    if any(hint in normalized for hint in (
            "几号", "当前日期", "今天日期", "今天是几")):
        return f"今天是{current.year}年{current.month}月{current.day}日。"

    hour = current.hour
    if hour < 6:
        period = "凌晨"
    elif hour < 12:
        period = "上午"
    elif hour < 13:
        period = "中午"
    elif hour < 18:
        period = "下午"
    else:
        period = "晚上"
    display_hour = hour % 12 or 12
    minute = "整" if current.minute == 0 else f"{current.minute:02d}分"
    return f"现在是{period}{display_hour}点{minute}。"


register_tool(
    name="get_time",
    schema={
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "获取当前日期和时间",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "时区，默认 local（本地时间）",
                        "enum": ["local", "utc"],
                        "default": "local"
                    }
                },
                "required": []
            }
        }
    },
    handler=get_time
)
