function empty() { return {mode:"none",point:null,hits:0,reference:null,calibration:null} }
function contains(b,p) { return p.x>=b.left && p.x<=b.right && p.y>=b.top && p.y<=b.bottom }
function clamp(v,lo,hi) { return Math.max(lo,Math.min(hi,v)) }
function eligible(b,h) {
    return h.score>=.80 && h.width>0 && contains(b,h) &&
        h.y<=b.top+.65*(b.bottom-b.top) && h.width<=.8*(b.right-b.left)
}
function sameBody(a,b) {
    // QML can wrap a QVariantMap anew on each property read. Compare the
    // current frame's values, not JavaScript object identity.
    return a && b && a.left===b.left && a.right===b.right &&
        a.top===b.top && a.bottom===b.bottom && a.score===b.score
}
function matchingSize(edges,excludedBody,excludedHead,headCount) {
    var owner=[]
    for (var i=0;i<headCount;++i) owner.push(-1)
    function augment(body,visited) {
        for (var j=0;j<edges[body].length;++j) {
            var head=edges[body][j]
            if (head===excludedHead || visited[head]) continue
            visited[head]=true
            if (owner[head]===-1 || augment(owner[head],visited)) {
                owner[head]=body
                return true
            }
        }
        return false
    }
    var count=0
    for (var b=0;b<edges.length;++b)
        if (b!==excludedBody && augment(b,[])) ++count
    return count
}
function assignedHead(target,bodies,heads) {
    // Test every maximum one-to-one assignment, without choosing by score or
    // array order. A locally shared face can still have a globally forced
    // owner: A->{a,b}, B->{b} has only A->a, B->b. Genuine alternatives pause.
    var index=target.index, edges=[]
    if (index===undefined || index<0 || index>=bodies.length || !sameBody(bodies[index],target.box)) {
        index=-1
        for (var b=0;b<bodies.length;++b) if (sameBody(bodies[b],target.box)) { index=b;break }
    }
    if (index<0) return {ambiguous:true,head:null,reason:"body_not_current"}
    for (var i=0;i<bodies.length;++i) {
        var choices=[]
        for (var j=0;j<heads.length;++j) if (eligible(bodies[i],heads[j])) choices.push(j)
        edges.push(choices)
    }
    if (!edges[index].length) return {ambiguous:false,head:null,reason:"no_face"}
    var maximum=matchingSize(edges,-1,-1,heads.length), possible=[]
    var mayBeUnmatched=matchingSize(edges,index,-1,heads.length)===maximum
    for (var k=0;k<edges[index].length;++k) {
        var h=edges[index][k]
        if (1+matchingSize(edges,index,h,heads.length)===maximum) possible.push(h)
    }
    if (mayBeUnmatched || possible.length!==1)
        return {ambiguous:true,head:null,reason:"multiple_assignments"}
    return {ambiguous:false,head:heads[possible[0]],reason:"unique_assignment"}
}
function ownershipFit(body, head, owner) {
    var width=body.right-body.left, height=body.bottom-body.top
    var expectedWidth=owner.width*width
    if (!(width>0 && height>0 && expectedWidth>0)) return Infinity
    var ratio=head.width/expectedWidth
    if (ratio<.75 || ratio>1.33) return Infinity
    var dx=head.x-(body.left+owner.x*width)
    var dy=head.y-(body.top+owner.y*height)
    return Math.sqrt(dx*dx+dy*dy)/head.width
}
function continuousOwner(previous,target,bodies,heads,stamp) {
    var owner=previous.owner, body=target.box
    var probe=target.frameProbe===undefined ? stamp : target.frameProbe
    if (!owner || owner.hits<3 || body.score<.70 || stamp<=owner.stamp || stamp-owner.stamp>500 ||
            probe<=owner.probe || stamp-owner.probe>500 || stamp<probe || stamp-probe>500 ||
            !sameBody(bodies[target.index],body)) return null
    var old=owner.body, aw=old.right-old.left, ah=old.bottom-old.top
    var bw=body.right-body.left, bh=body.bottom-body.top
    var areaRatio=(aw*ah)/(bw*bh)
    var dx=(old.left+old.right-body.left-body.right)/2
    var dy=(old.top+old.bottom-body.top-body.bottom)/2
    if (areaRatio<.75 || areaRatio>1.33 || Math.sqrt(dx*dx+dy*dy)>.12) return null
    var compatible=[], eligibleCount=0
    for (var h=0;h<heads.length;++h)
        if (eligible(body,heads[h])) {
            ++eligibleCount
            if (heads[h].score>=.85 && ownershipFit(body,heads[h],owner)<=.35)
                compatible.push(heads[h])
        }
    if (eligibleCount!==1 || compatible.length!==1) return null
    var head=compatible[0], fit=ownershipFit(body,head,owner)
    // The face is a current observation. Require a unique geometric owner,
    // not a higher detector score or a preference for the previous index.
    for (var i=0;i<bodies.length;++i) {
        if (i===target.index || !eligible(bodies[i],head)) continue
        if (ownershipFit(bodies[i],head,owner)<Math.max(.75,fit+.50)) return null
    }
    return head
}
function rememberOwner(next,previous,body,head,stamp,inferred,probe) {
    var old=previous.owner, width=body.right-body.left, height=body.bottom-body.top
    var continuous=old && stamp>old.stamp && probe>old.probe && stamp-old.probe<=500 &&
        ownershipFit(body,head,old)<=.35
    // Store only this frame's actual body/face. Inferred ownership does not
    // increase maturity; empty, stale or ambiguous frames clear this chain.
    next.owner={body:body,x:inferred ? old.x : (head.x-body.left)/width,
        y:inferred ? old.y : (head.y-body.top)/height,
        width:inferred ? old.width : head.width/width,stamp:stamp,probe:probe,
        hits:inferred ? old.hits : continuous ? old.hits+1 : 1}
    next.ownerSource=inferred ? "continuous_owner" : "unique_assignment"
    return next
}
function framed(previous,next,b,stamp) {
    var relative=next.point.y-(b.top+b.bottom)/2
    var reference=next.reference.y
    var relativeX=next.point.x-(b.left+b.right)/2
    var referenceX=next.reference.x
    if (previous.point && previous.reference && previous.relative !== undefined &&
            stamp>previous.stamp && stamp-previous.stamp<=500) {
        // Translate the framing reference when the measurement source changes;
        // do not mix old image coordinates into the new measured control point.
        var start=previous.reference.y
        if (previous.mode!==next.mode) start+=relative-previous.relative
        var limit=.15*Math.min(.25,(stamp-previous.stamp)/1000)
        reference=start+clamp(reference-start,-limit,limit)
        if (previous.relativeX!==undefined) {
            var startX=previous.reference.x
            if (previous.mode!==next.mode) startX+=relativeX-previous.relativeX
            referenceX=startX+clamp(referenceX-startX,-limit,limit)
        }
    }
    next.goalY=next.reference.y
    next.reference.y=clamp(reference,.20,.85)
    next.reference.x=clamp(referenceX,.20,.80)
    next.relativeX=relativeX
    next.relative=relative;next.stamp=stamp
    return next
}
function bodyAim(b,calibration) {
    var height=b.bottom-b.top, width=b.right-b.left
    var compatible=calibration && height/calibration.height>=.75 && height/calibration.height<=1.33 &&
        width/calibration.width>=.75 && width/calibration.width<=1.33
    // This is a framing reference, not a predicted face. The measured body
    // centre remains the only fallback control point, with original timestamps.
    return {mode:"body",point:{x:(b.left+b.right)/2,y:(b.top+b.bottom)/2},
        reference:{x:.5,y:compatible ? clamp(.33+calibration.offset*height,.20,.85) : .60},
        calibration:compatible ? calibration : null,hits:0,
        referenceKind:compatible ? "body_calibrated" : "body_default"}
}
function updateCurrent(previous,target,bodies,heads,stamp) {
    if (target.state!=="selected" || !target.box) return empty()
    var probe=target.frameProbe===undefined ? stamp : target.frameProbe
    if (probe<=0 || stamp<probe || stamp-probe>500) return empty()
    var b=target.box, assignment=assignedHead(target,bodies,heads)
    if (assignment.ambiguous && assignment.reason==="multiple_assignments") {
        var owned=continuousOwner(previous,target,bodies,heads,stamp)
        if (owned) assignment={ambiguous:false,head:owned,reason:"continuous_owner"}
    }
    if (assignment.ambiguous) {
        if (assignment.reason!=="multiple_assignments" || b.score<.70)
            return {mode:"pause",point:null,hits:0,reference:null,calibration:null,reason:assignment.reason}
        // A shared/ambiguous face must not block a reliable body target. Keep
        // the body composition point until face ownership becomes unique; all
        // frame-age, stop and camera-fault protections remain in the worker.
        var bodyOnly=bodyAim(b,previous.calibration)
        bodyOnly.reason="head_ambiguous";bodyOnly.hits=0
        return framed(previous,bodyOnly,b,stamp)
    }
    var fallback=bodyAim(b,previous.calibration)
    if (!assignment.head) return framed(previous,fallback,b,stamp)
    var p=assignment.head
    var continuous=previous.candidate && stamp>previous.stamp && stamp-previous.stamp<=500 &&
        Math.abs(p.x-previous.candidate.x)<=.15 && Math.abs(p.y-previous.candidate.y)<=.15
    var hits=continuous ? previous.hits+1 : 1
    if (hits<2) {
        fallback.hits=hits;fallback.stamp=stamp;fallback.candidate=p
        return rememberOwner(framed(previous,fallback,b,stamp),previous,b,p,stamp,assignment.reason==="continuous_owner",probe)
    }
    var height=b.bottom-b.top
    return rememberOwner(framed(previous,{mode:"head",point:p,reference:{x:.5,y:.33},referenceKind:"face_upper_third",
        hits:hits,stamp:stamp,candidate:p,
        calibration:{offset:((b.top+b.bottom)/2-p.y)/height,
                     height:height,width:b.right-b.left}},b,stamp),previous,b,p,stamp,assignment.reason==="continuous_owner",probe)
}

function update(previous,target,bodies,heads,stamp) {
    if (target.state!=="selected") {
        var memory=previous.memory || (previous.point ? previous : null)
        var next=empty()
        // Keep only reference/calibration history. The suspended result has no
        // point or reference, so neither UI nor worker can drive an old aim.
        if (target.state==="recovering" && memory && memory.frameProbe>0 &&
                stamp>=memory.frameProbe && stamp-memory.frameProbe<=500)
            next.memory=memory
        return next
    }
    var prior=previous.memory
    if (prior && prior.body && prior.frameProbe>0 &&
            stamp>=prior.frameProbe && stamp-prior.frameProbe<=500 &&
            target.frameProbe>prior.frameProbe &&
            sameBody(bodies[target.index],target.box)) {
        var b=target.box, old=prior.body
        var inter=Math.max(0,Math.min(b.right,old.right)-Math.max(b.left,old.left))*
                  Math.max(0,Math.min(b.bottom,old.bottom)-Math.max(b.top,old.top))
        var union=(b.right-b.left)*(b.bottom-b.top)+(old.right-old.left)*(old.bottom-old.top)-inter
        if (union>0 && inter/union>=.25) previous=prior
    }
    var result=updateCurrent(previous,target,bodies,heads,stamp)
    if (result.point) {
        result.body=target.box
        result.frameProbe=target.frameProbe===undefined ? stamp : target.frameProbe
    }
    return result
}
