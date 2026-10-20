#ifndef CAMERAMONITOR_H
#define CAMERAMONITOR_H

#include <QObject>
#include <QString>
#include <QTimer>

class CameraMonitor : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool present READ present NOTIFY presentChanged)
    Q_PROPERTY(QString deviceId READ deviceId NOTIFY presentChanged)

public:
    explicit CameraMonitor(QObject *parent = nullptr);
    bool present() const { return !m_deviceId.isEmpty(); }
    QString deviceId() const { return m_deviceId; }

signals:
    void presentChanged();

private:
    void refresh();

    QTimer m_timer;
    QString m_deviceId;
};

#endif
