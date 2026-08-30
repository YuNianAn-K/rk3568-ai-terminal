"""
Weather Tool - Get weather information via wttr.in
"""
import requests
from tools import register_tool


def get_weather(city: str = "auto") -> str:
    """Get weather for a city using wttr.in"""
    try:
        url = f"https://wttr.in/{city}?format=j1"
        resp = requests.get(url, timeout=10, headers={"Accept-Language": "zh-CN"})
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current_condition", [{}])[0]
        area = data.get("nearest_area", [{}])[0]

        area_name = area.get("areaName", [{}])[0].get("value", city)
        temp_c = current.get("temp_C", "?")
        feels_like = current.get("FeelsLikeC", "?")
        desc = current.get("lang_zh", [{}])[0].get("value",
              current.get("weatherDesc", [{}])[0].get("value", "未知"))
        humidity = current.get("humidity", "?")
        wind_speed = current.get("windspeedKmph", "?")

        return (f"{area_name}天气：{desc}，"
                f"温度{temp_c}°C（体感{feels_like}°C），"
                f"湿度{humidity}%，风速{wind_speed}km/h")
    except Exception as e:
        return f"获取天气失败: {e}"


register_tool(
    name="get_weather",
    schema={
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的当前天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，如 北京、上海、广州。不填则查询自动定位的天气"
                    }
                },
                "required": []
            }
        }
    },
    handler=get_weather
)
