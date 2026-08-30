#include "voicebridge.h"

#include <QJsonDocument>
#include <QJsonObject>

namespace {
const char kVoiceSocketPath[] = "/tmp/ai-voice.sock";
}

VoiceBridge::VoiceBridge(QObject *parent)
    : QObject(parent)
{
    m_reconnectTimer.setInterval(1500);
    m_reconnectTimer.setSingleShot(false);

    connect(&m_reconnectTimer, &QTimer::timeout,
            this, &VoiceBridge::connectService);
    connect(&m_socket, &QLocalSocket::connected,
            this, &VoiceBridge::onConnected);
    connect(&m_socket, &QLocalSocket::disconnected,
            this, &VoiceBridge::onDisconnected);
    connect(&m_socket, &QLocalSocket::readyRead,
            this, &VoiceBridge::onReadyRead);
    connect(&m_socket, &QLocalSocket::errorOccurred,
            this, &VoiceBridge::onSocketError);

    m_reconnectTimer.start();
    QTimer::singleShot(0, this, &VoiceBridge::connectService);
}

VoiceBridge::~VoiceBridge()
{
    m_reconnectTimer.stop();
    disconnect(&m_reconnectTimer, nullptr, this, nullptr);
    disconnect(&m_socket, nullptr, this, nullptr);
    m_socket.abort();
}

bool VoiceBridge::connected() const { return m_connected; }
QString VoiceBridge::state() const { return m_state; }
QString VoiceBridge::message() const { return m_message; }
QString VoiceBridge::transcript() const { return m_transcript; }
QString VoiceBridge::answer() const { return m_answer; }
QString VoiceBridge::errorMessage() const { return m_errorMessage; }
QVariantMap VoiceBridge::timings() const { return m_timings; }
QVariantMap VoiceBridge::diagnostics() const { return m_diagnostics; }
int VoiceBridge::roundId() const { return m_roundId; }

void VoiceBridge::startRecording()
{
    setTranscript(QString());
    setAnswer(QString());
    setErrorMessage(QString());
    sendCommand(QStringLiteral("start"));
}

void VoiceBridge::stopRecording()
{
    sendCommand(QStringLiteral("stop"));
}

void VoiceBridge::cancel()
{
    sendCommand(QStringLiteral("cancel"));
}

void VoiceBridge::reconnectService()
{
    connectService();
}

void VoiceBridge::refreshStatus()
{
    sendCommand(QStringLiteral("status"));
}

void VoiceBridge::connectService()
{
    if (m_socket.state() == QLocalSocket::ConnectedState ||
            m_socket.state() == QLocalSocket::ConnectingState) {
        return;
    }
    m_socket.abort();
    m_socket.connectToServer(QString::fromLatin1(kVoiceSocketPath),
                             QIODevice::ReadWrite);
}

void VoiceBridge::onConnected()
{
    setConnected(true);
    setState(QStringLiteral("initializing"));
    setMessage(QStringLiteral("正在同步语音服务状态"));
    m_reconnectTimer.stop();
    sendCommand(QStringLiteral("status"));
}

void VoiceBridge::onDisconnected()
{
    setConnected(false);
    setState(QStringLiteral("offline"));
    setMessage(QStringLiteral("语音服务已断开，正在重连"));
    if (!m_reconnectTimer.isActive())
        m_reconnectTimer.start();
}

void VoiceBridge::onReadyRead()
{
    m_buffer += m_socket.readAll();
    while (true) {
        const int newline = m_buffer.indexOf('\n');
        if (newline < 0)
            break;
        const QByteArray line = m_buffer.left(newline).trimmed();
        m_buffer.remove(0, newline + 1);
        if (!line.isEmpty())
            processMessage(line);
    }
    if (m_buffer.size() > 64 * 1024) {
        m_buffer.clear();
        setErrorMessage(QStringLiteral("语音服务消息过长"));
        setState(QStringLiteral("error"));
    }
}

void VoiceBridge::onSocketError(QLocalSocket::LocalSocketError error)
{
    Q_UNUSED(error)
    if (m_socket.state() != QLocalSocket::ConnectedState) {
        setConnected(false);
        setState(QStringLiteral("offline"));
        setMessage(QStringLiteral("等待语音服务启动"));
        if (!m_reconnectTimer.isActive())
            m_reconnectTimer.start();
    }
}

void VoiceBridge::sendCommand(const QString &command)
{
    if (m_socket.state() != QLocalSocket::ConnectedState) {
        setState(QStringLiteral("offline"));
        setMessage(QStringLiteral("语音服务未连接"));
        connectService();
        return;
    }

    QJsonObject object;
    object.insert(QStringLiteral("command"), command);
    const QByteArray payload = QJsonDocument(object).toJson(QJsonDocument::Compact)
            + '\n';
    m_socket.write(payload);
    m_socket.flush();
}

void VoiceBridge::processMessage(const QByteArray &line)
{
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(line, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        setErrorMessage(QStringLiteral("语音服务返回格式错误"));
        setState(QStringLiteral("error"));
        return;
    }

    const QJsonObject object = document.object();
    const QString type = object.value(QStringLiteral("type")).toString();

    if (type == QStringLiteral("snapshot")) {
        setState(object.value(QStringLiteral("state")).toString());
        setMessage(object.value(QStringLiteral("message")).toString());
        setTranscript(object.value(QStringLiteral("transcript")).toString());
        setAnswer(object.value(QStringLiteral("answer")).toString());
        setErrorMessage(object.value(QStringLiteral("error")).toString());
        updateDiagnostics(object);
        return;
    }
    if (type == QStringLiteral("timing")) {
        const QString stage = object.value(QStringLiteral("stage")).toString();
        if (!stage.isEmpty()) {
            m_timings.insert(
                stage,
                object.value(QStringLiteral("elapsed_ms")).toVariant());
        }
        m_roundId = object.value(QStringLiteral("round_id")).toInt(m_roundId);
        emit diagnosticsChanged();
        return;
    }
    if (type == QStringLiteral("diagnostics")) {
        updateDiagnostics(object);
        return;
    }
    if (type == QStringLiteral("state")) {
        setState(object.value(QStringLiteral("state")).toString());
        setMessage(object.value(QStringLiteral("message")).toString());
        return;
    }
    if (type == QStringLiteral("transcript")) {
        setTranscript(object.value(QStringLiteral("text")).toString());
        return;
    }
    if (type == QStringLiteral("answer_delta")) {
        setAnswer(m_answer + object.value(QStringLiteral("text")).toString());
        return;
    }
    if (type == QStringLiteral("answer")) {
        setAnswer(object.value(QStringLiteral("text")).toString());
        return;
    }
    if (type == QStringLiteral("error")) {
        const QString error = object.value(QStringLiteral("message")).toString();
        setErrorMessage(error);
        setMessage(error);
        setState(QStringLiteral("error"));
        return;
    }
    if (type == QStringLiteral("ack") &&
            !object.value(QStringLiteral("accepted")).toBool()) {
        const QString code = object.value(QStringLiteral("code")).toString();
        const QString message = object.value(QStringLiteral("message")).toString();
        setMessage(message);
        if (code != QStringLiteral("busy")) {
            setErrorMessage(message);
            setState(QStringLiteral("error"));
        }
    }
}

void VoiceBridge::setConnected(bool connected)
{
    if (m_connected == connected)
        return;
    m_connected = connected;
    emit connectedChanged();
}

void VoiceBridge::setState(const QString &state)
{
    if (m_state == state)
        return;
    m_state = state;
    emit stateChanged();
}

void VoiceBridge::setMessage(const QString &message)
{
    if (m_message == message)
        return;
    m_message = message;
    emit messageChanged();
}

void VoiceBridge::setTranscript(const QString &transcript)
{
    if (m_transcript == transcript)
        return;
    m_transcript = transcript;
    emit transcriptChanged();
}

void VoiceBridge::setAnswer(const QString &answer)
{
    if (m_answer == answer)
        return;
    m_answer = answer;
    emit answerChanged();
}

void VoiceBridge::setErrorMessage(const QString &errorMessage)
{
    if (m_errorMessage == errorMessage)
        return;
    m_errorMessage = errorMessage;
    emit errorMessageChanged();
}

void VoiceBridge::updateDiagnostics(const QJsonObject &object)
{
    if (object.value(QStringLiteral("timings")).isObject()) {
        m_timings = object.value(QStringLiteral("timings"))
                .toObject().toVariantMap();
    }
    if (object.value(QStringLiteral("diagnostics")).isObject()) {
        m_diagnostics = object.value(QStringLiteral("diagnostics"))
                .toObject().toVariantMap();
    }
    m_roundId = object.value(QStringLiteral("round_id")).toInt(m_roundId);
    emit diagnosticsChanged();
}
