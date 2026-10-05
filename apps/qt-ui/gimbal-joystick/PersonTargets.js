.pragma library

function empty() {
    return {locked: false, box: null, index: -1, state: "searching"}
}

function overlap(a, b) {
    var width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
    var height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top))
    var intersection = width * height
    var area = (a.right - a.left) * (a.bottom - a.top) +
               (b.right - b.left) * (b.bottom - b.top) - intersection
    return area > 0 ? intersection / area : 0
}

function select(index, boxes) {
    if (index < 0 || index >= boxes.length)
        return empty()
    return {locked: true, box: boxes[index], index: index, state: "selected"}
}

function update(previous, boxes) {
    if (!previous.locked) {
        if (boxes.length === 1)
            return select(0, boxes)
        return {locked: false, box: null, index: -1,
                state: boxes.length ? "multiple" : "no_person"}
    }
    // A lost or ambiguous target requires an explicit tap. Box overlap is
    // geometric association, not identity recognition or automatic re-ID.
    if (!previous.box)
        return {locked: true, box: null, index: -1, state: "lost"}
    var best = -1, bestValue = 0, second = 0
    for (var i = 0; i < boxes.length; ++i) {
        var value = overlap(previous.box, boxes[i])
        if (value > bestValue) {
            second = bestValue
            bestValue = value
            best = i
        } else {
            second = Math.max(second, value)
        }
    }
    if (bestValue < 0.25 || (second >= 0.25 && bestValue - second < 0.15))
        return {locked: true, box: null, index: -1, state: "lost"}
    return select(best, boxes)
}

function description(state, count) {
    if (state.state === "selected")
        return "人物：目标已选 · " + count + " 人 · 仅检测"
    if (state.state === "multiple")
        return "人物：" + count + " 人 · 点击人物框选择"
    if (state.state === "lost")
        return "人物：目标丢失 · 点击人物框重新选择"
    return "人物：无人 · 仅检测"
}
