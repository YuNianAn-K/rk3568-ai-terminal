"""Render the actual QML with test-only camera/bridge data on desktop Qt6.

This checks layout and target selection, not Qt5 camera support or real detections.
The existing PySide6 runtime is supplied by the invoking environment.
"""
import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot, Qt, QPointF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPainterPath
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtQuick import QQuickPaintedItem, QQuickWindow
from PySide6.QtTest import QTest


class Preview(QQuickPaintedItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.radius = 0
    def set_radius(self, radius):
        self.radius = radius
        self.update()
    cornerRadius = Property(float, lambda self: self.radius, set_radius)
    def paint(self, painter):
        path = QPainterPath()
        path.addRoundedRect(self.boundingRect(), self.radius, self.radius)
        painter.setClipPath(path)
        painter.fillRect(self.boundingRect(), QColor("#182b34"))
        width = min(self.width(), self.height() * 4 / 3)
        height = min(self.height(), self.width() * 3 / 4)
        painter.fillRect((self.width() - width) / 2, (self.height() - height) / 2,
                         width, height, QColor("#314d59"))


class Bridge(QObject):
    trackingEnded = Signal()
    changed = Signal()
    def __init__(self):
        super().__init__()
        self.starts = 0
        self.stops = 0
        self.samples = []
        self.position_ready = True
        self.armed = False
    connected = Property(bool, lambda self: True, constant=True)
    trackCapable = Property(bool, lambda self: True, constant=True)
    positionReady = Property(bool, lambda self: self.position_ready, notify=changed)
    personArmed = Property(bool, lambda self: self.armed, notify=changed)
    status = Property(str, lambda self: "人物跟随中" if self.armed else "已停止", notify=changed)
    detail = Property(str, lambda self: "PA6 / PA7 均已停止", constant=True)
    @Slot()
    def stop(self):
        self.stops += 1
        self.armed = False
        self.changed.emit()
    @Slot(str)
    def personStart(self, request_id): self.starts += 1
    @Slot()
    def personPause(self):
        self.armed = False
        self.changed.emit()
    @Slot(float, float, float, int, int)
    def personSample(self, x, y, score, probe, result):
        self.samples.append((x, y, score, probe, result))
    @Slot()
    def refresh(self): pass
    @Slot()
    def center(self): pass
    @Slot(str)
    def press(self, direction): pass


class Hand(QObject):
    active = Property(bool, lambda self: False, constant=True)
    previewReady = Property(bool, lambda self: True, constant=True)
    status = Property(str, lambda self: "跟手：未启动", constant=True)
    @Slot()
    def start(self): pass
    @Slot()
    def stop(self): pass


class Camera(QObject):
    cameraStatus = Property(int, lambda self: 1, constant=True)


class Tracking(QObject):
    request = Signal(str, str)
    def __init__(self):
        super().__init__()
        self.codes = []
    @Slot(str)
    def resolve(self, code): self.codes.append(code)


class Voice(QObject):
    stateChanged = Signal()
    messageChanged = Signal()
    connected = Property(bool, lambda self: self.available, notify=stateChanged)
    state = Property(str, lambda self: self.value, notify=stateChanged)
    message = Property(str, lambda self: self.notice, notify=messageChanged)
    transcript = Property(str, lambda self: self.heard, notify=stateChanged)
    answer = Property(str, lambda self: self.reply, notify=stateChanged)
    errorMessage = Property(str, lambda self: self.error, notify=stateChanged)
    def __init__(self):
        super().__init__()
        self.value = "idle"
        self.available = True
        self.heard = ""
        self.reply = ""
        self.error = ""
        self.notice = "点说话，说开始跟踪人物或停止跟踪"
    @Slot()
    def startRecording(self):
        self.value = "recording"
        self.stateChanged.emit()
    @Slot()
    def stopRecording(self):
        self.value = "recognizing"
        self.stateChanged.emit()
    @Slot()
    def cancel(self):
        self.value = "idle"
        self.stateChanged.emit()


class Monitor(QObject):
    presentChanged = Signal()
    present = Property(bool, lambda self: True, constant=True)


class Person(QObject):
    activeChanged = Signal()
    detectionsChanged = Signal()
    active = Property(bool, lambda self: self.enabled, notify=activeChanged)
    status = Property(str, lambda self: "人物：检测中" if self.enabled else "人物：已停止", notify=activeChanged)
    metrics = Property(str, lambda self: "布局测试 · 输入为模拟框", constant=True)
    resultProbeMs = Property(int, lambda self: 1000, constant=True)
    resultMs = Property(int, lambda self: self.stamp, notify=detectionsChanged)
    resultFresh = Property(bool, lambda self: True, constant=True)
    def __init__(self):
        super().__init__()
        self.boxes = []
        self.enabled = True
        self.stamp = 1000
    detections = Property('QVariantList', lambda self: self.boxes, notify=detectionsChanged)
    @Slot()
    def start(self):
        self.enabled = True
        self.activeChanged.emit()
    @Slot()
    def stop(self):
        if self.enabled:
            self.enabled = False
            self.activeChanged.emit()
    def set_boxes(self, boxes):
        self.stamp += 150
        self.boxes = boxes
        self.detectionsChanged.emit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    source = (root / "Main.qml").read_text(encoding="utf-8")
    source = source.replace("import QtMultimedia 5.15\n", "")
    start = source.index("    Camera {")
    end, depth = source.index("{", start), 1
    end += 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    source = source[:start] + source[end:]
    source = source.replace("Camera.ActiveStatus", "1")
    source = source.replace("width: Screen.width", "width: 720")
    source = source.replace("height: Screen.height", "height: 1280")
    app = QGuiApplication(sys.argv)
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Microsoft YaHei"))
    qmlRegisterType(Preview, "GimbalPreview", 1, 0, "PreviewFrame")
    engine = QQmlApplicationEngine()
    person = Person()
    mocks = dict(gimbalBridge=Bridge(), handTracker=Hand(), camera=Camera(),
                 cameraMonitor=Monitor(), personTracker=person, voiceBridge=Voice(),
                 trackingControl=Tracking())
    for name, value in mocks.items():
        engine.rootContext().setContextProperty(name, value)
    engine.loadData(source.encode(), QUrl.fromLocalFile(str(root / "Main.qml")))
    assert engine.rootObjects(), "QML failed to load"
    window = engine.rootObjects()[0]
    window.requestActivate()
    errors = []
    a = dict(left=.10, top=.10, right=.40, bottom=.85, score=.91)
    b = dict(left=.60, top=.15, right=.90, bottom=.90, score=.83)

    def capture(name):
        QTest.qWait(120)
        image = window.grabWindow()
        assert not image.isNull(), "QML render unavailable"
        assert image.save(str(args.output / (name + ".png")))

    def state():
        value = window.property("personTarget")
        return value.toVariant() if hasattr(value, "toVariant") else value

    def visual_item(name):
        # Repeater delegates belong to the visual tree, not necessarily the
        # window's QObject ownership tree.
        pending = [window.contentItem()]
        while pending:
            item = pending.pop()
            if item.objectName() == name:
                return item
            pending.extend(item.childItems())
        return None

    def click_item(name):
        item = visual_item(name)
        assert item and item.isVisible(), name
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())

    def run():
        try:
            # Reproduce the 70% display regression: ordinary 60% detections
            # must be visible without automatically selecting or moving.
            bridge = mocks["gimbalBridge"]
            person.set_boxes([dict(a, score=.60)])
            QTest.qWait(100)
            box = visual_item("personBox0")
            assert box and box.property("visible"), "60% candidate was hidden"
            assert window.property("visiblePersonCount") == 1
            assert state()["state"] == "candidate" and bridge.starts == 0
            capture("candidate_60")
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                             __import__('PySide6.QtCore', fromlist=['QPoint']).QPoint(220, 220))
            assert state()["state"] == "selected" and state()["box"]["score"] == .60
            assert bridge.starts == 0
            person.stop()
            person.start()
            person.set_boxes([dict(a, score=.45)])
            QTest.qWait(100)
            box = visual_item("personBox0")
            assert box and box.property("visible"), "weak candidate was hidden"
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                             __import__('PySide6.QtCore', fromlist=['QPoint']).QPoint(220, 220))
            assert state()["state"] == "candidate" and bridge.starts == 0
            capture("candidate_45")
            person.set_boxes([a, b])
            QTest.qWait(100)
            assert state()["state"] == "multiple", state()
            capture("multiple")
            # Main preview at (48,136), 624x366; the 4:3 image starts at x=116.
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                             __import__('PySide6.QtCore', fromlist=['QPoint']).QPoint(220, 220))
            assert state()["index"] == 0, state()
            capture("selected")
            bridge = mocks["gimbalBridge"]
            assert bridge.starts == 0 and not bridge.samples
            click_item("followButton")
            assert window.property("personFollowing") and bridge.starts == 1
            person.set_boxes([a, b])
            assert bridge.samples[-1] == (.25, .475, .91, 1000, person.stamp)
            capture("following")
            stopped = bridge.stops
            samples_before = len(bridge.samples)
            person.set_boxes([a, dict(a, left=.11)])
            assert state()["state"] == "recovering" and state()["reason"] == "ambiguous"
            assert window.property("personFollowing") and bridge.stops == stopped
            assert len(bridge.samples) == samples_before
            assert "重叠" in window.property("personHint")
            capture("ambiguous")
            person.set_boxes([a, b])
            assert state()["state"] == "selected" and len(bridge.samples) == samples_before + 1
            partial = dict(a, bottom=.40)
            samples_before = len(bridge.samples)
            person.set_boxes([partial])
            assert state()["state"] == "recovering" and state()["reason"] == "geometry"
            assert len(bridge.samples) == samples_before and bridge.stops == stopped
            assert "重新确认" in window.property("personHint")
            capture("geometry")
            person.set_boxes([partial])
            assert state()["state"] == "selected"
            samples_before = len(bridge.samples)
            person.set_boxes([a])
            assert state()["state"] == "selected" and window.property("personFollowing")
            assert len(bridge.samples) == samples_before + 1 and bridge.stops == stopped
            assert bridge.samples[-1] == (.25, .475, .91, 1000, person.stamp)
            capture("shape_return")
            person.set_boxes([a])
            assert state()["state"] == "selected" and window.property("personFollowing")
            person.set_boxes([])
            assert state()["state"] == "recovering", state()
            assert window.property("personFollowing") and bridge.stops == stopped
            capture("recovering")
            person.set_boxes([dict(a, score=.45), b])
            assert state()["state"] == "selected" and bridge.samples[-1][2] == .45
            person.set_boxes([])
            person.stamp += 900
            person.set_boxes([])
            assert state()["state"] == "lost", state()
            assert not window.property("personFollowing") and bridge.stops > stopped
            capture("lost")
            person.set_boxes([b])
            assert state()["state"] == "lost", state()
            assert bridge.starts == 1
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                             __import__('PySide6.QtCore', fromlist=['QPoint']).QPoint(470, 240))
            assert state()["index"] == 0 and bridge.starts == 1
            click_item("followButton")
            assert window.property("personFollowing") and bridge.starts == 2
            stopped = bridge.stops
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                             __import__('PySide6.QtCore', fromlist=['QPoint']).QPoint(470, 240))
            assert not window.property("personFollowing") and bridge.stops > stopped
            click_item("followButton")
            bridge.trackingEnded.emit()
            assert not window.property("personFollowing")
            control = mocks["trackingControl"]
            person.set_boxes([])
            person.stamp += 900
            person.set_boxes([])
            person.set_boxes([a, b])
            control.request.emit("START_TRACKING", "a" * 32)
            assert control.codes[-1] == "select_target"  # Association is lost.
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                             __import__('PySide6.QtCore', fromlist=['QPoint']).QPoint(220, 220))
            control.request.emit("START_TRACKING", "b" * 32)
            assert control.codes[-1] == "pending" and window.property("personFollowing")
            capture("confirming")
            bridge.armed = True
            bridge.changed.emit()
            starts = bridge.starts
            control.request.emit("START_TRACKING", "d" * 32)
            assert control.codes[-1] == "active" and bridge.starts == starts
            click_item("voiceRecordButton")
            assert window.property("voiceOwned") and mocks["voiceBridge"].value == "recording"
            capture("voice_recording")
            click_item("voiceRecordButton")
            assert mocks["voiceBridge"].value == "recognizing" and window.property("voiceOwned")
            voice = mocks["voiceBridge"]
            voice.heard = "开始跟踪人物"
            voice.reply = "已开始跟踪选中的人物。"
            voice.value = "idle"
            voice.stateChanged.emit()
            capture("voice_result")
            assert window.findChild(QObject, "voiceTranscript").property("text") == "识别：开始跟踪人物"
            voice.error = "云台状态未确认，请查看板屏或按立即停止。"
            voice.stateChanged.emit()
            capture("voice_error")
            voice.available = False
            voice.value = "offline"
            voice.stateChanged.emit()
            assert window.property("voiceLabel") == "语音未连接"
            click_item("voiceRecordButton")
            assert not window.property("voiceOwned")
            capture("voice_unavailable")
            bridge.trackingEnded.emit()
            bridge.position_ready = False
            bridge.changed.emit()
            assert "回中位" in window.property("personHint")
            capture("position_unknown")
            control.request.emit("STOP_TRACKING", "c" * 32)
            assert control.codes[-1] == "pending" and not window.property("personFollowing")
            voice.available = True
            voice.error = ""
            voice.heard = "停止跟踪"
            voice.reply = "云台已停止跟踪。"
            voice.value = "idle"
            voice.stateChanged.emit()
            assert window.property("showVoicePanel") and not person.enabled
            capture("stopped_result")
            assert window.findChild(QObject, "voiceFeedback").property("text") == "云台已停止跟踪。"
            starts = bridge.starts
            click_item("manualPanelButton")
            assert window.property("manualPanelOpen") and bridge.starts == starts
            assert window.property("showVoicePanel")
            capture("manual")
            # Wake stays in this window: no app launch, focus request or tracking stop.
            voice.value = "starting"
            voice.notice = "已唤醒，提示音后请说话"
            voice.messageChanged.emit()
            voice.stateChanged.emit()
            assert window.property("voiceNotice")
            stops = bridge.stops
            voice.value = "recording"
            voice.notice = "正在聆听，说完会自动结束"
            voice.messageChanged.emit()
            voice.stateChanged.emit()
            assert window.property("autoVoice") and not window.property("voiceOwned")
            assert bridge.stops == stops
            capture("wake_recording")

            # Ordinary replies and internal panel focus keep the same task alive.
            voice.value = "idle"
            voice.stateChanged.emit()
            bridge.position_ready = True
            bridge.changed.emit()
            person.start()
            person.set_boxes([a, b])
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                             __import__('PySide6.QtCore', fromlist=['QPoint']).QPoint(220, 220))
            assert window.startPersonFollow("") == "pending"
            bridge.armed = True
            bridge.changed.emit()
            stops = bridge.stops
            samples = len(bridge.samples)
            preview = visual_item("preview")
            click_item("taskTab")
            assert window.property("personFollowing") and person.enabled
            assert bridge.stops == stops and visual_item("preview") is preview
            click_item("conversationTab")
            for phase in ("recording", "recognizing", "thinking", "speaking", "idle"):
                voice.value = phase
                voice.stateChanged.emit()
                person.set_boxes([a, b])
                assert window.property("personFollowing") and person.enabled
                assert bridge.stops == stops and window.property("cameraReady")
            assert len(bridge.samples) == samples + 5
            window.setProperty("manualPanelOpen", False)
            voice.heard = "今天有什么建议？"
            voice.reply = "先完成眼前的小目标，再给自己一点休息时间。"
            voice.value = "speaking"
            voice.stateChanged.emit()
            capture("glass_design")
            voice.heard = "请介绍一下你正在做什么"
            voice.reply = "我正在同一窗口显示相机画面与语音回复。" * 35
            voice.stateChanged.emit()
            capture("unified_long_reply")
            scroll = visual_item("voiceConversationScroll")
            assert scroll.property("contentHeight") > scroll.height()
            assert window.findChild(QObject, "voiceFeedback").property("text") == voice.reply
            # STOP bypasses the speech/LLM state; it does not cancel normal chat.
            voice.value = "thinking"
            voice.stateChanged.emit()
            control.request.emit("STOP_TRACKING", "e" * 32)
            assert control.codes[-1] == "pending" and not window.property("personFollowing")
            assert bridge.stops > stops and voice.value == "thinking"
            capture("unified_stop_while_thinking")
            person.start()
            stops = bridge.stops
            click_item("emergencyStopButton")
            assert not person.enabled and bridge.stops > stops
            assert voice.value == "thinking"

            # Item focus differs from a true top-level activation loss.
            person.start()
            other_window = QQuickWindow()
            other_window.show()
            other_window.requestActivate()
            QTest.qWait(60)
            assert not window.isActive() and not person.enabled
            other_window.close()
            window.requestActivate()
            QTest.qWait(60)

            # A real top-level hide still releases task ownership and recording.
            person.start()
            voice.value = "recording"
            voice.stateChanged.emit()
            window.setProperty("voiceOwned", True)
            window.hide()
            QTest.qWait(50)
            assert not person.enabled and not window.property("personFollowing")
            assert voice.value == "idle" and not window.property("cameraReady")
            window.show()
            window.requestActivate()
            QTest.qWait(50)
            assert not person.enabled and not window.property("personFollowing")
            assert window.property("showVoicePanel")
            capture("unified_return_idle")
            print("PASS: actual QML target safety; persistent preview through voice/panel states; full scrollable reply; independent STOP during thinking; real hide cancels owned recording and stops detection; restore stays idle")
        except Exception as error:
            errors.append(error)
        finally:
            app.quit()

    QTimer.singleShot(100, run)
    app.exec()
    if errors:
        raise RuntimeError("QML render or selection assertion failed") from errors[0]


if __name__ == "__main__":
    main()
