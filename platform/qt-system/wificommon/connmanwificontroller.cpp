#include "connmanwificontroller.h"

#include <QCoreApplication>
#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusError>
#include <QDBusInterface>
#include <QDBusMessage>
#include <QDBusMetaType>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusVariant>
#include <QRegularExpression>

namespace {
const char kConnmanService[] = "net.connman";
const char kManagerPath[] = "/";
const char kManagerInterface[] = "net.connman.Manager";
const char kServiceInterface[] = "net.connman.Service";
}

QDBusArgument &operator<<(QDBusArgument &argument, const ConnmanService &service)
{
    argument.beginStructure();
    argument << service.path << service.properties;
    argument.endStructure();
    return argument;
}

const QDBusArgument &operator>>(const QDBusArgument &argument,
                                ConnmanService &service)
{
    argument.beginStructure();
    argument >> service.path >> service.properties;
    argument.endStructure();
    return argument;
}

ConnmanAgentAdaptor::ConnmanAgentAdaptor(ConnmanWifiController *controller)
    : QDBusAbstractAdaptor(controller), m_controller(controller)
{
    setAutoRelaySignals(true);
}

QVariantMap ConnmanAgentAdaptor::RequestInput(const QDBusObjectPath &service,
                                              const QVariantMap &fields)
{
    Q_UNUSED(service)
    QVariantMap response;
    if (fields.contains(QStringLiteral("Name")))
        response.insert(QStringLiteral("Name"), m_controller->agentSsid());
    if (fields.contains(QStringLiteral("Passphrase")))
        response.insert(QStringLiteral("Passphrase"),
                        m_controller->agentPassphrase());
    return response;
}

void ConnmanAgentAdaptor::ReportError(const QDBusObjectPath &service,
                                      const QString &error)
{
    Q_UNUSED(service)
    m_controller->handleAgentError(error);
}

void ConnmanAgentAdaptor::Cancel()
{
    m_controller->handleAgentError(QStringLiteral("cancelled"));
}

void ConnmanAgentAdaptor::Release()
{
}

ConnmanWifiController::ConnmanWifiController(QObject *parent)
    : QObject(parent)
{
    qRegisterMetaType<ConnmanService>();
    qRegisterMetaType<QList<ConnmanService> >();
    qDBusRegisterMetaType<ConnmanService>();
    qDBusRegisterMetaType<QList<ConnmanService> >();

    m_refreshTimer.setInterval(2000);
    connect(&m_refreshTimer, &QTimer::timeout,
            this, &ConnmanWifiController::refresh);
    m_refreshTimer.start();

    m_connectionTimeout.setSingleShot(true);
    m_connectionTimeout.setInterval(20000);
    connect(&m_connectionTimeout, &QTimer::timeout,
            this, &ConnmanWifiController::connectionTimedOut);

    QTimer::singleShot(0, this, &ConnmanWifiController::refresh);
}

ConnmanWifiController::~ConnmanWifiController()
{
    if (!m_agentRegistered)
        return;

    QDBusInterface manager(kConnmanService, kManagerPath, kManagerInterface,
                           QDBusConnection::systemBus());
    manager.call(QStringLiteral("UnregisterAgent"),
                 QDBusObjectPath(m_agentPath));
    QDBusConnection::systemBus().unregisterObject(m_agentPath);
}

bool ConnmanWifiController::connected() const
{
    return m_connected;
}

QString ConnmanWifiController::ssid() const
{
    return m_ssid;
}

int ConnmanWifiController::strength() const
{
    return m_strength;
}

bool ConnmanWifiController::busy() const
{
    return m_busy;
}

QString ConnmanWifiController::statusMessage() const
{
    return m_statusMessage;
}

QString ConnmanWifiController::agentSsid() const
{
    return m_pendingSsid;
}

QString ConnmanWifiController::agentPassphrase() const
{
    return m_agentPassphrase;
}

QVariant ConnmanWifiController::unwrapped(const QVariant &value)
{
    if (value.userType() == qMetaTypeId<QDBusVariant>())
        return value.value<QDBusVariant>().variant();
    return value;
}

QString ConnmanWifiController::serviceIdFromPath(const QDBusObjectPath &path)
{
    return path.path().section(QLatin1Char('/'), -1);
}

void ConnmanWifiController::refresh()
{
    QDBusInterface manager(kConnmanService, kManagerPath, kManagerInterface,
                           QDBusConnection::systemBus());
    manager.setTimeout(1000);
    const QDBusMessage reply = manager.call(QStringLiteral("GetServices"));
    if (reply.type() == QDBusMessage::ErrorMessage || reply.arguments().isEmpty())
        return;

    const QList<ConnmanService> services =
        qdbus_cast<QList<ConnmanService> >(reply.arguments().constFirst());

    bool nextConnected = false;
    QString nextSsid;
    int nextStrength = 0;
    QString activeServiceId;

    for (const ConnmanService &service : services) {
        const QString type = unwrapped(
            service.properties.value(QStringLiteral("Type"))).toString();
        if (type != QStringLiteral("wifi"))
            continue;

        const QString state = unwrapped(
            service.properties.value(QStringLiteral("State"))).toString();
        if (state != QStringLiteral("ready") &&
            state != QStringLiteral("online")) {
            continue;
        }

        nextConnected = true;
        nextSsid = unwrapped(
            service.properties.value(QStringLiteral("Name"))).toString();
        nextStrength = unwrapped(
            service.properties.value(QStringLiteral("Strength"))).toInt();
        activeServiceId = serviceIdFromPath(service.path);
        break;
    }

    if (m_connected != nextConnected) {
        m_connected = nextConnected;
        emit connectedChanged();
    }
    if (m_ssid != nextSsid) {
        m_ssid = nextSsid;
        emit ssidChanged();
    }
    if (m_strength != nextStrength) {
        m_strength = nextStrength;
        emit strengthChanged();
    }

    if (m_busy && nextConnected && activeServiceId == m_pendingServiceId)
        finishConnectionSuccess(nextSsid.isEmpty() ? m_pendingSsid : nextSsid);
}

bool ConnmanWifiController::ensureAgent()
{
    if (m_agentRegistered)
        return true;

    m_agentPath = QStringLiteral("/com/alientek/WifiAgent/p%1")
                      .arg(QCoreApplication::applicationPid());
    m_agentAdaptor = new ConnmanAgentAdaptor(this);

    QDBusConnection bus = QDBusConnection::systemBus();
    if (!bus.registerObject(m_agentPath, this,
                            QDBusConnection::ExportAdaptors)) {
        return false;
    }

    QDBusInterface manager(kConnmanService, kManagerPath, kManagerInterface, bus);
    manager.setTimeout(1000);
    const QDBusMessage reply = manager.call(QStringLiteral("RegisterAgent"),
                                             QDBusObjectPath(m_agentPath));
    if (reply.type() == QDBusMessage::ErrorMessage) {
        bus.unregisterObject(m_agentPath);
        return false;
    }

    m_agentRegistered = true;
    return true;
}

void ConnmanWifiController::connectService(const QString &serviceId,
                                           const QString &networkName,
                                           const QString &passphrase)
{
    static const QRegularExpression servicePattern(
        QStringLiteral("^wifi_[A-Za-z0-9_]+$"));
    if (!servicePattern.match(serviceId).hasMatch()) {
        finishConnectionFailure(QStringLiteral("网络标识无效，请重新扫描"));
        return;
    }

    if (!ensureAgent()) {
        finishConnectionFailure(QStringLiteral("无法注册 ConnMan 密码代理"));
        return;
    }

    m_pendingServiceId = serviceId;
    m_pendingSsid = networkName;
    m_agentPassphrase = passphrase;
    setStatusMessage(QStringLiteral("正在连接 %1…").arg(networkName));
    setBusy(true);
    m_connectionTimeout.start();

    const QString path = QStringLiteral("/net/connman/service/%1").arg(serviceId);
    QDBusInterface service(kConnmanService, path, kServiceInterface,
                           QDBusConnection::systemBus());
    service.setTimeout(20000);
    QDBusPendingCallWatcher *watcher = new QDBusPendingCallWatcher(
        service.asyncCall(QStringLiteral("Connect")), this);

    connect(watcher, &QDBusPendingCallWatcher::finished, this,
            [this, watcher]() {
        const QDBusPendingReply<> reply = *watcher;
        watcher->deleteLater();
        if (!reply.isError()) {
            refresh();
            return;
        }

        const QString errorName = reply.error().name();
        if (errorName.endsWith(QStringLiteral("AlreadyConnected")) ||
            errorName.endsWith(QStringLiteral("InProgress"))) {
            refresh();
            return;
        }

        if (errorName.contains(QStringLiteral("InvalidKey"),
                               Qt::CaseInsensitive)) {
            finishConnectionFailure(QStringLiteral("密码错误，请重新输入"));
        } else {
            finishConnectionFailure(QStringLiteral("连接失败，请检查密码和信号"));
        }
    });
}

void ConnmanWifiController::handleAgentError(const QString &error)
{
    if (!m_busy)
        return;

    if (error.contains(QStringLiteral("key"), Qt::CaseInsensitive) ||
        error.contains(QStringLiteral("pass"), Qt::CaseInsensitive)) {
        finishConnectionFailure(QStringLiteral("密码错误，请重新输入"));
    } else {
        finishConnectionFailure(QStringLiteral("连接失败，请重试"));
    }
}

void ConnmanWifiController::setBusy(bool busy)
{
    if (m_busy == busy)
        return;
    m_busy = busy;
    emit busyChanged();
}

void ConnmanWifiController::setStatusMessage(const QString &message)
{
    if (m_statusMessage == message)
        return;
    m_statusMessage = message;
    emit statusMessageChanged();
}

void ConnmanWifiController::finishConnectionSuccess(const QString &networkName)
{
    if (!m_busy)
        return;
    m_connectionTimeout.stop();
    setBusy(false);
    m_agentPassphrase.clear();
    setStatusMessage(QStringLiteral("已连接 %1").arg(networkName));
    emit connectionSucceeded(networkName);
}

void ConnmanWifiController::finishConnectionFailure(const QString &message)
{
    m_connectionTimeout.stop();
    setBusy(false);
    m_agentPassphrase.clear();
    setStatusMessage(message);
    emit connectionFailed(message);
}

void ConnmanWifiController::connectionTimedOut()
{
    finishConnectionFailure(QStringLiteral("连接超时，请检查密码和信号"));
}
