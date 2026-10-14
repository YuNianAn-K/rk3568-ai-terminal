"""Checks use the pinned real Paho API, with no broker connection."""
import json
import ssl
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))
import paho.mqtt.client as mqtt
from paho.mqtt.reasoncodes import ReasonCode
from paho.mqtt.packettypes import PacketTypes
from status_agent import Agent


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(mqtt, {"device_id": "rk3568-01", "controller_ids": ["phone-owner"],
                                 "host": "broker.example.invalid", "port": 8883,
                                 "username": "device-rk3568-01"}, "fixture-password", lambda: {})

    def test_real_paho_client_enforces_tls_and_expiring_offline_will(self):
        client = self.agent.new_client()
        self.assertEqual(client._protocol, mqtt.MQTTv5)
        self.assertTrue(client._ssl_context.check_hostname)
        self.assertEqual(client._ssl_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(client._ssl_context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertTrue(client._will_retain)
        self.assertEqual(client._will_properties.MessageExpiryInterval, 60)
        will = json.loads(client._will_payload)
        self.assertFalse(will["online"])
        self.assertFalse(will["simulated"])
        self.assertIsNone(will["updated_at"])

    def test_ready_only_after_successful_suback_and_retained_requests_marked(self):
        transport = Mock()
        transport.subscribe.return_value = (mqtt.MQTT_ERR_SUCCESS, 42)
        self.agent.on_connect(transport, None, None, ReasonCode(PacketTypes.CONNACK, "Success"), None)
        self.assertFalse(self.agent.ready)
        subscriptions = transport.subscribe.call_args.args[0]
        self.assertEqual(subscriptions[0][0], "rk3568/v1/devices/rk3568-01/request/phone-owner")
        options = subscriptions[0][1]
        self.assertEqual(options.retainHandling, 2)
        self.assertTrue(options.retainAsPublished)
        self.agent.on_subscribe(transport, None, 42, [ReasonCode(PacketTypes.SUBACK, "Granted QoS 1")], None)
        self.assertTrue(self.agent.ready)

    def test_acl_failure_never_becomes_ready_and_puback_denial_is_fatal(self):
        transport = Mock()
        self.agent.subscription_mid = 42
        self.agent.on_subscribe(transport, None, 42, [ReasonCode(PacketTypes.SUBACK, "Not authorized")], None)
        self.assertFalse(self.agent.ready)
        self.assertTrue(self.agent.fatal)
        transport.disconnect.assert_called()
        self.agent.fatal = False
        self.agent.on_publish(transport, None, 7, ReasonCode(PacketTypes.PUBACK, "Not authorized"), None)
        self.assertTrue(self.agent.fatal)

    def test_offline_publish_is_not_queued(self):
        transport = Mock()
        self.agent.client = transport
        self.assertIsNone(self.agent.publish("unused", b"{}"))
        transport.publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
