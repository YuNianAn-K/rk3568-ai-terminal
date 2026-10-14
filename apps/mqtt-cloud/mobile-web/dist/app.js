import { TOPIC, requestId, makeRequest, makeReply, matchingReply, deviceTopics,
  makeDeviceRequest, matchingDeviceReply, freshDeviceStatus, validIdentity } from './protocol.js';
const $ = id => document.getElementById(id);
const simulator = new URLSearchParams(location.search).get('role') === 'simulator';
const clientId = `rk3568-${simulator ? 'sim' : 'phone'}-${requestId()}`;
let client = null, ready = false, pending = null, pendingTimer = null;
let business = null, latestStatus = null;
const replies = new Map();
function notice(text, error = false) { $('notice').textContent = text; $('notice').classList.toggle('error', error); }
function controls(state, text) {
  ready = state;
  $('badge').textContent = text;
  $('badge').classList.toggle('online', state);
  $('hello').disabled = !state || simulator || !!business;
  $('query').disabled = !state || !!pending || simulator;
}
function log(kind, text) {
  $('messages').querySelector('.empty')?.remove();
  const item = document.createElement('li');
  const meta = document.createElement('div'); meta.className = 'message-meta';
  const label = document.createElement('span'); label.textContent = kind;
  const time = document.createElement('time'); time.textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  meta.append(label, time);
  const body = document.createElement('pre'); body.className = 'message-body'; body.textContent = text;
  item.append(meta, body); $('messages').prepend(item);
  while ($('messages').children.length > 60) $('messages').lastChild.remove();
}
function finishPending(text) {
  clearTimeout(pendingTimer); pendingTimer = null; pending = null;
  $('result').textContent = text; $('query').disabled = !ready || simulator;
}
function errorText(error) {
  const code = Number(error?.code);
  if ([4, 5, 134, 135].includes(code)) return '账号、密码或主题权限被拒绝，请核对 MQTT 测试账号。';
  return '连接或消息传输失败，请检查网络、加密连接地址和账号权限。';
}
function disconnect() {
  const old = client; client = null; ready = false;
  old?.end(true);
  controls(false, '未连接');
  $('connect').disabled = false; $('disconnect').hidden = true;
  $('mode').disabled = simulator; $('device-id').disabled = false; $('username').disabled = false;
  latestStatus = null; renderStatus();
  if (pending) finishPending('连接已断开，查询未完成。请连接后重新查询。');
  notice('已断开连接。');
}
function publish(data, callback = () => {}, topic = TOPIC) {
  if (!ready || !client?.connected) { notice('请先连接云端，断线时不发送或排队。', true); return false; }
  const active = client;
  const text = JSON.stringify(data);
  log('发送中', text);
  active.publish(topic, text, { qos: 1, retain: false, properties: { messageExpiryInterval: 15 } }, (error, packet) => {
    if (client !== active) return;
    if (!error && packet?.reasonCode >= 128) error = { code: packet.reasonCode };
    if (error) notice('服务器未确认消息：' + errorText(error), true);
    else notice('云端已确认消息；查询是否完成以对应回执为准。');
    callback(error);
  });
  return true;
}
function received(topic, payload, packet) {
  if (payload.length > 16384 || (!business && topic !== TOPIC)) return;
  const text = payload.toString();
  let data; try { data = JSON.parse(text); } catch { log('收到消息', text); return; }
  if (business) {
    if (topic === business.topics.status && freshDeviceStatus(data, business.deviceId)) {
      const revivedOldSession = data.online && latestStatus?.online === false && data.session_id === latestStatus.session_id;
      const olderSample = data.online && latestStatus?.online && data.updated_at < latestStatus.updated_at;
      if (!revivedOldSession && !olderSample && (data.online || !latestStatus || data.session_id === latestStatus.session_id)) latestStatus = data;
      renderStatus();
    }
    if (topic === business.topics.reply && !packet.retain && matchingDeviceReply(data, pending, business.controllerId)) {
      if (data.status === 'success' && latestStatus?.online === false && data.data.session_id === latestStatus.session_id) return;
      log('真实设备回执', text);
      if (data.status === 'success') {
        latestStatus = data.data; renderStatus();
        finishPending(`查询完成 · ${business.deviceId}\n真实系统采样 · ${new Date(data.updated_at).toLocaleTimeString('zh-CN')}`);
      } else finishPending('设备采样失败，未返回虚构状态。');
    }
    return;
  }
  log(data?.sender === clientId ? '服务器回传 · 本机消息' : '收到消息', text);
  if (simulator && data?.type === 'request' && data.target === 'pc-simulator') {
    if (packet.retain || typeof data.request_id !== 'string' || !/^[a-f0-9]{24}$/.test(data.request_id) || typeof data.sender !== 'string' || data.sender.length > 100) return;
    const now = Date.now();
    for (const [key, value] of replies) if (value.until <= now) replies.delete(key);
    const key = `${data.sender}:${data.request_id}`;
    let saved = replies.get(key);
    if (saved && saved.request !== text) return;
    if (!saved) {
      saved = { request: text, reply: makeReply(data, clientId, now), until: now + 60000 };
      replies.set(key, saved);
      if (replies.size > 100) replies.delete(replies.keys().next().value);
    }
    publish(saved.reply);
  }
  if (!simulator && !packet.retain && matchingReply(data, pending, clientId)) {
    finishPending(data.status === 'success'
      ? '查询完成 · 电脑模拟终端在线\n这是模拟回执，未连接真实 RK3568。'
      : `模拟端拒绝或执行失败：${String(data.reason || data.status)}`);
  }
}
$('connect-form').addEventListener('submit', event => {
  event.preventDefault();
  if (client) disconnect();
  let url;
  try { url = new URL($('broker').value.trim()); } catch { notice('请填写完整的 wss:// 连接地址。', true); return; }
  if (url.protocol !== 'wss:' || url.username || url.password || url.search || url.hash) { notice('请使用不含凭据的 wss:// 加密连接地址。', true); return; }
  if (!window.mqtt) { notice('MQTT 组件未加载，请重新打开网页。', true); return; }
  business = null; latestStatus = null;
  if ($('mode').value === 'device') {
    const controllerId = $('username').value.trim(), deviceId = $('device-id').value.trim();
    if (simulator || controllerId === 'rk3568-test' || !validIdentity(controllerId) || !validIdentity(deviceId)) {
      notice('真实设备模式需要独立管理账号和有效设备 ID，不能使用共用测试账号。', true); return;
    }
    business = { controllerId, deviceId, topics: deviceTopics(deviceId, controllerId) };
  }
  $('mode').disabled = true; $('device-id').disabled = true; $('username').disabled = true;
  $('connect').disabled = true; $('disconnect').hidden = false; controls(false, '连接中'); notice('正在连接云端…');
  const password = $('password').value;
  $('password').value = '';
  const active = window.mqtt.connect(url.href, { clientId, username: $('username').value.trim(), password,
    protocolVersion: 5, clean: true, keepalive: 30, connectTimeout: 12000,
    reconnectPeriod: 0, resubscribe: false, queueQoSZero: false });
  client = active;
  active.on('connect', () => {
    if (client !== active) return;
    const subscriptions = business ? {
      [business.topics.status]: { qos: 1, nl: false, rap: true, rh: 0 },
      [business.topics.reply]: { qos: 1, nl: false, rap: true, rh: 2 }
    } : { [TOPIC]: { qos: 1, nl: false, rap: true, rh: 2 } };
    active.subscribe(subscriptions, (error, granted) => {
      if (client !== active) return;
      if (error || granted?.length !== Object.keys(subscriptions).length || granted.some(item => item.qos >= 128)) { disconnect(); notice('主题订阅被拒绝，请核对所选模式的账号权限。', true); return; }
      controls(true, '已连接'); notice(business ? '云端已连接。设备是否在线，以新鲜状态和匹配回执为准。' : simulator ? '电脑模拟端已就绪，可回应手机的查询。' : '已连接并订阅 echo 主题，可以开始测试。');
    });
  });
  active.on('message', (topic, payload, packet) => { if (client === active) received(topic, payload, packet); });
  active.on('error', error => { if (client === active) { const text = errorText(error); disconnect(); notice(text, true); } });
  active.on('close', () => { if (client === active) { disconnect(); notice('连接已中断，请重新输入密码并连接。', true); } });
});
$('disconnect').addEventListener('click', disconnect);
$('hello').addEventListener('click', () => publish({ message: 'hello rk3568', sender: clientId }));
$('query').addEventListener('click', () => {
  if (!ready || pending) return;
  const request = business ? makeDeviceRequest(business.controllerId, business.deviceId) : makeRequest(clientId);
  pending = request; $('query').disabled = true;
  $('result').textContent = business ? '等待真实设备回复…' : '等待电脑模拟端回复…';
  pendingTimer = setTimeout(() => finishPending(business ? '设备回执超时。请检查设备代理、网络与独立账号权限。' : '等待回执超时。请确认电脑模拟端已打开并连接；MQTTX 不会自动回应查询。'), 10000);
  if (!publish(request, error => { if (error && pending === request) finishPending('查询发送失败，请重新查询。'); }, business ? business.topics.request : TOPIC)) finishPending('未连接，查询未发送。');
});
$('clear').addEventListener('click', () => { $('messages').replaceChildren(); });
if (simulator) {
  $('mode').disabled = true;
  $('eyebrow').textContent = '电脑模拟端 · 无硬件操作'; $('heading').textContent = '准备回应手机。';
  $('intro').textContent = '保持此页连接，仅回应 get_status 查询，所有结果明确标为模拟数据。';
  $('actions').hidden = true; $('role-link').href = '/'; $('role-link').textContent = '打开手机控制台 →';
}
function renderStatus() {
  if (!ready || !latestStatus) { $('device-status').textContent = '尚未收到有效的真实设备状态。'; return; }
  if (!latestStatus.online) { $('device-status').textContent = '设备代理离线 · 遗嘱或正常退出通知'; return; }
  if (!freshDeviceStatus(latestStatus, business?.deviceId)) { $('device-status').textContent = '设备状态已过期 · 不代表当前在线'; return; }
  const system = latestStatus.system, mem = system.memory_kib;
  $('device-status').textContent = `真实设备在线 · ${latestStatus.device_id}\n运行 ${system.uptime_s ?? '未知'} 秒 · 负载 ${system.load_1m ?? '未知'}\n可用内存 ${mem ? Math.round(mem.available / 1024) + ' MiB' : '未知'}\n采样 ${new Date(latestStatus.updated_at).toLocaleTimeString('zh-CN')}`;
}
function modeChanged() {
  const device = $('mode').value === 'device';
  $('device-field').hidden = !device; $('device-status').hidden = !device; $('hello').hidden = device;
  $('account-hint').textContent = device ? '使用专用管理账号（如 phone-owner）。请先配置独立业务主题权限，密码不保存。' : '使用 MQTT 测试账号密码。密码仅用于本次连接，不保存。';
  $('query-title').textContent = device ? '查询真实设备状态' : '查询模拟终端';
  $('query-hint').textContent = device ? '只读系统采样 · 需要板端代理在线' : '需要电脑模拟端保持连接';
  $('action-heading').textContent = device ? '查看设备状态' : '试着发一条消息';
  $('action-tag').textContent = device ? '只读查询' : 'echo 测试';
  $('topic-hint').textContent = device ? '独立设备主题 · QoS 1 · 请求不保留' : '测试主题 rk3568/test/echo · QoS 1';
  $('result').textContent = device ? '尚未查询，连接云端不代表设备在线。' : '暂未查询。当前没有连接真实开发板。';
  latestStatus = null; renderStatus();
}
$('mode').addEventListener('change', modeChanged);
setInterval(renderStatus, 1000);
fetch('/connection.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : {}).then(config => {
  if (!$('broker').value) $('broker').value = config.broker || '';
  if (!$('username').value) $('username').value = config.username || '';
}).catch(() => notice('请手动填写云端地址和用户名。'));
window.addEventListener('pagehide', disconnect);
