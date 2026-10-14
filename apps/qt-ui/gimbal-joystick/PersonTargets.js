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

function select(index, boxes, stamp) {
    if (index < 0 || index >= boxes.length || boxes[index].score < 0.55)
        return empty()
    return {locked: true, box: boxes[index], index: index, state: "selected", boxStamp: stamp}
}

function continuity(a, b) {
    var aw = a.right - a.left, ah = a.bottom - a.top
    var bw = b.right - b.left, bh = b.bottom - b.top
    var scale = Math.min(aw * ah, bw * bh) / Math.max(aw * ah, bw * bh)
    var distance = Math.sqrt(Math.pow((a.left + a.right - b.left - b.right) / 2, 2) +
                             Math.pow((a.top + a.bottom - b.top - b.bottom) / 2, 2))
    return {value: 0.65 * overlap(a, b) + 0.20 * scale +
                   0.15 * Math.max(0, 1 - distance / 0.25),
            scale: scale, distance: distance}
}

function bodyPart(a, b) {
    var aw = a.right - a.left, ah = a.bottom - a.top
    var bw = b.right - b.left, bh = b.bottom - b.top
    var horizontal = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
    var heightRatio = Math.min(ah, bh) / Math.max(ah, bh)
    // Occlusion can remove the legs without moving the head. Require shared
    // horizontal extent and a nearby top edge; a disjoint rival cannot qualify.
    return overlap(a, b) >= 0.15 && heightRatio >= 0.35 && heightRatio <= 0.75 &&
        Math.min(aw, bw) / Math.max(aw, bw) >= 0.60 &&
        horizontal / Math.min(aw, bw) >= 0.55 &&
        Math.abs(a.top - b.top) / Math.max(ah, bh) <= 0.12 &&
        Math.abs((a.left + a.right - b.left - b.right) / 2) / Math.max(aw, bw) <= 0.45
}

function accepted(previous, box, index, stamp) {
    var next = {locked: true, box: box, index: index, state: "selected", boxStamp: stamp}
    if (previous.alternateBox && stamp - previous.alternateStamp <= 900) {
        next.alternateBox = previous.alternateBox
        next.alternateStamp = previous.alternateStamp
    }
    if (previous.boxStamp !== undefined && bodyPart(previous.box, box)) {
        next.alternateBox = previous.box
        next.alternateStamp = previous.boxStamp
    }
    return next
}

function knownShape(previous, box, stamp) {
    // Shape memory is for association only. Every emitted box is still from
    // the current result, and the controller independently enforces 500ms.
    if (!previous.alternateBox || stamp - previous.alternateStamp > 900) return false
    var shape = continuity(previous.alternateBox, box)
    return overlap(previous.alternateBox, box) >= 0.60 && shape.scale >= 0.65 &&
        bodyPart(previous.box, box)
}

function recovering(previous, stamp, reason, candidate, hits) {
    var since = previous.missingSince === undefined ? stamp : previous.missingSince
    if (stamp - since >= 900)
        return {locked: true, box: null, index: -1, state: "lost", reason: reason}
    return {locked: true, box: previous.box, index: -1, state: "recovering",
            missingSince: since, reason: reason, candidate: candidate,
            hits: hits || 0, stamp: stamp, boxStamp: previous.boxStamp,
            alternateBox: previous.alternateBox, alternateStamp: previous.alternateStamp}
}

function update(previous, boxes, stamp) {
    stamp = stamp === undefined ? Date.now() : stamp
    if (!previous.locked) {
        var eligible = []
        for (var j = 0; j < boxes.length; ++j)
            if (boxes[j].score >= 0.70) eligible.push(j)
        if (eligible.length === 1) {
            var candidate = boxes[eligible[0]]
            var hits = previous.candidate && overlap(previous.candidate, candidate) >= 0.4 &&
                       stamp > previous.stamp && stamp - previous.stamp <= 500 ? previous.hits + 1 : 1
            if (hits >= 3) return select(eligible[0], boxes, stamp)
            return {locked: false, box: null, index: -1, state: "confirming",
                    candidate: candidate, hits: hits, stamp: stamp}
        }
        return {locked: false, box: null, index: -1,
                state: eligible.length ? "multiple" : boxes.length ? "candidate" : "no_person"}
    }
    // A lost or ambiguous target requires an explicit tap. Box overlap is
    // geometric association, not identity recognition or automatic re-ID.
    if (!previous.box)
        return {locked: true, box: null, index: -1, state: "lost"}
    if (previous.state === "recovering" && stamp - previous.missingSince >= 900)
        return {locked: true, box: null, index: -1, state: "lost"}
    // During a scale-change confirmation, associate the next fresh result to
    // that candidate; using the old tiny fragment again can reject its body.
    var reference = previous.reason === "geometry" && previous.candidate &&
        stamp > previous.stamp && stamp - previous.stamp <= 500 ? previous.candidate : previous.box
    var best = -1, bestValue = 0, second = 0, secondIndex = -1
    for (var i = 0; i < boxes.length; ++i) {
        if (boxes[i].score < 0.40) continue
        var normalMatch = overlap(reference, boxes[i]) >= 0.25
        var partialMatch = boxes[i].score >= 0.55 && bodyPart(reference, boxes[i])
        if (!normalMatch && !partialMatch) continue
        // Score alone cannot distinguish an upper-body fragment from the
        // previously selected full-body box. Prefer stable size and centre.
        var value = continuity(reference, boxes[i]).value
        if (value > bestValue) {
            second = bestValue
            secondIndex = best
            bestValue = value
            best = i
        } else {
            if (value > second) { second = value; secondIndex = i }
        }
    }
    if (best < 0) return recovering(previous, stamp, "missing")
    var ambiguous = secondIndex >= 0 && bestValue - second < 0.12
    if (ambiguous && boxes[best].score >= 0.55 &&
            boxes[secondIndex].score < 0.55 && boxes[best].score - boxes[secondIndex].score >= 0.08)
        ambiguous = false
    // A single ambiguous result pauses PWM rather than destroying the session.
    // The original recovery deadline remains fixed even if boxes alternate.
    if (ambiguous) return recovering(previous, stamp, "ambiguous")
    var geometry = continuity(previous.box, boxes[best])
    var partialRecovery = overlap(previous.box, boxes[best]) < 0.25
    if (partialRecovery || (geometry.scale < 0.50 && !knownShape(previous, boxes[best], stamp))) {
        var confirmations = previous.reason === "geometry" && previous.candidate &&
            overlap(previous.candidate, boxes[best]) >= 0.40 &&
            stamp > previous.stamp && stamp - previous.stamp <= 500 ? previous.hits + 1 : 1
        if (confirmations < 2)
            return recovering(previous, stamp, "geometry", boxes[best], confirmations)
    }
    return accepted(previous, boxes[best], best, stamp)
}

function description(state, count) {
    if (state.state === "selected")
        return "人物：目标已选 · " + count + " 人 · 仅检测"
    if (state.state === "multiple")
        return "人物：" + count + " 人 · 点击人物框选择"
    if (state.state === "lost")
        return "人物：目标丢失 · 点击人物框重新选择"
    if (state.state === "recovering")
        return "人物：短暂漏检 · 暂停运动，等待目标"
    return "人物：无人 · 仅检测"
}
