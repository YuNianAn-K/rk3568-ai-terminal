import QtQuick 2.12
import com.alientek.wifi 1.0

Item {
    id: wifiStatusWindow
    // A desktop item cannot float above another application's window.
    width: Math.min(parent.width * 0.42, 300)
    height: Math.max(44, parent.width / 720 * 56)
    x: parent.width - width - Math.max(8, parent.width / 720 * 16)
    y: Math.max(8, parent.width / 720 * 12)

    ConnmanWifiController {
        id: wifiStatus
    }

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: "#b8101010"
        border.color: "#88ffffff"
        border.width: 1

        Row {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 14
            spacing: 8

            Item {
                width: 30
                height: parent.height

                Canvas {
                    id: wifiIcon
                    anchors.centerIn: parent
                    width: 28
                    height: 28

                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)
                        ctx.lineCap = "round"
                        ctx.lineWidth = 2.6
                        ctx.strokeStyle = wifiStatus.connected ? "white" : "#aaaaaa"
                        ctx.fillStyle = ctx.strokeStyle

                        var level = wifiStatus.strength >= 67 ? 3
                                  : wifiStatus.strength >= 34 ? 2 : 1
                        var cx = width / 2
                        var cy = height * 0.72
                        for (var i = 1; i <= 3; ++i) {
                            ctx.globalAlpha = wifiStatus.connected && i <= level ? 1.0 : 0.25
                            ctx.beginPath()
                            ctx.arc(cx, cy, 4 + i * 4.2, Math.PI * 1.18,
                                    Math.PI * 1.82, false)
                            ctx.stroke()
                        }
                        ctx.globalAlpha = wifiStatus.connected ? 1.0 : 0.45
                        ctx.beginPath()
                        ctx.arc(cx, cy, 2.2, 0, Math.PI * 2, false)
                        ctx.fill()

                        if (!wifiStatus.connected) {
                            ctx.globalAlpha = 1.0
                            ctx.beginPath()
                            ctx.moveTo(5, 5)
                            ctx.lineTo(width - 5, height - 5)
                            ctx.stroke()
                        }
                    }

                    Connections {
                        target: wifiStatus
                        function onConnectedChanged() { wifiIcon.requestPaint() }
                        function onStrengthChanged() { wifiIcon.requestPaint() }
                    }
                }
            }

            Text {
                width: parent.width - 38
                anchors.verticalCenter: parent.verticalCenter
                text: wifiStatus.connected && wifiStatus.ssid.length > 0
                      ? wifiStatus.ssid : "Wi-Fi 未连接"
                color: "white"
                elide: Text.ElideRight
                font.pixelSize: Math.max(16, wifiStatusWindow.parent.width / 720 * 20)
            }
        }
    }

}
