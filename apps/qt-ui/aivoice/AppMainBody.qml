import QtQuick 2.12
import "VoiceState.js" as VoiceState

Item {
    id: root
    property var service: voiceBridge
    property bool active: true
    property bool diagnosticsVisible: false
    readonly property real unit: Math.min(width / 720, height / 1280)
    readonly property string voiceState: service.state
    readonly property string visualState: VoiceState.visualState(voiceState, service.connected)
    readonly property string interaction: VoiceState.action(voiceState, service.connected)
    readonly property bool motionEnabled: active && visible && !diagnosticsVisible
    property string lastErrorKey: ""
    property string errorNotice: ""
    property bool errorNoticeVisible: false

    UiTheme { id: appTheme }
    function resetInteraction() {
        if (voiceState === "recording" && service.message.indexOf("自动结束") < 0) service.cancel()
    }
    function activateVoice() {
        if (!active || !visible || diagnosticsVisible) return
        switch (interaction) {
        case "start": service.startRecording(); break
        case "stop": service.stopRecording(); break
        case "reconnect": service.reconnectService(); break
        }
    }
    function presentError() {
        if (!active || !visible || diagnosticsVisible || !service.connected || voiceState !== "error") return
        var message = service.errorMessage || service.message || "本轮处理失败，请重试"
        var key = VoiceState.errorKey(service.roundId, message)
        if (key === lastErrorKey) return
        lastErrorKey = key
        errorNotice = message
        errorNoticeVisible = true
        errorNoticeTimer.restart()
        core.playError()
    }
    onVoiceStateChanged: {
        if (voiceState !== "error") errorNoticeVisible = false
        Qt.callLater(presentError)
    }
    onActiveChanged: {
        if (active) Qt.callLater(presentError)
        else { errorNoticeVisible = false; diagnosticsVisible = false }
    }
    onVisibleChanged: {
        if (visible) Qt.callLater(presentError)
        else errorNoticeVisible = false
    }
    onDiagnosticsVisibleChanged: {
        if (diagnosticsVisible) service.refreshStatus()
        else Qt.callLater(presentError)
    }
    Connections {
        target: root.service
        function onErrorMessageChanged() { Qt.callLater(root.presentError) }
        function onConnectedChanged() {
            if (!root.service.connected) root.lastErrorKey = ""
        }
    }
    Component.onCompleted: Qt.callLater(presentError)
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: appTheme.backgroundTop }
            GradientStop { position: 1; color: appTheme.backgroundBottom }
        }
    }
    // Fit both dimensions while preserving the portrait layout and hit targets.
    Item {
        id: canvas
        width: 720; height: 1280
        anchors.centerIn: parent
        scale: root.unit
        Item {
            x: 40; y: 34; width: 260; height: 64
            Row {
                anchors.verticalCenter: parent.verticalCenter; spacing: 10
                Rectangle {
                    width: 6; height: 6; radius: 3
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.visualState === "offline" ? appTheme.orange : appTheme.cyan
                }
                Text {
                    text: root.visualState === "offline" ? "离线" : "情绪核心"
                    color: appTheme.textSecondary; font.pixelSize: 18; font.letterSpacing: 2
                }
            }
            MouseArea { anchors.fill: parent; onPressAndHold: root.diagnosticsVisible = true }
        }
        // Reserve the top-right region for the existing system Wi-Fi overlay.
        EmotionCore {
            id: core
            x: 130; y: 164; width: 460; height: 460
            theme: appTheme; visualState: root.visualState; motionEnabled: root.motionEnabled
            interactive: root.interaction === "start" && root.active && !root.diagnosticsVisible
            onActivated: root.activateVoice()
        }
        Text {
            x: 40; y: 650; width: 640
            text: VoiceState.title(root.voiceState, root.service.connected, root.service.message)
            horizontalAlignment: Text.AlignHCenter
            color: appTheme.textPrimary; font.pixelSize: 30; font.weight: Font.Medium
        }
        Text {
            x: 40; y: 701; width: 640
            text: VoiceState.hint(root.voiceState, root.service.connected, root.service.message)
            horizontalAlignment: Text.AlignHCenter
            color: appTheme.textSecondary; font.pixelSize: 19; wrapMode: Text.Wrap
        }
        ConversationCard {
            objectName: "conversationCard"
            x: 40; y: 775; width: 640; height: 246
            theme: appTheme; transcript: root.service.transcript; answer: root.service.answer
        }
        VoiceWave {
            x: 230; y: 1037; width: 260; height: 54
            mode: root.voiceState === "starting" ? "idle" : root.visualState
            motionEnabled: root.motionEnabled
            accent: root.visualState === "offline" ? appTheme.orange : appTheme.cyan
        }
        Rectangle {
            id: microphone
            antialiasing: true
            x: 312; y: 1110; width: 96; height: 96; radius: 48
            color: root.voiceState === "recording" ? "#234250" : appTheme.panel
            border.width: 1; border.color: root.visualState === "offline" ? appTheme.orange : appTheme.cyan
            opacity: root.interaction === "none" ? 0.38 : 1
            scale: microphoneArea.pressed ? 0.96 : 1
            Behavior on color { ColorAnimation { duration: appTheme.stateDuration } }
            Behavior on scale { NumberAnimation { duration: 100 } }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 25; width: 16; height: 29; radius: 8
                z: 1
                antialiasing: true
                color: root.visualState === "offline" ? appTheme.orange : appTheme.cyan
            }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 40; width: 30; height: 25; radius: 15
                color: "transparent"; border.width: 2
                border.color: root.visualState === "offline" ? appTheme.orange : appTheme.cyan
                Rectangle { x: -2; y: -2; width: 34; height: 13; color: microphone.color }
            }
            Rectangle { x: 47; y: 64; width: 2; height: 10; color: microphone.border.color }
            Rectangle { x: 37; y: 73; width: 22; height: 2; radius: 1; color: microphone.border.color }
            MouseArea {
                id: microphoneArea
                anchors.fill: parent; anchors.margins: -8
                enabled: root.active && root.interaction !== "none" && !root.diagnosticsVisible
                onClicked: root.activateVoice()
            }
        }
        Rectangle {
            x: 40; y: 110; width: 640; height: noticeText.implicitHeight + 32
            radius: 14; color: appTheme.panel; border.color: appTheme.orange
            visible: root.errorNoticeVisible
            Text {
                id: noticeText
                x: 16; y: 16; width: 608
                text: root.errorNotice; textFormat: Text.PlainText
                wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
                color: appTheme.textPrimary; font.pixelSize: 20
            }
        }
    }
    Dock {}
    Timer {
        id: errorNoticeTimer
        interval: appTheme.errorNoticeDuration; repeat: false
        onTriggered: root.errorNoticeVisible = false
    }
    DiagnosticsPanel {
        anchors.fill: parent; z: 100
        visible: root.diagnosticsVisible && root.active && root.visible
        theme: appTheme; service: root.service; unit: root.unit
        onClosed: root.diagnosticsVisible = false
    }
}
