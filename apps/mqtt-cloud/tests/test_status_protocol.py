import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))
from status_protocol import RequestHandler, decode, encode, sample_linux, topics
from status_agent import load_config


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000000
        self.calls = 0
        self.tick = 0
        def sample():
            self.calls += 1
            return {"source": "test-fixture"}
        self.handler = RequestHandler("rk3568-01", ["phone-owner"], "a" * 32,
                                      sample, lambda: self.now, lambda: self.tick, capacity=2)
        self.topic = topics("rk3568-01", "phone-owner")["request"]
        self.request = {"version": 1, "type": "request", "request_id": "a" * 24,
                        "sender": "phone-owner", "target": "rk3568-01", "action": "get_status",
                        "issued_at": self.now, "expires_at": self.now + 15000}

    def handle(self, request=None, topic=None, retain=False):
        return self.handler.handle(topic or self.topic, encode(request or self.request), retain)

    def test_real_reply_routing_and_read_only_sampling(self):
        topic, payload = self.handle()
        reply = json.loads(payload)
        self.assertEqual(topic, topics("rk3568-01", "phone-owner")["reply"])
        self.assertFalse(reply["simulated"])
        self.assertEqual(reply["sender"], "rk3568-01")
        self.assertEqual(reply["request_id"], self.request["request_id"])
        self.assertEqual(reply["data"]["system"], {"source": "test-fixture"})
        self.assertNotIn("gimbal", reply["data"])

    def test_retained_wrong_device_topic_account_and_action_never_sample(self):
        self.assertIsNone(self.handle(retain=True))
        self.assertIsNone(self.handle(topic=topics("rk3568-01", "other")["request"]))
        self.assertIsNone(self.handle(topic=topics("other")["request"]))
        for change in [{"sender": "intruder"}, {"target": "other"}, {"action": "led_on"},
                       {"version": True}, {"version": 2}, {"request_id": "bad"}, {"extra": "UART PING"}]:
            self.assertIsNone(self.handle({**self.request, **change}))
        self.assertEqual(self.calls, 0)

    def test_expiry_boundaries_and_clock_reversal(self):
        self.assertIsNotNone(self.handle({**self.request, "request_id": "d" * 24,
                                         "issued_at": self.now + 500, "expires_at": self.now + 15500}))
        self.calls = 0
        self.handler.cache.clear()
        for change in [{"expires_at": self.now}, {"expires_at": self.now + 15001},
                       {"issued_at": self.now + 5000}, {"issued_at": True}, {"expires_at": "later"}]:
            self.assertIsNone(self.handle({**self.request, **change}))
        self.handle()
        self.now -= 5000
        self.assertIsNone(self.handle())
        self.assertEqual(self.calls, 1)

    def test_duplicate_reuses_reply_conflict_ignored_and_no_live_eviction(self):
        original = self.handle()
        self.assertEqual(self.handle(), original)
        self.assertIsNone(self.handle({**self.request, "expires_at": self.now + 14000}))
        self.handle({**self.request, "request_id": "b" * 24})
        self.assertIsNone(self.handle({**self.request, "request_id": "c" * 24}))
        self.assertEqual(self.handle(), original)
        self.assertEqual(self.calls, 2)
        self.handler.session_id = "b" * 32
        self.assertIsNone(self.handle())
        self.now += 15000
        self.assertIsNone(self.handle())

    def test_malformed_oversized_duplicate_fields_and_nonfinite(self):
        for payload in [b'{}', b'not JSON', b'\xff', b'x' * 4097,
                        b'{"version":1,"version":1}', b'{"value":NaN}', b'[]']:
            self.assertIsNone(self.handler.handle(self.topic, payload))
        with self.assertRaises(ValueError):
            decode(b'{"a":1,"a":2}')
        self.assertEqual(self.calls, 0)

    def test_sampler_failure_is_not_success(self):
        def fail():
            raise OSError("private details must not be sent")
        self.handler.sampler = fail
        reply = json.loads(self.handle()[1])
        self.assertEqual(reply["status"], "failed")
        self.assertEqual(reply["reason"], "sample_unavailable")
        self.assertNotIn("data", reply)
        self.assertNotIn("private", str(reply))

    def test_kernel_sampling_and_missing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            (proc / "uptime").write_text("123.50 456.00\n")
            (proc / "meminfo").write_text("MemTotal: 4096 kB\nMemAvailable: 1024 kB\n")
            (proc / "loadavg").write_text("0.25 0.50 1.00 1/20 100\n")
            sample = sample_linux(proc)
            self.assertEqual(sample["uptime_s"], 123.5)
            self.assertEqual(sample["memory_kib"], {"total": 4096, "available": 1024})
            self.assertEqual(sample["load_1m"], 0.25)
            self.assertEqual(sample["sample_errors"], [])
            (proc / "uptime").write_text("nan")
            (proc / "meminfo").unlink()
            sample = sample_linux(proc)
            self.assertIsNone(sample["uptime_s"])
            self.assertIsNone(sample["memory_kib"])
            self.assertEqual(len(sample["sample_errors"]), 2)

    def test_config_rejects_test_account_credentials_and_ip_hosts(self):
        base = {"host": "broker.example.com", "device_id": "rk3568-01", "username": "device-rk3568-01", "controller_ids": ["phone-owner"]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for change in [{"username": "rk3568-test"}, {"password": "never"}, {"host": "127.0.0.1"},
                           {"controller_ids": ["+"]}, {"device_id": "../../x"}, {"port": True}]:
                path.write_text(json.dumps({**base, **change}))
                with self.assertRaises(ValueError):
                    load_config(path)
            path.write_text(json.dumps(base))
            self.assertEqual(load_config(path)["port"], 8883)


if __name__ == "__main__":
    unittest.main()
