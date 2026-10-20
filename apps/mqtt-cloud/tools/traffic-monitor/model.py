"""Public-IP monitoring estimates, never a billing meter or network cutoff."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math

TZ = timezone(timedelta(hours=8))
GB = 1_000_000_000


def month_key(now):
    return datetime.fromtimestamp(now, TZ).strftime("%Y-%m")


def bounds(now):
    current = datetime.fromtimestamp(now, TZ)
    month = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    day = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(month.timestamp() * 1000), int(day.timestamp() * 1000)


def metric_points(payload, instance, ip):
    if payload.get("Success") is not True:
        raise ValueError("monitor query rejected")
    points = payload.get("Datapoints")
    points = json.loads(points) if isinstance(points, str) else points
    if not isinstance(points, list):
        raise ValueError("invalid metrics")
    result = {}
    for point in points:
        if point.get("instanceId") != instance or point.get("ip") != ip:
            raise ValueError("wrong metric identity")
        stamp, rate = point.get("timestamp"), point.get("Average")
        if type(stamp) is not int or type(rate) not in (int, float) or not math.isfinite(rate) or rate < 0:
            raise ValueError("invalid metric point")
        if stamp in result and result[stamp] != rate:
            raise ValueError("conflicting timestamps")
        result[stamp] = rate
    return result


def summarize(points, now, period=60):
    month, day = bounds(now)
    end = int(now * 1000)
    valid = {s: r for s, r in points.items() if month < s <= end}
    # Integrate complete reported intervals only, without filling gaps with zeros.
    mp = {s: r for s, r in valid.items() if s - period * 1000 >= month}
    dp = {s: r for s, r in valid.items() if s - period * 1000 >= day}
    latest = max(valid, default=None)
    age = None if latest is None else now - latest / 1000
    return {"bps": valid[latest] if latest is not None and 0 <= age <= 180 else None,
            "latest_at": latest / 1000 if latest is not None else None,
            "month_gb": sum(mp.values()) * period / 8 / GB if mp else None,
            "day_gb": sum(dp.values()) * period / 8 / GB if dp else None,
            "covered_seconds": len(mp) * period,
            "elapsed_seconds": max(0, (end - month) / 1000)}


def quota_view(used_gb, quota_gb=20):
    if used_gb is None:
        return {"remaining_gb": None, "estimate_cny": None, "level": "unknown"}
    if not math.isfinite(used_gb) or used_gb < 0:
        raise ValueError("invalid usage")
    level = "over" if used_gb >= quota_gb else "critical" if used_gb >= 18 else "warning" if used_gb >= 15 else "notice" if used_gb >= 10 else "normal"
    return {"remaining_gb": max(0, quota_gb - used_gb),
            "estimate_cny": float(max(Decimal(0), Decimal(str(used_gb)) - Decimal(str(quota_gb))) * Decimal("0.80")),
            "level": level}


def bill_summary(items, instance):
    matching, other = [], 0
    for item in items:
        if item.get("ProductCode") != "cdt" and item.get("PipCode") != "cdt":
            raise ValueError("unexpected billing product")
        if item.get("InstanceID") != instance:
            other += 1
            continue
        if item.get("Currency") != "CNY":
            raise ValueError("unsupported billing currency")
        amount = Decimal(str(item["PretaxAmount"]))
        if not amount.is_finite():
            raise ValueError("invalid amount")
        matching.append(amount)
    return {"cny": float(sum(matching)) if matching else None,
            "matched_rows": len(matching), "other_rows": other,
            "status": "已出账（约延迟24小时）" if matching else "暂无可归属此实例的账单，非零费用证明"}
