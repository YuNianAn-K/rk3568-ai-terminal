import QtQuick 2.12

Rectangle {
    id: root
    property var theme
    property string transcript: ""
    property string answer: ""
    readonly property bool contentFits: question.y + question.height <= content.height
                                       && reply.y + reply.height <= content.height
    radius: 22; color: theme.panel; border.color: theme.panelBorder; border.width: 1
    clip: true
    Column {
        id: content
        anchors.fill: parent; anchors.margins: 24; spacing: 14
        Text {
            id: question
            width: parent.width
            text: root.transcript || "你的话，会被认真听见"
            color: root.theme.textSecondary
            font.pixelSize: 20; lineHeight: 1.2
            textFormat: Text.PlainText; wrapMode: Text.Wrap
            maximumLineCount: 2; elide: Text.ElideRight
        }
        Rectangle { width: parent.width; height: 1; color: root.theme.panelBorder }
        Text {
            id: reply
            width: parent.width
            height: Math.max(0, content.height - question.height - 29)
            text: root.answer || "回答会在这里慢慢展开。"
            color: root.answer ? root.theme.textPrimary : root.theme.textSecondary
            font.pixelSize: 24; lineHeight: 1.25
            textFormat: Text.PlainText; wrapMode: Text.Wrap
            maximumLineCount: 6
            elide: Text.ElideRight
        }
    }
}
