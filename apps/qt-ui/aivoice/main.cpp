#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>

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

    const QUrl url(QStringLiteral("qrc:/main.qml"));
    QObject::connect(
        &engine,
        &QQmlApplicationEngine::objectCreated,
        &app,
        [url](QObject *object, const QUrl &objectUrl) {
            if (!object && url == objectUrl)
                QCoreApplication::exit(-1);
        },
        Qt::QueuedConnection);

    engine.load(url);
    return app.exec();
}
