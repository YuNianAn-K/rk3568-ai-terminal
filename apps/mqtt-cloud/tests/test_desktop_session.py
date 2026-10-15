"""Manual launcher resource and failure-path checks; no broker authentication."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'apps/mqtt-cloud/tools/desktop/session.py'
spec = importlib.util.spec_from_file_location('desktop_session', SCRIPT)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class DesktopSessionTests(unittest.TestCase):
    def test_remote_wrapper_compiles(self):
        ast.parse(session.REMOTE_CODE)

    def test_unsafe_ip_rejected_before_start(self):
        for address in ['127.0.0.1', '0.0.0.0', '224.0.0.1', '169.254.1.2',
                        '10.104.157.255', '8.8.8.8', '10.1.1.1; echo injected']:
            with self.subTest(address=address), self.assertRaises(ValueError):
                session.validate_ip(address)

    def test_occupied_port_preserved_and_password_not_written(self):
        identifier = uuid.uuid4().hex
        output = ROOT / 'local/mqtt/manual' / (identifier + '.json')
        marker = 'synthetic-test-placeholder'
        with socket.socket() as listener:
            try:
                listener.bind(('127.0.0.1', 8787))
            except OSError:
                self.skipTest('Port occupied before test; no process touched')
            listener.listen(4)
            try:
                result = subprocess.run([sys.executable, str(SCRIPT), '--session', identifier],
                                        input=json.dumps({'ip': '10.104.157.235', 'password': marker}),
                                        text=True, encoding='utf-8', capture_output=True, timeout=10,
                                        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                self.assertEqual(result.returncode, 2)
                state_text = output.read_text(encoding='utf-8')
                state = json.loads(state_text)
                self.assertEqual(state['stage'], 'failed')
                self.assertIn('8787', state['message'])
                self.assertNotIn(marker, state_text + result.stdout + result.stderr)
                self.assertNotIn('web_pid', state)
                with socket.create_connection(('127.0.0.1', 8787), timeout=1):
                    pass
            finally:
                output.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
