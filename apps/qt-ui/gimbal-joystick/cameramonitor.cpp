#include "cameramonitor.h"

#include <QCameraInfo>
#include <QFileInfo>
#include <QDebug>

CameraMonitor::CameraMonitor(QObject *parent) : QObject(parent)
{
    connect(&m_timer, &QTimer::timeout, this, &CameraMonitor::refresh);
    m_timer.start(750);
    refresh();
}

void CameraMonitor::refresh()
{
    if (!m_deviceId.isEmpty() && QFileInfo::exists(m_deviceId))
        return;

    QString found;
    const auto cameras = QCameraInfo::availableCameras();
    for (const QCameraInfo &camera : cameras) {
        // The accepted UVC unit identifies itself as "2M: 2M" on this board.
        if (camera.description().contains(QStringLiteral("2M")) &&
            QFileInfo::exists(camera.deviceName())) {
            found = camera.deviceName();
            break;
        }
    }
    if (found == m_deviceId)
        return;
    m_deviceId = found;
    qInfo() << "UVC capture device:" << (found.isEmpty() ? "unavailable" : found);
    emit presentChanged();
}
