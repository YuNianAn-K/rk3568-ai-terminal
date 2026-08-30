#ifndef CONNMANWIFICONTROLLER_H
#define CONNMANWIFICONTROLLER_H

#include <QDBusAbstractAdaptor>
#include <QDBusArgument>
#include <QDBusObjectPath>
#include <QObject>
#include <QTimer>
#include <QVariantMap>

struct ConnmanService
{
    QDBusObjectPath path;
    QVariantMap properties;
};

Q_DECLARE_METATYPE(ConnmanService)
Q_DECLARE_METATYPE(QList<ConnmanService>)

QDBusArgument &operator<<(QDBusArgument &argument, const ConnmanService &service);
const QDBusArgument &operator>>(const QDBusArgument &argument, ConnmanService &service);

class ConnmanWifiController;

class ConnmanAgentAdaptor : public QDBusAbstractAdaptor
{
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "net.connman.Agent")

public:
    explicit ConnmanAgentAdaptor(ConnmanWifiController *controller);

public slots:
    QVariantMap RequestInput(const QDBusObjectPath &service,
                             const QVariantMap &fields);
    void ReportError(const QDBusObjectPath &service, const QString &error);
    void Cancel();
    void Release();

private:
    ConnmanWifiController *m_controller;
};

class ConnmanWifiController : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)
    Q_PROPERTY(QString ssid READ ssid NOTIFY ssidChanged)
    Q_PROPERTY(int strength READ strength NOTIFY strengthChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString statusMessage READ statusMessage NOTIFY statusMessageChanged)

public:
    explicit ConnmanWifiController(QObject *parent = nullptr);
    ~ConnmanWifiController() override;

    bool connected() const;
    QString ssid() const;
    int strength() const;
    bool busy() const;
    QString statusMessage() const;

    Q_INVOKABLE void refresh();
    Q_INVOKABLE void connectService(const QString &serviceId,
                                    const QString &networkName,
                                    const QString &passphrase);

    QString agentSsid() const;
    QString agentPassphrase() const;
    void handleAgentError(const QString &error);

signals:
    void connectedChanged();
    void ssidChanged();
    void strengthChanged();
    void busyChanged();
    void statusMessageChanged();
    void connectionSucceeded(const QString &networkName);
    void connectionFailed(const QString &message);

private slots:
    void connectionTimedOut();

private:
    bool ensureAgent();
    void setBusy(bool busy);
    void setStatusMessage(const QString &message);
    void finishConnectionSuccess(const QString &networkName);
    void finishConnectionFailure(const QString &message);
    static QVariant unwrapped(const QVariant &value);
    static QString serviceIdFromPath(const QDBusObjectPath &path);

    bool m_connected = false;
    QString m_ssid;
    int m_strength = 0;
    bool m_busy = false;
    QString m_statusMessage;
    QString m_pendingServiceId;
    QString m_pendingSsid;
    QString m_agentPassphrase;
    QString m_agentPath;
    ConnmanAgentAdaptor *m_agentAdaptor = nullptr;
    bool m_agentRegistered = false;
    QTimer m_refreshTimer;
    QTimer m_connectionTimeout;
};

#endif
