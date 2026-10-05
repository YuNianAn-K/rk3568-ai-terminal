#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QCamera>
#include <QQuickWindow>
#include <QTimer>
#include <QDebug>

#include "gimbalbridge.h"
#include "cameramonitor.h"
#include "handtracker.h"
#include "persontracker.h"
#include "previewitem.h"
#include "trackingcontrol.h"
#include "voicebridge.h"
#include "systemuicommonapiclient.h"

int main(int argc, char *argv[])
{
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    QCoreApplication::setAttribute(Qt::AA_EnableHighDpiScaling);
#endif
    QGuiApplication app(argc, argv);
    qmlRegisterType<PreviewItem>("GimbalPreview", 1, 0, "PreviewFrame");
    GimbalBridge bridge;
    HandTracker handTracker(&bridge);
    PersonTracker personTracker;
    VoiceBridge voiceBridge;
    TrackingControl trackingControl(&bridge);
    QObject::connect(&handTracker, &HandTracker::detectionFrame,
                     &personTracker, &PersonTracker::onFrame);
    QObject::connect(&handTracker, &HandTracker::previewReadyChanged, &personTracker, [&]() {
        personTracker.setFrameAvailable(handTracker.previewReady());
    });
    QObject::connect(&personTracker, &PersonTracker::activeChanged, &handTracker, [&]() {
        if (personTracker.active())
            handTracker.stop();
    });
    QObject::connect(&handTracker, &HandTracker::activeChanged, &personTracker, [&]() {
        if (handTracker.active())
            personTracker.stop();
    });
    CameraMonitor cameraMonitor;
    SystemUICommonApiClient desktopClient;
    desktopClient.setAppName(QStringLiteral("gimbalcam"));
    QQmlApplicationEngine engine;
    QObject::connect(&engine, &QQmlApplicationEngine::quit,
                     &app, &QCoreApplication::quit);
    engine.rootContext()->setContextProperty("gimbalBridge", &bridge);
    engine.rootContext()->setContextProperty("cameraMonitor", &cameraMonitor);
    engine.rootContext()->setContextProperty("handTracker", &handTracker);
    engine.rootContext()->setContextProperty("personTracker", &personTracker);
    engine.rootContext()->setContextProperty("voiceBridge", &voiceBridge);
    engine.rootContext()->setContextProperty("trackingControl", &trackingControl);
    engine.load(QUrl(QStringLiteral("qrc:/Main.qml")));
    if (engine.rootObjects().isEmpty())
        return 1;
    trackingControl.listen();
    PreviewItem *preview = engine.rootObjects().first()->findChild<PreviewItem *>(
        QStringLiteral("preview"));
    if (preview)
        QObject::connect(&handTracker, &HandTracker::previewFrame,
                         preview, &PreviewItem::setFrame);
    QQuickWindow *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
    if (window) {
        QObject::connect(window, &QWindow::activeChanged, window, [window]() {
            qInfo() << "gimbal window active:" << window->isActive();
        });
        // The desktop remaps above a newly launched window before sending its icon properties.
        QObject::connect(&desktopClient, &SystemUICommonApiClient::appAppPropertyChanged,
                         window, [window]() {
            QTimer::singleShot(150, window, [window]() {
                window->requestActivate();
                qInfo() << "gimbal window requested activation";
            });
        });
    }
    QObject::connect(&desktopClient, &SystemUICommonApiClient::actionCommand,
                     &app, [&](SystemUICommonApiClient::Command command) {
        if (command == SystemUICommonApiClient::Show) {
            if (window)
                window->requestActivate();
            desktopClient.askSystemUItohideOrShow(SystemUICommonApiClient::Hide);
        } else if (command == SystemUICommonApiClient::Quit) {
            app.quit();
        }
    });
    QObject::connect(&app, &QCoreApplication::aboutToQuit, &app, [&]() {
        if (window && window->property("voiceOwned").toBool() &&
            voiceBridge.state() == QStringLiteral("recording")) voiceBridge.cancel();
        handTracker.stop();
        personTracker.stop();
        bridge.stop();
        desktopClient.askSystemUItohideOrShow(SystemUICommonApiClient::Show);
    });
    QObject *cameraObject = engine.rootObjects().first()->findChild<QObject *>(QStringLiteral("camera"));
    QCamera *camera = cameraObject ? qobject_cast<QCamera *>(
        cameraObject->property("mediaObject").value<QObject *>()) : nullptr;
    if (camera) {
        QObject::connect(camera, &QCamera::statusChanged, &app,
                         [](QCamera::Status status) { qInfo() << "camera status:" << status; });
        QObject::connect(camera, QOverload<QCamera::Error>::of(&QCamera::error), &app,
                         [camera](QCamera::Error error) {
            qWarning() << "camera error:" << error << camera->errorString();
        });
    }
    handTracker.attach(camera);
    return app.exec();
}
