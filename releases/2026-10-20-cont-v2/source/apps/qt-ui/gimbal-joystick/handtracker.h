#ifndef HANDTRACKER_H
#define HANDTRACKER_H

#include <QObject>
#include <QImage>
#include <QElapsedTimer>
#include <QProcess>
#include <QTimer>
#include <QVideoProbe>

class GimbalBridge;
class QCamera;

class HandTracker : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool active READ active NOTIFY activeChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(bool previewReady READ previewReady NOTIFY previewReadyChanged)

public:
    explicit HandTracker(GimbalBridge *bridge, QObject *parent = nullptr);
    ~HandTracker() override;
    bool attach(QCamera *camera);
    bool active() const { return m_active; }
    bool previewReady() const { return m_previewReady; }
    QString status() const { return m_status; }
    Q_INVOKABLE void start();
    Q_INVOKABLE void stop();
    void setPersonDetectionActive(bool active) { m_personDetectionActive = active; }

signals:
    void activeChanged();
    void statusChanged();
    void previewReadyChanged();
    void previewFrame(const QImage &frame);
    void detectionFrame(const QImage &frame, qint64 probeMs);

private:
    void onFrame(const QVideoFrame &frame);
    void onOutput();
    void setStatus(const QString &status);

    GimbalBridge *m_bridge;
    QVideoProbe m_probe;
    QProcess m_detector;
    QTimer m_watchdog;
    QElapsedTimer m_sampleAge;
    QElapsedTimer m_sendAge;
    QElapsedTimer m_previewAge;
    QElapsedTimer m_previewSendAge;
    QByteArray m_output;
    bool m_active = false;
    bool m_personDetectionActive = false;
    bool m_pending = false;
    bool m_receivedSample = false;
    bool m_attached = false;
    bool m_previewFrameLogged = false;
    bool m_previewReady = false;
    bool m_timingEnabled = false;
    qint64 m_lastProbeMs = 0;
    qint64 m_pendingProbeMs = 0;
    qint64 m_lastSampleProbeMs = 0;
    qint64 m_pendingMediaUs = -1;
    qint64 m_pendingProbeIntervalMs = 0;
    qint64 m_pendingSampleIntervalMs = 0;
    qint64 m_previewConvertMs = 0;
    int m_sampleSequence = 0;
    QString m_status = QStringLiteral("跟手：未启动");
};

#endif
