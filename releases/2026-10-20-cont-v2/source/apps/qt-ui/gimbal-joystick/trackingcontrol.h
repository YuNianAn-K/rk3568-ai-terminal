#ifndef TRACKINGCONTROL_H
#define TRACKINGCONTROL_H
#include <QObject>
#include <QLocalServer>
#include <QLocalSocket>
#include <QPointer>
#include <QSet>
#include <QStringList>
#include <QTimer>

class GimbalBridge;
class TrackingControl : public QObject
{
    Q_OBJECT
public:
    explicit TrackingControl(GimbalBridge *bridge, QObject *parent = nullptr);
    ~TrackingControl() override;
    bool listen(const QString &path = QStringLiteral("/tmp/gimbal-tracking.sock"));
    Q_INVOKABLE void resolve(const QString &code);
signals:
    void request(const QString &command, const QString &requestId);
private:
    void receive(QLocalSocket *socket);
    void reply(QLocalSocket *socket, const QString &id, const QString &code);
    void finish(const QString &code);
    void cancelStart();
    GimbalBridge *m_bridge;
    QLocalServer m_server;
    QTimer m_deadline;
    QSet<QLocalSocket *> m_clients;
    QStringList m_seen;
    QPointer<QLocalSocket> m_pending;
    QString m_requestId;
    QString m_command;
};
#endif
