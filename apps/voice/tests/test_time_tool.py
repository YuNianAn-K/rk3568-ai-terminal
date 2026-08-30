#!/usr/bin/env python3
"""Offline tests for explicit voice-tool timezone handling."""

import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import get_local_response
from tools.time_tool import format_spoken_time, get_time


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        instant = cls(2026, 8, 24, 5, 3, 4, tzinfo=timezone.utc)
        if tz is None:
            return instant.replace(tzinfo=None)
        return instant.astimezone(tz)


class TimeToolTests(unittest.TestCase):
    def test_local_time_is_china_standard_time(self):
        with mock.patch("tools.time_tool.datetime", FixedDateTime):
            self.assertEqual(get_time("local"), "2026-08-24 13:03:04")

    def test_utc_time_remains_utc(self):
        with mock.patch("tools.time_tool.datetime", FixedDateTime):
            self.assertEqual(get_time("utc"), "2026-08-24 05:03:04")


    def test_spoken_time_formats_time_date_and_weekday(self):
        current = datetime(2026, 8, 24, 15, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(format_spoken_time("现在几点", current), "现在是下午3点04分。")
        self.assertEqual(format_spoken_time("今天几号", current), "今天是2026年8月24日。")
        self.assertEqual(format_spoken_time("今天星期几", current), "今天是星期一。")

    def test_local_response_is_conservative(self):
        self.assertEqual(get_local_response("你好。"), "你好，有什么可以帮你的吗？")
        self.assertTrue(get_local_response("你好，现在几点钟了？"))
        self.assertEqual(get_local_response("给我讲个笑话"), "")
        self.assertEqual(get_local_response("北京天气怎么样"), "")


if __name__ == "__main__":
    unittest.main()
