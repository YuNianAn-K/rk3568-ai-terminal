// Run only in an isolated local test page; no real broker or credentials.
async function browserDeviceQA() {
  const $ = id => document.getElementById(id);
  const checks = [];
  const check = (condition, name) => { if (!condition) throw new Error(name); checks.push(name); };
  const transports = [];
  window.mqtt = { connect(url, options) {
    const active = { connected: true, handlers: {}, messages: [], options,
      on(event, callback) { this.handlers[event] = callback; },
      subscribe(topics, callback) { this.subscriptions = topics; callback(null, Object.keys(topics).map(topic => ({ topic, qos: 1 }))); },
      publish(topic, text, settings, callback) { this.messages.push({ topic, data: JSON.parse(text), settings }); callback(null, { reasonCode: 0 }); },
      end() { this.connected = false; }
    };
    transports.push(active); return active;
  } };
  $('mode').value = 'device'; $('mode').dispatchEvent(new Event('change'));
  $('broker').value = 'wss://broker.example.invalid:8084/mqtt';
  $('username').value = 'phone-owner'; $('password').value = 'fixture-password';
  $('connect-form').dispatchEvent(new Event('submit', { cancelable: true }));
  const active = transports[0]; active.handlers.connect();
  check($('password').value === '', 'password field cleared');
  check(active.options.reconnectPeriod === 0 && active.options.protocolVersion === 5, 'manual reconnect MQTT5');
  check(active.subscriptions['rk3568/v1/devices/rk3568-01/status'].rh === 0, 'retained status subscribed');
  check(active.subscriptions['rk3568/v1/devices/rk3568-01/reply/phone-owner'].rap === true, 'retained reply flag preserved');
  $('query').click();
  const sent = active.messages[0], request = sent.data;
  check(sent.topic === 'rk3568/v1/devices/rk3568-01/request/phone-owner' && sent.settings.retain === false, 'isolated nonretained query');
  const now = Date.now();
  const status = { version: 1, type: 'status', device_id: 'rk3568-01', session_id: 'a'.repeat(32),
    simulated: false, online: true, updated_at: now, expires_at: now + 30000, capabilities: ['get_status'],
    system: { source: 'linux-proc', arch: 'aarch64', uptime_s: 100, memory_kib: { total: 4096, available: 2048 }, load_1m: 0.1, sample_errors: [] } };
  const reply = { version: 1, type: 'reply', sender: 'rk3568-01', target: 'phone-owner', request_id: request.request_id,
    action: 'get_status', simulated: false, status: 'success', updated_at: now, expires_at: request.expires_at, data: status };
  const receive = (topic, data, retain = false) => active.handlers.message(topic, new TextEncoder().encode(JSON.stringify(data)), { retain });
  // MQTT.js provides a Buffer with a text .toString(), unlike Uint8Array.
  active.handlers.message = ((original) => (topic, bytes, packet) => original(topic, {
    length: bytes.length, toString: () => new TextDecoder().decode(bytes)
  }, packet))(active.handlers.message);
  receive('rk3568/v1/devices/rk3568-01/reply/phone-owner', { ...reply, simulated: true });
  receive('rk3568/v1/devices/rk3568-01/reply/phone-owner', reply, true);
  check($('result').textContent.includes('等待'), 'simulated and retained replies ignored');
  receive('rk3568/v1/devices/rk3568-01/reply/phone-owner', reply);
  check($('result').textContent.includes('查询完成') && $('device-status').textContent.includes('100'), 'matching real status shown');
  const realNow = Date.now;
  try {
    Date.now = () => status.expires_at + 1;
    await new Promise(resolve => setTimeout(resolve, 1100));
    check($('device-status').textContent.includes('过期'), 'online snapshot expires in visible UI');
  } finally { Date.now = realNow; }
  receive('rk3568/v1/devices/rk3568-01/status', { ...status, online: false, updated_at: null, expires_at: null, session_id: 'b'.repeat(32) }, true);
  check($('device-status').textContent.includes('在线'), 'old-session offline will ignored');
  receive('rk3568/v1/devices/rk3568-01/status', { ...status, online: false, updated_at: null, expires_at: null }, true);
  check($('device-status').textContent.includes('离线'), 'matching-session offline will shown');
  receive('rk3568/v1/devices/rk3568-01/status', status, true);
  check($('device-status').textContent.includes('离线'), 'old online duplicate cannot revive offline session');
  $('query').click();
  const secondRequest = active.messages[1].data, secondNow = Date.now();
  const delayedReply = { ...reply, request_id: secondRequest.request_id, expires_at: secondRequest.expires_at,
    updated_at: secondNow, data: { ...status, updated_at: secondNow, expires_at: secondNow + 30000 } };
  receive('rk3568/v1/devices/rk3568-01/reply/phone-owner', delayedReply);
  check($('device-status').textContent.includes('离线') && $('result').textContent.includes('等待'), 'late reply cannot revive offline session');
  $('disconnect').click();
  const count = active.messages.length; $('query').click();
  check($('query').disabled && active.messages.length === count, 'offline query disabled without queue');
  $('mode').value = 'echo'; $('mode').dispatchEvent(new Event('change'));
  $('username').value = 'rk3568-test'; $('password').value = 'fixture-password';
  $('connect-form').dispatchEvent(new Event('submit', { cancelable: true }));
  const echo = transports[1]; echo.handlers.connect(); $('hello').click();
  check(echo.messages[0].topic === 'rk3568/test/echo', 'existing greeting remains on echo topic');
  $('query').click();
  const simulatedRequest = echo.messages[1].data;
  const { makeReply } = await import('/protocol.js');
  const simulatedReply = makeReply(simulatedRequest, 'sim-fixture');
  const echoPayload = JSON.stringify(simulatedReply);
  echo.handlers.message('rk3568/test/echo', { length: echoPayload.length, toString: () => echoPayload }, { retain: false });
  check($('result').textContent.includes('查询完成') && $('result').textContent.includes('模拟'), 'existing simulator reply remains explicit');
  $('disconnect').click();
  $('mode').value = 'device'; $('mode').dispatchEvent(new Event('change'));
  check(!localStorage.length && !sessionStorage.length, 'credentials not stored');
  return { checks, overflow: document.documentElement.scrollWidth > innerWidth, mock: true };
}
