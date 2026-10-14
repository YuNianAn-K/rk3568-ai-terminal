#include "connmanwificontroller.h"

#include <QCoreApplication>
#include <QDBusConnectionInterface>
#include <QDBusInterface>
#include <QDBusMessage>
#include <QDBusMetaType>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusReply>
#include <QDBusVirtualObject>
#include <QDebug>
#include <QElapsedTimer>
#include <QHash>
#include <QProcess>
#include <QThread>
#include <QTimer>

#include <functional>

namespace {
const char kConnmanService[] = "net.connman";
const char kManagerInterface[] = "net.connman.Manager";
const char kServiceInterface[] = "net.connman.Service";
const char kAgentInterface[] = "net.connman.Agent";
const char kControlService[] = "com.alientek.ConnmanControllerTest";
const char kControlInterface[] = "com.alientek.ConnmanControllerTest.Control";

QString servicePath(const QString &id)
{
    return QStringLiteral("/net/connman/service/%1").arg(id);
}

bool waitFor(const std::function<bool()> &condition, int timeoutMs = 1500)
{
    QElapsedTimer timer;
    timer.start();
    while (timer.elapsed() < timeoutMs) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
        if (condition())
            return true;
        QThread::msleep(5);
    }
    QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
    return condition();
}

class FakeConnman : public QDBusVirtualObject
{
public:
    explicit FakeConnman(const QDBusConnection &bus)
        : m_bus(bus)
    {
    }

    QString introspect(const QString &) const override
    {
        return QStringLiteral(
            "<interface name=\"net.connman.Manager\">"
            "<method name=\"GetServices\"/>"
            "<method name=\"RegisterAgent\"/>"
            "<method name=\"UnregisterAgent\"/>"
            "</interface>"
            "<interface name=\"net.connman.Service\">"
            "<method name=\"Connect\"/>"
            "</interface>"
            "<interface name=\"com.alientek.ConnmanControllerTest.Control\"/>"
        );
    }

    bool handleMessage(const QDBusMessage &message,
                       const QDBusConnection &connection) override
    {
        if (message.interface() == QLatin1String(kManagerInterface))
            return handleManager(message, connection);
        if (message.interface() == QLatin1String(kServiceInterface))
            return handleService(message);
        if (message.interface() == QLatin1String(kControlInterface))
            return handleControl(message, connection);
        return false;
    }

private:
    bool handleManager(const QDBusMessage &message,
                       const QDBusConnection &connection)
    {
        if (message.member() == QStringLiteral("GetServices")) {
            if (m_failRefresh) {
                connection.send(message.createErrorReply(
                    QStringLiteral("net.connman.Error.Failed"),
                    QStringLiteral("simulated refresh failure")));
            } else {
                connection.send(message.createReply(
                    QVariantList() << QVariant::fromValue(m_services)));
            }
            return true;
        }
        if (message.member() == QStringLiteral("RegisterAgent")) {
            m_agentOwner = message.service();
            m_agentPath = message.arguments().value(0)
                              .value<QDBusObjectPath>().path();
            ++m_registerCount;
            connection.send(message.createReply());
            return true;
        }
        if (message.member() == QStringLiteral("UnregisterAgent")) {
            m_agentOwner.clear();
            m_agentPath.clear();
            connection.send(message.createReply());
            return true;
        }
        return false;
    }

    bool handleService(const QDBusMessage &message)
    {
        if (message.member() != QStringLiteral("Connect"))
            return false;
        const QString id = message.path().section(QLatin1Char('/'), -1);
        ++m_connectCounts[id];
        m_pendingConnects[id].append(message);
        return true;
    }

    bool handleControl(const QDBusMessage &message,
                       const QDBusConnection &connection)
    {
        const QVariantList args = message.arguments();
        const QString member = message.member();
        if (member == QStringLiteral("SetService")) {
            setService(args.value(0).toString(), args.value(1).toString(),
                       args.value(2).toString(), args.value(3).toInt());
            connection.send(message.createReply());
        } else if (member == QStringLiteral("SetServiceQuiet")) {
            updateService(args.value(0).toString(), args.value(1).toString(),
                          args.value(2).toString(), args.value(3).toInt());
            connection.send(message.createReply());
        } else if (member == QStringLiteral("EmitServicesChanged")) {
            emitServicesChanged();
            connection.send(message.createReply());
        } else if (member == QStringLiteral("EmitPropertyChanged")) {
            emitPropertyChanged(args.value(0).toString());
            connection.send(message.createReply());
        } else if (member == QStringLiteral("SetRefreshFailure")) {
            m_failRefresh = args.value(0).toBool();
            connection.send(message.createReply());
        } else if (member == QStringLiteral("ConnectCount")) {
            connection.send(message.createReply(
                QVariantList() << m_connectCounts.value(args.value(0).toString())));
        } else if (member == QStringLiteral("RegisterCount")) {
            connection.send(message.createReply(
                QVariantList() << m_registerCount));
        } else if (member == QStringLiteral("ReplyConnect")) {
            replyConnect(args.value(0).toString(), args.value(1).toString());
            connection.send(message.createReply());
        } else if (member == QStringLiteral("CallRequestInput")) {
            callRequestInput(args.value(0).toString());
            connection.send(message.createReply());
        } else if (member == QStringLiteral("CallReportError")) {
            callAgentVoid(QStringLiteral("ReportError"),
                          QVariantList()
                              << QVariant::fromValue(QDBusObjectPath(
                                     servicePath(args.value(0).toString())))
                              << args.value(1).toString());
            connection.send(message.createReply());
        } else if (member == QStringLiteral("CallRelease")) {
            callAgentVoid(QStringLiteral("Release"), QVariantList());
            connection.send(message.createReply());
        } else if (member == QStringLiteral("AgentCallSerial")) {
            connection.send(message.createReply(
                QVariantList() << m_agentCallSerial));
        } else if (member == QStringLiteral("LastInputSize")) {
            connection.send(message.createReply(
                QVariantList() << m_lastInput.size()));
        } else if (member == QStringLiteral("LastInputValue")) {
            connection.send(message.createReply(
                QVariantList() << m_lastInput.value(args.value(0).toString())
                                      .toString()));
        } else if (member == QStringLiteral("Restart")) {
            connection.send(message.createReply());
            QTimer::singleShot(0, this, [this]() {
                m_bus.unregisterService(QString::fromLatin1(kConnmanService));
            });
            QTimer::singleShot(300, this, [this]() {
                m_bus.registerService(QString::fromLatin1(kConnmanService));
            });
        } else {
            return false;
        }
        return true;
    }

    void setService(const QString &id, const QString &name,
                    const QString &state, int strength)
    {
        updateService(id, name, state, strength);
        emitServicesChanged();
        emitPropertyChanged(id);
    }

    void updateService(const QString &id, const QString &name,
                       const QString &state, int strength)
    {
        ConnmanService updated;
        updated.path = QDBusObjectPath(servicePath(id));
        updated.properties.insert(QStringLiteral("Type"),
                                  QStringLiteral("wifi"));
        updated.properties.insert(QStringLiteral("Name"), name);
        updated.properties.insert(QStringLiteral("State"), state);
        updated.properties.insert(QStringLiteral("Strength"), strength);

        bool replaced = false;
        for (ConnmanService &service : m_services) {
            if (service.path.path() == updated.path.path()) {
                service = updated;
                replaced = true;
                break;
            }
        }
        if (!replaced)
            m_services.append(updated);
    }

    void emitServicesChanged()
    {
        QDBusMessage changed = QDBusMessage::createSignal(
            QStringLiteral("/"), QString::fromLatin1(kManagerInterface),
            QStringLiteral("ServicesChanged"));
        changed << QVariant::fromValue(m_services)
                << QVariant::fromValue(QList<QDBusObjectPath>());
        m_bus.send(changed);
    }

    void emitPropertyChanged(const QString &id)
    {
        const QString path = servicePath(id);
        QString state;
        for (const ConnmanService &service : m_services) {
            if (service.path.path() == path) {
                state = service.properties.value(QStringLiteral("State"))
                            .toString();
                break;
            }
        }
        QDBusMessage property = QDBusMessage::createSignal(
            path, QString::fromLatin1(kServiceInterface),
            QStringLiteral("PropertyChanged"));
        property << QStringLiteral("State")
                 << QVariant::fromValue(QDBusVariant(state));
        m_bus.send(property);
    }

    void replyConnect(const QString &id, const QString &mode)
    {
        QList<QDBusMessage> &pending = m_pendingConnects[id];
        if (pending.isEmpty())
            return;
        const QDBusMessage call = pending.takeFirst();
        if (mode == QStringLiteral("success")) {
            m_bus.send(call.createReply());
        } else {
            const QString errorName = mode == QStringLiteral("invalid")
                ? QStringLiteral("net.connman.Error.InvalidKey")
                : QStringLiteral("net.connman.Error.Failed");
            m_bus.send(call.createErrorReply(errorName,
                                             QStringLiteral("simulated")));
        }
    }

    void callRequestInput(const QString &id)
    {
        m_lastInput.clear();
        QVariantMap fields;
        fields.insert(QStringLiteral("Name"), QVariantMap());
        fields.insert(QStringLiteral("Passphrase"), QVariantMap());
        QDBusMessage call = QDBusMessage::createMethodCall(
            m_agentOwner, m_agentPath, QString::fromLatin1(kAgentInterface),
            QStringLiteral("RequestInput"));
        call << QVariant::fromValue(QDBusObjectPath(servicePath(id)))
             << fields;
        QDBusPendingCallWatcher *watcher = new QDBusPendingCallWatcher(
            m_bus.asyncCall(call, 1000), this);
        QObject::connect(watcher, &QDBusPendingCallWatcher::finished, this,
                         [this, watcher]() {
            const QDBusPendingReply<QVariantMap> reply = *watcher;
            if (!reply.isError())
                m_lastInput = reply.value();
            ++m_agentCallSerial;
            watcher->deleteLater();
        });
    }

    void callAgentVoid(const QString &member, const QVariantList &arguments)
    {
        QDBusMessage call = QDBusMessage::createMethodCall(
            m_agentOwner, m_agentPath, QString::fromLatin1(kAgentInterface),
            member);
        call.setArguments(arguments);
        QDBusPendingCallWatcher *watcher = new QDBusPendingCallWatcher(
            m_bus.asyncCall(call, 1000), this);
        QObject::connect(watcher, &QDBusPendingCallWatcher::finished, this,
                         [this, watcher]() {
            ++m_agentCallSerial;
            watcher->deleteLater();
        });
    }

    QDBusConnection m_bus;
    QList<ConnmanService> m_services;
    QHash<QString, int> m_connectCounts;
    QHash<QString, QList<QDBusMessage> > m_pendingConnects;
    QString m_agentOwner;
    QString m_agentPath;
    QVariantMap m_lastInput;
    int m_registerCount = 0;
    int m_agentCallSerial = 0;
    bool m_failRefresh = false;
};

bool callVoid(QDBusInterface &control, const QString &method,
              const QVariantList &arguments = QVariantList())
{
    const QDBusMessage reply = control.callWithArgumentList(
        QDBus::Block, method, arguments);
    if (reply.type() == QDBusMessage::ErrorMessage) {
        qCritical() << method << reply.errorName() << reply.errorMessage();
        return false;
    }
    return true;
}

int callInt(QDBusInterface &control, const QString &method,
            const QVariantList &arguments = QVariantList())
{
    const QDBusReply<int> reply = control.callWithArgumentList(
        QDBus::Block, method, arguments);
    return reply.isValid() ? reply.value() : -1;
}

QString callString(QDBusInterface &control, const QString &method,
                   const QVariantList &arguments = QVariantList())
{
    const QDBusReply<QString> reply = control.callWithArgumentList(
        QDBus::Block, method, arguments);
    return reply.isValid() ? reply.value() : QString();
}

bool check(bool condition, const QString &message)
{
    if (!condition)
        qCritical().noquote() << QStringLiteral("FAIL: %1").arg(message);
    return condition;
}

bool setService(QDBusInterface &control, const QString &id,
                const QString &name, const QString &state, int strength)
{
    return callVoid(control, QStringLiteral("SetService"),
                    QVariantList() << id << name << state << strength);
}

bool runTests(const QDBusConnection &bus, QDBusInterface &control)
{
    const QString a = QStringLiteral("wifi_a");
    const QString b = QStringLiteral("wifi_b");
    if (!setService(control, a, QStringLiteral("Alpha"),
                    QStringLiteral("ready"), 72) ||
        !setService(control, b, QStringLiteral("Beta"),
                    QStringLiteral("idle"), 40)) {
        return false;
    }

    ConnmanWifiController controller(bus, QString::fromLatin1(kConnmanService),
                                     300);
    int successes = 0;
    int failures = 0;
    QObject::connect(&controller, &ConnmanWifiController::connectionSucceeded,
                     [&successes]() { ++successes; });
    QObject::connect(&controller, &ConnmanWifiController::connectionFailed,
                     [&failures]() { ++failures; });

    if (!check(waitFor([&controller]() {
            return controller.connected() && controller.ssid() == "Alpha";
        }), QStringLiteral("initial async refresh did not report Alpha"))) {
        return false;
    }

    if (!callVoid(control, QStringLiteral("SetServiceQuiet"),
                  QVariantList() << a << QStringLiteral("Alpha")
                                 << QStringLiteral("idle") << 72) ||
        !callVoid(control, QStringLiteral("EmitPropertyChanged"),
                  QVariantList() << a) ||
        !check(waitFor([&controller]() { return !controller.connected(); }),
               QStringLiteral("Service.PropertyChanged did not refresh status")) ||
        !callVoid(control, QStringLiteral("SetServiceQuiet"),
                  QVariantList() << a << QStringLiteral("Alpha")
                                 << QStringLiteral("ready") << 72) ||
        !callVoid(control, QStringLiteral("EmitServicesChanged")) ||
        !check(waitFor([&controller]() { return controller.connected(); }),
               QStringLiteral("Manager.ServicesChanged did not refresh status"))) {
        return false;
    }

    if (!callVoid(control, QStringLiteral("SetRefreshFailure"),
                  QVariantList() << true))
        return false;
    controller.refresh();
    if (!check(waitFor([&controller]() { return !controller.connected(); }),
               QStringLiteral("failed status query preserved stale connection")))
        return false;
    if (!callVoid(control, QStringLiteral("SetRefreshFailure"),
                  QVariantList() << false) ||
        !setService(control, a, QStringLiteral("Alpha"),
                    QStringLiteral("idle"), 72)) {
        return false;
    }

    controller.connectService(a, QStringLiteral("Alpha"),
                              QStringLiteral("test-passphrase"));
    if (!check(waitFor([&control, &a]() {
            return callInt(control, QStringLiteral("ConnectCount"),
                           QVariantList() << a) == 1;
        }) && controller.busy(),
        QStringLiteral("first Connect was not issued"))) {
        return false;
    }
    controller.connectService(b, QStringLiteral("Beta"),
                              QStringLiteral("other-passphrase"));
    if (!check(callInt(control, QStringLiteral("ConnectCount"),
                       QVariantList() << b) == 0,
               QStringLiteral("overlapping Connect bypassed busy guard")))
        return false;

    int serial = callInt(control, QStringLiteral("AgentCallSerial"));
    if (!callVoid(control, QStringLiteral("CallRequestInput"),
                  QVariantList() << b) ||
        !check(waitFor([&control, serial]() {
            return callInt(control, QStringLiteral("AgentCallSerial")) > serial;
        }), QStringLiteral("wrong-service RequestInput did not complete")) ||
        !check(callInt(control, QStringLiteral("LastInputSize")) == 0,
               QStringLiteral("wrong service received credentials"))) {
        return false;
    }

    serial = callInt(control, QStringLiteral("AgentCallSerial"));
    if (!callVoid(control, QStringLiteral("CallRequestInput"),
                  QVariantList() << a) ||
        !check(waitFor([&control, serial]() {
            return callInt(control, QStringLiteral("AgentCallSerial")) > serial;
        }), QStringLiteral("matching RequestInput did not complete")) ||
        !check(callString(control, QStringLiteral("LastInputValue"),
                          QVariantList() << QStringLiteral("Passphrase")) ==
                   QStringLiteral("test-passphrase"),
               QStringLiteral("matching service did not receive passphrase"))) {
        return false;
    }

    serial = callInt(control, QStringLiteral("AgentCallSerial"));
    if (!callVoid(control, QStringLiteral("CallReportError"),
                  QVariantList() << b << QStringLiteral("invalid-key")) ||
        !check(waitFor([&control, serial]() {
            return callInt(control, QStringLiteral("AgentCallSerial")) > serial;
        }) && controller.busy(),
        QStringLiteral("wrong-service ReportError ended active request"))) {
        return false;
    }
    if (!callVoid(control, QStringLiteral("ReplyConnect"),
                  QVariantList() << a << QStringLiteral("invalid")) ||
        !check(waitFor([&controller]() { return !controller.busy(); }),
               QStringLiteral("InvalidKey did not end first request"))) {
        return false;
    }

    controller.connectService(a, QStringLiteral("Alpha"),
                              QStringLiteral("test-passphrase"));
    if (!check(waitFor([&control, &a]() {
            return callInt(control, QStringLiteral("ConnectCount"),
                           QVariantList() << a) == 2;
        }), QStringLiteral("timeout scenario Connect was not issued")) ||
        !check(waitFor([&controller]() { return !controller.busy(); }, 1000),
               QStringLiteral("logical connection timeout did not fire"))) {
        return false;
    }

    controller.connectService(b, QStringLiteral("Beta"),
                              QStringLiteral("beta-passphrase"));
    if (!check(waitFor([&control, &b]() {
            return callInt(control, QStringLiteral("ConnectCount"),
                           QVariantList() << b) == 1;
        }) && controller.busy(),
        QStringLiteral("post-timeout request did not start"))) {
        return false;
    }
    if (!callVoid(control, QStringLiteral("ReplyConnect"),
                  QVariantList() << a << QStringLiteral("failed")))
        return false;
    QThread::msleep(30);
    QCoreApplication::processEvents();
    if (!check(controller.busy(),
               QStringLiteral("stale callback ended newer request")))
        return false;

    if (!setService(control, b, QStringLiteral("Beta"),
                    QStringLiteral("ready"), 68) ||
        !check(waitFor([&controller, &successes]() {
            return !controller.busy() && controller.ssid() == "Beta" &&
                   successes == 1;
        }), QStringLiteral("ServicesChanged/PropertyChanged did not finish Beta"))) {
        return false;
    }
    callVoid(control, QStringLiteral("ReplyConnect"),
             QVariantList() << b << QStringLiteral("success"));

    const int registrationsBeforeRelease =
        callInt(control, QStringLiteral("RegisterCount"));
    serial = callInt(control, QStringLiteral("AgentCallSerial"));
    if (!callVoid(control, QStringLiteral("CallRelease")) ||
        !check(waitFor([&control, serial]() {
            return callInt(control, QStringLiteral("AgentCallSerial")) > serial;
        }), QStringLiteral("Agent.Release did not complete")) ||
        !setService(control, b, QStringLiteral("Beta"),
                    QStringLiteral("idle"), 68)) {
        return false;
    }

    controller.connectService(a, QStringLiteral("Alpha"),
                              QStringLiteral("test-passphrase"));
    if (!check(waitFor([&control, registrationsBeforeRelease]() {
            return callInt(control, QStringLiteral("RegisterCount")) ==
                   registrationsBeforeRelease + 1;
        }) && controller.busy(),
        QStringLiteral("Release retry did not reuse object and re-register agent"))) {
        return false;
    }
    callVoid(control, QStringLiteral("ReplyConnect"),
             QVariantList() << a << QStringLiteral("failed"));
    if (!check(waitFor([&controller]() { return !controller.busy(); }),
               QStringLiteral("Release retry cleanup failed")))
        return false;

    if (!setService(control, a, QStringLiteral("Alpha"),
                    QStringLiteral("ready"), 75) ||
        !check(waitFor([&controller]() { return controller.connected(); }),
               QStringLiteral("pre-restart connected state missing"))) {
        return false;
    }
    const int registrationsBeforeRestart =
        callInt(control, QStringLiteral("RegisterCount"));
    if (!callVoid(control, QStringLiteral("Restart")) ||
        !check(waitFor([&controller]() { return !controller.connected(); }),
               QStringLiteral("ConnMan owner loss did not clear state")) ||
        !check(waitFor([&control, registrationsBeforeRestart]() {
            return callInt(control, QStringLiteral("RegisterCount")) ==
                   registrationsBeforeRestart + 1;
        }, 2000), QStringLiteral("ConnMan restart did not re-register agent")) ||
        !check(waitFor([&controller]() {
            return controller.connected() && controller.ssid() == "Alpha";
        }), QStringLiteral("ConnMan restart did not restore status"))) {
        return false;
    }

    if (!check(failures >= 3,
               QStringLiteral("expected failure paths were not observed")))
        return false;
    qInfo() << "PASS: ConnMan lifecycle regression scenarios";
    return true;
}
}

int main(int argc, char *argv[])
{
    QCoreApplication app(argc, argv);
    qRegisterMetaType<ConnmanService>();
    qRegisterMetaType<QList<ConnmanService> >();
    qDBusRegisterMetaType<ConnmanService>();
    qDBusRegisterMetaType<QList<ConnmanService> >();

    QDBusConnection bus = QDBusConnection::sessionBus();
    if (!bus.isConnected()) {
        qCritical() << "A private session D-Bus is required";
        return 2;
    }

    if (app.arguments().contains(QStringLiteral("--fake-service"))) {
        FakeConnman fake(bus);
        if (!bus.registerVirtualObject(QStringLiteral("/"), &fake,
                                       QDBusConnection::SubPath) ||
            !bus.registerService(QString::fromLatin1(kControlService)) ||
            !bus.registerService(QString::fromLatin1(kConnmanService))) {
            qCritical() << "Unable to register fake ConnMan" << bus.lastError();
            return 3;
        }
        return app.exec();
    }

    QProcess child;
    child.setProcessChannelMode(QProcess::ForwardedChannels);
    child.start(QCoreApplication::applicationFilePath(),
                QStringList() << QStringLiteral("--fake-service"));
    if (!child.waitForStarted(1000) ||
        !waitFor([&bus]() {
            return bus.interface()->isServiceRegistered(
                QString::fromLatin1(kControlService)).value();
        })) {
        qCritical() << "Fake ConnMan did not start";
        child.kill();
        child.waitForFinished();
        return 4;
    }

    QDBusInterface control(QString::fromLatin1(kControlService),
                           QStringLiteral("/test"),
                           QString::fromLatin1(kControlInterface), bus);
    const bool passed = runTests(bus, control);
    child.terminate();
    if (!child.waitForFinished(1000)) {
        child.kill();
        child.waitForFinished();
    }
    return passed ? 0 : 1;
}
