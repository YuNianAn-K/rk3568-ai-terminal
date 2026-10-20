#include "persontracker.h"

#include <QCoreApplication>
#include <QDebug>
#include <QDir>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QtGlobal>
#include <cmath>
#include <cstring>

PersonTracker::PersonTracker(QObject *parent) : QObject(parent)
{
    m_timingEnabled = qEnvironmentVariable("GIMBAL_TIMING") == QStringLiteral("1");
    m_dispatchTimer.setSingleShot(true);
    m_dispatchTimer.setTimerType(Qt::PreciseTimer);
    connect(&m_dispatchTimer, &QTimer::timeout, this, &PersonTracker::trySendLatest);
    connect(&m_detector, &QProcess::readyReadStandardOutput, this, &PersonTracker::onOutput);
    connect(&m_detector, &QProcess::readyReadStandardError, this, [this]() {
        qWarning() << "PERSON_STDERR" << m_detector.readAllStandardError();
    });
    connect(&m_detector, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, [this](int, QProcess::ExitStatus) {
        if (m_active)
            fail(QStringLiteral("检测进程已退出"));
    });
    connect(&m_detector, &QProcess::errorOccurred, this, [this](QProcess::ProcessError) {
        if (m_active)
            fail(QStringLiteral("无法运行检测进程"));
    });
    connect(&m_watchdog, &QTimer::timeout, this, [this]() {
        if (!m_active)
            return;
        if (m_frameAge.elapsed() > 1500) {
            fail(QStringLiteral("画面停顿，已停止"));
        } else if (!m_ready && m_startAge.elapsed() > 10000) {
            fail(QStringLiteral("模型初始化超时"));
        } else if (m_pending && m_sendAge.elapsed() > (m_receivedResult ? 2000 : 10000)) {
            fail(QStringLiteral("推理超时，已停止"));
        } else if (m_receivedResult && m_resultAge.elapsed() > 1000) {
            clearDetections();
            setStatus(QStringLiteral("人物：结果过期，等待新帧"));
        }
    });
    m_watchdog.start(200);
}

PersonTracker::~PersonTracker()
{
    stop();
}

bool PersonTracker::resultFresh() const
{
    QElapsedTimer clock;
    clock.start();
    const qint64 age = clock.msecsSinceReference() - m_resultProbeMs;
    return m_active && !m_detections.isEmpty() && m_resultProbeMs > 0 && age >= 0 && age <= 500;
}

void PersonTracker::setStatus(const QString &status)
{
    if (status == m_status)
        return;
    m_status = status;
    emit statusChanged();
}

void PersonTracker::clearDetections()
{
    m_heads.clear();
    if (m_detections.isEmpty())
        return;
    m_detections.clear();
    emit detectionsChanged();
}

void PersonTracker::setFrameAvailable(bool available)
{
    m_frameAvailable = available;
    if (!available && m_active)
        fail(QStringLiteral("摄像头不可用，已停止"));
}

void PersonTracker::start()
{
    if (m_active || !m_frameAvailable || m_detector.state() != QProcess::NotRunning)
        return;
    m_active = true;
    m_dispatchTimer.stop();
    m_latestFrame = QImage();
    m_probeMs = m_latestProbeMs = m_lastReceivedProbeMs = m_pendingFrameWaitMs = 0;
    m_ready = m_pending = m_receivedResult = false;
    m_sequence = m_previewCount = m_resultCount = 0;
    m_previewFps = m_detectionHz = 0;
    m_output.clear();
    clearDetections();
    m_metrics.clear();
    emit metricsChanged();
    m_startAge.start();
    m_frameAge.start();
    m_rateWindow.start();
    m_sendAge.invalidate();
    m_resultAge.invalidate();
    setStatus(QStringLiteral("人物：正在加载 CPU 模型"));
    emit activeChanged();
    m_detector.setProgram(QStringLiteral("python3"));
    m_detector.setArguments({QDir(QCoreApplication::applicationDirPath()).filePath(
        QStringLiteral("person_detector.py"))});
    m_detector.start();
    qInfo() << "PERSON_START_DETECTION_ONLY";
}

void PersonTracker::stop()
{
    if (!m_active && m_detector.state() == QProcess::NotRunning)
        return;
    m_active = m_ready = m_pending = false;
    m_dispatchTimer.stop();
    m_latestFrame = QImage();
    m_latestProbeMs = m_lastReceivedProbeMs = 0;
    clearDetections();
    m_output.clear();
    emit activeChanged();
    if (m_detector.state() != QProcess::NotRunning) {
        m_detector.kill();
        m_detector.waitForFinished(500);
    }
    m_metrics.clear();
    emit metricsChanged();
    setStatus(QStringLiteral("人物：已停止"));
    qInfo() << "PERSON_STOP";
}

void PersonTracker::fail(const QString &message)
{
    stop();
    setStatus(QStringLiteral("人物：") + message);
    qWarning() << "PERSON_FAILURE" << message;
}

void PersonTracker::onFrame(const QImage &image, qint64 probeMs)
{
    if (!m_active)
        return;
    QElapsedTimer clock;
    clock.start();
    const qint64 age = clock.msecsSinceReference() - probeMs;
    // Keep one newest, distinct source frame. Never replay a frame or reset
    // its timestamp to the dispatch time; downstream 500 ms checks use capture.
    if (probeMs <= 0 || probeMs <= m_lastReceivedProbeMs || age < 0 || age > 80)
        return;
    if (image.width() != 640 || image.height() != 480 || image.isNull()) {
        fail(QStringLiteral("预览帧格式异常"));
        return;
    }
    m_lastReceivedProbeMs = probeMs;
    m_latestFrame = image;
    m_latestProbeMs = probeMs;
    m_frameAge.restart();
    ++m_previewCount;
    if (m_rateWindow.elapsed() >= 1000) {
        const double seconds = m_rateWindow.elapsed() / 1000.0;
        m_previewFps = m_previewCount / seconds;
        m_detectionHz = m_resultCount / seconds;
        m_previewCount = m_resultCount = 0;
        m_rateWindow.restart();
    }
    trySendLatest();
}

void PersonTracker::trySendLatest()
{
    if (!m_active || !m_ready || m_pending || m_latestFrame.isNull() ||
        m_detector.state() != QProcess::Running)
        return;
    QElapsedTimer clock;
    clock.start();
    const qint64 age = clock.msecsSinceReference() - m_latestProbeMs;
    if (age < 0 || age > 80 || m_latestProbeMs <= m_probeMs) {
        m_latestFrame = QImage();
        m_latestProbeMs = 0;
        return;
    }
    const qint64 elapsed = m_sendAge.isValid() ? m_sendAge.elapsed() : 100;
    if (elapsed < 100) {
        m_dispatchTimer.start(int(100 - elapsed));
        return;
    }
    const QImage image = m_latestFrame;
    const qint64 probeMs = m_latestProbeMs;
    m_latestFrame = QImage();
    m_latestProbeMs = 0;
    const QImage rgb = image.convertToFormat(QImage::Format_RGB888);
    if (rgb.width() != 640 || rgb.height() != 480 || rgb.bytesPerLine() < 1920) {
        fail(QStringLiteral("预览帧格式异常"));
        return;
    }
    const quint32 length = 640 * 480 * 3;
    QByteArray payload(4 + length, Qt::Uninitialized);
    for (int i = 0; i < 4; ++i)
        payload[i] = char((length >> (8 * i)) & 0xff);
    for (int row = 0; row < 480; ++row)
        std::memcpy(payload.data() + 4 + row * 1920, rgb.constScanLine(row), 1920);
    if (m_detector.write(payload) != payload.size()) {
        fail(QStringLiteral("传帧失败"));
        return;
    }
    m_pending = true;
    m_probeMs = probeMs;
    m_pendingFrameWaitMs = age;
    ++m_sequence;
    m_sendAge.restart();
}

void PersonTracker::onOutput()
{
    m_output += m_detector.readAllStandardOutput();
    if (m_output.size() > 32768) {
        fail(QStringLiteral("检测输出过长"));
        return;
    }
    while (m_active) {
        const int newline = m_output.indexOf('\n');
        if (newline < 0)
            return;
        const QByteArray line = m_output.left(newline);
        m_output.remove(0, newline + 1);
        const QJsonDocument document = QJsonDocument::fromJson(line);
        if (!document.isObject()) {
            fail(QStringLiteral("检测输出格式错误"));
            return;
        }
        QJsonObject data = document.object();
        const QString event = data.value(QStringLiteral("event")).toString();
        if (event == QStringLiteral("ready") && !m_ready) {
            m_ready = true;
            setStatus(QStringLiteral("人物：等待画面"));
            if (m_timingEnabled)
                qInfo().noquote() << "PERSON_TIMING" << line;
            trySendLatest();
            continue;
        }
        if (event != QStringLiteral("result") || !m_pending ||
            data.value(QStringLiteral("seq")).toInt(-1) != m_sequence ||
            !data.value(QStringLiteral("boxes")).isArray()) {
            fail(QStringLiteral("检测结果顺序或格式错误"));
            return;
        }
        const QJsonArray boxes = data.value(QStringLiteral("boxes")).toArray();
        if (boxes.size() > 10) {
            fail(QStringLiteral("检测框数量异常"));
            return;
        }
        QVariantList next;
        for (const QJsonValue &value : boxes) {
            const QJsonObject box = value.toObject();
            bool valid = value.isObject();
            for (const QString &key : {QStringLiteral("left"), QStringLiteral("top"),
                                      QStringLiteral("right"), QStringLiteral("bottom"),
                                      QStringLiteral("score")}) {
                const QJsonValue number = box.value(key);
                valid = valid && number.isDouble() && std::isfinite(number.toDouble()) &&
                        number.toDouble() >= 0 && number.toDouble() <= 1;
            }
            valid = valid && box.value(QStringLiteral("right")).toDouble() >
                            box.value(QStringLiteral("left")).toDouble() &&
                            box.value(QStringLiteral("bottom")).toDouble() >
                            box.value(QStringLiteral("top")).toDouble();
            if (!valid) {
                fail(QStringLiteral("人物框坐标异常"));
                return;
            }
            next.append(box.toVariantMap());
        }
        QVariantList nextHeads;
        const QJsonArray heads = data.value(QStringLiteral("heads")).toArray();
        if (heads.size() > 10) { fail(QStringLiteral("头部结果数量异常")); return; }
        for (const QJsonValue &value : heads) {
            const QJsonObject h = value.toObject();
            bool valid = value.isObject();
            for (const QString &key : {QStringLiteral("x"), QStringLiteral("y"), QStringLiteral("width"), QStringLiteral("score")}) {
                const QJsonValue v = h.value(key);
                valid = valid && v.isDouble() && std::isfinite(v.toDouble()) && v.toDouble() > 0 && v.toDouble() <= 1;
            }
            if (!valid) { fail(QStringLiteral("头部结果格式异常")); return; }
            nextHeads.append(h.toVariantMap());
        }
        QElapsedTimer clock;
        clock.start();
        const qint64 resultMs = clock.msecsSinceReference();
        const qint64 age = resultMs - m_probeMs;
        m_pending = false;
        m_receivedResult = true;
        m_resultAge.restart();
        ++m_resultCount;
        if (age < 0 || age > 1000) {
            clearDetections();
            setStatus(QStringLiteral("人物：结果过期，等待新帧"));
        } else {
            m_resultProbeMs = m_probeMs;
            m_resultMs = resultMs;
            m_heads = nextHeads;
            m_detections = next;
            emit detectionsChanged();
            setStatus(next.isEmpty() ? QStringLiteral("人物：无人") : QStringLiteral("人物：检测中"));
        }
        m_metrics = QStringLiteral("检测 %1 Hz · 推理 %2 ms · 结果 %3 ms")
            .arg(m_detectionHz, 0, 'f', 1)
            .arg(data.value(QStringLiteral("inference_ms")).toDouble(), 0, 'f', 0)
            .arg(age);
        emit metricsChanged();
        if (m_timingEnabled) {
            data.insert(QStringLiteral("probe_ms"), double(m_probeMs));
            data.insert(QStringLiteral("result_ms"), double(resultMs));
            data.insert(QStringLiteral("probe_to_result_ms"), double(age));
            data.insert(QStringLiteral("capture_to_dispatch_ms"), double(m_pendingFrameWaitMs));
            data.insert(QStringLiteral("preview_delivery_fps"), m_previewFps);
            data.insert(QStringLiteral("detection_hz"), m_detectionHz);
            qInfo().noquote() << "PERSON_TIMING" << QString::fromUtf8(
                QJsonDocument(data).toJson(QJsonDocument::Compact));
        }
        trySendLatest();
    }
}
