import QtQuick 2.12
import QtQuick.Window 2.12
import QtMultimedia 5.15
import GimbalPreview 1.0
import "PersonTargets.js" as PersonTargets

Window {
    id: window
    visible: true
    width: Screen.width
    height: Screen.height
    color: "#06101c"
    flags: Qt.FramelessWindowHint

    property real uiScale: Math.min(width / 720, height / 1280)
    property string direction: ""
    property string cameraFault: ""
    property bool emergencyStopped: false
    property var personTarget: PersonTargets.empty()
    property bool personFollowing: false
    property int visiblePersonCount: {
        var count = 0
        for (var i = 0; i < personTracker.detections.length; ++i)
            if (personTracker.detections[i].score >= 0.40 || i === personTarget.index) ++count
        return count
    }
    property bool voiceOwned: false
    property bool voiceNotice: false
    property bool autoVoice: voiceBridge.state === "recording" && voiceBridge.message.indexOf("自动结束") >= 0
    property bool showVoicePanel: personTracker.active || voiceOwned || voiceNotice
    property string personHint: !cameraReady ? "请先连接摄像头，等待实时画面" :
        !gimbalBridge.connected ? "云台控制未连接，请等待恢复" :
        !gimbalBridge.positionReady ? "先关闭人物检测，点回中位，再重新开启检测" :
        personFollowing ? (personTarget.state === "recovering" ?
                          (personTarget.reason === "ambiguous" ? "目标框重叠 · 暂停运动，等待分离" :
                           personTarget.reason === "geometry" ? "人物框变化 · 暂停运动，重新确认" :
                           "短暂漏检 · 暂停运动，等待目标恢复") :
                          gimbalBridge.personArmed ? "正在跟随 · 短暂漏检可恢复" : "正在确认目标，请保持在画面内") :
        personTarget.state === "selected" ? "目标已选，可点开始跟随或使用语音指令" :
        personTarget.state === "lost" ? "目标已丢失，请点人物框重新选择，再开始跟随" :
        personTarget.state === "multiple" ? "检测到多人，请点画面中的人物框选择目标" :
        personTarget.state === "candidate" ? "检测到候选 · 可点较清晰的框选择，低分框请靠近镜头" :
        personTarget.state === "confirming" ? "正在确认人物，请保持在画面内" :
        "请站到镜头前，单人出现后自动选择"
    property string voiceLabel: !voiceBridge.connected ? "语音未连接" :
        (voiceOwned || autoVoice) && voiceBridge.state === "recording" ? "结束录音" :
        voiceBridge.state === "initializing" ? "语音准备中" :
        voiceBridge.state === "idle" && voiceBridge.message.indexOf("待唤醒") === 0 ? "小爱同学 · 或点此说话" :
        voiceBridge.state === "idle" || voiceBridge.state === "error" ? "说话控制云台" :
        voiceBridge.state === "recording" ? "其他页面正在录音" : "语音处理中"
    property bool cameraEnabled: cameraMonitor.present && visible && cameraFault === ""
    property bool cameraReady: cameraEnabled && camera.cameraStatus === Camera.ActiveStatus &&
                               handTracker.previewReady
    property string cameraStatusText: !cameraMonitor.present ? "摄像头：USB 已断开" :
                                      cameraFault !== "" ? "摄像头故障：" + cameraFault :
                                      cameraReady ? "摄像头：实时预览" : "摄像头：连接中"

    function moveStick(x, y) {
        var dx = x - 200
        var dy = y - 200
        var length = Math.sqrt(dx * dx + dy * dy)
        var reach = Math.min(length, 125)
        thumb.x = 200 + (length > 0 ? dx / length * reach : 0) - 34
        thumb.y = 200 + (length > 0 ? dy / length * reach : 0) - 34
        if (emergencyStopped || length < 42 || !cameraReady) {
            direction = ""
            gimbalBridge.stop()
            return
        }
        var next = Math.abs(dx) >= Math.abs(dy)
                 ? (dx < 0 ? "PAN_LEFT" : "PAN_RIGHT")
                 : (dy < 0 ? "TILT_UP" : "TILT_DOWN")
        if (direction !== next) {
            direction = next
            gimbalBridge.press(next)
        }
    }
    function releaseStick() {
        personFollowing = false
        direction = ""
        emergencyStopped = false
        thumb.x = 166
        thumb.y = 166
        gimbalBridge.stop()
    }
    function stopPersonFollow() {
        if (personFollowing) {
            personFollowing = false
            gimbalBridge.stop()
        }
    }
    function cancelVoiceRound() {
        if (voiceOwned && voiceBridge.state === "recording") {
            voiceBridge.cancel()
            voiceOwned = false
        }
    }
    function startPersonFollow(requestId) {
        if (!visible || !active) return "inactive"
        if (!cameraReady) return "camera_unavailable"
        if (!gimbalBridge.connected || !gimbalBridge.trackCapable) return "controller_unavailable"
        if (!gimbalBridge.positionReady) return "position_unknown"
        if (handTracker.active || direction !== "") return "busy"
        if (!personTracker.active || personTarget.state !== "selected" || !personTracker.resultFresh) return "select_target"
        if (personFollowing) return gimbalBridge.personArmed ? "active" : "busy"
        personFollowing = true
        gimbalBridge.personStart(requestId)
        return "pending"
    }
    onVisibleChanged: if (!visible) { cancelVoiceRound(); personTracker.stop(); handTracker.stop(); releaseStick() }
    onActiveChanged: if (!active) { cancelVoiceRound(); personTracker.stop(); handTracker.stop(); releaseStick() }
    onClosing: { personTracker.stop(); handTracker.stop(); releaseStick() }
    onCameraReadyChanged: if (!cameraReady) personTracker.stop()

    Connections {
        target: personTracker
        function onActiveChanged() {
            window.stopPersonFollow()
            window.personTarget = PersonTargets.empty()
        }
        function onDetectionsChanged() {
            var previousTarget = window.personTarget
            window.personTarget = PersonTargets.update(window.personTarget, personTracker.detections, personTracker.resultMs)
            if (window.personFollowing && (previousTarget.state !== window.personTarget.state ||
                    previousTarget.reason !== window.personTarget.reason))
                console.log("PERSON_ASSOCIATION " + JSON.stringify({
                    state: window.personTarget.state, reason: window.personTarget.reason || "",
                    result_ms: personTracker.resultMs, index: window.personTarget.index}))
            if (!window.personFollowing) return
            if (window.personTarget.state === "recovering") {
                gimbalBridge.personPause()
                return
            }
            if (window.personTarget.state !== "selected") {
                console.log("PERSON_FOLLOW_STOP target=" + window.personTarget.state)
                window.stopPersonFollow()
                return
            }
            var box = window.personTarget.box
            gimbalBridge.personSample((box.left + box.right) / 2,
                                      (box.top + box.bottom) / 2, box.score,
                                      personTracker.resultProbeMs, personTracker.resultMs)
        }
    }
    Connections {
        target: gimbalBridge
        function onTrackingEnded() { window.stopPersonFollow() }
    }
    Connections {
        target: trackingControl
        function onRequest(command, requestId) {
            if (command === "CANCEL_START") { window.stopPersonFollow(); return }
            if (command === "STOP_TRACKING") {
                handTracker.stop()
                personTracker.stop()
                window.releaseStick()
                trackingControl.resolve(gimbalBridge.connected ? "pending" : "controller_unavailable")
            } else {
                trackingControl.resolve(window.startPersonFollow(requestId))
            }
        }
    }
    Connections {
        target: voiceBridge
        function onMessageChanged() {
            // Display wake feedback here; never open/activate the AI Voice app.
            if (window.active && (voiceBridge.message.indexOf("已唤醒") === 0 || window.autoVoice))
                window.voiceNotice = true
        }
        function onStateChanged() {
            if (voiceBridge.state === "idle" || voiceBridge.state === "error" || voiceBridge.state === "offline")
                window.voiceOwned = false
            else if ((!window.visible || !window.active) && window.voiceOwned && voiceBridge.state === "recording")
                window.cancelVoiceRound()
        }
    }

    Camera {
        id: camera
        objectName: "camera"
        deviceId: cameraMonitor.deviceId
        captureMode: Camera.CaptureViewfinder
        cameraState: window.cameraEnabled ? Camera.ActiveState : Camera.UnloadedState
        viewfinder.resolution: Qt.size(640, 480)
        viewfinder.minimumFrameRate: 30
        viewfinder.maximumFrameRate: 30
        onError: {
            window.cameraFault = errorString || "无法取流"
            window.releaseStick()
            handTracker.stop()
            personTracker.stop()
        }
    }
    Connections {
        target: cameraMonitor
        function onPresentChanged() {
            if (!cameraMonitor.present) {
                window.cameraFault = "USB 已断开"
                window.releaseStick()
                handTracker.stop()
                personTracker.stop()
            } else {
                window.cameraFault = ""
            }
        }
    }
    Timer {
        interval: 2000
        repeat: true
        running: true
        onTriggered: if (window.direction === "" && !handTracker.active && !window.personFollowing) gimbalBridge.refresh()
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: "#06101c" }
            GradientStop { position: 1; color: "#101529" }
        }
    }
    Item {
        width: 720
        height: 1280
        anchors.centerIn: parent
        scale: window.uiScale

        Text {
            x: 40; y: 43; width: 520
            text: "云台摄像"
            color: "#eaf8fc"; font.pixelSize: 42; font.bold: true
        }
        Rectangle {
            x: 574; y: 44; width: 100; height: 64; radius: 17
            color: "#23404a"; border.width: 1; border.color: "#5b8891"
            Text { anchors.centerIn: parent; text: "退出"; color: "#def2f4"; font.pixelSize: 24 }
            MouseArea {
                anchors.fill: parent
                onClicked: { personTracker.stop(); handTracker.stop(); window.releaseStick(); Qt.quit() }
            }
        }
        Rectangle {
            x: 40; y: 128; width: 640; height: 382; radius: 18
            color: "#02090c"; border.width: 2; border.color: "#2e6c78"
            PreviewFrame {
                id: preview
                objectName: "preview"
                anchors.fill: parent
                anchors.margins: 8
                visible: window.cameraReady
            }
            PersonOverlay {
                anchors.fill: preview
                visible: window.cameraReady && personTracker.active
                detections: personTracker.detections
                selectedIndex: window.personTarget.index
                onSelected: {
                    window.stopPersonFollow()
                    window.personTarget = PersonTargets.select(index, personTracker.detections)
                }
            }
            Text {
                anchors.centerIn: parent
                width: parent.width - 40
                text: window.cameraStatusText
                color: "#c9e5e9"; font.pixelSize: 26
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                visible: !window.cameraReady
            }
        }
        Item {
            x: 40; y: 524; width: 640; height: 58
            Rectangle {
                x: 0; y: 0; width: 170; height: 58; radius: 14
                opacity: personTracker.active ? 0.45 : 1
                color: "#245b61"; border.width: 2; border.color: "#86dace"
                Text {
                    anchors.centerIn: parent; text: "回中位"
                    color: "white"; font.pixelSize: 24
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: window.cameraReady && gimbalBridge.connected &&
                             gimbalBridge.trackCapable && !handTracker.active && !personTracker.active
                    onClicked: { window.direction = ""; gimbalBridge.center() }
                }
            }
            Rectangle {
                x: 194; y: 0; width: 228; height: 58; radius: 14
                opacity: handTracker.active ? 0.45 : 1
                color: personTracker.active ? "#8b5143" : "#245b61"
                border.width: 2; border.color: "#86dace"
                Text {
                    anchors.centerIn: parent
                    text: personTracker.active ? "停止人物检测" : "人物检测"
                    color: "white"; font.pixelSize: 22
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: personTracker.active || (window.cameraReady && !handTracker.active)
                    onClicked: {
                        if (personTracker.active) personTracker.stop()
                        else {
                            window.releaseStick()
                            personTracker.start()
                        }
                    }
                }
            }
            Rectangle {
                x: 446; y: 0; width: 194; height: 58; radius: 14
                opacity: personTracker.active ? 0.45 : 1
                color: handTracker.active ? "#8b5143" : "#245b61"
                border.width: 2; border.color: "#86dace"
                Text {
                    anchors.centerIn: parent
                    text: handTracker.active ? "停止跟手" :
                          gimbalBridge.positionReady ? "开始跟手" : "请先回中位"
                    color: "white"; font.pixelSize: 24
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: handTracker.active || (window.cameraReady &&
                             gimbalBridge.connected && gimbalBridge.trackCapable &&
                             gimbalBridge.positionReady && !personTracker.active)
                    onClicked: {
                        if (handTracker.active) handTracker.stop()
                        else {
                            window.direction = ""
                            thumb.x = 166; thumb.y = 166
                            handTracker.start()
                        }
                    }
                }
            }
        }
        Rectangle {
            x: 40; y: 598; width: 640; height: 126; radius: 20
            color: "#101c2b"; border.width: 1
            border.color: window.cameraReady && gimbalBridge.connected ? "#243347" : "#d69a64"
            Text {
                x: 22; y: 12; width: 596; text: window.cameraStatusText
                color: "#eaf8fc"; font.pixelSize: 23; elide: Text.ElideRight
            }
            Text {
                x: 22; y: 48; width: 596; text: "云台：" + gimbalBridge.status
                color: "#eaf8fc"; font.pixelSize: 23; elide: Text.ElideRight
            }
            Text {
                x: 22; y: 84; width: 596
                text: handTracker.active ? handTracker.status :
                      personTracker.active ?
                          (personTracker.status === "人物：检测中" || personTracker.status === "人物：无人" ?
                           window.personHint :
                           personTracker.status) :
                      personTracker.status !== "人物：未启动" && personTracker.status !== "人物：已停止" ?
                          personTracker.status : gimbalBridge.detail
                color: "#91a5b6"; font.pixelSize: 18; elide: Text.ElideRight
            }
        }
        Text {
            x: 0; y: 732; width: 720
            z: 1
            visible: !window.showVoicePanel
            text: handTracker.active ? "手掌跟随中 · 松开手掌后自动停止" : "上轴后仰"
            horizontalAlignment: Text.AlignHCenter; color: "#a7d8e0"; font.pixelSize: 23
        }
        Item {
            x: 160; y: 714; width: 400; height: 400
            visible: !window.showVoicePanel
            opacity: personTracker.active ? 0.35 : 1
            Rectangle {
                anchors.fill: parent; radius: 200
                color: "#102c37"; border.width: 3; border.color: "#2e6c78"
            }
            Rectangle {
                x: 70; y: 70; width: 260; height: 260; radius: 130
                color: "transparent"; border.width: 2; border.color: "#25505c"
            }
            Rectangle {
                id: thumb; x: 166; y: 166; width: 68; height: 68; radius: 34
                color: stickArea.pressed ? "#54e1ca" : "#35c6b9"
                border.width: 3; border.color: "#b9fff2"
            }
            MouseArea {
                id: stickArea
                anchors.fill: parent
                enabled: gimbalBridge.connected && window.cameraReady && !handTracker.active && !personTracker.active
                preventStealing: true
                onPressed: window.moveStick(mouse.x, mouse.y)
                onPositionChanged: if (pressed) window.moveStick(mouse.x, mouse.y)
                onReleased: window.releaseStick()
                onCanceled: window.releaseStick()
            }
        }
        Rectangle {
            x: 160; y: 770; width: 400; height: 96; radius: 24
            visible: personTracker.active
            color: window.personFollowing ? "#8b5143" : "#245b61"
            opacity: followArea.enabled ? 1 : 0.45
            border.width: 2; border.color: "#86dace"
            Text {
                anchors.centerIn: parent
                text: window.personFollowing ? "停止跟随" :
                      !gimbalBridge.positionReady ? "停止检测后回中位" :
                      window.personTarget.state !== "selected" ? "请先选择人物" : "开始跟随"
                color: "white"; font.pixelSize: 28
            }
            MouseArea {
                id: followArea; anchors.fill: parent
                enabled: window.personFollowing || (window.cameraReady && personTracker.active &&
                         gimbalBridge.connected && gimbalBridge.trackCapable &&
                         gimbalBridge.positionReady && window.personTarget.state === "selected")
                onClicked: {
                    if (window.personFollowing) window.stopPersonFollow()
                    else window.startPersonFollow("")
                }
            }
        }
        Text {
            x: 40; y: 738; width: 640
            visible: personTracker.active
            text: "人物跟随 · " + window.visiblePersonCount + " 个候选"
            color: "#91a5b6"; font.pixelSize: 20
            horizontalAlignment: Text.AlignHCenter
        }
        Rectangle {
            x: 160; y: 770; width: 400; height: 96; radius: 24
            visible: !personTracker.active && window.voiceNotice
            color: "#15313d"; border.color: "#63cbdc"
            opacity: window.voiceOwned ? 0.45 : 1
            Text {
                anchors.centerIn: parent; text: "返回手动控制"
                color: "#e4eef2"; font.pixelSize: 26
            }
            MouseArea {
                anchors.fill: parent; enabled: !window.voiceOwned
                onClicked: window.voiceNotice = false
            }
        }
        Rectangle {
            x: 40; y: 886; width: 640; height: 230; radius: 20
            visible: window.showVoicePanel
            color: "#101c2b"; border.color: "#243347"
            Text {
                x: 22; y: 15; width: 596
                text: window.autoVoice ? "正在聆听 · 说完自动结束" :
                      window.voiceOwned && voiceBridge.state === "recording" ?
                      "正在录音 · 说完后点结束录音" :
                      window.voiceOwned || voiceBridge.state !== "idle" ? voiceBridge.message : "语音控制 · 开始跟踪人物 / 停止跟踪"
                color: "#91a5b6"; font.pixelSize: 18; elide: Text.ElideRight
            }
        }
        Rectangle {
            x: 190; y: 944; width: 340; height: 76; radius: 20
            visible: window.showVoicePanel
            color: window.voiceOwned && voiceBridge.state === "recording" ? "#8b5143" : "#245b61"
            opacity: voiceArea.enabled ? 1 : 0.45
            Text {
                anchors.centerIn: parent; color: "white"; font.pixelSize: 24
                text: window.voiceLabel
            }
            MouseArea {
                id: voiceArea; anchors.fill: parent
                enabled: voiceBridge.connected && (voiceBridge.state === "idle" || voiceBridge.state === "error" ||
                         ((window.voiceOwned || window.autoVoice) && voiceBridge.state === "recording"))
                onClicked: {
                    if ((window.voiceOwned || window.autoVoice) && voiceBridge.state === "recording") voiceBridge.stopRecording()
                    else {
                        window.voiceNotice = true
                        window.voiceOwned = true
                        voiceBridge.startRecording()
                    }
                }
            }
        }
        Text {
            objectName: "voiceTranscript"
            x: 62; y: 1030; width: 596; height: 26
            visible: window.showVoicePanel
            text: voiceBridge.transcript ? "识别：" + voiceBridge.transcript : "识别内容将在这里显示"
            textFormat: Text.PlainText
            color: "#e4eef2"; font.pixelSize: 18; elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
        }
        Text {
            objectName: "voiceFeedback"
            x: 62; y: 1062; width: 596; height: 46
            visible: window.showVoicePanel
            text: voiceBridge.errorMessage || voiceBridge.answer || voiceBridge.message
            textFormat: Text.PlainText
            color: voiceBridge.errorMessage ? "#d69a64" : "#91a5b6"; font.pixelSize: 18; wrapMode: Text.Wrap
            maximumLineCount: 2; elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
        }
        Text {
            x: 28; y: 870; width: 120; text: "底座\n向左"
            visible: !window.showVoicePanel
            horizontalAlignment: Text.AlignHCenter; color: "#a7d8e0"; font.pixelSize: 23
        }
        Text {
            x: 570; y: 870; width: 120; text: "底座\n向右"
            visible: !window.showVoicePanel
            horizontalAlignment: Text.AlignHCenter; color: "#a7d8e0"; font.pixelSize: 23
        }
        Text {
            x: 0; y: 1080; width: 720; text: "上轴前倾"
            visible: !window.showVoicePanel
            horizontalAlignment: Text.AlignHCenter; color: "#a7d8e0"; font.pixelSize: 23
        }
        Rectangle {
            x: 40; y: 1135; width: 640; height: 88; radius: 24
            color: stopArea.pressed ? "#ad4b42" : "#8d3736"
            border.width: 2; border.color: "#f2a49c"
            Text {
                anchors.centerIn: parent; text: "立即停止"
                color: "white"; font.pixelSize: 34; font.bold: true
            }
            MouseArea {
                id: stopArea; anchors.fill: parent
                onClicked: {
                    window.emergencyStopped = true
                    window.direction = ""
                    handTracker.stop()
                    personTracker.stop()
                    gimbalBridge.stop()
                }
            }
        }
        Text {
            x: 40; y: 1235; width: 640
            text: personTracker.active ? (personTracker.metrics || "选中人物后点开始跟人") :
                                        "手动单轴点动 · 跟手双轴平滑 · 立即停止"
            color: "#89aeb8"; font.pixelSize: 18
            horizontalAlignment: Text.AlignHCenter
        }
    }
}
