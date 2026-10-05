#include "handtracker.h"

#include <QCamera>
#include <QCoreApplication>
#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QDebug>
#include <QVideoFrame>
#include <QtGlobal>
#include <cstring>

#include "gimbalbridge.h"

HandTracker::HandTracker(GimbalBridge *bridge, QObject *parent)
    : QObject(parent), m_bridge(bridge)
{
    m_timingEnabled = qEnvironmentVariable("GIMBAL_TIMING") == QStringLiteral("1");
    connect(&m_probe, &QVideoProbe::videoFrameProbed,
            this, &HandTracker::onFrame);
    connect(&m_detector, &QProcess::readyReadStandardOutput,
            this, &HandTracker::onOutput);
    connect(&m_detector, &QProcess::readyReadStandardError, this, [this]() {
        qWarning() << "hand detector stderr:" << m_detector.readAllStandardError();
    });
    connect(&m_detector, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, [this](int code, QProcess::ExitStatus) {
        if (m_active) {
            qWarning() << "HAND_PROCESS_FINISHED" << code;
            stop();
            setStatus(QStringLiteral("跟手：检测进程已退出"));
        }
    });
    connect(&m_detector, &QProcess::errorOccurred, this, [this](QProcess::ProcessError) {
        if (m_active) {
            qWarning() << "HAND_PROCESS_ERROR" << m_detector.errorString();
            stop();
            setStatus(QStringLiteral("跟手：检测进程故障"));
        }
    });
    connect(m_bridge, &GimbalBridge::trackingEnded, this, [this]() {
        stop();
        setStatus(QStringLiteral("跟手：目标丢失，已停止"));
    });
    connect(&m_watchdog, &QTimer::timeout, this, [this]() {
        if (m_previewReady && m_previewAge.elapsed() > 1500) {
            m_previewReady = false;
            emit previewReadyChanged();
            if (m_active) {
                stop();
                setStatus(QStringLiteral("跟手：画面停顿，已停止"));
            }
        }
        if (!m_active)
            return;
        const int limit = m_receivedSample ? 1500 : 5000;
        if ((m_pending && m_sendAge.elapsed() > limit) ||
            m_sampleAge.elapsed() > limit) {
            qWarning() << "HAND_WATCHDOG" << m_pending << m_sendAge.elapsed()
                       << m_sampleAge.elapsed();
            stop();
            setStatus(QStringLiteral("跟手：画面停顿，已停止"));
        }
    });
    m_watchdog.start(200);
}

HandTracker::~HandTracker()
{
    stop();
}

bool HandTracker::attach(QCamera *camera)
{
    m_attached = camera && m_probe.setSource(camera);
    qInfo() << "hand video probe attached:" << m_attached;
    return m_attached;
}

void HandTracker::setStatus(const QString &status)
{
    if (m_status == status)
        return;
    m_status = status;
    qInfo() << status;
    emit statusChanged();
}

void HandTracker::start()
{
    if (m_active || !m_attached || !m_previewReady || !m_bridge->connected() ||
        !m_bridge->trackCapable() || !m_bridge->positionReady())
        return;
    m_active = true;
    qInfo() << "HAND_START";
    m_pending = false;
    m_receivedSample = false;
    m_output.clear();
    m_sampleSequence = 0;
    m_lastSampleProbeMs = 0;
    m_sampleAge.start();
    setStatus(QStringLiteral("跟手：寻找单只手"));
    emit activeChanged();
    m_detector.setProgram(QStringLiteral("python3"));
    m_detector.setArguments({QDir(QCoreApplication::applicationDirPath()).filePath(
        QStringLiteral("hand_detector.py"))});
    m_detector.start();
    m_bridge->trackStart();
}

void HandTracker::stop()
{
    if (!m_active)
        return;
    m_active = false;
    qInfo() << "HAND_STOP" << m_sampleAge.elapsed();
    m_pending = false;
    emit activeChanged();
    m_bridge->trackStop();
    if (m_detector.state() != QProcess::NotRunning) {
        m_detector.kill();
        m_detector.waitForFinished(200);
    }
    setStatus(QStringLiteral("跟手：已停止"));
}

void HandTracker::onFrame(const QVideoFrame &input)
{
    QElapsedTimer probeClock;
    probeClock.start();
    const qint64 probeMs = probeClock.msecsSinceReference();
    const qint64 probeIntervalMs = m_lastProbeMs ? probeMs - m_lastProbeMs : 0;
    m_lastProbeMs = probeMs;
    if (input.width() == 640 && input.height() == 480 &&
        input.pixelFormat() == QVideoFrame::Format_YUYV &&
        (!m_previewSendAge.isValid() || m_previewSendAge.elapsed() >= 50)) {
        QVideoFrame sample(input);
        if (sample.map(QAbstractVideoBuffer::ReadOnly)) {
            QImage image(640, 480, QImage::Format_RGB32);
            if (!image.isNull() && sample.bytesPerLine() >= 1280) {
                const auto clamp = [](int value) {
                    return value < 0 ? 0 : (value > 255 ? 255 : value);
                };
                for (int row = 0; row < 480; ++row) {
                    const uchar *source = sample.bits() + row * sample.bytesPerLine();
                    QRgb *destination = reinterpret_cast<QRgb *>(image.scanLine(row));
                    for (int col = 0; col < 640; col += 2) {
                        const int u = int(source[1]) - 128;
                        const int v = int(source[3]) - 128;
                        const int red = 409 * v + 128;
                        const int green = -100 * u - 208 * v + 128;
                        const int blue = 516 * u + 128;
                        const int y0 = 298 * (int(source[0]) - 16);
                        const int y1 = 298 * (int(source[2]) - 16);
                        destination[col] = qRgb(clamp((y0 + red) >> 8),
                                                clamp((y0 + green) >> 8),
                                                clamp((y0 + blue) >> 8));
                        destination[col + 1] = qRgb(clamp((y1 + red) >> 8),
                                                    clamp((y1 + green) >> 8),
                                                    clamp((y1 + blue) >> 8));
                        source += 4;
                    }
                }
                emit previewFrame(image);
                emit detectionFrame(image, probeMs);
                if (m_timingEnabled)
                    m_previewConvertMs = probeClock.elapsed();
                m_previewAge.restart();
                m_previewSendAge.restart();
                if (!m_previewReady) {
                    m_previewReady = true;
                    emit previewReadyChanged();
                }
                if (!m_previewFrameLogged) {
                    qInfo() << "preview painted first YUYV frame:" << image.size();
                    m_previewFrameLogged = true;
                }
            }
            sample.unmap();
        }
    }
    if (!m_active || m_pending || m_detector.state() != QProcess::Running ||
        (m_sendAge.isValid() && m_sendAge.elapsed() < 100))
        return;
    QVideoFrame frame(input);
    if (frame.width() != 640 || frame.height() != 480 ||
        frame.pixelFormat() != QVideoFrame::Format_YUYV ||
        !frame.map(QAbstractVideoBuffer::ReadOnly)) {
        qWarning() << "HAND_BAD_FRAME" << frame.width() << frame.height()
                   << frame.pixelFormat();
        stop();
        setStatus(QStringLiteral("跟手：视频格式异常，已停止"));
        return;
    }
    QByteArray payload;
    payload.resize(4 + 640 * 480 * 2);
    const quint32 length = 640 * 480 * 2;
    for (int i = 0; i < 4; ++i)
        payload[i] = char((length >> (8 * i)) & 0xff);
    for (int row = 0; row < 480; ++row)
        std::memcpy(payload.data() + 4 + row * 1280,
                    frame.bits() + row * frame.bytesPerLine(), 1280);
    frame.unmap();
    if (m_detector.write(payload) != payload.size()) {
        qWarning() << "HAND_WRITE_FAILED" << m_detector.errorString();
        stop();
        setStatus(QStringLiteral("跟手：传帧失败，已停止"));
        return;
    }
    m_pending = true;
    m_pendingProbeMs = probeMs;
    m_pendingMediaUs = input.startTime();
    m_pendingProbeIntervalMs = probeIntervalMs;
    m_pendingSampleIntervalMs = m_lastSampleProbeMs ? probeMs - m_lastSampleProbeMs : 0;
    m_lastSampleProbeMs = probeMs;
    ++m_sampleSequence;
    m_sendAge.restart();
}

void HandTracker::onOutput()
{
    m_output += m_detector.readAllStandardOutput();
    while (m_active) {
        const int newline = m_output.indexOf('\n');
        if (newline < 0)
            break;
        const QByteArray line = m_output.left(newline);
        m_output.remove(0, newline + 1);
        const QJsonDocument document = QJsonDocument::fromJson(line);
        if (!document.isObject()) {
            stop();
            setStatus(QStringLiteral("跟手：检测结果错误，已停止"));
            return;
        }
        const QJsonObject data = document.object();
        if (data.value(QStringLiteral("event")).toString() == QStringLiteral("timing")) {
            if (m_timingEnabled)
                qInfo().noquote() << "GIMBAL_TIMING" << QString::fromUtf8(line);
            continue;
        }
        if (!m_receivedSample)
            qInfo() << "HAND_FIRST_SAMPLE_MS" << m_sampleAge.elapsed();
        m_pending = false;
        m_receivedSample = true;
        m_sampleAge.restart();
        const bool found = data.value(QStringLiteral("found")).toBool();
        const bool ambiguous = data.value(QStringLiteral("ambiguous")).toBool();
        const double x = data.value(QStringLiteral("x")).toDouble();
        const double y = data.value(QStringLiteral("y")).toDouble();
        const double score = data.value(QStringLiteral("score")).toDouble();
        QElapsedTimer resultClock;
        resultClock.start();
        const qint64 resultMs = resultClock.msecsSinceReference();
        if (m_timingEnabled) {
            QJsonObject timing = data;
            timing.insert(QStringLiteral("type"), QStringLiteral("vision"));
            timing.insert(QStringLiteral("seq"), m_sampleSequence);
            timing.insert(QStringLiteral("probe_ms"), double(m_pendingProbeMs));
            timing.insert(QStringLiteral("result_ms"), double(resultMs));
            timing.insert(QStringLiteral("probe_to_result_ms"), double(resultMs - m_pendingProbeMs));
            timing.insert(QStringLiteral("probe_interval_ms"), double(m_pendingProbeIntervalMs));
            timing.insert(QStringLiteral("sample_interval_ms"), double(m_pendingSampleIntervalMs));
            timing.insert(QStringLiteral("media_timestamp_us"), double(m_pendingMediaUs));
            timing.insert(QStringLiteral("preview_convert_ms"), double(m_previewConvertMs));
            qInfo().noquote() << "GIMBAL_TIMING" << QString::fromUtf8(
                QJsonDocument(timing).toJson(QJsonDocument::Compact));
        }
        m_bridge->trackSample(x, y, found ? score : 0.0, ambiguous,
                             m_pendingProbeMs, resultMs);
        setStatus(found ? QStringLiteral("跟手：检测到单只手") :
                          QStringLiteral("跟手：寻找单只手"));
    }
    if (m_output.size() > 4096) {
        stop();
        setStatus(QStringLiteral("跟手：检测输出过长，已停止"));
    }
}
