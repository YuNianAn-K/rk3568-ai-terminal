import QtQuick 2.12
import QtQuick.Controls 2.12

Item {
    id: root

    property real unit: width / 720
    property string voiceState: voiceBridge.state
    property string transcript: voiceBridge.transcript
    property string answer: voiceBridge.answer
    property bool diagnosticsVisible: false
    property var timingRows: [
        { "label": "MIC OPEN", "start": "button_trigger", "end": "record_start" },
        { "label": "RECORD FINALIZE", "start": "record_stop_requested", "end": "record_end" },
        { "label": "ASR", "start": "asr_request", "end": "asr_result" },
        { "label": "LLM FIRST", "start": "llm_request", "end": "llm_first_token" },
        { "label": "LLM TOTAL", "start": "llm_request", "end": "llm_end" },
        { "label": "TTS", "start": "tts_request", "end": "tts_ready" },
        { "label": "PLAYBACK", "start": "playback_start", "end": "reply_end" },
        { "label": "END TO END", "start": "button_trigger", "end": "reply_end" }
    ]

    onDiagnosticsVisibleChanged: {
        if (diagnosticsVisible)
            voiceBridge.refreshStatus()
    }

    function diagnosticValue(name, suffix) {
        var value = voiceBridge.diagnostics[name]
        if (value === undefined || value === null || value === "")
            return "--"
        return String(value) + (suffix || "")
    }

    function durationText(startStage, endStage) {
        var start = voiceBridge.timings[startStage]
        var end = voiceBridge.timings[endStage]
        if (start === undefined || end === undefined)
            return "--"
        return String(Math.max(0, Number(end) - Number(start))) + " ms"
    }

    function resetInteraction() {
        if (voiceState === "recording")
            voiceBridge.cancel()
    }

    function toggleRecording() {
        if (voiceState === "idle" || voiceState === "error") {
            voiceBridge.startRecording()
        } else if (voiceState === "recording") {
            voiceBridge.stopRecording()
        } else if (voiceState === "offline") {
            voiceBridge.reconnectService()
        }
    }

    function stateTitle() {
        switch (voiceState) {
        case "recording": return "正在聆听"
        case "recognizing": return "正在识别"
        case "thinking": return "正在思考"
        case "replying": return "正在回答"
        case "playing": return "正在播放"
        case "error": return "出现问题"
        case "initializing": return "正在初始化"
        case "starting": return "正在打开麦克风"
        case "offline": return "服务未连接"
        default: return "轻触开始对话"
        }
    }

    function stateHint() {
        switch (voiceState) {
        case "recording": return "说完后再次轻触"
        case "recognizing": return "正在整理你的声音"
        case "thinking": return "正在生成回答"
        case "replying": return "回答正在到来"
        case "playing": return "再次轻触可开始下一轮"
        case "error": return "轻触重新尝试"
        case "initializing": return "语音服务正在准备"
        case "starting": return "请稍候"
        case "offline": return "轻触重新连接"
        default: return "按下麦克风，然后自然说话"
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#050505"
    }

    Rectangle {
        id: topLine
        height: Math.max(1, root.unit)
        color: "#262626"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: 116 * root.unit
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: 54 * root.unit
        anchors.top: parent.top
        anchors.topMargin: 42 * root.unit
        spacing: 4 * root.unit

        Text {
            text: "AI VOICE"
            color: "#FAFAFA"
            font.pixelSize: 24 * root.unit
            font.weight: Font.DemiBold
            font.letterSpacing: 4 * root.unit
        }

        Text {
            text: "MIMO INTELLIGENCE"
            color: "#777777"
            font.pixelSize: 10 * root.unit
            font.letterSpacing: 2 * root.unit
        }
    }

    Item {
        id: statusIndicator
        anchors.right: parent.right
        anchors.rightMargin: 54 * root.unit
        anchors.verticalCenter: topLine.top
        width: statusContent.width
        height: Math.max(statusContent.height, 44 * root.unit)

        Row {
            id: statusContent
            anchors.centerIn: parent
            spacing: 10 * root.unit

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 7 * root.unit
                height: width
                radius: width / 2
                color: voiceBridge.connected ? "#F5F5F5" : "#777777"
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: voiceBridge.connected ? "READY" : "OFFLINE"
                color: "#A0A0A0"
                font.pixelSize: 11 * root.unit
                font.letterSpacing: 2 * root.unit
            }
        }

        MouseArea {
            anchors.fill: parent
            onPressAndHold: root.diagnosticsVisible = true
        }
    }

    Item {
        id: interactionArea
        width: parent.width
        height: 560 * root.unit
        anchors.top: topLine.bottom

        Item {
            id: wave
            width: 400 * root.unit
            height: 96 * root.unit
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 72 * root.unit

            Row {
                anchors.centerIn: parent
                spacing: 13 * root.unit

                Repeater {
                    model: 11

                    Item {
                        width: 3 * root.unit
                        height: wave.height

                        Rectangle {
                            id: waveBar
                            width: parent.width
                            height: root.voiceState === "recording"
                                    ? (22 + (index % 4) * 10) * root.unit
                                    : 3 * root.unit
                            radius: width / 2
                            color: index === 5 ? "#FFFFFF" : "#777777"
                            anchors.centerIn: parent

                            SequentialAnimation on height {
                                running: root.voiceState === "recording"
                                loops: Animation.Infinite
                                NumberAnimation {
                                    to: (26 + ((index + 2) % 5) * 12) * root.unit
                                    duration: 260 + index * 19
                                    easing.type: Easing.InOutSine
                                }
                                NumberAnimation {
                                    to: (12 + (index % 3) * 7) * root.unit
                                    duration: 310 + index * 17
                                    easing.type: Easing.InOutSine
                                }
                            }

                            Behavior on height {
                                NumberAnimation { duration: 220 }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            id: voiceButton
            width: 224 * root.unit
            height: width
            radius: width / 2
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: wave.bottom
            anchors.topMargin: 38 * root.unit
            color: root.voiceState === "recording" ? "#050505" : "#F7F7F5"
            border.width: 2 * root.unit
            border.color: "#F7F7F5"
            scale: buttonArea.pressed ? 0.96 : 1.0

            Behavior on color { ColorAnimation { duration: 180 } }
            Behavior on scale { NumberAnimation { duration: 100 } }

            Rectangle {
                width: 40 * root.unit
                height: 66 * root.unit
                radius: width / 2
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: -12 * root.unit
                color: root.voiceState === "recording" ? "#F7F7F5" : "#050505"
            }

            Rectangle {
                width: 70 * root.unit
                height: 56 * root.unit
                radius: width / 2
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 8 * root.unit
                color: "transparent"
                border.width: 5 * root.unit
                border.color: root.voiceState === "recording" ? "#F7F7F5" : "#050505"

                Rectangle {
                    width: parent.width + 4 * root.unit
                    height: parent.height / 2
                    x: -2 * root.unit
                    y: -2 * root.unit
                    color: voiceButton.color
                }
            }

            Rectangle {
                width: 5 * root.unit
                height: 28 * root.unit
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 48 * root.unit
                color: root.voiceState === "recording" ? "#F7F7F5" : "#050505"
            }

            Rectangle {
                width: 46 * root.unit
                height: 5 * root.unit
                radius: height / 2
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 62 * root.unit
                color: root.voiceState === "recording" ? "#F7F7F5" : "#050505"
            }

            MouseArea {
                id: buttonArea
                anchors.fill: parent
                onClicked: root.toggleRecording()
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: voiceButton.bottom
            anchors.topMargin: 32 * root.unit
            text: root.stateTitle()
            color: "#F5F5F5"
            font.pixelSize: 28 * root.unit
            font.weight: Font.Medium
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: voiceButton.bottom
            anchors.topMargin: 78 * root.unit
            text: root.stateHint()
            color: "#777777"
            font.pixelSize: 15 * root.unit
        }
    }

    Rectangle {
        id: conversationPanel
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 42 * root.unit
        anchors.rightMargin: 42 * root.unit
        anchors.top: interactionArea.bottom
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 48 * root.unit
        radius: 28 * root.unit
        color: "#0C0C0C"
        border.width: Math.max(1, root.unit)
        border.color: "#252525"

        Column {
            anchors.fill: parent
            anchors.margins: 32 * root.unit
            spacing: 22 * root.unit

            Text {
                text: "CONVERSATION"
                color: "#666666"
                font.pixelSize: 10 * root.unit
                font.letterSpacing: 2 * root.unit
            }

            Text {
                width: parent.width
                text: root.transcript.length > 0
                      ? root.transcript
                      : "你的问题会显示在这里"
                color: root.transcript.length > 0 ? "#AFAFAF" : "#555555"
                font.pixelSize: 17 * root.unit
                wrapMode: Text.Wrap
                maximumLineCount: 3
                elide: Text.ElideRight
            }

            Rectangle {
                width: parent.width
                height: Math.max(1, root.unit)
                color: "#222222"
            }

            Text {
                width: parent.width
                text: root.answer.length > 0
                      ? root.answer
                      : "AI 的回答会在这里出现"
                color: root.answer.length > 0 ? "#F2F2F2" : "#555555"
                font.pixelSize: 21 * root.unit
                lineHeight: 1.25
                wrapMode: Text.Wrap
                maximumLineCount: 6
                elide: Text.ElideRight
            }
        }
    }

    Dock {}

    Rectangle {
        id: diagnosticsPanel
        anchors.fill: parent
        z: 100
        visible: root.diagnosticsVisible
        color: "#050505"

        Timer {
            interval: 2000
            repeat: true
            running: diagnosticsPanel.visible
            onTriggered: voiceBridge.refreshStatus()
        }

        Column {
            anchors.fill: parent
            anchors.leftMargin: 54 * root.unit
            anchors.rightMargin: 54 * root.unit
            anchors.topMargin: 48 * root.unit
            anchors.bottomMargin: 48 * root.unit
            spacing: 24 * root.unit

            Row {
                width: parent.width

                Column {
                    width: parent.width - closeLabel.width
                    spacing: 4 * root.unit

                    Text {
                        text: "DIAGNOSTICS"
                        color: "#FAFAFA"
                        font.pixelSize: 24 * root.unit
                        font.weight: Font.DemiBold
                        font.letterSpacing: 4 * root.unit
                    }

                    Text {
                        text: "VOICE PIPELINE / LIVE"
                        color: "#666666"
                        font.pixelSize: 10 * root.unit
                        font.letterSpacing: 2 * root.unit
                    }
                }

                Text {
                    id: closeLabel
                    text: "CLOSE"
                    color: "#A0A0A0"
                    font.pixelSize: 12 * root.unit
                    font.letterSpacing: 2 * root.unit

                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -16 * root.unit
                        onClicked: root.diagnosticsVisible = false
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: Math.max(1, root.unit)
                color: "#262626"
            }

            Grid {
                width: parent.width
                columns: 2
                columnSpacing: 20 * root.unit
                rowSpacing: 18 * root.unit

                Repeater {
                    model: [
                        { "label": "STATE", "value": root.voiceState.toUpperCase() },
                        { "label": "ROUND", "value": String(voiceBridge.roundId) },
                        { "label": "NETWORK", "value": root.diagnosticValue("network", "").toUpperCase() },
                        { "label": "CLIENTS", "value": root.diagnosticValue("clients", "") },
                        { "label": "MEM AVAILABLE", "value": root.diagnosticValue("memory_available_mb", " MB") },
                        { "label": "SERVICE RSS", "value": root.diagnosticValue("service_rss_mb", " MB") },
                        { "label": "SERVICE UPTIME", "value": root.diagnosticValue("service_uptime_s", " s") },
                        { "label": "SOCKET", "value": voiceBridge.connected ? "CONNECTED" : "OFFLINE" }
                    ]

                    Column {
                        width: (diagnosticsPanel.width - 128 * root.unit) / 2
                        spacing: 5 * root.unit

                        Text {
                            text: modelData.label
                            color: "#606060"
                            font.pixelSize: 10 * root.unit
                            font.letterSpacing: 1.5 * root.unit
                        }

                        Text {
                            text: modelData.value
                            color: "#F0F0F0"
                            font.pixelSize: 18 * root.unit
                        }
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: Math.max(1, root.unit)
                color: "#262626"
            }

            Text {
                text: "LAST ROUND LATENCY"
                color: "#666666"
                font.pixelSize: 10 * root.unit
                font.letterSpacing: 2 * root.unit
            }

            Column {
                width: parent.width
                spacing: 13 * root.unit

                Repeater {
                    model: root.timingRows

                    Row {
                        width: parent.width

                        Text {
                            width: parent.width * 0.65
                            text: modelData.label
                            color: "#888888"
                            font.pixelSize: 14 * root.unit
                            font.letterSpacing: 1.5 * root.unit
                        }

                        Text {
                            width: parent.width * 0.35
                            horizontalAlignment: Text.AlignRight
                            text: root.durationText(modelData.start, modelData.end)
                            color: "#F5F5F5"
                            font.pixelSize: 16 * root.unit
                        }
                    }
                }
            }

            Text {
                width: parent.width
                text: "Long-press READY to open · Values refresh every 2 seconds"
                color: "#484848"
                font.pixelSize: 10 * root.unit
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }
}
