import QtQuick 2.12

Item {
    id: surface
    property real radius: 26
    property color topFill: "#dd30343d"
    property color bottomFill: "#dc191c23"
    property color edge: "#45ffffff"
    property bool shadow: true
    // Layered static surfaces keep the frosted look without a live video blur pass.
    Rectangle {
        z: -3; x: -2; y: 7; width: parent.width + 4; height: parent.height + 2
        radius: surface.radius + 2; color: "#24000000"; visible: surface.shadow
    }
    Rectangle {
        z: -2; x: 0; y: 4; width: parent.width; height: parent.height
        radius: surface.radius; color: "#32000000"; visible: surface.shadow
    }
    Rectangle {
        z: -1; anchors.fill: parent; radius: surface.radius
        gradient: Gradient {
            GradientStop { position: 0; color: surface.topFill }
            GradientStop { position: 1; color: surface.bottomFill }
        }
        border.width: 1.2; border.color: surface.edge
    }
    Rectangle {
        z: -1; anchors.fill: parent; anchors.margins: 2
        radius: Math.max(0, surface.radius - 2); color: "transparent"
        border.width: 1; border.color: "#10ffffff"
    }
}
