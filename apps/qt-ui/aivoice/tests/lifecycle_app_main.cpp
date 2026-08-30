#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QTimer>

#include "systemuicommonapiclient.h"
#include "voicebridge.h"

int main(int argc, char *argv[])
{
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    QCoreApplication::setAttribute(Qt::AA_EnableHighDpiScaling);
#endif

    qputenv("QT_QUICK_BACKEND", "");
    QGuiApplication app(argc, argv);

    qmlRegisterType<SystemUICommonApiClient>(
        "com.alientek.qmlcomponents", 1, 0, "SystemUICommonApiClient");

    VoiceBridge voiceBridge;
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(
        "appCurrtentDir", QCoreApplication::applicationDirPath());
    engine.rootContext()->setContextProperty("voiceBridge", &voiceBridge);
    engine.load(QUrl(QStringLiteral("qrc:/main.qml")));

    QTimer::singleShot(2000, &app, &QCoreApplication::quit);
    return app.exec();
}
