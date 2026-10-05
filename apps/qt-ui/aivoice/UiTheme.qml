import QtQuick 2.12

QtObject {
    readonly property color backgroundTop: "#06101c"
    readonly property color backgroundBottom: "#101529"
    readonly property color panel: "#101c2b"
    readonly property color panelBorder: "#243347"
    readonly property color textPrimary: "#e4eef2"
    readonly property color textSecondary: "#91a5b6"
    readonly property color cyan: "#63cbdc"
    readonly property color indigo: "#767dc7"
    readonly property color orange: "#d69a64"
    readonly property real coreDiameter: 300
    readonly property real floatDistance: 6
    readonly property real activeFloatDistance: 2
    readonly property real offlineFloatDistance: 3
    readonly property int floatDuration: 2400
    readonly property int offlineFloatDuration: 3400
    readonly property int breathDuration: 1800
    readonly property int speakingBreathDuration: 420
    readonly property int offlineBreathDuration: 3000
    readonly property real idleBreathAmount: 0.025
    readonly property real listeningBreathAmount: 0.045
    readonly property real thinkingBreathAmount: 0.016
    readonly property real speakingBreathAmount: 0.06
    readonly property real offlineBreathAmount: 0.012
    readonly property int stateDuration: 280
    readonly property int errorNoticeDuration: 2800
}
