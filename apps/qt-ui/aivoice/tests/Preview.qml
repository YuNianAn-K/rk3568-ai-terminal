import QtQuick 2.12
import QtQuick.Window 2.12
import "../"

Window {
    id: root
    width: 720; height: 1280; visible: true
    property bool done: false
    property int failures: 0
    property int testIndex: -1
    property var core: null
    property var signatures: ({})
    property real previousEyeHeight: 22
    property var cases: [
        { name: "idle", raw: "idle", visual: "idle", action: "start" },
        { name: "listening", raw: "recording", visual: "listening", action: "stop" },
        { name: "thinking", raw: "thinking", visual: "thinking", action: "none" },
        { name: "speaking", raw: "playing", visual: "speaking", action: "none" },
        { name: "offline", raw: "offline", visual: "offline", action: "reconnect" },
        { name: "error", raw: "error", visual: "error", action: "start" },
        { name: "portrait1080", raw: "idle", visual: "idle", action: "start", w: 1080, h: 1920 },
        { name: "listening1080", raw: "recording", visual: "listening", action: "stop", w: 1080, h: 1920 },
        { name: "thinking1080", raw: "thinking", visual: "thinking", action: "none", w: 1080, h: 1920 },
        { name: "speaking1080", raw: "playing", visual: "speaking", action: "none", w: 1080, h: 1920 },
        { name: "landscape", raw: "idle", visual: "idle", action: "start", w: 1280, h: 720 },
        { name: "longtext", raw: "idle", visual: "idle", action: "start", longText: true },
        { name: "diagnostics", raw: "idle", visual: "idle", action: "start", diagnostics: true },
        { name: "wake_waiting", raw: "idle", visual: "idle", action: "start", message: "待唤醒：小爱同学 · 也可按键" },
        { name: "auto_listening", raw: "recording", visual: "listening", action: "stop", message: "正在聆听，说完会自动结束" }
    ]
    function check(condition, label) {
        if (!condition) { failures++; console.error("FAILED: " + label) }
    }
    function near(actual, expected) { return Math.abs(actual - expected) < 0.01 }
    function findItem(item, name) {
        if (item.objectName === name) return item
        for (var i = 0; i < item.children.length; ++i) {
            var found = findItem(item.children[i], name)
            if (found) return found
        }
        return null
    }
    QtObject {
        id: mock
        property bool connected: true
        property string state: "idle"
        property string transcript: "今天想听你说点什么。"
        property string answer: "我在这里。轻触麦克风，就可以开始我们的对话。"
        property string errorMessage: "声音太轻，请靠近麦克风重试"
        property string message: "测试状态"
        property int roundId: 4
        property var timings: ({ button_trigger: 0, record_start: 350, llm_request: 2100, llm_first_token: 2800 })
        property var diagnostics: ({ network: "up", clients: 1, memory_available_mb: 2850, service_rss_mb: 119, service_uptime_s: 1800 })
        property int starts: 0
        property int stops: 0
        property int reconnects: 0
        property int cancels: 0
        function startRecording() { starts++ }
        function stopRecording() { stops++ }
        function reconnectService() { reconnects++ }
        function cancel() { cancels++ }
        function refreshStatus() {}
        function enableWake() {}
        function disableWake() {}
    }
    AppMainBody { id: body; anchors.fill: parent; service: mock }
    function nextCase() {
        testIndex++
        if (testIndex >= cases.length) { edgeChecks(); return }
        var test = cases[testIndex]
        previousEyeHeight = core.eyeHeight
        width = test.w || 720; height = test.h || 1280
        mock.connected = test.raw !== "offline"
        mock.state = test.raw
        mock.message = test.message || "测试状态"
        mock.answer = test.longText ? new Array(50).join("这是较长的回答，包含 <b>普通文本</b>，不得超出卡片。")
                                    : "我在这里。轻触麦克风，就可以开始我们的对话。"
        body.diagnosticsVisible = !!test.diagnostics
        transitionTimer.restart()
        captureTimer.restart()
    }
    Timer {
        id: startTimer; interval: 100; running: true
        onTriggered: {
            root.core = root.findItem(body, "emotionCore")
            root.check(!!root.core, "emotion core exists")
            if (root.core) root.nextCase()
            else root.done = true
        }
    }
    Timer {
        id: transitionTimer; interval: 110
        onTriggered: {
            var test = root.cases[root.testIndex]
            if (!test.diagnostics && !root.near(root.previousEyeHeight, root.core.pose.eyeHeight)) {
                root.check(!root.near(root.core.eyeHeight, root.previousEyeHeight), test.name + " transition starts")
                root.check(!root.near(root.core.eyeHeight, root.core.pose.eyeHeight), test.name + " transition is not a jump")
            }
            if (test.visual === "error") root.check(root.core.errorContraction < 0.999, "error contracts once")
        }
    }
    Timer {
        id: captureTimer
        interval: 420
        onTriggered: {
            var test = root.cases[root.testIndex]
            root.check(body.visualState === test.visual, test.name + " state")
            root.check(body.interaction === test.action, test.name + " action")
            root.check(body.motionEnabled === !test.diagnostics, test.name + " motion")
            root.check(root.near(root.core.eyeWidth, root.core.pose.eyeWidth), test.name + " eye width settles")
            root.check(root.near(root.core.eyeHeight, root.core.pose.eyeHeight), test.name + " eye height settles")
            root.check(root.near(root.core.gazeX, root.core.pose.gazeX) && root.near(root.core.gazeY, root.core.pose.gazeY), test.name + " gaze settles")
            root.check(root.near(root.core.smileAmount, root.core.pose.smile), test.name + " smile settles")
            root.check(!test.diagnostics || !root.core.animationsRunning, "diagnostics stops core animation")
            if (root.testIndex < 6) {
                var signature = [root.core.eyeWidth, root.core.eyeHeight, root.core.gazeX, root.core.gazeY, root.core.smileAmount, root.core.eyeTilt].join(":")
                root.check(!root.signatures[signature], test.name + " distinct silhouette")
                root.signatures[signature] = true
            }
            var before = mock.starts + mock.stops + mock.reconnects
            body.activateVoice()
            root.check(mock.starts + mock.stops + mock.reconnects === before + (test.action === "none" || test.diagnostics ? 0 : 1), test.name + " dispatch")
            body.grabToImage(function(result) {
                root.check(result.saveToFile(previewDirectory + "/" + test.name + ".png"), test.name + " capture")
                nextTimer.restart()
            })
        }
    }
    Timer { id: nextTimer; interval: 80; onTriggered: root.nextCase() }
    function edgeChecks() {
        body.diagnosticsVisible = false
        body.active = false
        check(!body.motionEnabled, "background stops motion")
        check(!core.animationsRunning, "background stops core animations")
        body.active = true
        body.visible = false
        check(!body.motionEnabled, "hidden stops motion")
        check(!core.animationsRunning, "hidden stops core animations")
        body.visible = true
        mock.state = "recording"
        mock.message = "测试状态"
        var before = mock.cancels
        body.resetInteraction()
        check(mock.cancels === before + 1, "return cancels recording")
        mock.message = "正在聆听，说完会自动结束"
        before = mock.cancels
        body.resetInteraction()
        check(mock.cancels === before, "background page does not cancel automatic recording")
        for (var i = 0; i < 3; i++) {
            mock.state = ["initializing", "starting", "replying"][i]
            check(body.interaction === "none", "transitional state has no start")
        }
        mock.state = "playing"
        pauseTransitionTimer.start()
    }
    Timer {
        id: pauseTransitionTimer; interval: 100
        onTriggered: {
            root.check(root.core.transitionsRunning, "mid-transition before background")
            body.active = false
            pauseSettledTimer.start()
        }
    }
    Timer {
        id: pauseSettledTimer; interval: 50
        onTriggered: {
            root.check(!root.core.animationsRunning, "background completes in-flight transitions")
            root.check(root.near(root.core.smileAmount, 1), "paused speaking silhouette remains correct")
            mock.connected = false
            mock.state = "offline"
            backgroundStateTimer.start()
        }
    }
    Timer {
        id: backgroundStateTimer; interval: 50
        onTriggered: {
            root.check(!root.core.animationsRunning, "background state change stays static")
            root.check(root.near(root.core.eyeHeight, 6) && root.near(root.core.warmAmount, 1), "background state change selects current pose")
            body.active = true
            mock.connected = true
            mock.roundId = 42
            mock.state = "error"
            Qt.callLater(function() { body.presentError(); repeatErrorTimer.start() })
        }
    }
    Timer {
        id: repeatErrorTimer
        interval: 3200
        onTriggered: {
            root.check(!body.errorNoticeVisible, "error notice expires")
            root.check(root.near(root.core.errorContraction, 1) && !root.core.animationsRunning, "error returns to static pose")
            body.presentError()
            root.check(!body.errorNoticeVisible, "same error is not repeated")
            mock.roundId++
            body.presentError()
            root.check(body.errorNoticeVisible, "new round may show error once")
            mock.state = "idle"
            root.check(!body.errorNoticeVisible, "retry clears notice")
            root.done = true
        }
    }
}
