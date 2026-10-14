"""Standalone MQTT 5 status agent; TLS only, no hardware control."""
import argparse
import json
import os
import signal
import ssl
import sys
import time
import uuid
from pathlib import Path

from status_protocol import RequestHandler, encode, offline, sample_linux, status, topics, valid_id


def load_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    allowed = {"host", "port", "username", "device_id", "controller_ids", "ca_file"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError("unknown config field; password belongs in MQTT_PASSWORD")
    host = data.get("host")
    if not isinstance(host, str) or not host or any(x in host for x in "/:@?# "):
        raise ValueError("host must be a DNS hostname")
    # IP literals cannot replace the broker's certificate hostname / SNI.
    import ipaddress
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("DNS hostname required")
    if type(data.get("port", 8883)) is not int or not 1 <= data.get("port", 8883) <= 65535:
        raise ValueError("invalid TLS port")
    if not valid_id(data.get("device_id")) or not isinstance(data.get("controller_ids"), list):
        raise ValueError("invalid identities")
    if not data["controller_ids"] or len(data["controller_ids"]) > 16 or not all(valid_id(x) for x in data["controller_ids"]):
        raise ValueError("invalid controller whitelist")
    username = data.get("username")
    if not isinstance(username, str) or not username or len(username) > 100 or username == "rk3568-test":
        raise ValueError("separate device account required")
    data.setdefault("port", 8883)
    return data


class Agent:
    def __init__(self, mqtt, config, password, sampler=sample_linux):
        from paho.mqtt.packettypes import PacketTypes
        from paho.mqtt.properties import Properties
        from paho.mqtt.subscribeoptions import SubscribeOptions
        self.Properties, self.PacketTypes, self.SubscribeOptions = Properties, PacketTypes, SubscribeOptions
        self.config, self.mqtt, self.password, self.sampler = config, mqtt, password, sampler
        self.session_id = uuid.uuid4().hex
        self.handler = RequestHandler(config["device_id"], config["controller_ids"], self.session_id, sampler)
        self.topics = topics(config["device_id"])
        self.stopping = False
        self.fatal = False
        self.ready = False
        self.client = None
        self.subscription_mid = None
        self.next_status = 0

    def properties(self, packet_type, expiry):
        props = self.Properties(packet_type)
        props.MessageExpiryInterval = expiry
        return props

    def new_client(self):
        self.session_id = uuid.uuid4().hex
        self.handler.session_id = self.session_id
        client = self.mqtt.Client(self.mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="rk3568-device-" + self.config["device_id"],
                                  protocol=self.mqtt.MQTTv5, reconnect_on_failure=False)
        client.max_queued_messages_set(16)
        client.max_inflight_messages_set(8)
        client.connect_timeout = 8
        context = ssl.create_default_context(cafile=self.config.get("ca_file"))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        client.tls_set_context(context)
        client.username_pw_set(self.config["username"], self.password)
        client.will_set(self.topics["status"], encode(offline(self.config["device_id"], self.session_id)),
                        qos=1, retain=True, properties=self.properties(self.PacketTypes.WILLMESSAGE, 60))
        client.on_connect, client.on_subscribe = self.on_connect, self.on_subscribe
        client.on_message, client.on_publish = self.on_message, self.on_publish
        client.on_disconnect = self.on_disconnect
        return client

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.fatal = True
            print("Broker rejected connection; check device account locally", file=sys.stderr)
            client.disconnect()
            return
        options = self.SubscribeOptions(qos=1, retainAsPublished=True, retainHandling=2)
        subscriptions = [(topics(self.config["device_id"], controller)["request"], options)
                         for controller in self.config["controller_ids"]]
        rc, self.subscription_mid = client.subscribe(subscriptions)
        if rc != self.mqtt.MQTT_ERR_SUCCESS:
            self.fatal = True
            client.disconnect()

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if (mid != self.subscription_mid or len(reason_codes) != len(self.config["controller_ids"])
                or any(code.is_failure for code in reason_codes)):
            self.fatal = True
            print("Request subscription rejected; check device ACL", file=sys.stderr)
            client.disconnect()
            return
        self.ready, self.next_status = True, 0
        print("Status agent ready (read-only)", flush=True)

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.ready = False

    def on_publish(self, client, userdata, mid, reason_code, properties):
        if reason_code.is_failure:
            self.fatal = True
            print("Broker rejected publish; check device ACL", file=sys.stderr)
            client.disconnect()

    def publish(self, topic, payload, retained=False, expiry=15):
        if not self.ready or not self.client.is_connected():
            return None
        info = self.client.publish(topic, payload, qos=1, retain=retained,
                                   properties=self.properties(self.PacketTypes.PUBLISH, expiry))
        if info.rc != self.mqtt.MQTT_ERR_SUCCESS:
            print("Publish not accepted by local transport", file=sys.stderr)
            self.ready = False
            self.client.disconnect()
        return info

    def on_message(self, client, userdata, message):
        if not self.ready:
            return
        reply = self.handler.handle(message.topic, message.payload, message.retain)
        if reply:
            # The payload TTL remains authoritative even if a cached reply is resent.
            self.publish(*reply)

    def run(self):
        retry = 2
        while not self.stopping and not self.fatal:
            # Fresh client/session discards old outbound QoS data after a connection loss.
            self.ready = False
            self.client = self.new_client()
            try:
                props = self.Properties(self.PacketTypes.CONNECT)
                props.SessionExpiryInterval = 0
                props.MaximumPacketSize = 16384
                self.client.connect(self.config["host"], self.config["port"], 20,
                                    clean_start=True, properties=props)
                started = time.monotonic()
                while not self.stopping and not self.fatal:
                    rc = self.client.loop(timeout=0.25)
                    if rc != self.mqtt.MQTT_ERR_SUCCESS:
                        break
                    if not self.ready and time.monotonic() - started > 10:
                        break
                    if self.ready and time.monotonic() >= self.next_status:
                        payload = status(self.config["device_id"], self.session_id,
                                         int(time.time() * 1000), self.sampler)
                        self.publish(self.topics["status"], encode(payload), True, 30)
                        self.next_status = time.monotonic() + 10
                        retry = 2
                if self.stopping and self.ready:
                    info = self.publish(self.topics["status"], encode(offline(self.config["device_id"], self.session_id)), True, 60)
                    deadline = time.monotonic() + 2
                    while info and not info.is_published() and time.monotonic() < deadline:
                        if self.client.loop(timeout=0.1) != self.mqtt.MQTT_ERR_SUCCESS:
                            break
            except ssl.SSLError:
                print("TLS verification/handshake failed; stopped", file=sys.stderr)
                self.fatal = True
            except (OSError, RuntimeError, ValueError):
                print("Transport or sampling unavailable; no status fabricated", file=sys.stderr)
            finally:
                self.ready = False
                self.client.disconnect()
                self.client = None
            deadline = time.monotonic() + retry
            while not self.stopping and not self.fatal and time.monotonic() < deadline:
                time.sleep(0.2)
            retry = min(retry * 2, 30)
        return 2 if self.fatal else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="untracked local JSON; never include passwords")
    parser.add_argument("--deps-dir", help="optional directory with verified paho-mqtt 2.1.0 offline package")
    parser.add_argument("--sample", action="store_true", help="print real Linux status once without network")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.sample:
            print(encode(status(config["device_id"], uuid.uuid4().hex, int(time.time() * 1000))).decode())
            return 0
        if args.deps_dir:
            sys.path.insert(0, str(Path(args.deps_dir).resolve()))
        import paho.mqtt
        import paho.mqtt.client as mqtt
        if paho.mqtt.__version__ != "2.1.0":
            raise ValueError("paho-mqtt 2.1.0 required; do not upgrade board packages automatically")
        password = os.environ.get("MQTT_PASSWORD")
        if not password:
            raise ValueError("MQTT_PASSWORD required in local environment")
        sample_linux()
        agent = Agent(mqtt, config, password)
        def stop(signum, frame):
            agent.stopping = True
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        return agent.run()
    except (OSError, ValueError, RuntimeError, ImportError):
        print("Startup rejected: check local config, Linux sampling and pinned dependency; no secrets logged", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
