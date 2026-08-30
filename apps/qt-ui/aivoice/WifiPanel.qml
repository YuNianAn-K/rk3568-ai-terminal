import QtQuick 2.12
import QtQuick.Controls 2.12

Item {
    id: root

    property bool appVisible: false
    property bool panelVisible: false
    property bool passwordVisible: false
    property bool shift: false
    property bool symbols: false
    property string selectedSsid: ""
    property string selectedService: ""
    property bool selectedRequiresPassword: true
    property var keyboardRows: root.symbols ? [
        ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"],
        ["-", "_", "+", "=", "[", "]", "{", "}", "?", "/"],
        [".", ",", ":", ";", "'", "\"", "`", "~", "<", ">"],
        ["ABC", "SPACE", "CLEAR", "CONNECT"]
    ] : [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
        ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
        ["SYM", "z", "x", "c", "v", "b", "n", "m", "BACK"],
        ["SPACE", "CLEAR", "CONNECT"]
    ]

    visible: appVisible

    function openNetwork(network) {
        selectedSsid = network.ssid
        selectedService = network.service
        selectedRequiresPassword = network.requiresPassword
        symbols = false
        passwordInput.text = ""
        shift = false
        if (selectedRequiresPassword) {
            passwordVisible = true
        } else {
            wifiBridge.connectNetwork(selectedService, "")
        }
    }

    function pressKey(key) {
        if (key === "SHIFT") {
            shift = !shift
        } else if (key === "SYM") {
            symbols = true
            shift = false
        } else if (key === "ABC") {
            symbols = false
        } else if (key === "BACK") {
            passwordInput.text = passwordInput.text.slice(0, -1)
        } else if (key === "CLEAR") {
            passwordInput.text = ""
        } else if (key === "SPACE") {
            passwordInput.text += " "
        } else if (key === "CONNECT") {
            if (passwordInput.text.length > 0) {
                wifiBridge.connectNetwork(selectedService, passwordInput.text)
                passwordVisible = false
            }
        } else {
            passwordInput.text += shift ? key.toUpperCase() : key
        }
    }

    Item {
        id: wifiIndicator
        anchors.right: parent.right
        anchors.rightMargin: 250 * root.width / 720
        anchors.top: parent.top
        anchors.topMargin: 72 * root.width / 720
        width: indicatorRow.width
        height: Math.max(indicatorRow.height, 44 * root.width / 720)

        Row {
            id: indicatorRow
            anchors.centerIn: parent
            spacing: 8 * root.width / 720

            Rectangle {
                width: 7 * root.width / 720
                height: width
                radius: width / 2
                anchors.verticalCenter: parent.verticalCenter
                color: wifiBridge.connected ? "#F5F5F5" : "#555555"
            }

            Text {
                width: 118 * root.width / 720
                elide: Text.ElideRight
                text: wifiBridge.connected ? wifiBridge.ssid : "WIFI OFFLINE"
                color: wifiBridge.connected ? "#A0A0A0" : "#555555"
                font.pixelSize: 11 * root.width / 720
                font.letterSpacing: 1.2 * root.width / 720
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: root.panelVisible = true
        }
    }

    Rectangle {
        id: networkPanel
        anchors.fill: parent
        z: 10
        visible: root.panelVisible && !root.passwordVisible
        color: "#050505"

        Timer {
            interval: 5000
            repeat: true
            running: networkPanel.visible
            onTriggered: wifiBridge.refresh()
        }

        Column {
            anchors.fill: parent
            anchors.leftMargin: 54 * root.width / 720
            anchors.rightMargin: 54 * root.width / 720
            anchors.topMargin: 46 * root.width / 720
            anchors.bottomMargin: 46 * root.width / 720
            spacing: 22 * root.width / 720

            Row {
                width: parent.width

                Column {
                    width: parent.width - closeLabel.width - 30 * root.width / 720
                    spacing: 4 * root.width / 720

                    Text {
                        text: "WIFI NETWORK"
                        color: "#FAFAFA"
                        font.pixelSize: 24 * root.width / 720
                        font.weight: Font.DemiBold
                        font.letterSpacing: 4 * root.width / 720
                    }

                    Text {
                        text: wifiBridge.status
                        color: wifiBridge.errorMessage.length > 0 ? "#D8D8D8" : "#666666"
                        font.pixelSize: 12 * root.width / 720
                        elide: Text.ElideRight
                    }
                }

                Text {
                    id: closeLabel
                    text: "CLOSE"
                    color: "#A0A0A0"
                    font.pixelSize: 12 * root.width / 720
                    font.letterSpacing: 2 * root.width / 720

                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -16 * root.width / 720
                        onClicked: root.panelVisible = false
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: Math.max(1, root.width / 720)
                color: "#262626"
            }

            Row {
                width: parent.width
                spacing: 12 * root.width / 720

                Rectangle {
                    width: 160 * root.width / 720
                    height: 42 * root.width / 720
                    color: wifiBridge.busy ? "#202020" : "#F7F7F5"
                    radius: 8 * root.width / 720

                    Text {
                        anchors.centerIn: parent
                        text: wifiBridge.busy ? "SCANNING" : "RESCAN"
                        color: wifiBridge.busy ? "#777777" : "#050505"
                        font.pixelSize: 12 * root.width / 720
                        font.letterSpacing: 2 * root.width / 720
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: !wifiBridge.busy && !wifiBridge.connecting
                        onClicked: wifiBridge.scan()
                    }
                }

                Text {
                    width: parent.width - 172 * root.width / 720
                    text: wifiBridge.networks.length + " networks"
                    color: "#606060"
                    font.pixelSize: 12 * root.width / 720
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            ListView {
                id: networkList
                width: parent.width
                height: parent.height - 142 * root.width / 720
                clip: true
                spacing: 10 * root.width / 720
                model: wifiBridge.networks

                delegate: Rectangle {
                    width: networkList.width
                    height: 66 * root.width / 720
                    radius: 12 * root.width / 720
                    color: modelData.connected ? "#252525" : "#101010"
                    border.width: Math.max(1, root.width / 720)
                    border.color: modelData.connected ? "#D8D8D8" : "#252525"

                    Column {
                        anchors.left: parent.left
                        anchors.leftMargin: 18 * root.width / 720
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 5 * root.width / 720

                        Text {
                            text: modelData.ssid
                            color: "#F2F2F2"
                            font.pixelSize: 17 * root.width / 720
                            elide: Text.ElideRight
                            width: networkList.width - 220 * root.width / 720
                        }

                        Text {
                            text: modelData.connected ? "CONNECTED" : modelData.security
                            color: modelData.connected ? "#BEBEBE" : "#666666"
                            font.pixelSize: 10 * root.width / 720
                            font.letterSpacing: 1.5 * root.width / 720
                        }
                    }

                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 18 * root.width / 720
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.connected ? "✓" : ">"
                        color: modelData.connected ? "#F2F2F2" : "#777777"
                        font.pixelSize: 20 * root.width / 720
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: !wifiBridge.busy && !wifiBridge.connecting
                        onClicked: root.openNetwork(modelData)
                    }
                }
            }
        }
    }

    Rectangle {
        id: passwordPanel
        anchors.fill: parent
        z: 20
        visible: root.panelVisible && root.passwordVisible
        color: "#050505"

        Column {
            anchors.fill: parent
            anchors.leftMargin: 44 * root.width / 720
            anchors.rightMargin: 44 * root.width / 720
            anchors.topMargin: 46 * root.width / 720
            anchors.bottomMargin: 36 * root.width / 720
            spacing: 18 * root.width / 720

            Row {
                width: parent.width

                Column {
                    width: parent.width - backLabel.width - 30 * root.width / 720
                    spacing: 4 * root.width / 720

                    Text {
                        text: "PASSWORD"
                        color: "#FAFAFA"
                        font.pixelSize: 24 * root.width / 720
                        font.weight: Font.DemiBold
                        font.letterSpacing: 4 * root.width / 720
                    }

                    Text {
                        width: parent.width
                        text: root.selectedSsid
                        color: "#777777"
                        font.pixelSize: 14 * root.width / 720
                        elide: Text.ElideRight
                    }
                }

                Text {
                    id: backLabel
                    text: "BACK"
                    color: "#A0A0A0"
                    font.pixelSize: 12 * root.width / 720
                    font.letterSpacing: 2 * root.width / 720

                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -16 * root.width / 720
                        onClicked: root.passwordVisible = false
                    }
                }
            }

            TextInput {
                id: passwordInput
                width: parent.width
                height: 54 * root.width / 720
                readOnly: true
                echoMode: TextInput.Password
                color: "#F7F7F5"
                font.pixelSize: 24 * root.width / 720
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                passwordCharacter: "•"
                text: ""
                selectionColor: "#777777"
                Rectangle {
                    anchors.fill: parent
                    z: -1
                    color: "#101010"
                    border.width: Math.max(1, root.width / 720)
                    border.color: "#303030"
                    radius: 10 * root.width / 720
                }
            }

            Column {
                width: parent.width
                spacing: 8 * root.width / 720

                Repeater {
                    model: root.keyboardRows

                    delegate: Row {
                        width: parent.width
                        height: 52 * root.width / 720
                        spacing: 7 * root.width / 720

                        Repeater {
                            model: modelData

                            delegate: Rectangle {
                                property string keyText: modelData
                                width: keyText === "SPACE" ? 240 * root.width / 720
                                       : (keyText === "CONNECT" ? 145 * root.width / 720
                                          : (keyText.length > 1 ? 92 * root.width / 720
                                             : 51 * root.width / 720))
                                height: parent.height
                                radius: 8 * root.width / 720
                                color: keyText === "CONNECT" ? "#F7F7F5" : "#171717"
                                border.width: Math.max(1, root.width / 720)
                                border.color: keyText === "CONNECT" ? "#F7F7F5" : "#303030"

                                Text {
                                    anchors.centerIn: parent
                                    text: keyText === "SHIFT" && root.shift ? "SHIFT*" : keyText
                                    color: keyText === "CONNECT" ? "#050505" : "#D8D8D8"
                                    font.pixelSize: (keyText.length > 1 ? 11 : 18) * root.width / 720
                                    font.letterSpacing: keyText.length > 1 ? 1 * root.width / 720 : 0
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: keyText !== "CONNECT" || passwordInput.text.length > 0
                                    onClicked: root.pressKey(keyText)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
