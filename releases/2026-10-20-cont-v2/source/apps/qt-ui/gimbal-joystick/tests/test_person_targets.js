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
state = api.update(api.empty(), [a], 1000);
assert.equal(state.state, 'confirming');
state = api.update(state, [a], 1150);
assert.equal(state.state, 'confirming');
state = api.update(state, [a], 1300);
assert.equal(state.state, 'selected');
state = api.update(state, [b, {...a, left: .12}]);
assert.equal(state.index, 1); // A new high-score candidate does not steal the target.
state = api.update(state, [b], 1450);
assert.equal(state.state, 'recovering');
state = api.update(state, [{...a, score: .43}], 1600);
assert.equal(state.state, 'selected');
state = api.update(state, [], 1750);
state = api.update(state, [a], 2650);
assert.equal(state.state, 'lost');
state = api.update(state, [a]);
assert.equal(state.state, 'lost'); // Re-selection is explicit after loss.
state = api.select(0, [a]);
assert.equal(state.state, 'selected');
state = api.update(state, [a, {...a, left: .11}]);
assert.equal(state.state, 'recovering'); // One crossing result pauses; it cannot steer.
state = api.update(state, [a], state.stamp + 150);
assert.equal(state.state, 'selected'); // Separation restores the same geometric target.
state = api.select(0, [a]);
state = api.update(state, [a, {...a, left: .11, score: .45}], 1000);
assert.equal(state.state, 'selected'); // A weak fragment cannot steal the reliable match.
state = api.update(state, [{...a, score: .43}, {...a, left: .11, score: .42}], 1150);
assert.equal(state.state, 'recovering'); // Uncertain weak matches pause; they cannot steer.
state = api.update(state, [a], 1300);
assert.equal(state.state, 'selected');
assert.equal(api.select(5, [a]).state, 'searching');
assert.equal(api.overlap(a, b), 0);
assert.equal(api.overlap(a, a), 1);
assert.equal(api.update(api.empty(), [{...a, score: .69}], 1000).state, 'candidate');
assert.equal(api.select(0, [{...a, score: .69}]).state, 'selected');
assert.equal(api.select(0, [{...a, score: .54}]).locked, false);
state = api.empty();
for (let stamp = 1000; stamp < 3000; stamp += 150)
    state = api.update(state, [{...a, score: .60}], stamp);
assert.equal(state.state, 'candidate'); // Visible is not automatically selected.
state = api.update(api.empty(), [a], 1000);
state = api.update(state, [a], 1000);
assert.equal(state.hits, 1); // A repeated timestamp cannot confirm a target.

// Full-body scale continuity wins over a slightly higher-scoring local box.
const full = {left: .1, top: .05, right: .9, bottom: .95, score: .58};
const upper = {left: .12, top: .05, right: .88, bottom: .48, score: .62};
state = api.select(0, [full]);
state = api.update(state, [upper, {...full, left: .11}], 1000);
assert.equal(state.index, 1);
assert.equal(state.state, 'selected');

// A scale jump needs two different, adjacent results; no stale/held sample.
state = api.select(0, [full]);
state = api.update(state, [upper], 1000);
assert.equal(state.state, 'recovering');
assert.equal(state.reason, 'geometry');
assert.equal(state.index, -1);
state = api.update(state, [upper], 1000);
assert.equal(state.state, 'recovering');
state = api.update(state, [upper], 1150);
assert.equal(state.state, 'selected');

// Recorded fragment -> body -> shifted body: the second confirmation must
// match the pending body, even when it no longer overlaps the old fragment.
const fragment = {left:.76039, top:.03519, right:.99684, bottom:.98592, score:.4883};
state = {locked:true, box:fragment, index:0, state:'selected'};
state = api.update(state, [], 1000);
state = api.update(state, [{left:.51273, top:.00104, right:.98561,
                          bottom:.99273, score:.5508}], 1200);
assert.equal(state.reason, 'geometry');
state = api.update(state, [{left:.50660, top:.00848, right:.86891,
                          bottom:.94429, score:.5508}], 1400);
assert.equal(state.state, 'selected');
assert.equal(state.index, 0);

// Repeated ambiguity cannot restart the recovery clock or auto-select a rival.
state = api.select(0, [a]);
for (let stamp = 1000; stamp < 1900; stamp += 150) {
    state = api.update(state, [a, {...a, left: .11}], stamp);
    assert.equal(state.state, 'recovering');
    assert.equal(state.index, -1);
    assert.equal(state.missingSince, 1000);
}
state = api.update(state, [a], 1900);
assert.equal(state.state, 'lost');
assert.equal(api.update(state, [a], 2050).state, 'lost');
// Actual YOLOv8 test: legs disappear behind a chair, while the head moves only
// slightly. A background person must not take the selected foreground target.
const recorded = JSON.parse(fs.readFileSync(path.join(__dirname, 'person_association_recorded.json')));
state = api.select(0, recorded['223'].boxes, recorded['223'].result_ms);
for (const seq of [224,225,226])
    state = api.update(state, recorded[seq].boxes, recorded[seq].result_ms);
assert.equal(state.state, 'recovering');
assert.equal(state.reason, 'geometry');
assert.equal(state.index, -1);
state = api.update(state, recorded['227'].boxes, recorded['227'].result_ms);
assert.equal(state.state, 'selected');
assert.equal(state.index, 1); // Confirmed foreground, despite lower score than background.
assert.equal(state.box, recorded['227'].boxes[1]); // Never emit a remembered box.

// Full/upper-body alternation after a missed result must not repeatedly restart
// shape confirmation once both recent shapes have already been accepted.
state = api.select(0, recorded['460'].boxes, recorded['460'].result_ms);
for (const seq of [461,462,463,464,465])
    state = api.update(state, recorded[seq].boxes, recorded[seq].result_ms);
assert.equal(state.state, 'selected');
state = api.update(state, recorded['466'].boxes, recorded['466'].result_ms);
assert.equal(state.state, 'selected');
assert.equal(state.box, recorded['466'].boxes[0]);

// A new partial match pauses first; repeated or widely spaced results cannot
// satisfy the fresh confirmation. Similar competing heads still pause.
const oldBody = recorded['223'].boxes[0];
const newUpper = recorded['226'].boxes[1];
state = api.select(0, [oldBody], 1000);
state = api.update(state, [newUpper], 1150);
assert.equal(state.state, 'recovering');
state = api.update(state, [newUpper], 1150);
assert.equal(state.state, 'recovering');
state = api.update(state, [newUpper], 1750);
assert.equal(state.state, 'recovering');
assert.equal(state.missingSince, 1150);
state = api.update(state, [newUpper], 2050);
assert.equal(state.state, 'lost');
state = api.select(0, [oldBody], 1000);
state = api.update(state, [newUpper,{...newUpper,left:newUpper.left+.01,right:newUpper.right+.01}], 1150);
assert.equal(state.state, 'recovering');
assert.equal(state.reason, 'ambiguous');
assert.equal(state.index, -1);
assert.equal(api.bodyPart(oldBody,{...newUpper,top:.6,bottom:.99}), false);
assert.equal(api.bodyPart(oldBody,{...oldBody,left:.60,right:.84}), false);

// Confirmed shape memory expires; it cannot waive confirmation indefinitely.
state = api.select(0, recorded['460'].boxes, 1000);
state = api.update(state, recorded['461'].boxes, 1150);
state = api.update(state, recorded['462'].boxes, 1300);
state = api.update(state, recorded['464'].boxes.slice(0,1), 1450);
state = api.update(state, recorded['465'].boxes.slice(1), 2401);
state = api.update(state, recorded['466'].boxes, 2550);
assert.equal(state.state, 'recovering');
assert.equal(state.index, -1);
console.log('PASS: recorded body/part recovery; current boxes only; fresh confirmation; rival/stale rejection; fixed recovery deadline');
