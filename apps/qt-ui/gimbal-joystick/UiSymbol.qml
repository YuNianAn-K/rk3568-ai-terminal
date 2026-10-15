import QtQuick 2.12

Canvas {
    id: symbol
    property string name: "person"
    property color ink: "#edf1f7"
    onNameChanged: requestPaint()
    onInkChanged: requestPaint()
    onPaint: {
        var c = getContext("2d")
        c.clearRect(0, 0, width, height)
        c.save(); c.scale(width / 40, height / 40)
        c.strokeStyle = ink; c.fillStyle = ink; c.lineWidth = 2.6
        c.lineCap = "round"; c.lineJoin = "round"
        if (name === "person") {
            c.beginPath(); c.arc(20, 11, 5, 0, Math.PI * 2); c.stroke()
            c.beginPath(); c.moveTo(9, 33); c.quadraticCurveTo(9, 21, 20, 21)
            c.quadraticCurveTo(31, 21, 31, 33); c.stroke()
        } else if (name === "pause") {
            c.fillRect(12, 9, 5, 22); c.fillRect(23, 9, 5, 22)
        } else if (name === "play") {
            c.beginPath(); c.moveTo(14, 9); c.lineTo(30, 20); c.lineTo(14, 31); c.closePath(); c.fill()
        } else if (name === "manual") {
            var triangles = [[[20,4],[16,11],[24,11]],[[20,36],[16,29],[24,29]],
                             [[4,20],[11,16],[11,24]],[[36,20],[29,16],[29,24]]]
            for (var i=0; i<triangles.length; ++i) {
                var t=triangles[i]; c.beginPath(); c.moveTo(t[0][0],t[0][1])
                c.lineTo(t[1][0],t[1][1]); c.lineTo(t[2][0],t[2][1]); c.closePath(); c.fill()
            }
        } else if (name === "center") {
            c.beginPath(); c.arc(20,20,8,0,Math.PI*2); c.stroke()
            c.beginPath(); c.moveTo(20,3); c.lineTo(20,12); c.moveTo(20,28); c.lineTo(20,37)
            c.moveTo(3,20); c.lineTo(12,20); c.moveTo(28,20); c.lineTo(37,20); c.stroke()
        } else if (name === "mic") {
            c.beginPath(); c.moveTo(15,9); c.quadraticCurveTo(15,4,20,4)
            c.quadraticCurveTo(25,4,25,9); c.lineTo(25,21)
            c.quadraticCurveTo(25,26,20,26); c.quadraticCurveTo(15,26,15,21); c.closePath(); c.stroke()
            c.beginPath(); c.moveTo(10,18); c.lineTo(10,21); c.quadraticCurveTo(10,31,20,31)
            c.quadraticCurveTo(30,31,30,21); c.lineTo(30,18); c.moveTo(20,31); c.lineTo(20,37)
            c.moveTo(15,37); c.lineTo(25,37); c.stroke()
        } else if (name === "stop") {
            c.fillRect(10,10,20,20)
        } else if (name === "hand") {
            c.beginPath(); c.arc(20,20,13,0,Math.PI*2); c.stroke()
            c.beginPath(); c.moveTo(13,24); c.lineTo(13,14); c.moveTo(19,26); c.lineTo(19,10)
            c.moveTo(25,24); c.lineTo(25,14); c.stroke()
        }
        c.restore()
    }
}
