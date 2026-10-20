import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
import unittest
import os
import subprocess
import tempfile
from datetime import datetime
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "tools/traffic-monitor"
sys.path.insert(0, str(SOURCE))
from model import TZ, bounds, metric_points, summarize, quota_view, bill_summary, month_key
from provider import CloudReader
from monitor import Monitor, make_handler
from credential_store import CredentialStore

CONFIG = {"instance_id": "i-fixture", "public_ip": "203.0.113.1"}


class TrafficModelTests(unittest.TestCase):
    def test_units_dedup_and_gap_never_interpolated(self):
        now = datetime(2026, 10, 19, 10, 0, tzinfo=TZ).timestamp()
        point = {"instanceId": "i-fixture", "ip": "203.0.113.1", "timestamp": int(now * 1000), "Average": 8_000_000}
        parsed = metric_points({"Success": True, "Datapoints": json.dumps([point, point])}, **dict(instance="i-fixture", ip="203.0.113.1"))
        values = summarize(parsed, now)
        self.assertEqual(values["day_gb"], 0.06)
        self.assertEqual(values["covered_seconds"], 60)
        self.assertEqual(summarize(parsed, now + 181)["bps"], None)
        self.assertIsNone(summarize({}, now)["month_gb"])

    def test_timezone_month_boundary_and_old_samples(self):
        now = datetime(2026, 11, 1, 0, 1, tzinfo=TZ).timestamp()
        self.assertEqual(month_key(now), "2026-11")
        self.assertEqual(summarize({int((now - 120) * 1000): 100}, now)["month_gb"], None)
        self.assertEqual(bounds(now)[0], int((now - 60) * 1000))

    def test_bad_identity_and_nonfinite_are_not_accepted(self):
        point = {"instanceId": "i-fixture", "ip": "203.0.113.1", "timestamp": 1000, "Average": 1}
        for change in [{"ip": "other"}, {"Average": float('nan')}, {"Average": -1}, {"timestamp": True}]:
            with self.assertRaises(ValueError):
                metric_points({"Success": True, "Datapoints": [{**point, **change}]}, "i-fixture", "203.0.113.1")

    def test_quota_levels_and_empty_bill_not_zero(self):
        for usage, level in [(0, "normal"), (10, "notice"), (15, "warning"), (18, "critical"), (20, "over")]:
            self.assertEqual(quota_view(usage)["level"], level)
        self.assertEqual(quota_view(21)["estimate_cny"], 0.8)
        self.assertIsNone(quota_view(None)["estimate_cny"])
        self.assertIsNone(bill_summary([], "i-fixture")["cny"])
        item = {"ProductCode": "cdt", "InstanceID": "other", "Currency": "CNY", "PretaxAmount": 12}
        self.assertIsNone(bill_summary([item], "i-fixture")["cny"])
        item["InstanceID"] = "i-fixture"
        self.assertEqual(bill_summary([item], "i-fixture")["cny"], 12)


class ReaderTests(unittest.TestCase):
    def test_official_sdk_requests_use_tls_and_only_read_actions(self):
        client = Mock()
        client.do_action_with_exception.return_value = b'{"Success":true}'
        reader = CloudReader(CONFIG, "fixture-id", "fixture-secret", sdk_client=client)
        reader.call("DescribeMetricList", {"Namespace": "acs_ecs_dashboard"})
        req = client.do_action_with_exception.call_args.args[0]
        self.assertEqual(req.get_protocol_type(), "https")
        self.assertEqual(req.get_domain(), "metrics.cn-shenzhen.aliyuncs.com")
        with self.assertRaises(ValueError):
            reader.call("StopInstance", {})

    def test_metric_pagination_and_incremental_update(self):
        now = datetime(2026, 10, 19, 10, tzinfo=TZ).timestamp()
        point = {"instanceId": "i-fixture", "ip": "203.0.113.1", "timestamp": int(now * 1000), "Average": 100}
        reader = CloudReader(CONFIG, "id", "secret", sdk_client=Mock())
        def call(action, params):
            return {"Success": True, "Period": "60", "Datapoints": json.dumps([point]),
                    "NextToken": None if params.get("NextToken") else "page2"}
        reader.call = Mock(side_effect=call)
        self.assertEqual(reader.metrics(now)["out"]["covered_seconds"], 60)
        self.assertEqual(reader.call.call_count, 4)
        self.assertEqual(reader.metrics(now)["out"]["covered_seconds"], 60)

    def test_bill_pagination_and_no_instance_misattribution(self):
        now = datetime(2026, 10, 19, 10, tzinfo=TZ).timestamp()
        reader = CloudReader(CONFIG, "id", "secret", sdk_client=Mock())
        row = {"ProductCode": "cdt", "InstanceID": "i-fixture", "Currency": "CNY", "PretaxAmount": "0.8"}
        reader.call = Mock(side_effect=[{"Data": {"BillingCycle": "2026-10", "Items": [row], "NextToken": "next"}},
                                       {"Data": {"BillingCycle": "2026-10", "Items": [], "NextToken": ""}}])
        self.assertEqual(reader.bills(now)["cny"], 0.8)


@unittest.skipUnless(os.name == "nt", "Real Windows DPAPI required")
class CredentialPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / 'credentials.dpapi'
        self.store = CredentialStore(self.path, CONFIG)
        self.credentials = {'access_id':'fixture-access-id', 'secret':'fixture-secret-unique', 'token':''}

    def tearDown(self):
        self.temporary.cleanup()

    def test_real_dpapi_encrypted_roundtrip_across_processes_and_target_binding(self):
        self.store.save(self.credentials)
        encrypted = self.path.read_bytes()
        for value in self.credentials.values():
            if value:
                self.assertNotIn(value.encode(), encrypted)
        self.assertEqual(self.store.load(), self.credentials)
        code = ('import sys; sys.path.insert(0, sys.argv[1]); from credential_store import CredentialStore; '
                'import json; value=CredentialStore(sys.argv[2],json.loads(sys.argv[3])).load(); '
                'assert value["secret"] == "fixture-secret-unique"; print("restored")')
        result = subprocess.run([sys.executable,'-c',code,str(SOURCE),str(self.path),json.dumps(CONFIG)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, 'Fresh-process DPAPI restore failed')
        self.assertEqual(result.stdout.strip(), 'restored')
        with self.assertRaises(Exception):
            CredentialStore(self.path, {**CONFIG,'instance_id':'other'}).load()
        self.path.write_bytes(encrypted[:-10] + b'corrupted!')
        with self.assertRaises(Exception):
            self.store.load()

    def test_storage_failure_keeps_old_file_and_never_writes_plaintext(self):
        self.store.save(self.credentials)
        old = self.path.read_bytes()
        with patch('credential_store.protect_bytes', side_effect=OSError('fixture')):
            with self.assertRaises(OSError):
                self.store.save({**self.credentials,'secret':'replacement'})
        self.assertEqual(self.path.read_bytes(), old)
        with self.assertRaises(ValueError):
            self.store.save({**self.credentials,'token':'temporary-token'})

    def test_saved_connection_restarts_and_forget_drops_active_and_saved_identity(self):
        with patch('provider.CloudReader') as reader:
            monitor = Monitor(CONFIG, self.store)
            monitor.connect({**self.credentials,'remember':True})
            restarted = Monitor(CONFIG, CredentialStore(self.path, CONFIG))
            restarted.restore_saved()
            self.assertTrue(restarted.snapshot()['connected'])
            self.assertTrue(restarted.snapshot()['credential_saved'])
            text = json.dumps(restarted.snapshot())
            self.assertNotIn(self.credentials['secret'], text)
            self.assertNotIn(self.credentials['access_id'], text)
            restarted.forget_credentials()
            self.assertIsNone(restarted.reader)
            self.assertFalse(self.store.exists())
            fresh = Monitor(CONFIG, self.store)
            fresh.restore_saved()
            self.assertFalse(fresh.snapshot()['connected'])

    def test_one_time_replacement_removes_old_saved_key_and_corruption_is_visible(self):
        self.store.save(self.credentials)
        with patch('provider.CloudReader'):
            monitor = Monitor(CONFIG, self.store)
            monitor.connect({**self.credentials,'remember':False})
            self.assertFalse(self.store.exists())
            self.assertFalse(monitor.snapshot()['credential_saved'])
            self.path.write_bytes(b'broken-encrypted-file')
            restarted = Monitor(CONFIG, self.store)
            restarted.restore_saved()
            self.assertFalse(restarted.snapshot()['connected'])
            self.assertTrue(restarted.snapshot()['credential_saved'])
            self.assertIn('无法载入', restarted.snapshot()['credential_notice'])


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.monitor = Monitor(CONFIG)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.monitor, 'fixture-session'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, headers=None, body=None):
        conn = HTTPConnection('127.0.0.1', self.port)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        result = response.status, response.read().decode()
        conn.close()
        return result

    def test_private_state_requires_capability_and_dns_rebinding_rejected(self):
        self.assertEqual(self.request('GET', '/api/state')[0], 403)
        self.assertEqual(self.request('GET', '/', {'Host':'evil.invalid'})[0], 403)
        code, text = self.request('GET', '/api/state', {'X-Monitor-Session':'fixture-session'})
        self.assertEqual(code, 200)
        self.assertIsNone(json.loads(text)['metrics'])
        self.assertFalse(json.loads(text)['guard_enabled'])

    def test_cross_origin_credentials_blocked_and_static_no_keys(self):
        headers = {'X-Monitor-Session':'fixture-session', 'Origin':'https://evil.invalid'}
        self.assertEqual(self.request('POST', '/api/connect', headers, '{"secret":"private-fixture"}')[0], 403)
        self.assertIsNone(self.monitor.reader)
        for path in ['/', '/app.js', '/style.css']:
            code, text = self.request('GET', path)
            self.assertEqual(code, 200)
            self.assertNotIn('private-fixture', text)
        self.assertEqual(self.request('GET', '/../../config.json')[0], 404)
        self.assertEqual(self.request('GET', '/credentials.dpapi')[0], 404)
        self.assertEqual(self.request('POST', '/api/forget', headers, '{}')[0], 403)

    def test_remember_requires_explicit_boolean_and_forget_is_authenticated(self):
        headers = {'X-Monitor-Session':'fixture-session', 'Origin':f'http://127.0.0.1:{self.port}'}
        for remember in ['true', 1, None]:
            body = json.dumps({'access_id':'fixture', 'secret':'fixture', 'remember':remember})
            self.assertEqual(self.request('POST', '/api/connect', headers, body)[0], 400)
        self.assertEqual(self.request('POST', '/api/forget', headers, '{}')[0], 200)
        self.assertFalse(self.monitor.snapshot()['credential_saved'])

    def test_stop_has_no_cloud_action_and_old_observation_expires(self):
        self.monitor.config['observation'] = {'month':'2000-01', 'used_gb':1}
        self.assertIsNone(self.monitor.snapshot()['observation'])
        headers = {'X-Monitor-Session':'fixture-session', 'Origin':f'http://127.0.0.1:{self.port}'}
        self.assertEqual(self.request('POST', '/api/stop', headers, '{}')[0], 200)
        self.assertTrue(self.monitor.stop.is_set())


if __name__ == '__main__':
    unittest.main()
