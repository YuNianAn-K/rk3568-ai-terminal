export const TOPIC = 'rk3568/test/echo';
export const validIdentity = value => typeof value === 'string' && /^[a-z0-9][a-z0-9_-]{0,47}$/.test(value);
export function deviceTopics(deviceId, controllerId) {
  if (!validIdentity(deviceId) || !validIdentity(controllerId)) throw new Error('invalid identity');
  const root = `rk3568/v1/devices/${deviceId}`;
  return { request: `${root}/request/${controllerId}`, status: `${root}/status`, reply: `${root}/reply/${controllerId}` };
}
export function makeDeviceRequest(sender, target, now = Date.now()) {
  deviceTopics(target, sender);
  return { version: 1, type: 'request', request_id: requestId(), sender, target,
    action: 'get_status', issued_at: now, expires_at: now + 15000 };
}
export function freshDeviceStatus(data, deviceId, now = Date.now()) {
  if (data?.version !== 1 || data.type !== 'status' || data.device_id !== deviceId ||
      data.simulated !== false || typeof data.session_id !== 'string' || !/^[a-f0-9]{32}$/.test(data.session_id)) return false;
  if (data.online === false) return data.updated_at === null && data.expires_at === null;
  const system = data.system;
  const finite = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
  return data.online === true && Number.isSafeInteger(data.updated_at) && Number.isSafeInteger(data.expires_at) &&
    data.updated_at <= now + 1000 && now < data.expires_at &&
    data.expires_at - data.updated_at === 30000 &&
    data.capabilities?.length === 1 && data.capabilities[0] === 'get_status' &&
    system?.source === 'linux-proc' && typeof system.arch === 'string' && system.arch.length <= 32 &&
    Array.isArray(system.sample_errors) && system.sample_errors.length <= 3 &&
    system.sample_errors.every(x => ['uptime_unavailable', 'memory_unavailable', 'load_unavailable'].includes(x)) &&
    (system.uptime_s === null || finite(system.uptime_s)) && (system.load_1m === null || finite(system.load_1m)) &&
    (system.memory_kib === null || (Number.isSafeInteger(system.memory_kib?.total) && system.memory_kib.total > 0 &&
      Number.isSafeInteger(system.memory_kib.available) && system.memory_kib.available >= 0 && system.memory_kib.available <= system.memory_kib.total));
}
export function matchingDeviceReply(data, pending, controllerId, now = Date.now()) {
  return !!pending && now < pending.expires_at && data?.version === 1 && data.type === 'reply' &&
    data.request_id === pending.request_id && data.sender === pending.target && data.target === controllerId &&
    data.action === 'get_status' && data.simulated === false &&
    Number.isSafeInteger(data.updated_at) && data.updated_at >= pending.issued_at - 1000 && data.updated_at <= now + 1000 &&
    data.expires_at === pending.expires_at && ['success', 'failed'].includes(data.status) &&
    (data.status === 'failed' ? data.reason === 'sample_unavailable' :
      data.data?.online === true && freshDeviceStatus(data.data, pending.target, now) && data.data.updated_at === data.updated_at);
}
export function requestId() {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return [...bytes].map(n => n.toString(16).padStart(2, '0')).join('');
}
export function makeRequest(sender, now = Date.now()) {
  return { version: 1, type: 'request', request_id: requestId(), sender,
    target: 'pc-simulator', action: 'get_status', expires_at: now + 15000 };
}
export function validateRequest(data, now = Date.now()) {
  if (!data || data.version !== 1 || data.type !== 'request' ||
      typeof data.request_id !== 'string' || !/^[a-f0-9]{24}$/.test(data.request_id) ||
      typeof data.sender !== 'string' || data.sender.length > 100) return 'invalid_request';
  if (data.target !== 'pc-simulator') return 'wrong_target';
  if (data.action !== 'get_status') return 'unknown_action';
  if (!Number.isSafeInteger(data.expires_at) || data.expires_at <= now || data.expires_at > now + 15000) return 'expired_or_invalid_time';
  return null;
}
export function makeReply(data, sender, now = Date.now()) {
  const reason = validateRequest(data, now);
  return { version: 1, type: 'reply', request_id: data.request_id, target: data.sender,
    sender, status: reason ? 'rejected' : 'success', simulated: true,
    ...(reason ? { reason } : { data: { device: '电脑模拟终端', online: true, updated_at: now } }) };
}
export function matchingReply(data, pending, clientId) {
  return !!pending && data?.version === 1 && data.type === 'reply' &&
    data.request_id === pending.request_id && data.target === clientId &&
    data.simulated === true && typeof data.sender === 'string' &&
    ['success', 'rejected', 'failed'].includes(data.status) &&
    (data.status !== 'success' || (data.data?.device === '电脑模拟终端' && data.data.online === true && Number.isSafeInteger(data.data.updated_at)));
}
