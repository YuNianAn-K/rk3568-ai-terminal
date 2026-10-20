#include "trackingcontrol.h"
#include "gimbalbridge.h"
#include <QElapsedTimer>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QDebug>
#ifdef Q_OS_UNIX
#include <sys/stat.h>
#include <unistd.h>
#endif

TrackingControl::TrackingControl(GimbalBridge *bridge, QObject *parent)
    : QObject(parent), m_bridge(bridge)
{
    m_server.setSocketOptions(QLocalServer::UserAccessOption);
    m_server.setMaxPendingConnections(4);
    m_deadline.setSingleShot(true);
    m_deadline.setInterval(4000);
    connect(&m_deadline, &QTimer::timeout, this, [this]() {
        cancelStart();
        m_bridge->stop();
        finish(QStringLiteral("timeout"));
    });
    connect(bridge, &GimbalBridge::controlAck, this, [this](const QString &id, const QString &state) {
        if (!m_pending || id != m_requestId) return;
        if ((m_command == QStringLiteral("START_TRACKING") && state == QStringLiteral("active")) ||
            (m_command == QStringLiteral("STOP_TRACKING") && state == QStringLiteral("off")))
            finish(state);
    });
    connect(bridge, &GimbalBridge::trackingEnded, this, [this]() {
        if (m_pending && m_command == QStringLiteral("START_TRACKING")) {
            cancelStart();
            finish(m_bridge->connected() ? QStringLiteral("lost") : QStringLiteral("controller_unavailable"));
        }
    });
    connect(&m_server, &QLocalServer::newConnection, this, [this]() {
        while (m_server.hasPendingConnections()) {
            QLocalSocket *socket = m_server.nextPendingConnection();
            if (m_clients.size() >= 4) { socket->abort(); socket->deleteLater(); continue; }
            m_clients.insert(socket);
            socket->setReadBufferSize(4097);
            connect(socket, &QLocalSocket::readyRead, this, [this, socket]() { receive(socket); });
            connect(socket, &QLocalSocket::disconnected, this, [this, socket]() {
                if (m_pending == socket) {
                    cancelStart();
                    m_deadline.stop();
                    m_pending.clear();
                    m_command.clear();
                    m_requestId.clear();
                }
                m_clients.remove(socket);
                socket->deleteLater();
            });
            QTimer::singleShot(7000, socket, [socket]() { socket->disconnectFromServer(); });
        }
    });
}

TrackingControl::~TrackingControl()
{
    m_deadline.stop();
    disconnect(&m_server, nullptr, this, nullptr);
    for (QLocalSocket *socket : m_clients) {
        disconnect(socket, nullptr, this, nullptr);
        socket->abort();
    }
    m_server.close();
}

bool TrackingControl::listen(const QString &path)
{
#ifdef Q_OS_UNIX
    struct stat info;
    if (::lstat(path.toLocal8Bit().constData(), &info) == 0) {
        // Only reclaim our own stale socket. Never unlink a file/symlink or
        // replace a live server merely because listen failed.
        if (!S_ISSOCK(info.st_mode) || info.st_uid != ::geteuid()) return false;
        QLocalSocket probe;
        probe.connectToServer(path);
        if (probe.waitForConnected(150)) return false;
        if (probe.error() != QLocalSocket::ConnectionRefusedError) return false;
        if (!QLocalServer::removeServer(path)) return false;
    }
#endif
    const bool ok = m_server.listen(path);
    if (ok) qInfo() << "TRACKING_CONTROL_READY" << path;
    else qWarning() << "TRACKING_CONTROL_UNAVAILABLE" << m_server.errorString();
    return ok;
}

void TrackingControl::reply(QLocalSocket *socket, const QString &id, const QString &code)
{
    if (!socket) return;
    QJsonObject data;
    data.insert(QStringLiteral("version"), 1);
    data.insert(QStringLiteral("request_id"), id);
    data.insert(QStringLiteral("accepted"), code == QStringLiteral("active") || code == QStringLiteral("off"));
    data.insert(QStringLiteral("code"), code);
    socket->write(QJsonDocument(data).toJson(QJsonDocument::Compact) + '\n');
    socket->flush();
    socket->disconnectFromServer();
    qInfo() << "TRACKING_CONTROL_RESULT" << id << code;
}

void TrackingControl::receive(QLocalSocket *socket)
{
    if (socket->property("received").toBool()) return;
    QByteArray buffer = socket->property("buffer").toByteArray() + socket->readAll();
    socket->setProperty("buffer", buffer);
    if (buffer.size() > 4096) { reply(socket, QString(), QStringLiteral("invalid")); return; }
    if (!buffer.contains('\n')) return;
    socket->setProperty("received", true);
    const QJsonDocument document = QJsonDocument::fromJson(buffer.left(buffer.indexOf('\n')));
    const QJsonObject data = document.object();
    const QString id = data.value(QStringLiteral("request_id")).toString();
    const QString command = data.value(QStringLiteral("command")).toString();
    QElapsedTimer clock;
    clock.start();
    const double now = clock.msecsSinceReference();
    const QJsonValue issued = data.value(QStringLiteral("issued_ms"));
    if (!document.isObject() || data.value(QStringLiteral("version")).toDouble(-1) != 1 ||
        !QRegularExpression(QStringLiteral("^[a-f0-9]{32}$")).match(id).hasMatch() ||
        data.value(QStringLiteral("target")).toString() != QStringLiteral("PERSON") ||
        (command != QStringLiteral("START_TRACKING") && command != QStringLiteral("STOP_TRACKING")) ||
        !issued.isDouble() || issued.toDouble() > now || now - issued.toDouble() > 1500) {
        reply(socket, id, QStringLiteral("invalid")); return;
    }
    if (m_seen.contains(id)) { reply(socket, id, QStringLiteral("duplicate")); return; }
    m_seen.append(id);
    if (m_seen.size() > 64) m_seen.removeFirst();
    if (m_pending) {
        if (command == QStringLiteral("STOP_TRACKING") && m_command == QStringLiteral("START_TRACKING")) {
            cancelStart();
            finish(QStringLiteral("cancelled"));
        } else { reply(socket, id, QStringLiteral("busy")); return; }
    }
    m_pending = socket;
    m_requestId = id;
    m_command = command;
    m_deadline.start();
    emit request(command, id);
}

void TrackingControl::resolve(const QString &code)
{
    if (!m_pending) return;
    if (code == QStringLiteral("off")) {
        m_bridge->requestStop(m_requestId);
        return;
    }
    if (code == QStringLiteral("pending")) {
        if (m_command == QStringLiteral("STOP_TRACKING")) m_bridge->requestStop(m_requestId);
        return;
    }
    if (code == QStringLiteral("active") && !m_bridge->personArmed()) {
        finish(QStringLiteral("controller_unavailable")); return;
    }
    finish(code);
}

void TrackingControl::cancelStart()
{
    if (m_command == QStringLiteral("START_TRACKING")) {
        emit request(QStringLiteral("CANCEL_START"), QString());
        m_bridge->stop();
    }
}

void TrackingControl::finish(const QString &code)
{
    m_deadline.stop();
    const QPointer<QLocalSocket> socket = m_pending;
    const QString id = m_requestId;
    m_pending.clear();
    m_requestId.clear();
    m_command.clear();
    reply(socket, id, code);
}
