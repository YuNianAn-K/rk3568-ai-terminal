import QtQuick 2.12

GlassSurface {
    id: panel
    property var bridge
    property bool recordingOwned: false
    property string buttonLabel: "点此说话"
    property string visualStatus: "视觉待机"
    property bool showTask: false
    onShowTaskChanged: console.log("UNIFIED_PANEL task=" + showTask)
    signal recordRequested()
    readonly property string phase: !bridge.connected ? "语音离线" :
        bridge.state === "recording" ? "正在聆听" :
        bridge.state === "starting" ? "已唤醒" :
        bridge.state === "recognizing" ? "识别中" :
        bridge.state === "thinking" ? "思考中" :
        bridge.state === "speaking" ? "正在回答" :
        bridge.state === "error" ? "语音错误" :
        bridge.state === "idle" ? "待唤醒" : "语音处理中"
    radius: 30
    topFill: "#ec2c313b"
    bottomFill: "#de191d25"
    edge: bridge.errorMessage ? "#a48655" : "#40ffffff"

    Text {
        x: 24; y: 23
        text: "语音对话"
        color: "#eff3fa"; font.pixelSize: 26; font.bold: true
    }
    GlassSurface {
        x: parent.width - 190; y: 22; width: 166; height: 34; radius: 17
        topFill: "#c1444e60"; bottomFill: "#a42a3445"; shadow: false
        Rectangle { x: 12; y: 12; width: 9; height: 9; radius: 5
            color: !bridge.connected || bridge.errorMessage ? "#edb875" : "#87bfff" }
        Text {
            x: 30; width: parent.width-40; anchors.verticalCenter: parent.verticalCenter
            text: panel.phase; color: "#d1ddec"; font.pixelSize: 15; elide: Text.ElideRight
        }
    }
    Row {
        x: 24; y: 65; spacing: 8
        Repeater {
            model: ["对话", "执行状态"]
            delegate: Rectangle {
                objectName: index === 0 ? "conversationTab" : "taskTab"
                width: 92; height: 30; radius: 15
                color: panel.showTask === (index === 1) ? "#37475e" : "#16394250"
                Text { anchors.centerIn: parent; text: modelData; color: "#c3d1e4"; font.pixelSize: 15 }
                MouseArea { anchors.fill: parent; onClicked: panel.showTask = index === 1 }
            }
        }
    }
    Flickable {
        objectName: "voiceConversationScroll"
        x: 24; y: 108; width: parent.width-48; height: parent.height-246
        visible: !panel.showTask
        clip: true
        contentWidth: width
        contentHeight: conversation.height
        boundsBehavior: Flickable.StopAtBounds
        Column {
            id: conversation; width: parent.width; spacing: 14
            Item {
                width: parent.width; height: heardBubble.height
                GlassSurface {
                    id: heardBubble
                    x: 100; width: parent.width-100
                    height: heard.height+24; radius: 20; shadow: false
                    topFill: "#cf354f6c"; bottomFill: "#b0283b52"
                    Text {
                        id: heard; objectName: "voiceTranscript"
                        x: 16; y: 12; width: parent.width-32
                        text: bridge.transcript ? "识别：" + bridge.transcript : "说「小爱同学」，或按下方说话"
                        textFormat: Text.PlainText; wrapMode: Text.Wrap
                        color: "#d8e8fa"; font.pixelSize: 18
                    }
                }
            }
            Item {
                width: parent.width; height: replyBubble.height
                Rectangle {
                    x: 0; y: 8; width: 34; height: 34; radius: 17
                    gradient: Gradient {
                        GradientStop { position: 0; color: "#83b8ed" }
                        GradientStop { position: 1; color: "#3c70b2" }
                    }
                    border.width: 1; border.color: "#93c7ff"
                    Rectangle { x: 9; y: 12; width: 4; height: 5; radius: 2; color: "white" }
                    Rectangle { x: 21; y: 12; width: 4; height: 5; radius: 2; color: "white" }
                }
                GlassSurface {
                    id: replyBubble
                    x: 46; width: parent.width-80
                    height: reply.height+30; radius: 22; shadow: false
                    topFill: "#cf3b414d"; bottomFill: "#b3292f3a"
                    Text {
                        id: reply; objectName: "voiceFeedback"
                        x: 16; y: 15; width: parent.width-32
                        text: bridge.errorMessage || bridge.answer || bridge.message ||
                              "可以聊天，也可以说开始跟踪人物 / 停止跟踪"
                        textFormat: Text.PlainText; wrapMode: Text.Wrap
                        color: bridge.errorMessage ? "#efc38a" : "#e3eaf5"; font.pixelSize: 20
                    }
                }
            }
        }
    }
    Flickable {
        x: 24; y: 108; width: parent.width-48; height: parent.height-246
        visible: panel.showTask; clip: true
        contentWidth: width; contentHeight: taskText.height
        boundsBehavior: Flickable.StopAtBounds
        Text {
            id: taskText; objectName: "voiceTaskStatus"
            width: parent.width
            text: panel.visualStatus + "\n\n" +
                  (bridge.errorMessage || bridge.message || "唤醒或按键发起语音，停止始终可用")
            textFormat: Text.PlainText; wrapMode: Text.Wrap
            color: "#bdcbe0"; font.pixelSize: 19
        }
    }
    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height-132; height: 22; spacing: 6
        opacity: bridge.connected ? 0.65 : 0.3
        Repeater {
            model: 25
            delegate: Rectangle {
                width: 4; radius: 2
                height: Math.max(3, (12-Math.abs(index-12)) * 1.35 + (index%3)*2)
                anchors.verticalCenter: parent.verticalCenter
                color: "#81b6f2"
            }
        }
    }
    GlassSurface {
        objectName: "voiceRecordButton"
        x: (parent.width-78)/2; y: parent.height-108; width: 78; height: 78; radius: 39
        topFill: "#ed4d6380"
        bottomFill: panel.recordingOwned && bridge.state === "recording" ? "#713f50" : "#253b59"
        opacity: enabled ? 1 : 0.46
        enabled: bridge.connected && (bridge.state === "idle" || bridge.state === "error" ||
                 (panel.recordingOwned && bridge.state === "recording"))
        Rectangle {
            x: -5; y: -5; width: 88; height: 88; radius: 44
            color: "transparent"; border.width: 1; border.color: "#648fbbea"
        }
        UiSymbol {
            anchors.centerIn: parent; width: 35; height: 35
            name: "mic"; ink: panel.recordingOwned && bridge.state === "recording" ? "#ffb9c0" : "#a1ceff"
        }
        MouseArea { anchors.fill: parent; onClicked: panel.recordRequested() }
    }
    Text {
        x: 24; y: parent.height-24; width: parent.width-48
        text: panel.recordingOwned && bridge.state === "recording" ? "结束录音" :
              bridge.state === "idle" || bridge.state === "error" ? "说话" : panel.buttonLabel
        color: "#b0bfd4"; font.pixelSize: 15
        horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
    }
}
