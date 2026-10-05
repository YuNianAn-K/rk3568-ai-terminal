#include <QDir>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlError>
#include <QTimer>
#include <QDebug>
#include <cstdio>

static int runtimeWarnings = 0;
static void captureMessage(QtMsgType type, const QMessageLogContext &, const QString &message)
{
    if (type == QtWarningMsg || type == QtCriticalMsg || type == QtFatalMsg)
        ++runtimeWarnings;
    std::fprintf(stderr, "%s\n", message.toLocal8Bit().constData());
}

// Test-only service and software rendering; production never consumes mock data.
int main(int argc, char *argv[])
{
    qputenv("QT_QUICK_BACKEND", "software");
    qInstallMessageHandler(captureMessage);
    QGuiApplication app(argc, argv);
    if (app.arguments().size() != 2) {
        qCritical() << "Usage: emotion_preview_test OUTPUT_DIRECTORY";
        return 2;
    }
    const QString output = QDir(app.arguments().at(1)).absolutePath();
    if (!QDir().mkpath(output)) return 2;
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("previewDirectory", output);
    engine.load(QUrl(QStringLiteral("qrc:/tests/Preview.qml")));
    if (engine.rootObjects().isEmpty()) return 1;
    QObject *root = engine.rootObjects().first();
    QObject *card = root->findChild<QObject *>(QStringLiteral("conversationCard"));
    QTimer poll;
    QObject::connect(&poll, &QTimer::timeout, [&]() {
        if (root->property("done").toBool()) {
            const int failures = root->property("failures").toInt();
            qInfo() << "Preview finished, failures:" << failures << "warnings:" << runtimeWarnings;
            app.exit(failures || runtimeWarnings || !card || !card->property("contentFits").toBool() ? 1 : 0);
        }
    });
    poll.start(100);
    QTimer::singleShot(60000, &app, [&]() {
        qCritical() << "Preview timed out";
        app.exit(1);
    });
    return app.exec();
}
