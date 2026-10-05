import QtQuick 2.12
import QtQuick.Controls 2.12

Rectangle {
    id: root
    property var service
    property var theme
    property real unit: 1
    signal closed()
    color: theme.backgroundTop

    function value(name, suffix) {
        var result = service.diagnostics[name]
        return result === undefined || result === null || result === ""
                ? "--" : String(result) + (suffix || "")
    }
    function duration(start, end) {
        var a = service.timings[start], b = service.timings[end]
        return a === undefined || b === undefined ? "--" : String(Math.max(0, Number(b) - Number(a))) + " ms"
    }
    Timer {
        interval: 2000; repeat: true; running: root.visible
        onTriggered: root.service.refreshStatus()
    }
    // Consume touches so the covered microphone cannot start a round.
    MouseArea { anchors.fill: parent }
    Flickable {
        anchors.fill: parent; anchors.margins: 40 * root.unit
        clip: true; contentHeight: rows.height
        Column {
            id: rows
            width: parent.width; spacing: 20 * root.unit
            Row {
                width: parent.width
                Text {
                    width: parent.width - 100 * root.unit
                    text: "语音诊断"; color: root.theme.textPrimary; font.pixelSize: 28 * root.unit
                }
                Rectangle {
                    width: 100 * root.unit; height: 48 * root.unit
                    radius: 12 * root.unit; color: root.theme.panel
                    Text { anchors.centerIn: parent; text: "关闭"; color: root.theme.textPrimary; font.pixelSize: 20 * root.unit }
                    MouseArea { anchors.fill: parent; onClicked: root.closed() }
                }
            }
            Repeater {
                model: [
                    ["STATE", root.service.state], ["ROUND", String(root.service.roundId)],
                    ["NETWORK", root.value("network", "")], ["CLIENTS", root.value("clients", "")],
                    ["MEM AVAILABLE", root.value("memory_available_mb", " MB")],
                    ["SERVICE RSS", root.value("service_rss_mb", " MB")],
                    ["SERVICE UPTIME", root.value("service_uptime_s", " s")],
                    ["SOCKET", root.service.connected ? "CONNECTED" : "OFFLINE"]
                ]
                Row {
                    width: rows.width
                    Text { width: parent.width * 0.6; text: modelData[0]; color: root.theme.textSecondary; font.pixelSize: 18 * root.unit }
                    Text { width: parent.width * 0.4; text: modelData[1]; horizontalAlignment: Text.AlignRight; color: root.theme.textPrimary; font.pixelSize: 20 * root.unit; elide: Text.ElideRight }
                }
            }
            Rectangle { width: parent.width; height: 1; color: root.theme.panelBorder }
            Row {
                spacing: 12 * root.unit
                Repeater {
                    model: ["开启唤醒", "关闭唤醒/按键"]
                    Rectangle {
                        width: 240 * root.unit; height: 50 * root.unit
                        radius: 10 * root.unit; color: root.theme.panel
                        Text { anchors.centerIn: parent; text: modelData; color: root.theme.textPrimary; font.pixelSize: 18 * root.unit }
                        MouseArea {
                            anchors.fill: parent
                            enabled: root.service.connected && (root.service.state === "idle" || root.service.state === "error")
                            onClicked: { if (index === 0) root.service.enableWake(); else root.service.disableWake() }
                        }
                    }
                }
            }
            Repeater {
                model: [
                    ["WAKE → MIC", "wake_detected", "record_start"],
                    ["WAKE → REPLY", "wake_detected", "reply_end"],
                    ["MIC OPEN", "button_trigger", "record_start"],
                    ["RECORD FINALIZE", "record_stop_requested", "record_end"],
                    ["ASR", "asr_request", "asr_result"],
                    ["LLM FIRST", "llm_request", "llm_first_token"],
                    ["LLM TOTAL", "llm_request", "llm_end"],
                    ["TTS", "tts_request", "tts_ready"],
                    ["PLAYBACK", "playback_start", "reply_end"],
                    ["END TO END", "button_trigger", "reply_end"]
                ]
                Row {
                    width: rows.width
                    Text { width: parent.width * 0.65; text: modelData[0]; color: root.theme.textSecondary; font.pixelSize: 18 * root.unit }
                    Text { width: parent.width * 0.35; text: root.duration(modelData[1], modelData[2]); horizontalAlignment: Text.AlignRight; color: root.theme.textPrimary; font.pixelSize: 20 * root.unit }
                }
            }
            Text { text: "每 2 秒刷新 · 长按左上角状态打开"; color: root.theme.textSecondary; font.pixelSize: 16 * root.unit }
        }
    }
}
