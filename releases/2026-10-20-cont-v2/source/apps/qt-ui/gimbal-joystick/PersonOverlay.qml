import QtQuick 2.12

Item {
    id: overlay
    property var detections: []
    property int selectedIndex: -1
    property var aim: ({point:null,mode:"none"})
    signal selected(int index)
    readonly property real imageWidth: Math.min(width, height * 640 / 480)
    readonly property real imageHeight: Math.min(height, width * 480 / 640)
    readonly property real imageLeft: (width - imageWidth) / 2
    readonly property real imageTop: (height - imageHeight) / 2
    clip: true

    Rectangle {
        visible: overlay.aim.point !== null && overlay.aim.mode === "head"
        x: overlay.imageLeft + (overlay.aim.point ? overlay.aim.point.x : 0)*overlay.imageWidth-7
        y: overlay.imageTop + (overlay.aim.point ? overlay.aim.point.y : 0)*overlay.imageHeight-7
        width:14; height:14; radius:7; color:"#ff66ce"; border.color:"white"; border.width:2; z:10
    }
    Rectangle {
        visible: overlay.selectedIndex >= 0
        x: overlay.imageLeft; y: overlay.imageTop + overlay.imageHeight*.33
        width: overlay.imageWidth; height: 1; color: "#5582b9b4"
        Text { x: 8; y: 4; text: "脸部构图参考"; color: "#a6c4c1"; font.pixelSize: 13 }
    }
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
