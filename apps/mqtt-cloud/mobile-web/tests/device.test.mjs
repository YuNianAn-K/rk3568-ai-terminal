import test from 'node:test';
import assert from 'node:assert/strict';
import { deviceTopics, makeDeviceRequest, matchingDeviceReply, freshDeviceStatus } from '../dist/protocol.js';

const now = 1000000;
const request = makeDeviceRequest('phone-owner', 'rk3568-01', now);
const status = { version: 1, type: 'status', device_id: 'rk3568-01', session_id: 'a'.repeat(32),
  online: true, simulated: false, updated_at: now, expires_at: now + 30000, capabilities: ['get_status'],
  system: { source: 'linux-proc', arch: 'aarch64', uptime_s: 12, memory_kib: { total: 4096, available: 1024 }, load_1m: 0.1, sample_errors: [] } };
const reply = { version: 1, type: 'reply', request_id: request.request_id, sender: request.target,
  target: request.sender, action: 'get_status', simulated: false, status: 'success',
  updated_at: now, expires_at: request.expires_at, data: status };

test('device/account topic segments cannot contain wildcard or traversal', () => {
  assert.equal(deviceTopics('rk3568-01', 'phone-owner').reply, 'rk3568/v1/devices/rk3568-01/reply/phone-owner');
  for (const id of ['+', '#', 'a/b', '../x', '', 'A']) assert.throws(() => deviceTopics(id, 'phone-owner'));
});
test('freshness expires online status; offline will never invents a disconnect timestamp', () => {
  assert.equal(freshDeviceStatus(status, 'rk3568-01', now + 1), true);
  assert.equal(freshDeviceStatus(status, 'rk3568-01', now + 30000), false);
  assert.equal(freshDeviceStatus({ ...status, simulated: true }, 'rk3568-01', now), false);
  assert.equal(freshDeviceStatus({ ...status, system: { ...status.system, uptime_s: NaN } }, 'rk3568-01', now), false);
  assert.equal(freshDeviceStatus({ ...status, online: false, updated_at: null, expires_at: null }, 'rk3568-01', now), true);
});
test('reply must match device, controller, request, real sampling and expiry', () => {
  assert.equal(matchingDeviceReply(reply, request, 'phone-owner', now + 1), true);
  for (const change of [{ sender: 'other' }, { target: 'other' }, { request_id: 'b'.repeat(24) },
    { simulated: true }, { action: 'led_on' }, { expires_at: now + 999 }, { data: { ...status, online: false } },
    { data: { ...status, system: { source: 'simulator' } } }]) {
    assert.equal(matchingDeviceReply({ ...reply, ...change }, request, 'phone-owner', now + 1), false);
  }
  assert.equal(matchingDeviceReply(reply, request, 'phone-owner', now + 15000), false);
  assert.equal(matchingDeviceReply(reply, null, 'phone-owner', now), false);
});
