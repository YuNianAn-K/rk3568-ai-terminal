#ifndef PERSONTRACKER_H
#define PERSONTRACKER_H

#include <QObject>
#include <QElapsedTimer>
#include <QImage>
#include <QProcess>
#include <QTimer>
#include <QVariantList>

class PersonTracker : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool active READ active NOTIFY activeChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QVariantList detections READ detections NOTIFY detectionsChanged)
    Q_PROPERTY(QString metrics READ metrics NOTIFY metricsChanged)
    Q_PROPERTY(qint64 resultProbeMs READ resultProbeMs NOTIFY detectionsChanged)
    Q_PROPERTY(qint64 resultMs READ resultMs NOTIFY detectionsChanged)
    Q_PROPERTY(bool resultFresh READ resultFresh NOTIFY detectionsChanged)

public:
    explicit PersonTracker(QObject *parent = nullptr);
    ~PersonTracker() override;
    bool active() const { return m_active; }
    QString status() const { return m_status; }
    QString metrics() const { return m_metrics; }
    QVariantList detections() const { return m_detections; }
    qint64 resultProbeMs() const { return m_resultProbeMs; }
    qint64 resultMs() const { return m_resultMs; }
    bool resultFresh() const;
    Q_INVOKABLE void start();
    Q_INVOKABLE void stop();

public slots:
    void onFrame(const QImage &image, qint64 probeMs);
    void setFrameAvailable(bool available);

signals:
    void activeChanged();
    void statusChanged();
    void detectionsChanged();
    void metricsChanged();

private:
    void onOutput();
    void fail(const QString &message);
    void setStatus(const QString &status);
    void clearDetections();

    QProcess m_detector;
    QTimer m_watchdog;
    QElapsedTimer m_startAge;
    QElapsedTimer m_frameAge;
    QElapsedTimer m_sendAge;
    QElapsedTimer m_resultAge;
    QElapsedTimer m_rateWindow;
    QByteArray m_output;
    QVariantList m_detections;
    QString m_status = QStringLiteral("人物：未启动");
    QString m_metrics;
    bool m_active = false;
    bool m_ready = false;
    bool m_pending = false;
    bool m_frameAvailable = false;
    bool m_receivedResult = false;
    bool m_timingEnabled = false;
    qint64 m_probeMs = 0;
    qint64 m_resultProbeMs = 0;
    qint64 m_resultMs = 0;
    int m_sequence = 0;
    int m_previewCount = 0;
    int m_resultCount = 0;
    double m_previewFps = 0;
    double m_detectionHz = 0;
};

#endif
