#include "wifibridge.h"

#include <QRegularExpression>
#include <QStringList>

namespace {
const char kConnmanctl[] = "connmanctl";

bool hasFailure(const QString &text)
{
    static const QRegularExpression expression(
        QStringLiteral("(error|failed|failure|not found|invalid|incorrect)"),
        QRegularExpression::CaseInsensitiveOption);
    return expression.match(text).hasMatch();
}
}

WifiBridge::WifiBridge(QObject *parent)
    : QObject(parent)
{
    connect(&m_commandProcess, &QProcess::readyReadStandardOutput,
            this, &WifiBridge::onCommandReadyRead);
    connect(&m_commandProcess, &QProcess::readyReadStandardError,
            this, &WifiBridge::onCommandReadyRead);
    connect(&m_commandProcess,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this, &WifiBridge::onCommandFinished);

    connect(&m_connectProcess, &QProcess::started,
            this, &WifiBridge::onConnectStarted);
    connect(&m_connectProcess, &QProcess::readyReadStandardOutput,
            this, &WifiBridge::onConnectReadyRead);
    connect(&m_connectProcess, &QProcess::readyReadStandardError,
            this, &WifiBridge::onConnectReadyRead);
    connect(&m_connectProcess,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this, &WifiBridge::onConnectFinished);

    m_connectTimeout.setSingleShot(true);
    m_connectTimeout.setInterval(30000);
    connect(&m_connectTimeout, &QTimer::timeout,
            this, &WifiBridge::onConnectTimeout);

    QTimer::singleShot(0, this, &WifiBridge::refresh);
}

WifiBridge::~WifiBridge()
{
    m_connectTimeout.stop();
    if (m_commandProcess.state() != QProcess::NotRunning)
        m_commandProcess.kill();
    if (m_connectProcess.state() != QProcess::NotRunning)
        m_connectProcess.kill();
}

bool WifiBridge::online() const { return m_online; }
bool WifiBridge::connected() const { return m_connected; }
QString WifiBridge::ssid() const { return m_ssid; }
QString WifiBridge::status() const { return m_status; }
QString WifiBridge::errorMessage() const { return m_errorMessage; }
QVariantList WifiBridge::networks() const { return m_networks; }
bool WifiBridge::busy() const { return m_busy; }
bool WifiBridge::connecting() const { return m_connecting; }

void WifiBridge::refresh()
{
    if (m_busy || m_connecting)
        return;
    setErrorMessage(QString());
    startCommand({QStringLiteral("state")}, Operation::State);
}

void WifiBridge::scan()
{
    if (m_busy || m_connecting)
        return;
    setErrorMessage(QString());
    startCommand({QStringLiteral("scan"), QStringLiteral("wifi")},
                 Operation::Scan);
}

void WifiBridge::connectNetwork(const QString &service,
                                const QString &password)
{
    if (service.isEmpty() || m_busy || m_connecting)
        return;

    m_connectService = service;
    m_connectPassword = password;
    m_connectOutput.clear();
    m_passphraseSent = false;
    setErrorMessage(QString());
    setConnecting(true);
    m_status = QStringLiteral("正在连接 Wi-Fi");
    emit statusChanged();

    m_connectProcess.start(QString::fromLatin1(kConnmanctl));
    if (!m_connectProcess.waitForStarted(1500)) {
        setErrorMessage(QStringLiteral("无法启动 ConnMan"));
        setConnecting(false);
    }
}

void WifiBridge::startCommand(const QStringList &arguments,
                              Operation operation)
{
    if (m_commandProcess.state() != QProcess::NotRunning)
        return;
    m_commandOutput.clear();
    m_operation = operation;
    setBusy(true);
    m_commandProcess.start(QString::fromLatin1(kConnmanctl), arguments);
}

void WifiBridge::onCommandReadyRead()
{
    m_commandOutput += m_commandProcess.readAllStandardOutput();
    m_commandOutput += m_commandProcess.readAllStandardError();
    if (m_commandOutput.size() > 128 * 1024)
        m_commandOutput = m_commandOutput.right(64 * 1024);
}

void WifiBridge::onCommandFinished(int exitCode,
                                   QProcess::ExitStatus exitStatus)
{
    onCommandReadyRead();
    const Operation operation = m_operation;
    m_operation = Operation::None;

    if (exitStatus != QProcess::NormalExit || exitCode != 0) {
        setErrorMessage(QStringLiteral("ConnMan 命令执行失败"));
        m_status = QStringLiteral("Wi-Fi 服务不可用");
        emit statusChanged();
        setBusy(false);
        return;
    }

    if (operation == Operation::State) {
        parseState(m_commandOutput);
        startCommand({QStringLiteral("services")}, Operation::Services);
        return;
    }
    if (operation == Operation::Scan) {
        startCommand({QStringLiteral("services")}, Operation::Services);
        return;
    }
    if (operation == Operation::Services)
        parseServices(m_commandOutput);
    finishServiceCommand();
}

void WifiBridge::parseState(const QByteArray &output)
{
    const QString text = QString::fromLocal8Bit(output);
    const QRegularExpression stateExpression(
        QStringLiteral("^\\s*State\\s*=\\s*(\\S+)"),
        QRegularExpression::MultilineOption);
    const QRegularExpressionMatch match = stateExpression.match(text);
    const bool online = match.hasMatch() &&
            match.captured(1).compare(QStringLiteral("online"),
                                      Qt::CaseInsensitive) == 0;
    if (m_online == online)
        return;
    m_online = online;
    emit statusChanged();
}

void WifiBridge::parseServices(const QByteArray &output)
{
    QVariantList networks;
    QString connectedSsid;
    const QString text = QString::fromLocal8Bit(output);
    const QStringList lines = text.split(QRegularExpression(QStringLiteral("[\\r\\n]+")),
                                         Qt::SkipEmptyParts);

    for (const QString &line : lines) {
        const QString trimmed = line.trimmed();
        if (trimmed.isEmpty() || trimmed.startsWith(QStringLiteral("Available")))
            continue;

        const QStringList fields = trimmed.split(QRegularExpression(QStringLiteral("\\s+")),
                                                 Qt::SkipEmptyParts);
        if (fields.size() < 2)
            continue;
        const QString service = fields.last();
        if (!service.startsWith(QStringLiteral("wifi_")))
            continue;

        const int serviceIndex = trimmed.lastIndexOf(service);
        QString networkSsid = trimmed.mid(fields.first().size(),
                                           serviceIndex - fields.first().size()).trimmed();
        if (networkSsid.isEmpty())
            networkSsid = QStringLiteral("隐藏网络");

        const QString flags = fields.first();
        const bool isConnected = flags.contains(QLatin1Char('O')) ||
                flags.contains(QLatin1Char('R'));
        const bool requiresPassword = service.endsWith(QStringLiteral("_psk")) ||
                service.endsWith(QStringLiteral("_8021x"));

        QVariantMap network;
        network.insert(QStringLiteral("ssid"), networkSsid);
        network.insert(QStringLiteral("service"), service);
        network.insert(QStringLiteral("connected"), isConnected);
        network.insert(QStringLiteral("requiresPassword"), requiresPassword);
        network.insert(QStringLiteral("security"),
                       requiresPassword ? QStringLiteral("需要密码")
                                        : QStringLiteral("开放网络"));
        networks.append(network);
        if (isConnected && connectedSsid.isEmpty())
            connectedSsid = networkSsid;
    }

    if (m_networks != networks) {
        m_networks = networks;
        emit networksChanged();
    }

    const bool connected = !connectedSsid.isEmpty();
    const bool statusChangedNow = m_connected != connected || m_ssid != connectedSsid;
    m_connected = connected;
    m_ssid = connectedSsid;
    if (statusChangedNow)
        emit statusChanged();
}

void WifiBridge::finishServiceCommand()
{
    if (m_connected)
        m_status = QStringLiteral("已连接 · ") + m_ssid;
    else if (m_online)
        m_status = QStringLiteral("Wi-Fi 已开启，未连接");
    else
        m_status = QStringLiteral("Wi-Fi 未连接");
    emit statusChanged();
    setBusy(false);
}

void WifiBridge::onConnectStarted()
{
    m_connectTimeout.start();
    m_connectProcess.write("agent on\n");
    m_connectProcess.write("connect ");
    m_connectProcess.write(m_connectService.toUtf8());
    m_connectProcess.write("\n");
}

void WifiBridge::onConnectReadyRead()
{
    m_connectOutput += m_connectProcess.readAllStandardOutput();
    m_connectOutput += m_connectProcess.readAllStandardError();
    if (m_connectOutput.size() > 128 * 1024)
        m_connectOutput = m_connectOutput.right(64 * 1024);

    const QString text = QString::fromLocal8Bit(m_connectOutput);
    if (!m_passphraseSent &&
            text.contains(QStringLiteral("passphrase"), Qt::CaseInsensitive)) {
        m_connectProcess.write(m_connectPassword.toUtf8());
        m_connectProcess.write("\n");
        m_passphraseSent = true;
        m_connectPassword.clear();
    }

    if (text.contains(QStringLiteral("Connected"), Qt::CaseInsensitive) ||
            hasFailure(text)) {
        m_connectProcess.write("quit\n");
    }
}

void WifiBridge::onConnectFinished(int exitCode,
                                   QProcess::ExitStatus exitStatus)
{
    onConnectReadyRead();
    m_connectTimeout.stop();
    const QString output = QString::fromLocal8Bit(m_connectOutput);
    const bool failed = exitStatus != QProcess::NormalExit ||
            exitCode != 0 || hasFailure(output);
    m_connectPassword.clear();
    setConnecting(false);

    if (failed) {
        setErrorMessage(QStringLiteral("Wi-Fi 连接失败，请检查密码"));
        m_status = QStringLiteral("Wi-Fi 连接失败");
        emit statusChanged();
        return;
    }

    m_status = QStringLiteral("正在确认 Wi-Fi 连接");
    emit statusChanged();
    QTimer::singleShot(300, this, &WifiBridge::refresh);
}

void WifiBridge::onConnectTimeout()
{
    if (m_connectProcess.state() == QProcess::NotRunning)
        return;
    m_connectProcess.kill();
    setErrorMessage(QStringLiteral("Wi-Fi 连接超时"));
    m_status = QStringLiteral("Wi-Fi 连接超时");
    emit statusChanged();
    m_connectPassword.clear();
    setConnecting(false);
}

void WifiBridge::setErrorMessage(const QString &message)
{
    if (m_errorMessage == message)
        return;
    m_errorMessage = message;
    emit errorMessageChanged();
}

void WifiBridge::setBusy(bool busy)
{
    if (m_busy == busy)
        return;
    m_busy = busy;
    emit busyChanged();
}

void WifiBridge::setConnecting(bool connecting)
{
    if (m_connecting == connecting)
        return;
    m_connecting = connecting;
    emit connectingChanged();
}
