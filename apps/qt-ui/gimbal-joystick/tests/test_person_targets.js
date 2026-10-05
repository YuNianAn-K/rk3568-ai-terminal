// Run with Node. Qt's .pragma library directive is removed only by this harness.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const api = {};
vm.createContext(api);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../PersonTargets.js'), 'utf8')
    .replace(/^\.pragma library\s*/, ''), api);
const a = {left: .1, top: .1, right: .4, bottom: .9, score: .9};
const b = {left: .6, top: .1, right: .9, bottom: .9, score: .8};
let state = api.update(api.empty(), []);
assert.equal(state.state, 'no_person');
state = api.update(api.empty(), [a, b]);
assert.equal(state.state, 'multiple');
assert.equal(state.index, -1);
state = api.update(api.empty(), [a]);
assert.equal(state.state, 'selected');
state = api.update(state, [b, {...a, left: .12}]);
assert.equal(state.index, 1); // A new high-score candidate does not steal the target.
state = api.update(state, [b]);
assert.equal(state.state, 'lost');
state = api.update(state, [a]);
assert.equal(state.state, 'lost'); // Re-selection is explicit after loss.
state = api.select(0, [a]);
assert.equal(state.state, 'selected');
state = api.update(state, [a, {...a, left: .11}]);
assert.equal(state.state, 'lost'); // Crossing/overlapping candidates are ambiguous.
assert.equal(api.select(5, [a]).state, 'searching');
assert.equal(api.overlap(a, b), 0);
assert.equal(api.overlap(a, a), 1);
console.log('PASS: single/multiple selection, reordered boxes, loss and ambiguity require explicit selection');
