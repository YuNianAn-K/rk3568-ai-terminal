import test from 'node:test';
import assert from 'node:assert/strict';
import { makeRequest, validateRequest, makeReply, matchingReply } from '../dist/protocol.js';
test('only fresh status requests for the simulator are accepted', () => {
  const request = makeRequest('phone-1', 1000);
  assert.equal(validateRequest(request, 1001), null);
  assert.equal(validateRequest(request, 16000), 'expired_or_invalid_time');
  assert.equal(validateRequest({ ...request, action: 'led_on' }, 1001), 'unknown_action');
  assert.equal(validateRequest({ ...request, target: 'rk3568' }, 1001), 'wrong_target');
  assert.equal(validateRequest({ ...request, expires_at: '16000' }, 1001), 'expired_or_invalid_time');
  assert.equal(validateRequest({ ...request, version: 2 }, 1001), 'invalid_request');
});
test('a matching simulated reply is required; broker echoes are not replies', () => {
  const request = makeRequest('phone-1');
  const reply = makeReply(request, 'sim-1');
  assert.equal(matchingReply(request, request, 'phone-1'), false);
  assert.equal(matchingReply(reply, request, 'phone-1'), true);
  assert.equal(matchingReply({ ...reply, request_id: 'other' }, request, 'phone-1'), false);
  assert.equal(matchingReply({ ...reply, target: 'phone-2' }, request, 'phone-1'), false);
  assert.equal(matchingReply({ ...reply, simulated: false }, request, 'phone-1'), false);
  assert.equal(matchingReply(reply, null, 'phone-1'), false);
});
