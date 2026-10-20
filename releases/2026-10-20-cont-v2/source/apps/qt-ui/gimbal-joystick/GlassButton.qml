import QtQuick 2.12

GlassSurface {
    id: button
    property string label: ""
    property string symbol: ""
    property bool selected: false
    property bool horizontal: false
    property color textColor: "#edf1f7"
    signal triggered()
    radius: 20
    topFill: selected ? "#ed344e6c" : "#be373c46"
    bottomFill: selected ? "#dd20334d" : "#a820242c"
    edge: selected ? "#70a9d1ff" : "#30ffffff"
    shadow: selected
    opacity: enabled ? 1 : 0.42
    UiSymbol {
        visible: button.symbol !== ""
        x: button.horizontal ? (parent.width - title.implicitWidth - width - 14) / 2 : (parent.width-width)/2
        y: button.horizontal ? (parent.height-height)/2 : 13
        width: button.horizontal ? 28 : 34; height: width
        name: button.symbol; ink: button.selected ? "#8ac2ff" : button.textColor
    }
    Text {
        id: title
        x: button.horizontal ? (parent.width - implicitWidth + (button.symbol !== "" ? 42 : 0)) / 2 : 4
        y: button.horizontal ? (parent.height-height)/2 : parent.height-height-13
        width: button.horizontal ? implicitWidth : parent.width-8
        text: button.label; color: button.textColor; font.pixelSize: button.horizontal ? 19 : 21
        horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
    }
    MouseArea {
        id: touch; anchors.fill: parent
        onPressed: button.scale = 0.98
        onReleased: button.scale = 1
        onCanceled: button.scale = 1
        onClicked: button.triggered()
    }
}
