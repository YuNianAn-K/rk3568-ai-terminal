# iPhone MQTT control page

Live verification on 2026-10-14: dedicated MQTT accounts, eight ACL negative cases,
real board queries, normal offline/Will/reconnect and desktop status expiry/recovery passed.
The user confirmed iPhone Safari displayed a successful real system query. The test agent
was then stopped; no persistent service or autostart was installed. The pending statements
below describe earlier phases. Evidence: `local/mqtt/live-20261014/REPORT.md`.

PC-hosted prototype: mobile Safari connects directly to the existing broker over WSS. The standalone read-only board agent is deployed and live queries passed; hardware actions, video and public hosting are not included. Echo/simulator mode uses `rk3568/test/echo`; read-only device mode uses isolated versioned business topics and separate accounts/ACL. Passwords are entered in the browser, never sent to the HTTP server or stored in browser storage. The broker credentials remain in MQTT.js memory until disconnection/page closure.

## Run on Windows

Requires Node.js; no npm install or build step is needed. The checked-in browser bundle is MQTT.js 5.16.0, extracted from the official npm tarball after SHA512 integrity verification. Version/source/integrity are recorded in `package.json`, with the upstream license in `dist/vendor/`.

```powershell
# [Windows], from apps/mqtt-cloud/mobile-web
node server.mjs
node --test tests/protocol.test.mjs
```

Set the broker address and username in the Git-ignored `local/mobile-web/connection.json` at repository root, or use `MQTT_WS_URL` and `MQTT_USERNAME`. Never put a password or API Secret in this file. Only these two non-secret fields are served by `/connection.json`. With no local configuration the user fills both fields in the page.

The server listens on port 8787 and prints the LAN addresses. On iPhone Safari, open the WLAN address while the phone and PC share a reachable local network. The PC must remain on. If Windows Firewall blocks access, review its private-network prompt locally; the server does not change firewall rules. VPNs, Wi-Fi client isolation, and iPhone personal-hotspot routing can affect reachability. The current local page uses HTTP, so only use it on a trusted test network; public hosting requires HTTPS.

## Test

1. Open `/` on the phone; enter the MQTT password and connect. Each page gets a unique Client ID.
2. Keep MQTTX connected and subscribed to the echo topic. Tap Send greeting on the phone and check MQTTX. Publish a non-retained response from MQTTX to the same topic; the phone should display it.
3. For automatic query replies, open `/?role=simulator` on the PC and connect with the same test account. Keep the page open. The phone's query targets `pc-simulator`, not the board. MQTTX alone does not automatically respond.
4. Query results are accepted only for the pending request ID, intended recipient, protocol version and simulated schema. An echoed request or broker PUBACK is not execution success. Request timeout is 10 seconds; message expiry is 15 seconds. Commands and replies are never retained. Retained requests/replies are ignored.
5. Network loss disables sending, clears the pending query, and requires manual reconnection. No automatic reconnect or offline command queue is used.

The simulator only supports `get_status`. It rejects unknown actions, targets and expired requests. It caches identical replies by sender/request ID for up to 60 seconds, at most 100 entries. Conflicting payloads with the same ID are ignored. This is in-memory test deduplication; reloads clear it, and it provides no production exactly-once guarantee. A reply from a client sharing the test account is not a verified hardware identity. Separate phone/device accounts and business topics are required before real control.

## Read-only device mode

Choose the device mode before connecting. Enter the device ID and a dedicated management username such as `phone-owner`; the shared `rk3568-test` account is rejected in this mode. The username is the controller topic segment and request sender. Exact account ACLs and the standalone Linux status agent are described in `../client/README.md`; the versioned protocol is in `../topics/status-v1.md`.

Status subscriptions accept fresh retained snapshots; reply subscriptions preserve the retained flag and reject retained replies. Requests use the dedicated account topic with QoS 1, retain false, 15-second MQTT expiry and matching payload TTL. A query is successful only with a matching non-simulated reply from the expected device and fresh Linux system sampling. The page displays expiry/agent offline separately from its own cloud connection. An old connection's Will or duplicated online message cannot revive an offline connection. Echo/simulator mode remains available without changing its ACL.

The status agent is deployed in an isolated board directory. On 2026-10-14, dedicated device/phone account login, eight ACL negative cases and live board queries passed; existing echo rules and spend limit zero were retained. The console did not expose QoS/retain restrictions. No autostart or persistent service was installed; start the web server and agent manually for use. Hardware identity depends on correctly enforced dedicated broker ACLs, not a `simulated` field or claimed sender alone. Browser fixtures remain separate from the live evidence cited above.

The browser uses text-only DOM rendering and bounded message history. The HTTP server serves an explicit file allowlist, with no directory listings or repository/file access. Browser certificate validation remains enabled; no API credentials are needed.

## Verification on 2026-10-13

- Node.js 24.16.0 syntax checks and two protocol tests passed.
- Browser UI rendered at 390px and 320px widths; no horizontal overflow at 320px.
- Local browser tests with an explicitly mocked MQTT transport passed: matching replies, echo/retained reply rejection, safe text rendering, timeout recovery, disconnect cancellation, disabled offline sending, no credential storage, simulator duplicate reuse, conflicting ID rejection, expired/unknown-action rejection.
- HTTP checks returned 200 for the page at loopback and the PC WLAN address; server source and `.env` returned 404.
- These historical fixture checks did not verify cloud authentication or iPhone networking; those were subsequently checked in the live read-only session cited above. Hardware motion and video remain outside scope; mock data was not represented as live broker evidence.

Subsequent user feedback confirmed phone/MQTTX bidirectional echo traffic. Device mode passed separate protocol and isolated browser mock checks at 390px and 320px with no horizontal overflow. The 320px device page was visually inspected. Browser fixture checks are in `tests/browser-device-qa.js` and include retained/simulated reply rejection, matching results, old-session Will filtering, no offline queue and no credential storage. Subsequent live business-topic/cloud ACL verification is recorded at the top of this document.
