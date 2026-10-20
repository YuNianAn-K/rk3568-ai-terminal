#ifndef GIMBALBRIDGE_H
#define GIMBALBRIDGE_H

#include <QObject>
#include <QProcess>
#include <QString>
#include <QTimer>

class GimbalBridge : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)
    Q_PROPERTY(bool trackCapable READ trackCapable NOTIFY trackCapableChanged)
    Q_PROPERTY(bool positionReady READ positionReady NOTIFY positionReadyChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString detail READ detail NOTIFY detailChanged)
    Q_PROPERTY(bool personArmed READ personArmed NOTIFY personArmedChanged)

public:
    explicit GimbalBridge(QObject *parent = nullptr);
    ~GimbalBridge() override;

    bool connected() const { return m_connected; }
    bool trackCapable() const { return m_trackCapable; }
    bool positionReady() const { return m_positionReady; }
    QString status() const { return m_status; }
    QString detail() const { return m_detail; }
    bool personArmed() const { return m_personArmed; }

    Q_INVOKABLE void press(const QString &direction);
    Q_INVOKABLE void stop();
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void center();
    Q_INVOKABLE void personStart(const QString &requestId = QString());
    Q_INVOKABLE void personPause();
    void requestStop(const QString &requestId);
    Q_INVOKABLE void personSample(double x, double y, double score,
                                  qint64 probeMs, qint64 resultMs);
    void trackStart();
    void trackStop();
    void trackSample(double x, double y, double score, bool ambiguous,
                     qint64 probeMs = 0, qint64 resultMs = 0);

signals:
    void connectedChanged();
    void trackCapableChanged();
    void positionReadyChanged();
    void trackingEnded();
    void statusChanged();
    void detailChanged();
    void personArmedChanged();
    void controlAck(const QString &requestId, const QString &state);

private:
    void send(const QByteArray &line);
    void setConnected(bool connected);
    void setStatus(const QString &status);
    void setDetail(const QString &detail);
    void processOutput();
    void setPersonArmed(bool armed);

    QProcess m_worker;
    QTimer m_manualTimer;
    QByteArray m_buffer;
    QString m_direction;
    QString m_status;
    QString m_detail;
    bool m_connected = false;
    bool m_trackCapable = false;
    bool m_positionReady = false;
    bool m_failed = false;
    bool m_personTracking = false;
    bool m_personArmed = false;
    QString m_personRequestId;
};

#endif
