#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QCamera>
#include <QQuickWindow>
#include <QTimer>
#include <QDebug>
#include <QFile>
#include <QScopedPointer>
#include <QJsonDocument>
#include <QJsonObject>
#include <QDir>
#include <QLocalServer>
#include <QLocalSocket>

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
    QFile releaseFile(QCoreApplication::applicationDirPath() + QStringLiteral("/release-id.txt"));
    QString releaseId = QStringLiteral("UNVERSIONED");
    if (releaseFile.open(QIODevice::ReadOnly)) {
        const QString value = QString::fromUtf8(releaseFile.read(64)).trimmed();
        if (!value.isEmpty() && value.size() <= 48 && !value.contains('\n'))
            releaseId = value;
    }
    QCoreApplication::setApplicationVersion(releaseId);
    const bool standalonePreview = qEnvironmentVariableIntValue("GIMBAL_STANDALONE_PREVIEW") == 1;
    qInfo() << "GIMBAL_RELEASE" << releaseId << QCoreApplication::applicationFilePath()
            << "standalone:" << standalonePreview;
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
    QScopedPointer<SystemUICommonApiClient> desktopClient;
    // Direct previews have no desktop launch registration. Its watchdog would
    // otherwise bring the desktop above the still-running preview after 2s.
    if (!standalonePreview) {
        desktopClient.reset(new SystemUICommonApiClient);
        desktopClient->setAppName(QStringLiteral("gimbalcam"));
    }
    QQmlApplicationEngine engine;
    QObject::connect(&engine, &QQmlApplicationEngine::quit,
                     &app, &QCoreApplication::quit);
    engine.rootContext()->setContextProperty("gimbalBridge", &bridge);
    engine.rootContext()->setContextProperty("cameraMonitor", &cameraMonitor);
    engine.rootContext()->setContextProperty("handTracker", &handTracker);
    engine.rootContext()->setContextProperty("personTracker", &personTracker);
    engine.rootContext()->setContextProperty("voiceBridge", &voiceBridge);
    engine.rootContext()->setContextProperty("trackingControl", &trackingControl);
    engine.rootContext()->setContextProperty("appReleaseId", releaseId);
    engine.rootContext()->setContextProperty("appIsPreview", standalonePreview);
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
    QLocalServer previewWindowServer;
    if (standalonePreview && window) {
        const QString socketName = QStringLiteral("/tmp/gimbal-preview-window.sock");
        QLocalServer::removeServer(socketName); // Launcher holds the exclusive UI lock.
        previewWindowServer.setSocketOptions(QLocalServer::UserAccessOption);
        if (!previewWindowServer.listen(socketName)) return 2;
        QObject::connect(&previewWindowServer, &QLocalServer::newConnection, window, [&]() {
            while (previewWindowServer.hasPendingConnections()) {
                QLocalSocket *socket = previewWindowServer.nextPendingConnection();
                QObject::connect(socket, &QLocalSocket::disconnected, socket, &QObject::deleteLater);
                const auto showRequest = [socket, window, releaseId]() {
                    if (!socket->canReadLine()) return;
                    const QByteArray command = socket->readLine(128).trimmed();
                    if (command == QByteArray("SHOW ") + releaseId.toUtf8()) {
                        window->showFullScreen();
                        window->raise();
                        window->requestActivate();
                        socket->write(releaseId.toUtf8() + '\n');
                    } else {
                        socket->write("VERSION_MISMATCH\n");
                    }
                    socket->disconnectFromServer();
                };
                QObject::connect(socket, &QLocalSocket::readyRead, window, showRequest);
                showRequest();
            }
        });
    }
    if (window) {
        QObject::connect(window, &QWindow::activeChanged, window, [window]() {
            qInfo() << "gimbal window active:" << window->isActive();
        });
        // The desktop remaps above a newly launched window before sending its icon properties.
        if (desktopClient) QObject::connect(desktopClient.data(), &SystemUICommonApiClient::appAppPropertyChanged,
                         window, [window]() {
            QTimer::singleShot(150, window, [window]() {
                window->requestActivate();
                qInfo() << "gimbal window requested activation";
            });
        });
        if (standalonePreview) {
            QTimer::singleShot(150, window, [window]() {
                window->showFullScreen();
                window->raise();
                window->requestActivate();
            });
            const QString probeDir = qEnvironmentVariable("GIMBAL_PREVIEW_PROBE_DIR");
            if (!probeDir.isEmpty()) QTimer::singleShot(12000, window, [window, probeDir, releaseId]() {
                QDir().mkpath(probeDir);
                const QJsonObject state{{"release", releaseId}, {"visible", window->isVisible()},
                                        {"active", window->isActive()}, {"title", window->title()}};
                QFile file(probeDir + QStringLiteral("/window-state.json"));
                if (file.open(QIODevice::WriteOnly)) file.write(QJsonDocument(state).toJson());
                if (!window->grabWindow().save(probeDir + QStringLiteral("/window.png")))
                    qWarning() << "GIMBAL_PREVIEW_SNAPSHOT_FAILED";
                qInfo().noquote() << "GIMBAL_PREVIEW_STATE" << QJsonDocument(state).toJson(QJsonDocument::Compact);
            });
        }
    }
    if (desktopClient) QObject::connect(desktopClient.data(), &SystemUICommonApiClient::actionCommand,
                     &app, [&](SystemUICommonApiClient::Command command) {
        if (command == SystemUICommonApiClient::Show) {
            if (window)
                window->requestActivate();
            desktopClient->askSystemUItohideOrShow(SystemUICommonApiClient::Hide);
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
        if (desktopClient) desktopClient->askSystemUItohideOrShow(SystemUICommonApiClient::Show);
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
