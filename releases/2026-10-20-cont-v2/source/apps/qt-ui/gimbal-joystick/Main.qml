import QtQuick 2.12
import QtQuick.Window 2.12
import QtMultimedia 5.15
import GimbalPreview 1.0
import "PersonTargets.js" as PersonTargets
import "HeadAim.js" as HeadAim

Window {
    id: window
    visible: true
    title: "智能终端 · " + (typeof appReleaseId !== "undefined" ? appReleaseId : "未标记版本")
    width: Screen.width
    height: Screen.height
    color: "#0c0e12"
    flags: Qt.FramelessWindowHint

    property real uiScale: Math.min(width / 720, height / 1280)
    property string direction: ""
    property string cameraFault: ""
    property bool emergencyStopped: false
    property var personTarget: PersonTargets.empty()
    property bool personFollowing: false
    // A single missed result keeps executing the last fresh destination for a
    // short grace window; it does not freeze or predict a new position. The
    // grace is still bounded by that destination's original probe age.
    property int personMissGraceMs: 250
    property var headAim: HeadAim.empty()
    property int visiblePersonCount: {
        var count = 0
        for (var i = 0; i < personTracker.detections.length; ++i)
            if (personTracker.detections[i].score >= 0.40 || i === personTarget.index) ++count
        return count
    }
    property bool voiceOwned: false
    property bool voiceNotice: false
    property bool autoVoice: voiceBridge.state === "recording" && voiceBridge.message.indexOf("自动结束") >= 0
    // Internal panels do not own camera/control resources or window focus.
    property bool showVoicePanel: true
    property bool manualPanelOpen: false
    property string visualState: cameraFault !== "" ? "视觉故障" :
        !cameraReady ? "等待相机" :
        personFollowing ? (personTarget.state === "recovering" ?
                           (personGrace.holding ? "保持 · 等待恢复" : "暂停 · 恢复目标") :
                          headAim.mode === "pause" ? "暂停 · 恢复目标" :
                          gimbalBridge.personArmed ? "跟随中" : "确认目标") :
        handTracker.active ? "手掌跟随" :
        personTarget.state === "lost" ? "目标丢失" :
        personTracker.active ? "人物检测中" : "视觉待机"
    property string personHint: !cameraReady ? "请先连接摄像头，等待实时画面" :
        !gimbalBridge.connected ? "云台控制未连接，请等待恢复" :
        !gimbalBridge.positionReady ? "先关闭人物检测，点回中位，再重新开启检测" :
        personFollowing ? (personTarget.state === "recovering" ?
                          (personTarget.reason === "ambiguous" ? "目标框重叠 · 暂停运动，等待分离" :
                           personTarget.reason === "geometry" ? "人物框变化 · 暂停运动，重新确认" :
                           personGrace.holding ?
                             "短暂漏检 · 沿用最后目标，等待恢复" :
                             "短暂漏检 · 暂停运动，等待目标恢复") :
                          headAim.mode === "pause" ? "头部或身体归属不明确 · 暂停运动，等待分离" :
                          gimbalBridge.personArmed ? "正在跟随 · 短暂漏检可恢复" : "正在确认目标，请保持在画面内") :
        personTarget.state === "selected" ? "目标已选 · 请确认人物正确，可点其他框纠正，再开始跟随" :
        personTarget.state === "lost" ? "目标已丢失，请点人物框重新选择，再开始跟随" :
        personTarget.state === "multiple" ? "检测到多人，请点画面中的人物框选择目标" :
        personTarget.state === "candidate" ? "检测到候选 · 可点较清晰的框选择，低分框请靠近镜头" :
        personTarget.state === "confirming" ? "正在初选人物 · 可点框纠正，跟随需手动开始" :
        "请站到镜头前，单人出现后自动选择"
    property string voiceLabel: !voiceBridge.connected ? "语音未连接" :
        (voiceOwned || autoVoice) && voiceBridge.state === "recording" ? "结束录音" :
        voiceBridge.state === "initializing" ? "语音准备中" :
        voiceBridge.state === "idle" && voiceBridge.message.indexOf("待唤醒") === 0 ? "小爱同学 · 或点此说话" :
        voiceBridge.state === "idle" || voiceBridge.state === "error" ? "点此说话" :
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
        personGrace.clear()
        personFollowing = false
        direction = ""
        emergencyStopped = false
        thumb.x = 166
        thumb.y = 166
        gimbalBridge.stop()
    }
    function stopPersonFollow() {
        personGrace.clear()
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
    function toggleVoiceRecording() {
        if (!voiceBridge.connected) return
        if ((voiceOwned || autoVoice) && voiceBridge.state === "recording") {
            voiceBridge.stopRecording()
        } else if (voiceBridge.state === "idle" || voiceBridge.state === "error") {
            voiceNotice = true
            voiceOwned = true
            voiceBridge.startRecording()
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
            window.headAim = HeadAim.empty()
        }
        function onDetectionsChanged() {
            var previousTarget = window.personTarget
            window.personTarget = PersonTargets.update(window.personTarget, personTracker.detections,
                personTracker.resultMs, personTracker.heads, personTracker.resultProbeMs)
            if (window.personFollowing && (previousTarget.state !== window.personTarget.state ||
                    previousTarget.reason !== window.personTarget.reason))
                console.log("PERSON_ASSOCIATION " + JSON.stringify({
                    state: window.personTarget.state, reason: window.personTarget.reason || "",
                    result_ms: personTracker.resultMs, index: window.personTarget.index,
                    source: window.personTarget.associationSource || "geometry"}))
            window.headAim = HeadAim.update(window.headAim,window.personTarget,personTracker.detections,personTracker.heads,personTracker.resultMs)
            if (!window.personFollowing) { personGrace.clear(); return }
            if (window.personTarget.state === "recovering") {
                personGrace.update(window.personTarget, personTracker.resultMs, window.personMissGraceMs)
                var grace = personGrace.holding
                console.log("PERSON_PAUSE_REASON " + JSON.stringify({reason:window.personTarget.reason || "missing",grace:grace,index:window.personTarget.index,aim_probe_ms:window.personTarget.aimProbe,probe_ms:personTracker.resultProbeMs,result_ms:personTracker.resultMs}))
                return
            }
            personGrace.clear()
            if (window.personTarget.state !== "selected") {
                console.log("PERSON_FOLLOW_STOP target=" + window.personTarget.state)
                window.stopPersonFollow()
                return
            }
            var box = window.personTarget.box
            if (!window.headAim.point || window.headAim.mode === "pause") {
                console.log("PERSON_PAUSE_REASON " + JSON.stringify({reason:window.headAim.reason || "aim_unavailable",index:window.personTarget.index,probe_ms:personTracker.resultProbeMs,result_ms:personTracker.resultMs}))
                gimbalBridge.personPause(); return
            }
            console.log("PERSON_AIM " + JSON.stringify({mode:window.headAim.mode,x:window.headAim.point.x,y:window.headAim.point.y,desired_x:window.headAim.reference.x,desired_y:window.headAim.reference.y,reference_kind:window.headAim.referenceKind,ownership_source:window.headAim.ownerSource || "body",probe_ms:personTracker.resultProbeMs,result_ms:personTracker.resultMs}))
            gimbalBridge.personFramingSample(window.headAim.point.x,
                                      window.headAim.point.y, box.score,
                                      personTracker.resultProbeMs, personTracker.resultMs,
                                      window.headAim.reference.x, window.headAim.reference.y)
        }
    }
    FollowGrace {
        id: personGrace
        active: window.personFollowing && window.cameraReady && window.visible && window.active && personTracker.active
        onPauseRequested: gimbalBridge.personPause()
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
            console.log("UNIFIED_VOICE_STATE " + JSON.stringify({
                state: voiceBridge.state, active: window.active,
                detecting: personTracker.active, following: window.personFollowing,
                wall_ms: Date.now()}))
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
            GradientStop { position: 0; color: "#171a21" }
            GradientStop { position: 0.55; color: "#10131a" }
            GradientStop { position: 1; color: "#090b10" }
        }
    }
    Item {
        width: 720; height: 1280
        anchors.centerIn: parent
        scale: window.uiScale

        Text {
            x: 28; y: 32; width: 520
            text: "智能终端 · 人物检测"
            color: "#f3f5fa"; font.pixelSize: 36; font.bold: true
        }
        Text {
            x: 30; y: 80; width: 500
            objectName: "releaseBadge"
            text: (typeof appIsPreview !== "undefined" && appIsPreview ? "试用版 · " : "版本 · ") +
                  (typeof appReleaseId !== "undefined" ? appReleaseId : "未标记版本")
            color: "#7ce7ef"; font.pixelSize: 19; font.bold: true
        }
        GlassButton {
            objectName: "exitButton"
            x: 592; y: 32; width: 100; height: 48
            label: "退出"; horizontal: true; radius: 24
            onTriggered: { personTracker.stop(); handTracker.stop(); window.releaseStick(); Qt.quit() }
        }
        Rectangle {
            x: 24; y: 112; width: 672; height: 448; radius: 26
            color: "#191e28"
            border.width: 1; border.color: "#40ffffff"
            PreviewFrame {
                id: preview
                objectName: "preview"
                cornerRadius: 26
                anchors.fill: parent
                visible: window.cameraReady
            }
            PersonOverlay {
                anchors.fill: preview
                visible: window.cameraReady && personTracker.active
                detections: personTracker.detections
                selectedIndex: window.personTarget.index
                aim: window.headAim
                onSelected: {
                    window.stopPersonFollow()
                    window.personTarget = PersonTargets.select(index, personTracker.detections)
                    window.headAim = HeadAim.empty()
                }
            }
            Text {
                anchors.centerIn: parent; width: parent.width-60
                text: window.cameraStatusText
                color: "#aab6c8"; font.pixelSize: 24
                horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                visible: !window.cameraReady
            }
            GlassSurface {
                x: 434; y: 348; width: 214; height: 42; radius: 21
                topFill: "#d638404c"; bottomFill: "#d01b202a"
                Rectangle {
                    x: 15; y: 16; width: 10; height: 10; radius: 5
                    color: window.personFollowing ? "#7dbaff" : "#a2adbc"
                }
                Text {
                    x: 36; width: parent.width-48; anchors.verticalCenter: parent.verticalCenter
                    text: window.visualState
                    color: "#e1e7f1"; font.pixelSize: 17; elide: Text.ElideRight
                }
            }
        }
        GlassSurface {
            x: 48; y: 514; width: 624; height: 110; radius: 30
            topFill: "#ed353b46"; bottomFill: "#e31b2029"
            GlassButton {
                objectName: "detectionToggle"
                x: 10; y: 8; width: 195; height: 94
                label: personTracker.active ? "停止检测" : "人物检测"
                symbol: "person"; selected: personTracker.active
                enabled: personTracker.active || (window.cameraReady && !handTracker.active)
                onTriggered: {
                    if (personTracker.active) personTracker.stop()
                    else { window.releaseStick(); personTracker.start() }
                }
            }
            GlassButton {
                objectName: "followButton"
                x: 214; y: 8; width: 195; height: 94
                label: window.personFollowing ? "停止跟随" : "开始跟随"
                symbol: window.personFollowing ? "pause" : "play"
                selected: window.personFollowing
                enabled: window.personFollowing || (window.cameraReady && personTracker.active &&
                         gimbalBridge.connected && gimbalBridge.trackCapable &&
                         gimbalBridge.positionReady && window.personTarget.state === "selected")
                onTriggered: {
                    if (window.personFollowing) window.stopPersonFollow()
                    else window.startPersonFollow("")
                }
            }
            GlassButton {
                objectName: "manualPanelButton"
                x: 418; y: 8; width: 195; height: 94
                label: window.manualPanelOpen ? "收起控制" : "手动控制"
                symbol: "manual"; selected: window.manualPanelOpen
                onTriggered: window.manualPanelOpen = !window.manualPanelOpen
            }
        }
        Text {
            x: 36; y: 640; width: 648; height: 46
            visible: !window.manualPanelOpen
            text: personTracker.active ? window.personHint :
                  handTracker.active ? handTracker.status : gimbalBridge.detail
            color: !gimbalBridge.connected || !gimbalBridge.positionReady ? "#e4ba78" : "#a7b3c5"
            font.pixelSize: 18; wrapMode: Text.Wrap
            maximumLineCount: 2; elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
        }
        GlassSurface {
            x: 24; y: 638; width: 672; height: 180; radius: 26
            visible: window.manualPanelOpen
            GlassButton {
                objectName: "centerButton"
                x: 16; y: 16; width: 176; height: 60
                label: "回中位"; symbol: "center"; horizontal: true
                enabled: window.cameraReady && gimbalBridge.connected &&
                         gimbalBridge.trackCapable && !handTracker.active && !personTracker.active
                onTriggered: { window.direction = ""; gimbalBridge.center() }
            }
            GlassButton {
                objectName: "handToggle"
                x: 16; y: 96; width: 176; height: 60
                label: handTracker.active ? "停止跟手" : "开始跟手"
                symbol: "hand"; horizontal: true; selected: handTracker.active
                enabled: handTracker.active || (window.cameraReady &&
                         gimbalBridge.connected && gimbalBridge.trackCapable &&
                         gimbalBridge.positionReady && !personTracker.active)
                onTriggered: {
                    if (handTracker.active) handTracker.stop()
                    else { window.direction = ""; thumb.x=166; thumb.y=166; handTracker.start() }
                }
            }
            Text {
                x: 394; y: 32; width: 246
                text: "手动点动"
                color: "#e9eef7"; font.pixelSize: 21; font.bold: true
            }
            Text {
                x: 394; y: 70; width: 246; height: 80
                text: personTracker.active ? "人物检测中\n手动动作已锁定" :
                      handTracker.active ? "手掌跟随中\n手动动作已锁定" : "按住方向移动\n松开立即停止"
                color: "#a6b2c5"; font.pixelSize: 17; wrapMode: Text.Wrap
            }
            Item {
                x: 224; y: 20; width: 400; height: 400
                scale: 0.35; transformOrigin: Item.TopLeft
                opacity: personTracker.active || handTracker.active ? 0.4 : 1
                Rectangle {
                    anchors.fill: parent; radius: 200
                    color: "#252e3c"; border.width: 3; border.color: "#68758a"
                }
                Rectangle {
                    x: 70; y: 70; width: 260; height: 260; radius: 130
                    color: "transparent"; border.width: 2; border.color: "#55657b"
                }
                Rectangle {
                    id: thumb; x: 166; y: 166; width: 68; height: 68; radius: 34
                    color: stickArea.pressed ? "#6fb4ff" : "#467baa"
                    border.width: 3; border.color: "#a6c9ed"
                }
                MouseArea {
                    id: stickArea; anchors.fill: parent
                    enabled: gimbalBridge.connected && window.cameraReady &&
                             !handTracker.active && !personTracker.active
                    preventStealing: true
                    onPressed: window.moveStick(mouse.x, mouse.y)
                    onPositionChanged: if (pressed) window.moveStick(mouse.x, mouse.y)
                    onReleased: window.releaseStick()
                    onCanceled: window.releaseStick()
                }
            }
        }
        UnifiedVoicePanel {
            objectName: "unifiedVoicePanel"
            x: 24; y: window.manualPanelOpen ? 836 : 702
            width: 672; height: window.manualPanelOpen ? 308 : 442
            bridge: voiceBridge
            recordingOwned: window.voiceOwned || window.autoVoice
            buttonLabel: window.voiceLabel
            visualStatus: window.visualState + " · " + gimbalBridge.status
            onRecordRequested: window.toggleVoiceRecording()
        }
        GlassSurface {
            objectName: "emergencyStopButton"
            x: 24; y: 1164; width: 672; height: 78; radius: 30
            topFill: stopArea.pressed ? "#bb3541" : "#d84d59"
            bottomFill: stopArea.pressed ? "#8b2330" : "#ad303e"
            edge: "#db8992"
            UiSymbol { x: 232; y: 25; width: 28; height: 28; name: "stop"; ink: "#ffffff" }
            Text {
                x: 276; y: 21; width: 230
                text: "立即停止"; color: "white"; font.pixelSize: 28; font.bold: true
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
            x: 24; y: 1254; width: 672
            text: personTracker.active ? (personTracker.metrics || "检测就绪 · 选择目标后开始跟随") :
                                        "视觉与语音同时可用 · 随时停止"
            color: "#95a2b8"; font.pixelSize: 14
            horizontalAlignment: Text.AlignHCenter
        }
    }
}
