import QtQuick 2.12

Item {
    id: root
    objectName: "emotionCore"
    property var theme
    property string visualState: "idle"
    property bool motionEnabled: true
    property bool interactive: false
    readonly property color accent: visualState === "offline" ? theme.orange : theme.cyan
    // Distinct resting silhouettes remain readable even with all motion paused.
    readonly property var poses: ({
        idle:      { eyeWidth: 18, eyeHeight: 22, spacing: 54, gazeX: 0, gazeY: -4, tilt: 0, smile: 0, scale: 1, opacity: 1 },
        listening: { eyeWidth: 25, eyeHeight: 34, spacing: 60, gazeX: 0, gazeY: -9, tilt: 0, smile: 0, scale: 1.035, opacity: 1 },
        thinking:  { eyeWidth: 19, eyeHeight: 16, spacing: 52, gazeX: 16, gazeY: -22, tilt: -8, smile: 0, scale: 0.99, opacity: 1 },
        speaking:  { eyeWidth: 34, eyeHeight: 16, spacing: 48, gazeX: 0, gazeY: -4, tilt: 0, smile: 1, scale: 1, opacity: 1 },
        offline:   { eyeWidth: 23, eyeHeight: 6, spacing: 52, gazeX: 0, gazeY: 2, tilt: 0, smile: 0, scale: 0.97, opacity: 0.84 },
        error:     { eyeWidth: 27, eyeHeight: 8, spacing: 48, gazeX: 0, gazeY: 1, tilt: 22, smile: 0, scale: 0.96, opacity: 0.9 }
    })
    readonly property var pose: poses[visualState] || poses.idle
    // Let child animation target bindings observe the new pose before starting.
    onPoseChanged: Qt.callLater(root.updatePose)
    property bool ready: false
    property real eyeWidth: 18
    property real eyeHeight: 22
    property real eyeSpacing: 54
    property real gazeX: 0
    property real gazeY: -4
    property real leftEyeTilt: 0
    property real eyeTilt: 0
    property real smileAmount: 0
    property real bodyScale: 1
    property real bodyOpacity: 1
    property real warmAmount: 0
    property real orbitAmount: 0
    property color eyeColor: "#c4eaf0"
    property real floatOffset: 0
    property real breathing: 0
    property real gazeDrift: 0
    property real blinkAmount: 0
    property real errorContraction: 1
    readonly property real floatDistance: visualState === "idle" ? theme.floatDistance
        : visualState === "offline" ? theme.offlineFloatDistance : theme.activeFloatDistance
    readonly property int floatDuration: visualState === "offline" ? theme.offlineFloatDuration : theme.floatDuration
    readonly property real breathAmount: visualState === "listening" ? theme.listeningBreathAmount
        : visualState === "speaking" ? theme.speakingBreathAmount
        : visualState === "offline" ? theme.offlineBreathAmount
        : visualState === "thinking" ? theme.thinkingBreathAmount : theme.idleBreathAmount
    readonly property real displayedScale: bodyScale * errorContraction
        * (1 + (motionEnabled && visualState !== "error" ? breathing - 0.5 : 0) * breathAmount)
    readonly property bool transitionsRunning: poseAnimation.running
    readonly property bool animationsRunning: transitionsRunning || floatAnimation.running || breathAnimation.running
        || gazeAnimation.running || orbitAnimation.running || blinkAnimation.running
        || errorAnimation.running || (motionEnabled && visualState === "listening")
    signal activated()

    function updatePose() {
        if (!ready) return
        poseAnimation.stop()
        if (motionEnabled) poseAnimation.start()
        else {
            eyeWidth = pose.eyeWidth; eyeHeight = pose.eyeHeight; eyeSpacing = pose.spacing
            gazeX = pose.gazeX; gazeY = pose.gazeY
            eyeTilt = pose.tilt; leftEyeTilt = visualState === "error" ? -pose.tilt : pose.tilt
            smileAmount = pose.smile; bodyScale = pose.scale; bodyOpacity = pose.opacity
            warmAmount = visualState === "offline" ? 1 : 0
            orbitAmount = visualState === "thinking" ? 1 : 0
            eyeColor = visualState === "offline" ? "#f0d4b1" : "#c4eaf0"
        }
    }
    // A standalone group can be completed atomically when the app backgrounds.
    ParallelAnimation {
        id: poseAnimation
        NumberAnimation { target: root; property: "eyeWidth"; to: root.pose.eyeWidth; duration: root.theme.stateDuration; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "eyeHeight"; to: root.pose.eyeHeight; duration: root.theme.stateDuration; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "eyeSpacing"; to: root.pose.spacing; duration: root.theme.stateDuration; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "gazeX"; to: root.pose.gazeX; duration: root.theme.stateDuration; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "gazeY"; to: root.pose.gazeY; duration: root.theme.stateDuration; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "eyeTilt"; to: root.pose.tilt; duration: root.theme.stateDuration; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "leftEyeTilt"; to: root.visualState === "error" ? -root.pose.tilt : root.pose.tilt; duration: root.theme.stateDuration; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "smileAmount"; to: root.pose.smile; duration: root.theme.stateDuration; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "bodyScale"; to: root.pose.scale; duration: root.theme.stateDuration; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "bodyOpacity"; to: root.pose.opacity; duration: root.theme.stateDuration }
        NumberAnimation { target: root; property: "warmAmount"; to: root.visualState === "offline" ? 1 : 0; duration: root.theme.stateDuration }
        NumberAnimation { target: root; property: "orbitAmount"; to: root.visualState === "thinking" ? 1 : 0; duration: root.theme.stateDuration }
        ColorAnimation { target: root; property: "eyeColor"; to: root.visualState === "offline" ? "#f0d4b1" : "#c4eaf0"; duration: root.theme.stateDuration }
    }
    Component.onCompleted: {
        ready = true
        Qt.callLater(root.updatePose)
    }

    function playError() {
        if (motionEnabled) errorAnimation.restart()
    }
    onMotionEnabledChanged: {
        if (!motionEnabled) {
            if (poseAnimation.running) poseAnimation.complete()
            errorAnimation.stop()
            blinkAnimation.stop()
            errorContraction = 1
            blinkAmount = 0
        }
    }
    onVisualStateChanged: {
        blinkAnimation.stop()
        blinkAmount = 0
        if (visualState !== "error") {
            errorAnimation.stop()
            errorContraction = 1
        }
    }
    SequentialAnimation on floatOffset {
        id: floatAnimation
        running: root.motionEnabled && root.visualState !== "error"
        loops: Animation.Infinite
        NumberAnimation { to: -root.floatDistance; duration: root.floatDuration; easing.type: Easing.InOutSine }
        NumberAnimation { to: root.floatDistance; duration: root.floatDuration; easing.type: Easing.InOutSine }
    }
    // Speaking rhythm is decorative until the service supplies an audio envelope.
    SequentialAnimation on breathing {
        id: breathAnimation
        running: root.motionEnabled && root.visualState !== "error"
        loops: Animation.Infinite
        NumberAnimation { to: 1; duration: root.visualState === "speaking" ? root.theme.speakingBreathDuration : root.visualState === "offline" ? root.theme.offlineBreathDuration : root.theme.breathDuration; easing.type: Easing.InOutSine }
        NumberAnimation { to: 0; duration: root.visualState === "speaking" ? root.theme.speakingBreathDuration + 120 : root.visualState === "offline" ? root.theme.offlineBreathDuration : root.theme.breathDuration; easing.type: Easing.InOutSine }
    }
    SequentialAnimation on gazeDrift {
        id: gazeAnimation
        running: root.motionEnabled && root.visualState === "thinking"
        loops: Animation.Infinite
        NumberAnimation { from: 0; to: 4; duration: 1400; easing.type: Easing.InOutSine }
        NumberAnimation { to: 0; duration: 1700; easing.type: Easing.InOutSine }
    }
    Item {
        id: floating
        anchors.centerIn: parent
        width: root.theme.coreDiameter
        height: width
        transform: Translate { y: root.motionEnabled ? root.floatOffset : 0 }
        scale: root.displayedScale
        opacity: root.bodyOpacity
        Repeater {
            model: 2
            Rectangle {
                property real progress: 0
                anchors.centerIn: parent
                width: parent.width * (1.03 + progress * 0.33)
                height: width; radius: width / 2
                color: "transparent"; border.width: 2; border.color: root.accent
                antialiasing: true
                opacity: 0.42 * (1 - progress)
                visible: root.visualState === "listening"
                SequentialAnimation on progress {
                    running: root.motionEnabled && root.visualState === "listening"
                    loops: Animation.Infinite
                    PauseAnimation { duration: index * 550 }
                    NumberAnimation { from: 0; to: 1; duration: 1400; easing.type: Easing.OutSine }
                }
            }
        }
        Image {
            anchors.centerIn: parent
            width: parent.width * 1.28; height: width
            // Crossfade the two static textures; no live blur or shader.
            source: "core-cool.svg"
            opacity: 1 - root.warmAmount
            sourceSize.width: 384; sourceSize.height: 384
            smooth: true
        }
        Image {
            anchors.centerIn: parent
            width: parent.width * 1.28; height: width
            source: "core-warm.svg"
            opacity: root.warmAmount
            sourceSize.width: 384; sourceSize.height: 384
            smooth: true
        }
        Item {
            id: orbit
            anchors.centerIn: parent
            width: parent.width * 1.14; height: width
            visible: opacity > 0
            opacity: root.orbitAmount
            RotationAnimation on rotation {
                id: orbitAnimation
                running: root.motionEnabled && root.visualState === "thinking"
                loops: Animation.Infinite
                from: 0; to: 360; duration: 5200
            }
            Repeater {
                model: 4
                Rectangle {
                    width: index % 2 === 0 ? 8 : 5; height: width; radius: width / 2
                    x: orbit.width / 2 + Math.cos(index * Math.PI / 2) * orbit.width * 0.48 - width / 2
                    y: orbit.height / 2 + Math.sin(index * Math.PI / 2) * orbit.width * 0.42 - height / 2
                    color: index % 2 === 0 ? root.theme.cyan : root.theme.indigo
                    antialiasing: true; opacity: 0.72
                }
            }
        }
        Row {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: root.gazeY
            transform: Translate { x: root.gazeX + (root.visualState === "thinking" && root.motionEnabled ? root.gazeDrift : 0) }
            spacing: root.eyeSpacing
            Repeater {
                model: 2
                Item {
                    width: root.eyeWidth; height: 36
                    rotation: index === 0 ? root.leftEyeTilt : root.eyeTilt
                    transform: Scale { origin.x: width / 2; origin.y: height / 2; yScale: 1 - root.blinkAmount * 0.92 }
                    Rectangle {
                        anchors.centerIn: parent
                        width: parent.width; height: root.eyeHeight; radius: Math.min(width, height) / 2
                        antialiasing: true; color: root.eyeColor
                        opacity: 0.94 * (1 - root.smileAmount)
                    }
                    Image {
                        anchors.centerIn: parent
                        width: parent.width; height: 22
                        source: "eye-smile.svg"; sourceSize.width: 68; sourceSize.height: 44
                        smooth: true; opacity: root.smileAmount
                    }
                }
            }
        }
        MouseArea { anchors.fill: parent; enabled: root.interactive; onClicked: root.activated() }
    }
    Timer {
        interval: 6500; repeat: true
        running: root.motionEnabled && root.visualState === "idle"
        onTriggered: { blinkAnimation.restart(); interval = 5000 + Math.floor(Math.random() * 4000) }
    }
    SequentialAnimation {
        id: blinkAnimation
        NumberAnimation { target: root; property: "blinkAmount"; to: 1; duration: 70 }
        NumberAnimation { target: root; property: "blinkAmount"; to: 0; duration: 110 }
    }
    SequentialAnimation {
        id: errorAnimation
        loops: 1
        NumberAnimation { target: root; property: "errorContraction"; to: 0.94; duration: 140; easing.type: Easing.OutCubic }
        NumberAnimation { target: root; property: "errorContraction"; to: 1; duration: 260; easing.type: Easing.InOutCubic }
    }
}
