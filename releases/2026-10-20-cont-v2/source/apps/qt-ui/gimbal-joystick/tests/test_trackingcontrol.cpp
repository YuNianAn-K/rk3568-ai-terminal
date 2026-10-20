#include <QCoreApplication>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLocalSocket>
#include <QTemporaryDir>
#include <QThread>
#include <QFile>
#include <QDebug>
#include <functional>
#include "trackingcontrol.h"
#include "gimbalbridge.h"

static bool waitFor(const std::function<bool()> &condition, int limit = 2500)
{
    QElapsedTimer timer; timer.start();
    while (!condition() && timer.elapsed() < limit) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
        QThread::msleep(5);
    }
    return condition();
}
static void check(bool value, const char *message) { if (!value) qFatal("FAIL: %s", message); }
static QJsonObject packet(const QString &id, const QString &command, int age = 0)
{
    QElapsedTimer clock; clock.start();
    return QJsonObject{{"version", 1}, {"request_id", id}, {"command", command},
                       {"target", "PERSON"}, {"issued_ms", double(clock.msecsSinceReference() - age)}};
}
static void send(QLocalSocket &socket, const QString &path, const QJsonObject &data)
{
    socket.connectToServer(path);
    check(waitFor([&]() { return socket.state() == QLocalSocket::ConnectedState; }), "connect");
    socket.write(QJsonDocument(data).toJson(QJsonDocument::Compact) + '\n');
    socket.flush();
}
static QJsonObject receive(QLocalSocket &socket, int limit = 2500)
{
    check(waitFor([&]() { return socket.canReadLine(); }, limit), "reply available");
    return QJsonDocument::fromJson(socket.readLine()).object();
}

static void runCase(const QByteArray &mode)
{
    QTemporaryDir temp;
    check(temp.isValid(), "temporary directory");
    qputenv("PERSON_BRIDGE_TEST_LOG", temp.filePath("worker.log").toUtf8());
    qputenv("PERSON_BRIDGE_TEST_MODE", mode);
    GimbalBridge bridge;
    check(waitFor([&]() { return bridge.connected(); }), "controller ready");
    TrackingControl server(&bridge);
    const QString path = temp.filePath("control.sock");
    check(server.listen(path), "server listens");
    bool cancelled = false;
    QObject::connect(&server, &TrackingControl::request, [&](const QString &command, const QString &id) {
        if (command == "CANCEL_START") { cancelled = true; bridge.stop(); return; }
        if (mode == "reject" && command == "START_TRACKING") { server.resolve("select_target"); return; }
        if (command == "START_TRACKING") bridge.personStart(id);
        server.resolve("pending");
    });
    const QString id(32, 'a');
    QLocalSocket start;
    send(start, path, packet(id, "START_TRACKING"));
    if (mode == "reject") {
        const auto reply = receive(start);
        check(!reply.value("accepted").toBool() && reply.value("code") == "select_target", "unselected rejects");
    } else if (mode == "proof") {
        check(!start.canReadLine(), "no success before ARM");
        const auto reply = receive(start);
        check(reply.value("accepted").toBool() && reply.value("code") == "active" && bridge.personArmed(), "ARM-correlated success");
        QLocalSocket duplicate;
        send(duplicate, path, packet(id, "START_TRACKING"));
        check(receive(duplicate).value("code") == "duplicate", "duplicate does not restart");
    } else if (mode == "bad_ack") {
        const auto reply = receive(start, 5000);
        check(!reply.value("accepted").toBool() && reply.value("code") == "timeout", "wrong ARM id cannot succeed");
        check(cancelled && !bridge.personArmed(), "timeout cancels requested start");
    } else {
        // STOP preempts an unconfirmed start; no delayed ARM may revive it.
        QLocalSocket stop;
        send(stop, path, packet(QString(32, 'b'), "STOP_TRACKING"));
        check(receive(start).value("code") == "cancelled", "STOP cancels start");
        check(receive(stop).value("code") == "off", "STOP has correlated OFF proof");
        check(cancelled, "preemption requests UI stop");
    }
    QLocalSocket stop;
    send(stop, path, packet(QString(32, 'c'), "STOP_TRACKING"));
    const auto off = receive(stop);
    check(off.value("accepted").toBool() && off.value("code") == "off", "verified stop");
    QLocalSocket old;
    send(old, path, packet(QString(32, 'd'), "START_TRACKING", 2000));
    check(receive(old).value("code") == "invalid", "expired request cannot start");
    QLocalSocket raw;
    send(raw, path, packet(QString(32, 'e'), "PAN +100"));
    check(receive(raw).value("code") == "invalid", "raw commands rejected");
    // A regular file must never be removed as a stale endpoint.
    const QString regularPath = temp.filePath("regular");
    QFile file(regularPath); check(file.open(QIODevice::WriteOnly), "regular fixture");
    file.write("keep"); file.close();
    TrackingControl collision(&bridge);
    check(!collision.listen(regularPath) && QFile::exists(regularPath), "regular file preserved");
}

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    for (const QByteArray &mode : {QByteArray("reject"), QByteArray("proof"), QByteArray("bad_ack"), QByteArray("quiet")}) runCase(mode);
    qunsetenv("PERSON_BRIDGE_TEST_MODE");
    qInfo() << "PASS: target rejection; ARM/OFF correlation; duplicate/expired/raw rejection; timeout; STOP preemption; endpoint collision";
    return 0;
}
