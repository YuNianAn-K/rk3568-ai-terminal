#include "connmanwificontroller.h"

#include <QCoreApplication>
#include <QDBusError>
#include <QDBusInterface>
#include <QDBusMessage>
#include <QDBusMetaType>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
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
    return m_controller->handleInputRequest(service, fields);
}

void ConnmanAgentAdaptor::ReportError(const QDBusObjectPath &service,
                                      const QString &error)
{
    m_controller->handleAgentError(service, error);
}

void ConnmanAgentAdaptor::Cancel()
{
    m_controller->handleAgentCancel();
}

void ConnmanAgentAdaptor::Release()
{
    m_controller->handleAgentRelease();
}

ConnmanWifiController::ConnmanWifiController(QObject *parent)
    : ConnmanWifiController(QDBusConnection::systemBus(),
                            QString::fromLatin1(kConnmanService), 20000, parent)
{
}

ConnmanWifiController::ConnmanWifiController(const QDBusConnection &bus,
                                             const QString &connmanService,
                                             int connectionTimeoutMs,
                                             QObject *parent)
    : QObject(parent),
      m_bus(bus),
      m_connmanService(connmanService),
      m_serviceWatcher(connmanService, bus,
                       QDBusServiceWatcher::WatchForOwnerChange, this)
{
    qRegisterMetaType<ConnmanService>();
    qRegisterMetaType<QList<ConnmanService> >();
    qDBusRegisterMetaType<ConnmanService>();
    qDBusRegisterMetaType<QList<ConnmanService> >();

    m_refreshTimer.setInterval(2000);
    connect(&m_refreshTimer, &QTimer::timeout,
            this, &ConnmanWifiController::requestRefresh);
    m_refreshTimer.start();

    m_connectionTimeout.setSingleShot(true);
    m_connectionTimeout.setInterval(connectionTimeoutMs);
    connect(&m_connectionTimeout, &QTimer::timeout,
            this, &ConnmanWifiController::connectionTimedOut);

    connect(&m_serviceWatcher, &QDBusServiceWatcher::serviceOwnerChanged,
            this, &ConnmanWifiController::connmanOwnerChanged);
    m_bus.connect(m_connmanService, QString::fromLatin1(kManagerPath),
                  QString::fromLatin1(kManagerInterface),
                  QStringLiteral("ServicesChanged"), this,
                  SLOT(servicesChanged(QList<ConnmanService>,QList<QDBusObjectPath>)));
    m_bus.connect(m_connmanService, QString(),
                  QString::fromLatin1(kServiceInterface),
                  QStringLiteral("PropertyChanged"), this,
                  SLOT(servicePropertyChanged(QString,QDBusVariant)));

    QTimer::singleShot(0, this, &ConnmanWifiController::requestRefresh);
}

ConnmanWifiController::~ConnmanWifiController()
{
    if (m_agentRegistered) {
        QDBusInterface manager(m_connmanService,
                               QString::fromLatin1(kManagerPath),
                               QString::fromLatin1(kManagerInterface), m_bus);
        manager.call(QDBus::NoBlock, QStringLiteral("UnregisterAgent"),
                     QDBusObjectPath(m_agentPath));
    }
    if (m_agentObjectRegistered)
        m_bus.unregisterObject(m_agentPath);
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
    requestRefresh();
}

void ConnmanWifiController::requestRefresh()
{
    const quint64 generation = ++m_refreshGeneration;
    QDBusInterface manager(m_connmanService,
                           QString::fromLatin1(kManagerPath),
                           QString::fromLatin1(kManagerInterface), m_bus);
    manager.setTimeout(1000);
    if (!manager.isValid()) {
        clearConnectionState();
        if (!m_busy)
            setStatusMessage(QStringLiteral("网络服务不可用"));
        return;
    }

    QDBusPendingCallWatcher *watcher = new QDBusPendingCallWatcher(
        manager.asyncCall(QStringLiteral("GetServices")), this);
    connect(watcher, &QDBusPendingCallWatcher::finished, this,
            [this, watcher, generation]() {
        const QDBusPendingReply<QList<ConnmanService> > reply = *watcher;
        watcher->deleteLater();
        if (generation != m_refreshGeneration)
            return;
        if (reply.isError()) {
            clearConnectionState();
            if (!m_busy)
                setStatusMessage(QStringLiteral("无法读取网络状态"));
            return;
        }
        applyServices(reply.value());
    });
}

void ConnmanWifiController::applyServices(
    const QList<ConnmanService> &services)
{
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

    if (m_busy && nextConnected && activeServiceId == m_pendingServiceId) {
        finishConnectionSuccess(m_activeConnectionGeneration,
                                nextSsid.isEmpty() ? m_pendingSsid : nextSsid);
    }
}

void ConnmanWifiController::clearConnectionState()
{
    if (m_connected) {
        m_connected = false;
        emit connectedChanged();
    }
    if (!m_ssid.isEmpty()) {
        m_ssid.clear();
        emit ssidChanged();
    }
    if (m_strength != 0) {
        m_strength = 0;
        emit strengthChanged();
    }
}

bool ConnmanWifiController::ensureAgent()
{
    m_agentEverRequested = true;
    if (m_agentRegistered)
        return true;

    if (m_agentPath.isEmpty()) {
        m_agentPath = QStringLiteral("/com/alientek/WifiAgent/p%1_c%2")
                          .arg(QCoreApplication::applicationPid())
                          .arg(quintptr(this), 0, 16);
    }
    if (!m_agentAdaptor)
        m_agentAdaptor = new ConnmanAgentAdaptor(this);

    if (!m_agentObjectRegistered) {
        if (!m_bus.registerObject(m_agentPath, this,
                                  QDBusConnection::ExportAdaptors)) {
            return false;
        }
        m_agentObjectRegistered = true;
    }

    QDBusInterface manager(m_connmanService,
                           QString::fromLatin1(kManagerPath),
                           QString::fromLatin1(kManagerInterface), m_bus);
    manager.setTimeout(1000);
    const QDBusMessage reply = manager.call(QStringLiteral("RegisterAgent"),
                                             QDBusObjectPath(m_agentPath));
    if (reply.type() == QDBusMessage::ErrorMessage)
        return false;

    m_agentRegistered = true;
    return true;
}

void ConnmanWifiController::connectService(const QString &serviceId,
                                           const QString &networkName,
                                           const QString &passphrase)
{
    if (m_busy)
        return;

    static const QRegularExpression servicePattern(
        QStringLiteral("^wifi_[A-Za-z0-9_]+$"));
    if (!servicePattern.match(serviceId).hasMatch()) {
        rejectConnection(QStringLiteral("网络标识无效，请重新扫描"));
        return;
    }

    if (!ensureAgent()) {
        rejectConnection(QStringLiteral("无法注册 ConnMan 密码代理"));
        return;
    }

    const quint64 generation = ++m_connectionGeneration;
    m_activeConnectionGeneration = generation;
    m_pendingServiceId = serviceId;
    m_pendingSsid = networkName;
    m_agentPassphrase = passphrase;
    setStatusMessage(QStringLiteral("正在连接 %1…").arg(networkName));
    setBusy(true);
    m_connectionTimeout.start();

    const QString path = QStringLiteral("/net/connman/service/%1").arg(serviceId);
    QDBusInterface service(m_connmanService, path,
                           QString::fromLatin1(kServiceInterface), m_bus);
    // The UI timeout is intentionally shorter in tests and may finish first.
    // Keep the D-Bus call alive so its eventual reply is generation-checked.
    service.setTimeout(qMax(m_connectionTimeout.interval(), 20000));
    QDBusPendingCallWatcher *watcher = new QDBusPendingCallWatcher(
        service.asyncCall(QStringLiteral("Connect")), this);

    connect(watcher, &QDBusPendingCallWatcher::finished, this,
            [this, watcher, generation]() {
        const QDBusPendingReply<> reply = *watcher;
        watcher->deleteLater();
        if (!m_busy || generation != m_activeConnectionGeneration)
            return;
        if (!reply.isError()) {
            requestRefresh();
            return;
        }

        const QString errorName = reply.error().name();
        if (errorName.endsWith(QStringLiteral("AlreadyConnected")) ||
            errorName.endsWith(QStringLiteral("InProgress"))) {
            requestRefresh();
            return;
        }

        if (errorName.contains(QStringLiteral("InvalidKey"),
                               Qt::CaseInsensitive)) {
            finishConnectionFailure(generation,
                                    QStringLiteral("密码错误，请重新输入"));
        } else {
            finishConnectionFailure(generation,
                                    QStringLiteral("连接失败，请检查密码和信号"));
        }
    });
}

QVariantMap ConnmanWifiController::handleInputRequest(
    const QDBusObjectPath &service, const QVariantMap &fields) const
{
    QVariantMap response;
    if (!m_busy || !isPendingService(service))
        return response;
    if (fields.contains(QStringLiteral("Name")))
        response.insert(QStringLiteral("Name"), m_pendingSsid);
    if (fields.contains(QStringLiteral("Passphrase")))
        response.insert(QStringLiteral("Passphrase"), m_agentPassphrase);
    return response;
}

void ConnmanWifiController::handleAgentError(const QDBusObjectPath &service,
                                             const QString &error)
{
    if (!m_busy || !isPendingService(service))
        return;

    if (error.contains(QStringLiteral("key"), Qt::CaseInsensitive) ||
        error.contains(QStringLiteral("pass"), Qt::CaseInsensitive)) {
        finishConnectionFailure(m_activeConnectionGeneration,
                                QStringLiteral("密码错误，请重新输入"));
    } else {
        finishConnectionFailure(m_activeConnectionGeneration,
                                QStringLiteral("连接失败，请重试"));
    }
}

void ConnmanWifiController::handleAgentCancel()
{
    if (m_busy) {
        finishConnectionFailure(m_activeConnectionGeneration,
                                QStringLiteral("连接已取消"));
    }
}

void ConnmanWifiController::handleAgentRelease()
{
    m_agentRegistered = false;
    if (m_busy) {
        finishConnectionFailure(m_activeConnectionGeneration,
                                QStringLiteral("网络服务已重启，请重试"));
    }
}

bool ConnmanWifiController::isPendingService(
    const QDBusObjectPath &service) const
{
    return service.path() ==
           QStringLiteral("/net/connman/service/%1").arg(m_pendingServiceId);
}

void ConnmanWifiController::servicesChanged(
    const QList<ConnmanService> &changed,
    const QList<QDBusObjectPath> &removed)
{
    Q_UNUSED(changed)
    Q_UNUSED(removed)
    requestRefresh();
}

void ConnmanWifiController::servicePropertyChanged(const QString &name,
                                                   const QDBusVariant &value)
{
    Q_UNUSED(value)
    if (name == QStringLiteral("State") ||
        name == QStringLiteral("Strength") ||
        name == QStringLiteral("Name") ||
        name == QStringLiteral("Error")) {
        requestRefresh();
    }
}

void ConnmanWifiController::connmanOwnerChanged(const QString &service,
                                                const QString &oldOwner,
                                                const QString &newOwner)
{
    if (service != m_connmanService)
        return;

    ++m_refreshGeneration;
    m_agentRegistered = false;
    if (!oldOwner.isEmpty() && m_busy) {
        finishConnectionFailure(m_activeConnectionGeneration,
                                QStringLiteral("网络服务已重启，请重试"));
    }

    if (newOwner.isEmpty()) {
        clearConnectionState();
        if (!m_busy)
            setStatusMessage(QStringLiteral("网络服务不可用"));
        return;
    }

    if (m_agentEverRequested && !ensureAgent()) {
        if (m_busy) {
            finishConnectionFailure(m_activeConnectionGeneration,
                                    QStringLiteral("无法注册 ConnMan 密码代理"));
        } else {
            setStatusMessage(QStringLiteral("无法注册 ConnMan 密码代理"));
        }
    }
    requestRefresh();
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

void ConnmanWifiController::invalidateConnection()
{
    m_connectionTimeout.stop();
    m_activeConnectionGeneration = 0;
    m_pendingServiceId.clear();
    m_pendingSsid.clear();
    m_agentPassphrase.clear();
    setBusy(false);
}

void ConnmanWifiController::rejectConnection(const QString &message)
{
    setStatusMessage(message);
    emit connectionFailed(message);
}

void ConnmanWifiController::finishConnectionSuccess(
    quint64 generation, const QString &networkName)
{
    if (!m_busy || generation != m_activeConnectionGeneration)
        return;
    invalidateConnection();
    setStatusMessage(QStringLiteral("已连接 %1").arg(networkName));
    emit connectionSucceeded(networkName);
}

void ConnmanWifiController::finishConnectionFailure(
    quint64 generation, const QString &message)
{
    if (!m_busy || generation != m_activeConnectionGeneration)
        return;
    invalidateConnection();
    setStatusMessage(message);
    emit connectionFailed(message);
}

void ConnmanWifiController::connectionTimedOut()
{
    finishConnectionFailure(m_activeConnectionGeneration,
                            QStringLiteral("连接超时，请检查密码和信号"));
}
