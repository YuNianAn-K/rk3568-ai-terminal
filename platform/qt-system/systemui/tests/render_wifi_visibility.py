"""Render production desktop/Wi-Fi QML with test-only desktop dependencies.

Uses existing desktop PySide6; ARM64 Qt5 deployment is checked separately.
No real applications, network calls, or device operations are made.
"""
import argparse
from enum import IntEnum
import os
from pathlib import Path
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
from PySide6.QtCore import QObject, Property, QEnum, Signal, Slot, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest


class Server(QObject):
    class Command(IntEnum):
        Show = 1
        Hide = 5
        ActivateControl = 1
        IsRunningInBackground = 3
    QEnum(Command)
    appAsktoHideOrShow = Signal(int)
    currtentLauchAppNameChanged = Signal()
    def __init__(self):
        super().__init__()
        self.name = ''
    def set_name(self, value):
        self.name = value
        self.currtentLauchAppNameChanged.emit()
    currtentLauchAppName = Property(str, lambda self: self.name, set_name,
                                   notify=currtentLauchAppNameChanged)
    @Slot(float, float, float, float, str, int, int)
    def setAppProperty(self, *args): pass
    @Slot(str, int, int, str)
    def serverSendVariant(self, *args): pass


class Wifi(QObject):
    connectedChanged = Signal()
    ssidChanged = Signal()
    strengthChanged = Signal()
    connected = Property(bool, lambda self: True, notify=connectedChanged)
    ssid = Property(str, lambda self: 'Test Wi-Fi', notify=ssidChanged)
    strength = Property(int, lambda self: 83, notify=strengthChanged)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    app = QGuiApplication([])
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont('Microsoft YaHei'))
    qmlRegisterType(Server, 'com.alientek.qmlcomponents', 1, 0, 'SystemUICommonApiServer')
    qmlRegisterType(Wifi, 'com.alientek.wifi', 1, 0, 'ConnmanWifiController')
    with tempfile.TemporaryDirectory(prefix='wifi-qml-') as temp:
        staging = Path(temp)
        # Stub unrelated vendor/Qt5 effects, keeping actual root event handlers.
        for name in ('Page1', 'Page2', 'BottomApp', 'SearchBox'):
            (staging/(name + '.qml')).write_text('import QtQuick 2.12\nItem {}', encoding='utf-8')
        (staging/'SystemTime.qml').write_text('import QtQuick 2.12\nItem { property string system_time: "12:00" }', encoding='utf-8')
        (staging/'FastBlur.qml').write_text('import QtQuick 2.12\nItem { property var source; property real radius: 0 }', encoding='utf-8')
        (staging/'Viewcontroller.qml').write_text('import QtQuick 2.12\nItem { property int appCounts: 0; signal goBackToDesktop(bool normal); signal noAppIsRunning() }', encoding='utf-8')
        (staging/'WifiStatusOverlay.qml').write_text((root/'WifiStatusOverlay.qml').read_text(encoding='utf-8'), encoding='utf-8')
        source = (root/'main.qml').read_text(encoding='utf-8')
        source = source.replace('import QtGraphicalEffects 1.12\n', '')
        source = source.replace('width: Screen.desktopAvailableWidth', 'width: 720')
        source = source.replace('height: Screen.desktopAvailableHeight', 'height: 1280')
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty('appCurrtentDir', temp)
        engine.loadData(source.encode(), QUrl.fromLocalFile(str(staging/'main.qml')))
        assert engine.rootObjects(), 'Production QML failed to load'
        window = engine.rootObjects()[0]
        window.requestActivate()
        QTest.qWait(100)
        status = window.findChild(QQuickItem, 'desktopWifiStatus')
        server = window.findChild(Server)
        assert status is not None and server is not None
        assert status.window() is window
        assert len(app.allWindows()) == 1, 'Wi-Fi must not create an extra window'
        assert status.isVisible()
        assert window.grabWindow().save(str(args.output/'desktop.png'))
        icon = QQuickItem(window.contentItem())
        icon.setWidth(64)
        icon.setHeight(64)
        for name in ('settings', 'aivoice', 'gimbalcam'):
            window.callApp(name, 0, 0, icon, '', 0, 0)
            QTest.qWait(20)
            assert not status.isVisible(), name + ': visible during launch'
            server.appAsktoHideOrShow.emit(Server.Command.Hide)
            QTest.qWait(20)
            assert not status.isVisible(), name + ': visible inside app'
            # Prior periodic raises must not resurrect the badge.
            if name == 'settings':
                QTest.qWait(2150)
                assert not status.isVisible()
                assert window.grabWindow().save(str(args.output/'app_hidden.png'))
            server.appAsktoHideOrShow.emit(Server.Command.Show)
            QTest.qWait(350)
            assert status.isVisible(), name + ': missing after desktop return'
        # Failed launch routes through the same existing null/Show handler.
        window.callApp('missing-app', 0, 0, icon, '', 0, 0)
        server.set_name('null')
        QTest.qWait(350)
        assert status.isVisible()
        # An external window with no vendor Hide message still hides the badge.
        other = QQuickWindow()
        other.show()
        other.requestActivate()
        QTest.qWait(100)
        assert not window.isActive() and not status.isVisible()
        other.close()
        window.requestActivate()
        QTest.qWait(100)
        assert status.isVisible()
        window.hide()
        QTest.qWait(20)
        assert not status.isVisible()
        window.show()
        window.requestActivate()
        QTest.qWait(100)
        assert status.isVisible()
        window.close()
        print('PASS: actual desktop QML; one native window; settings/voice/gimbal Hide/Show; no timer resurrection; failed launch; external focus; hide/restore')


if __name__ == '__main__':
    main()
