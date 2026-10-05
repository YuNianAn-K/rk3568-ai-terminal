#include <QtTest>
#include <QLocalServer>
#include <QLocalSocket>
#include <QJsonDocument>
#include <QJsonObject>
#include "../voicebridge.h"

class VoiceBridgeTest : public QObject {
    Q_OBJECT
private slots:
    void automaticRoundAndButtonProtocol() {
        QLocalServer server;
        QVERIFY(server.listen(QStringLiteral("/tmp/ai-voice.sock")));
        VoiceBridge bridge;
        QTRY_VERIFY(server.hasPendingConnections());
        QLocalSocket *peer = server.nextPendingConnection();
        QTRY_VERIFY(bridge.connected());
        QTRY_VERIFY(peer->bytesAvailable() > 0);
        peer->readAll();
        auto send = [&](const QByteArray &line) { peer->write(line + '\n'); peer->flush(); };
        send("{\"type\":\"answer\",\"text\":\"old answer\",\"round_id\":0}");
        QTRY_COMPARE(bridge.answer(), QStringLiteral("old answer"));
        send("{\"type\":\"timing\",\"stage\":\"wake_detected\",\"elapsed_ms\":0,\"round_id\":1}");
        send("{\"type\":\"state\",\"state\":\"starting\",\"message\":\"wake\",\"round_id\":1}");
        QTRY_COMPARE(bridge.state(), QStringLiteral("starting"));
        QVERIFY(bridge.answer().isEmpty());
        QVERIFY(bridge.timings().contains(QStringLiteral("wake_detected")));
        send("{\"type\":\"state\",\"state\":\"recording\",\"message\":\"auto\",\"round_id\":1}");
        QTRY_COMPARE(bridge.state(), QStringLiteral("recording"));
        bridge.stopRecording();
        QTRY_VERIFY(peer->bytesAvailable() > 0);
        QCOMPARE(QJsonDocument::fromJson(peer->readLine()).object().value("command").toString(), QStringLiteral("stop"));
        bridge.disableWake();
        QTRY_VERIFY(peer->bytesAvailable() > 0);
        QCOMPARE(QJsonDocument::fromJson(peer->readLine()).object().value("command").toString(), QStringLiteral("wake_disable"));
        bridge.enableWake();
        QTRY_VERIFY(peer->bytesAvailable() > 0);
        QCOMPARE(QJsonDocument::fromJson(peer->readLine()).object().value("command").toString(), QStringLiteral("wake_enable"));
    }
};
QTEST_GUILESS_MAIN(VoiceBridgeTest)
#include "test_voicebridge.moc"
