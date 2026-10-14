#include "gimbalbridge.h"

#include <QCoreApplication>
#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QDebug>
#include <QtGlobal>
#include <QElapsedTimer>
#include <cmath>
#include <QUuid>
#include <QRegularExpression>

GimbalBridge::GimbalBridge(QObject *parent) : QObject(parent)
{
    setStatus(QStringLiteral("正在连接云台"));
    connect(&m_worker, &QProcess::readyReadStandardOutput, this, &GimbalBridge::processOutput);
    connect(&m_worker, &QProcess::readyReadStandardError, this, [this]() {
        m_worker.readAllStandardError();
    });
    connect(&m_worker, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, [this](int, QProcess::ExitStatus) {
        setConnected(false);
        if (!m_failed)
            setStatus(QStringLiteral("云台连接已断开"));
        m_direction.clear();
        emit trackingEnded();
    });
    connect(&m_worker, &QProcess::errorOccurred, this, [this](QProcess::ProcessError) {
        m_failed = true;
        setConnected(false);
        setStatus(QStringLiteral("云台 UART 异常 · 已请求停止"));
        setDetail(QStringLiteral("无法启动控制；STM32 有 2 秒失联保护"));
        emit trackingEnded();
    });

    m_worker.setProgram(QStringLiteral("python3"));
    m_worker.setArguments({QDir(QCoreApplication::applicationDirPath()).filePath(
        QStringLiteral("gimbal_worker.py"))});
    m_worker.start();
}

GimbalBridge::~GimbalBridge()
{
    if (m_worker.state() != QProcess::NotRunning) {
        send("STOP\nQUIT\n");
        if (!m_worker.waitForFinished(1500)) {
            m_worker.kill();
            m_worker.waitForFinished(200);
        }
    }
}

void GimbalBridge::send(const QByteArray &line)
{
    if (m_worker.state() == QProcess::Running)
        m_worker.write(line);
}

void GimbalBridge::press(const QString &direction)
{
    if (!m_connected)
        return;
    if (direction != QStringLiteral("PAN_LEFT") &&
        direction != QStringLiteral("PAN_RIGHT") &&
        direction != QStringLiteral("TILT_UP") &&
        direction != QStringLiteral("TILT_DOWN")) {
        stop();
        return;
    }
    if (m_direction == direction)
        return;
    m_direction = direction;
    send(direction.toLatin1() + '\n');
}

void GimbalBridge::stop()
{
    setPersonArmed(false);
    m_personTracking = false;
    m_direction.clear();
    send("STOP\n");
}

void GimbalBridge::refresh()
{
    if (m_connected)
        send("STATUS\n");
}

void GimbalBridge::trackStart()
{
    m_personTracking = false;
    if (m_connected && m_trackCapable && m_positionReady)
        send("TRACK_START\n");
}

void GimbalBridge::personStart(const QString &requestId)
{
    if (!m_connected || !m_trackCapable || !m_positionReady)
        return;
    m_personTracking = true;
    setPersonArmed(false);
    m_personRequestId = requestId.isEmpty() ?
        QUuid::createUuid().toString(QUuid::WithoutBraces).remove('-') : requestId;
    if (!QRegularExpression(QStringLiteral("^[a-f0-9]{32}$")).match(m_personRequestId).hasMatch()) {
        stop();
        return;
    }
    send("PERSON_START " + m_personRequestId.toLatin1() + '\n');
}

void GimbalBridge::requestStop(const QString &requestId)
{
    if (!QRegularExpression(QStringLiteral("^[a-f0-9]{32}$")).match(requestId).hasMatch())
        return;
    m_personTracking = false;
    setPersonArmed(false);
    m_direction.clear();
    send("CONTROL_STOP " + requestId.toLatin1() + '\n');
}

void GimbalBridge::setPersonArmed(bool armed)
{
    if (m_personArmed == armed) return;
    m_personArmed = armed;
    emit personArmedChanged();
}

void GimbalBridge::personPause()
{
    if (m_personTracking && m_connected)
        send("PERSON_PAUSE\n");
}

void GimbalBridge::personSample(double x, double y, double score,
                                qint64 probeMs, qint64 resultMs)
{
    if (!m_personTracking || !m_connected || !m_trackCapable)
        return;
    QElapsedTimer clock;
    clock.start();
    const qint64 now = clock.msecsSinceReference();
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(score) ||
        x <= 0 || x >= 1 || y <= 0 || y >= 1 ||
        score < 0.40 || score > 1 || probeMs <= 0 ||
        resultMs < probeMs || now < resultMs || now - probeMs > 500) {
        stop();
        emit trackingEnded();
        return;
    }
    send(QByteArray("PERSON ") + QByteArray::number(x, 'f', 4) + ' ' +
         QByteArray::number(y, 'f', 4) + ' ' + QByteArray::number(score, 'f', 3) +
         " 0 " + QByteArray::number(probeMs) + ' ' + QByteArray::number(resultMs) + '\n');
}

void GimbalBridge::center()
{
    if (m_connected && m_trackCapable)
        send("CENTER\n");
}

void GimbalBridge::trackStop()
{
    send("TRACK_STOP\n");
}

void GimbalBridge::trackSample(double x, double y, double score, bool ambiguous,
                              qint64 probeMs, qint64 resultMs)
{
    if (!m_connected || !m_trackCapable)
        return;
    QByteArray line = QByteArray("HAND ") + QByteArray::number(x, 'f', 4) + ' ' +
        QByteArray::number(y, 'f', 4) + ' ' + QByteArray::number(score, 'f', 3) + ' ' +
        (ambiguous ? "1" : "0");
    if (probeMs && resultMs)
        line += ' ' + QByteArray::number(probeMs) + ' ' + QByteArray::number(resultMs);
    send(line + '\n');
}

void GimbalBridge::setConnected(bool connected)
{
    if (m_connected == connected)
        return;
    m_connected = connected;
    if (!connected) setPersonArmed(false);
    emit connectedChanged();
}

void GimbalBridge::setStatus(const QString &status)
{
    if (m_status == status)
        return;
    m_status = status;
    emit statusChanged();
}

void GimbalBridge::setDetail(const QString &detail)
{
    if (m_detail == detail)
        return;
    m_detail = detail;
    emit detailChanged();
}

void GimbalBridge::processOutput()
{
    m_buffer += m_worker.readAllStandardOutput();
    while (true) {
        const int newline = m_buffer.indexOf('\n');
        if (newline < 0)
            break;
        const QByteArray line = m_buffer.left(newline);
        m_buffer.remove(0, newline + 1);
        const QJsonDocument document = QJsonDocument::fromJson(line);
        if (!document.isObject())
            continue;
        const QJsonObject data = document.object();
        const QString event = data.value(QStringLiteral("event")).toString();
        if (event == QStringLiteral("timing")) {
            qInfo().noquote() << "GIMBAL_TIMING" << QString::fromUtf8(line);
        } else if (event == QStringLiteral("ready")) {
            setConnected(true);
            const bool capable = data.value(QStringLiteral("track_capable")).toBool();
            if (m_trackCapable != capable) {
                m_trackCapable = capable;
                emit trackCapableChanged();
            }
            setStatus(QStringLiteral("已连接 · 等待触控"));
            m_positionReady = data.value(QStringLiteral("position_ready")).toBool();
            emit positionReadyChanged();
            setDetail(m_positionReady ? QStringLiteral("PA6 / PA7 均已停止") :
                      QStringLiteral("首次使用请先点“回中位”"));
        } else if (event == QStringLiteral("position")) {
            m_positionReady = data.value(QStringLiteral("ready")).toBool();
            emit positionReadyChanged();
            if (!m_positionReady)
                setDetail(QStringLiteral("首次使用请先点“回中位”"));
        } else if (event == QStringLiteral("centering")) {
            setStatus(QStringLiteral("正在回中位 · 随后自动停止"));
        } else if (event == QStringLiteral("active")) {
            const QString axis = data.value(QStringLiteral("axis")).toString();
            const QString pulse = data.value(QStringLiteral("pulse")).toString();
            setStatus(axis == QStringLiteral("PAN") ?
                          QStringLiteral("底座正在点动") : QStringLiteral("上轴正在点动"));
            setDetail(pulse + QStringLiteral(" · 松手停止"));
        } else if (event == QStringLiteral("stopped")) {
            setPersonArmed(false);
            setStatus(QStringLiteral("已停止"));
            setDetail(QStringLiteral("PA6 / PA7 均已停止"));
            m_direction.clear();
            if (data.value(QStringLiteral("pan")).toString() == QStringLiteral("OFF") &&
                data.value(QStringLiteral("tilt")).toString() == QStringLiteral("OFF"))
                emit controlAck(data.value(QStringLiteral("request_id")).toString(), QStringLiteral("off"));
        } else if (event == QStringLiteral("tracking")) {
            const QString state = data.value(QStringLiteral("state")).toString();
            if (state != QStringLiteral("active") || !data.contains(QStringLiteral("pulse")))
                qInfo().noquote() << "GIMBAL_STATE" << QString::fromUtf8(line);
            if (state == QStringLiteral("active")) {
                if (m_personTracking && data.value(QStringLiteral("request_id")).toString() == m_personRequestId) {
                    setPersonArmed(true);
                    emit controlAck(m_personRequestId, QStringLiteral("active"));
                }
                setStatus(m_personTracking ? QStringLiteral("跟人中 · 双轴平滑修正") :
                          QStringLiteral("跟手中 · 双轴平滑修正"));
                setDetail(data.value(QStringLiteral("pulse")).toString());
            } else if (state == QStringLiteral("paused")) {
                setPersonArmed(false);
                setStatus(QStringLiteral("人物暂时不可见 · 暂停等待"));
            } else if (state == QStringLiteral("lost")) {
                setStatus(m_personTracking ? QStringLiteral("人物目标丢失 · 已停止") :
                          QStringLiteral("跟手目标丢失 · 已停止"));
                m_personTracking = false;
                setPersonArmed(false);
                emit trackingEnded();
            } else if (state == QStringLiteral("searching")) {
                setStatus(m_personTracking ? QStringLiteral("跟人：确认选中目标") :
                          QStringLiteral("跟手：寻找单只手"));
            } else if (state == QStringLiteral("off")) {
                setStatus(QStringLiteral("已停止"));
            } else if (state == QStringLiteral("uninitialized")) {
                setStatus(QStringLiteral("请先回中位 · 未输出跟手动作"));
                emit trackingEnded();
            }
        } else if (event == QStringLiteral("error")) {
            m_failed = true;
            setConnected(false);
            setStatus(QStringLiteral("云台 UART 异常 · 已请求停止"));
            setDetail(data.value(QStringLiteral("message")).toString() +
                      QStringLiteral(" · STM32 有 2 秒失联保护"));
            m_direction.clear();
            emit trackingEnded();
        }
    }
}
