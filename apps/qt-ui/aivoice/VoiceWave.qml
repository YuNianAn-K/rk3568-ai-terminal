import QtQuick 2.12

Item {
    id: root
    property string mode: "idle"
    property color accent: "#63cbdc"
    property bool motionEnabled: true
    // Negative means the current protocol provides no real audio envelope.
    property real audioLevel: -1
    readonly property bool active: mode === "listening" || mode === "speaking"
    Row {
        anchors.centerIn: parent
        spacing: 9
        Repeater {
            model: 9
            Item {
                width: 4; height: root.height
                property real pulse: 0.4
                Rectangle {
                    anchors.centerIn: parent
                    width: 4
                    height: !root.active ? 4 : 7 + 38 * (root.audioLevel >= 0
                        ? Math.max(0, Math.min(1, root.audioLevel)) * (1 - Math.abs(index - 4) * 0.12)
                        : (root.motionEnabled ? parent.pulse : 0.25))
                    radius: 2; color: root.accent
                    opacity: root.active ? 0.75 : 0.28
                    Behavior on height { NumberAnimation { duration: 90 } }
                }
                SequentialAnimation on pulse {
                    running: root.motionEnabled && root.active && root.audioLevel < 0
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.45 + (index % 3) * 0.2; duration: 300 + index * 37; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 0.12 + (index % 2) * 0.1; duration: 370 + index * 23; easing.type: Easing.InOutSine }
                }
            }
        }
    }
}
