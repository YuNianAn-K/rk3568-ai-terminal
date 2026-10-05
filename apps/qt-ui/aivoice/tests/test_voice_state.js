// [Windows/VM] node tests/test_voice_state.js
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../VoiceState.js"), "utf8")
    .replace(/^\.pragma library\s*/, "");
const state = vm.createContext({});
vm.runInContext(source, state);

const expected = {
    idle: "idle", initializing: "idle", starting: "listening",
    recording: "listening", recognizing: "thinking", thinking: "thinking",
    replying: "thinking", playing: "speaking", error: "error", offline: "offline"
};
for (const [raw, visual] of Object.entries(expected)) {
    assert.equal(state.visualState(raw, true), visual, raw);
    assert.equal(state.visualState(raw, false), "offline", `disconnected ${raw}`);
    assert.ok(state.title(raw, true));
    assert.ok(state.hint(raw, true));
}
assert.equal(state.action("idle", true), "start");
assert.equal(state.action("error", true), "start");
assert.equal(state.action("recording", true), "stop");
for (const raw of ["initializing", "starting", "recognizing", "thinking", "replying", "playing", "unknown"]) {
    assert.equal(state.action(raw, true), "none", raw);
}
assert.equal(state.action("playing", false), "reconnect");
assert.equal(state.action("offline", true), "reconnect");
assert.equal(state.visualState("unknown", true), "idle");
assert.equal(state.errorKey(4, "failed"), state.errorKey(4, "failed"));
assert.notEqual(state.errorKey(4, "failed"), state.errorKey(5, "failed"));
assert.match(state.hint("playing", true), /播放结束/);
assert.doesNotMatch(state.title("offline", false), /本地/);
console.log("Voice state mapping and interaction checks passed.");
