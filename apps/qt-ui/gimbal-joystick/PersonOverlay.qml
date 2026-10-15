import QtQuick 2.12

Item {
    id: overlay
    property var detections: []
    property int selectedIndex: -1
    signal selected(int index)
    readonly property real imageWidth: Math.min(width, height * 640 / 480)
    readonly property real imageHeight: Math.min(height, width * 480 / 640)
    readonly property real imageLeft: (width - imageWidth) / 2
    readonly property real imageTop: (height - imageHeight) / 2
    clip: true

    Repeater {
        model: overlay.detections
        delegate: Rectangle {
            objectName: "personBox" + index
            visible: modelData.score >= 0.40 || index === overlay.selectedIndex
            x: overlay.imageLeft + modelData.left * overlay.imageWidth
            y: overlay.imageTop + modelData.top * overlay.imageHeight
            width: (modelData.right - modelData.left) * overlay.imageWidth
            height: (modelData.bottom - modelData.top) * overlay.imageHeight
            color: "transparent"
            border.width: index === overlay.selectedIndex ? 3 : 2
            border.color: index === overlay.selectedIndex ? "#4c9aff" : "#d8a958"
            Rectangle {
                width: label.implicitWidth + 12
                height: 27
                color: index === overlay.selectedIndex ? "#dd428ef5" : "#df3d3220"
                radius: 10
                Text {
                    id: label
                    anchors.centerIn: parent
                    text: (index === overlay.selectedIndex ? "目标 " :
                           modelData.score >= 0.70 ? "人物 " : "候选 ") +
                          Math.round(modelData.score * 100) + "%"
                    color: index === overlay.selectedIndex ? "white" : "#f0c982"
                    font.pixelSize: 18
                }
            }
            MouseArea {
                anchors.fill: parent
                enabled: modelData.score >= 0.55
                onClicked: overlay.selected(index)
            }
        }
    }
}
