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
            aimProbe: previous.aimProbe,
            alternateBox: previous.alternateBox, alternateStamp: previous.alternateStamp}
}

function clearFacePreference(index, boxes, heads) {
    if (!heads) return false
    for (var j=0;j<heads.length;++j) {
        var h=heads[j]
        if (h.score<.80 || !(h.width>0)) continue
        var owners=0, matches=false
        for (var i=0;i<boxes.length;++i) {
            var b=boxes[i]
            if (h.x>=b.left && h.x<=b.right && h.y>=b.top && h.y<=b.top+.65*(b.bottom-b.top) &&
                    h.width<=.8*(b.right-b.left)) {
                ++owners
                if (i===index) matches=true
            }
        }
        // A visible, uniquely associated face is an acquisition preference,
        // never liveness/identity proof (a poster can also contain a face).
        if (matches && owners===1) return true
    }
    return false
}
function preferredIndex(previous, boxes, indices, stamp, heads) {
    // Acquisition only: prefer the larger, more central, higher-scoring person.
    // This is a framing preference, not a nearest-person measurement, identity
    // check, or proof that the chosen person is the intended user. A small
    // bonus keeps the same candidate while it is being confirmed, so two
    // similar people cannot make the choice flip every frame.
    var best = indices[0], bestValue = -Infinity
    for (var k = 0; k < indices.length; ++k) {
        var index = indices[k], box = boxes[index]
        var area = (box.right - box.left) * (box.bottom - box.top)
        var cx = (box.left + box.right) / 2, cy = (box.top + box.bottom) / 2
        var centrality = 1 - Math.min(1, Math.sqrt((cx - .5) * (cx - .5) +
                                                   (cy - .5) * (cy - .5)) / .7071)
        var value = .65 * area + .25 * centrality + .10 * box.score
        if (clearFacePreference(index,boxes,heads)) value+=1
        if (previous.candidate && previous.stamp !== undefined && stamp > previous.stamp &&
                stamp - previous.stamp <= 500 && overlap(previous.candidate, box) >= .40)
            value += .15
        if (value > bestValue) { bestValue = value; best = index }
    }
    return best
}

function missGraceRemaining(previous, stamp, graceMs) {
    if (!missGraceActive(previous,stamp,graceMs)) return 0
    var remaining=(graceMs===undefined ? 250 : graceMs)-(stamp-previous.missingSince)
    if (previous.aimProbe!==undefined)
        remaining=Math.min(remaining,500-(stamp-previous.aimProbe))
    return isFinite(remaining) ? Math.max(0,remaining) : 0
}

function missGraceActive(previous, stamp, graceMs) {
    // A single missed result must not move PWM off immediately. The worker keeps
    // executing the last fresh destination during the grace window; it does not
    // freeze or predict a new position. The grace therefore may not outlive the
    // original capture frame: aimProbe is the probe time of the last selected
    // result, and the worker independently stops at probe age > 500ms. Keeping
    // both on the same boundary prevents the UI from extending stale motion.
    if (!previous || previous.state !== "recovering" || previous.reason !== "missing")
        return false
    if (previous.missingSince === undefined || !(stamp >= previous.missingSince))
        return false
    if (previous.aimProbe !== undefined &&
            (stamp < previous.aimProbe || stamp - previous.aimProbe > 500))
        return false
    return stamp - previous.missingSince < (graceMs === undefined ? 250 : graceMs)
}

function updateGeometry(previous, boxes, stamp, heads, referenceBox) {
    stamp = stamp === undefined ? Date.now() : stamp
    if (!previous.locked) {
        var eligible = []
        for (var j = 0; j < boxes.length; ++j)
            if (boxes[j].score >= 0.70) eligible.push(j)
        if (eligible.length) {
            var index = preferredIndex(previous, boxes, eligible, stamp, heads)
            var candidate = boxes[index]
            var hits = previous.candidate && overlap(previous.candidate, candidate) >= 0.4 &&
                       stamp > previous.stamp && stamp - previous.stamp <= 500 ? previous.hits + 1 : 1
            if (hits >= 3) return select(index, boxes, stamp)
            return {locked: false, box: null, index: -1, state: "confirming",
                    candidate: candidate, hits: hits, stamp: stamp,
                    reason: eligible.length > 1 ? "multi_auto" : "single"}
        }
        return {locked: false, box: null, index: -1,
                state: boxes.length ? "candidate" : "no_person"}
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
        stamp > previous.stamp && stamp - previous.stamp <= 500 ? previous.candidate : (referenceBox || previous.box)
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

function bounded(value, limit) { return Math.max(-limit, Math.min(limit, value)) }
function centre(box) { return {x:(box.left+box.right)/2, y:(box.top+box.bottom)/2} }
function inside(box, point) {
    return point.x>=box.left && point.x<=box.right && point.y>=box.top && point.y<=box.bottom
}
function owners(point, boxes) {
    var count=0
    for (var i=0;i<boxes.length;++i) if (inside(boxes[i],point)) ++count
    return count
}
function translated(box, dx, dy) {
    return {left:box.left+dx,right:box.right+dx,top:box.top+dy,bottom:box.bottom+dy,score:box.score}
}
function evidence(previous, heads, boxes, probe, selectedBox) {
    var old=previous.evidence || {}, next={}, key
    for (key in old) next[key]=old[key]
    var matches=[], dt=old.headProbe ? (probe-old.headProbe)/1000 : 0
    for (var i=0;i<heads.length;++i) {
        var h=heads[i]
        if (h.score<.80 || !(h.width>0)) continue
        if (selectedBox && (!inside(selectedBox,h) ||
                h.y>selectedBox.top+.65*(selectedBox.bottom-selectedBox.top) ||
                h.width>.8*(selectedBox.right-selectedBox.left) || owners(h,boxes)!==1)) continue
        if (old.head && dt>0 && dt<=.50) {
            var ratio=h.width/old.head.width
            var px=old.head.x+bounded((old.hvx||0)*dt,.20)
            var py=old.head.y+bounded((old.hvy||0)*dt,.20)
            var radius=Math.min(.20,Math.max(.065,.65*Math.max(h.width,old.head.width)+.45*dt))
            var travel=Math.sqrt(Math.pow(h.x-old.head.x,2)+Math.pow(h.y-old.head.y,2))
            // A longer detection gap may cover a larger real displacement.
            // Large jumps additionally require an established, consistent
            // velocity; a new face cannot seed itself during body recovery.
            if (dt>.35 && travel>.20) {
                var speed=Math.sqrt(Math.pow(old.hvx||0,2)+Math.pow(old.hvy||0,2))
                var alignment=(h.x-old.head.x)*(old.hvx||0)+(h.y-old.head.y)*(old.hvy||0)
                var residual=Math.sqrt(Math.pow(h.x-px,2)+Math.pow(h.y-py,2))
                if ((old.headHits||0)<3 || speed<.25 || alignment<=0 ||
                        residual>Math.max(.08,.45*Math.max(h.width,old.head.width)+.20*dt)) continue
            }
            if (ratio<.60 || ratio>1.67 || Math.abs(h.x-px)>radius || Math.abs(h.y-py)>radius ||
                    travel>Math.min(.45,.06+1.6*dt)) continue
        } else if (!selectedBox) continue
        matches.push(h)
    }
    if (matches.length===1) {
        var head=matches[0], continuous=old.head && dt>0 && dt<=.50
        next.hvx=continuous ? bounded(.5*(old.hvx||0)+.5*(head.x-old.head.x)/dt,1.6) : 0
        next.hvy=continuous ? bounded(.5*(old.hvy||0)+.5*(head.y-old.head.y)/dt,1.6) : 0
        next.head=head;next.headProbe=probe;next.headHits=continuous ? (old.headHits||0)+1 : 1
    } else if (matches.length>1 || (old.headProbe && probe-old.headProbe>500)) {
        next.head=null;next.headHits=0;next.hvx=next.hvy=0
    }
    return next
}
function remember(next, info, box, probe) {
    // A weak observed box may still drive a fresh, valid measurement. It may
    // not overwrite the association envelope that decides who returns next.
    if (next.state==="selected" && (box.score>=.70 || !info.body)) {
        var dt=info.bodyProbe ? (probe-info.bodyProbe)/1000 : 0
        var motionBox=box
        if (info.body && dt>0 && dt<=.5) {
            var ow=info.body.right-info.body.left, oh=info.body.bottom-info.body.top
            var nw=box.right-box.left, nh=box.bottom-box.top
            // A side-on body can narrow before it accelerates. Smooth only
            // the association envelope; never replace the observed output.
            if (Math.min(oh,nh)/Math.max(oh,nh)>=.85 &&
                    Math.min(ow,nw)/Math.max(ow,nw)>=.45 &&
                    Math.abs(info.body.top-box.top)<=.12*Math.max(oh,nh)) {
                var width=.7*ow+.3*nw, c=centre(box)
                motionBox={left:c.x-width/2,right:c.x+width/2,
                           top:box.top,bottom:box.bottom,score:box.score}
            }
        }
        if (info.body && dt>0 && dt<=.5 && continuity(info.body,motionBox).scale>=.65) {
            var old=centre(info.body), current=centre(box)
            info.vx=bounded(.4*(info.vx||0)+.6*(current.x-old.x)/dt,1.6)
            info.vy=bounded(.4*(info.vy||0)+.6*(current.y-old.y)/dt,1.6)
            info.velocityHits=(info.velocityHits||0)+1
        } else { info.vx=info.vy=0;info.velocityHits=0 }
        info.body=motionBox;info.bodyProbe=probe
    }
    next.evidence=info
    return next
}
function update(previous, boxes, stamp, heads, probe) {
    // Three-argument callers retain the original geometry contract. The live
    // caller supplies original frame time and current heads explicitly.
    if (heads===undefined || probe===undefined) return updateGeometry(previous,boxes,stamp)
    if (previous.locked && !previous.box) return updateGeometry(previous,boxes,stamp)
    if (probe<=0 || stamp<probe || stamp-probe>500 ||
            (previous.frameProbe!==undefined && probe<=previous.frameProbe)) {
        if (!previous.locked) return empty()
        var invalid=recovering(previous,stamp,"missing")
        invalid.evidence=previous.evidence;invalid.frameProbe=previous.frameProbe
        return invalid
    }
    if (!previous.locked || !previous.box) {
        var initial=updateGeometry(previous,boxes,stamp,heads)
        initial.frameProbe=probe
        if (initial.state!=="selected") return initial
        initial.aimProbe=probe
        return remember(initial,evidence({},heads,boxes,probe,initial.box),initial.box,probe)
    }
    var referenceBox=null
    var retained=previous.evidence
    if (previous.box.score<.55 && retained && retained.body &&
            probe>retained.bodyProbe && probe-retained.bodyProbe<=500) {
        referenceBox=retained.body
    }
    // The trusted envelope ranks candidates only. Shape confirmation still
    // compares with the last actual box; a retained wide body must not waive
    // a sudden displacement/crop confirmation of the current measurement.
    var next=updateGeometry(previous,boxes,stamp,undefined,referenceBox)
    // A current, continuously observed face can contradict a geometric body
    // handover. Only its unique current carrier qualifies; shared faces still
    // pause. This never seeds a new face or reopens an expired/lost session.
    var faceInfo=evidence(previous,heads,boxes,probe,null)
    var oldInfo=previous.evidence || {}
    if (next.state!=="lost" && oldInfo.head && oldInfo.headHits>=2 &&
            faceInfo.head && faceInfo.headProbe===probe) {
        var carriers=[]
        for (var fi=0;fi<boxes.length;++fi) {
            var fb=boxes[fi], fh=faceInfo.head
            if (fb.score>=.40 && inside(fb,fh) &&
                    fh.y<=fb.top+.65*(fb.bottom-fb.top) &&
                    fh.width<=.8*(fb.right-fb.left)) carriers.push(fi)
        }
        if (carriers.length===1 && (next.state!=="selected" || next.index!==carriers[0])) {
            var fb=boxes[carriers[0]], oldBody=oldInfo.body || previous.box
            var fit=continuity(oldBody,fb)
            if (fit.scale>=.40 && fit.distance<=.30 && overlap(oldBody,fb)>=.15) {
                next=accepted(previous,fb,carriers[0],stamp)
                next.associationSource="current_face_carrier"
            }
        }
    }
    var info=evidence(previous,heads,boxes,probe,next.state==="selected" ? next.box : null)
    next.frameProbe=probe
    if (next.state==="selected") {
        next.aimProbe=probe
        return remember(next,info,next.box,probe)
    }
    next.evidence=info
    // Do not waive the existing ambiguity pause, fixed recovery deadline, or
    // explicit re-selection after loss. Predictions never become output boxes.
    if (next.state==="lost" || next.reason==="ambiguous" || next.reason==="geometry") return next
    var candidates=[], body=info.body || previous.box
    var elapsed=info.bodyProbe ? (probe-info.bodyProbe)/1000 : 0
    var predicted=translated(body,bounded((info.vx||0)*elapsed,.30),bounded((info.vy||0)*elapsed,.30))
    for (var i=0;i<boxes.length;++i) {
        var box=boxes[i]
        if (box.score<.55) continue
        var scale=continuity(body,box).scale
        var face=info.head && info.headProbe===probe && info.headHits>=2 &&
            inside(box,info.head) && owners(info.head,boxes)===1 &&
            info.head.y<=box.top+.65*(box.bottom-box.top) &&
            info.head.width<=.8*(box.right-box.left)
        // Real event images show a head/shoulder crop at the frame bottom.
        // Only a strong, edge-clipped current body with a continuously tracked
        // strong face may waive the ordinary body-area continuity gate.
        var edgeCrop=face && scale>=.10 && box.score>=.70 && info.head.score>=.85 &&
            info.headHits>=3 && info.head.width>=.08 &&
            (box.bottom>=.97 || box.top<=.03 || box.left<=.03 || box.right>=.97)
        if (scale<.40 && !edgeCrop) continue
        var predictedMatch=info.velocityHits>=2 && elapsed>0 && elapsed<=.5 &&
            overlap(predicted,box)>=.30 && continuity(predicted,box).distance<=.16 &&
            continuity(body,box).scale>=.65
        // Confirm a tentative body-motion match against its fresh observation,
        // rather than the increasingly distant pre-gap prediction. This path
        // cannot start a recovery or extend its original deadline.
        var pending=previous.rescue
        var confirmedMotion=pending && pending.source==="body_motion" &&
            probe>pending.probe && probe-pending.probe<=250 && elapsed>0 && elapsed<=.5 &&
            overlap(pending.box,box)>=.40 && continuity(pending.box,box).scale>=.65 &&
            continuity(pending.box,box).distance<=.16
        if (!face && !predictedMatch && !confirmedMotion) continue
        candidates.push({index:i,box:box,source:face ? "face_motion" : "body_motion",
                         value:continuity(predicted,box).value+(face ? .30 : 0)})
    }
    if (!candidates.length) return next
    candidates.sort(function(a,b) {return b.value-a.value})
    if (candidates.length>1 && candidates[0].value-candidates[1].value<.12) {
        next=recovering(previous,stamp,"ambiguous")
        next.evidence=info;next.frameProbe=probe
        return next
    }
    var best=candidates[0], pending=previous.rescue
    var hits=pending && probe>pending.probe && probe-pending.probe<=250 &&
        overlap(pending.box,best.box)>=.40 ? pending.hits+1 : 1
    if (hits<2) {
        next=recovering(previous,stamp,"motion")
        next.rescue={box:best.box,probe:probe,hits:hits,source:best.source}
        next.evidence=info;next.frameProbe=probe
        return next
    }
    next=accepted(previous,best.box,best.index,stamp)
    next.frameProbe=probe;next.aimProbe=probe;next.associationSource=best.source
    return remember(next,info,best.box,probe)
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
