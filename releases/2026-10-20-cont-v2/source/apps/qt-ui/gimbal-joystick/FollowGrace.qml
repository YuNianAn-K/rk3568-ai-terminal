import QtQuick 2.12
import "PersonTargets.js" as PersonTargets

QtObject {
    id: grace
    property bool active: false
    property bool holding: false
    signal pauseRequested()
    property Timer deadline: Timer {
        repeat: false
        onTriggered: {
            grace.holding = false
            if (grace.active) grace.pauseRequested()
        }
    }
    function clear() {
        deadline.stop()
        holding = false
    }
    function update(target, resultStamp, graceMs) {
        if (!active) { clear(); return }
        var remaining = PersonTargets.missGraceRemaining(target,resultStamp,graceMs)
        if (!(remaining > 0)) { clear(); pauseRequested(); return }
        // Bound by the original miss origin and aim probe. A fresh result can
        // shorten this deadline; a stalled detector cannot postpone it.
        holding = true
        deadline.interval = Math.max(1,Math.ceil(remaining))
        deadline.restart()
    }
    onActiveChanged: if (!active) clear()
}
