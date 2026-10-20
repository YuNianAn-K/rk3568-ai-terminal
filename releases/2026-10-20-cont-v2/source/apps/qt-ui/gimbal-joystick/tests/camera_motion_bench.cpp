// Real camera/NPU feed ablation; fake control worker, no UART and no motion.
#include <QGuiApplication>
#include <QCamera>
#include <QCameraInfo>
#include <QCameraViewfinderSettings>
#include <QAbstractVideoSurface>
#include <QTimer>
#include <QFile>
#include <QJSEngine>
#include <QDebug>
#include "handtracker.h"
#include "persontracker.h"
#include "gimbalbridge.h"
#include "cameramonitor.h"
class Sink : public QAbstractVideoSurface {
public:
    QList<QVideoFrame::PixelFormat> supportedPixelFormats(QAbstractVideoBuffer::HandleType) const override {
        return {QVideoFrame::Format_YUYV};
    }
    bool present(const QVideoFrame &) override {return true;}
};
int main(int argc,char **argv) {
    QGuiApplication app(argc,argv);
    if(argc!=3)qFatal("mode and JS path required");
    QFile source(QString::fromLocal8Bit(argv[2]));if(!source.open(QIODevice::ReadOnly))qFatal("JS source missing");
    QString js=QString::fromUtf8(source.readAll());js.replace(".pragma library","");
    QJSEngine engine;QJSValue syntax=engine.evaluate(js);if(syntax.isError())qFatal("Qt5 JS syntax error");
    CameraMonitor monitor;if(!monitor.present())qFatal("accepted USB camera absent");
    QCameraInfo selected;
    for(const QCameraInfo &info:QCameraInfo::availableCameras())
        if(info.deviceName()==monitor.deviceId())selected=info;
    if(selected.isNull())qFatal("accepted camera not enumerated");
    qInfo()<<"CAMERA_DEVICE"<<selected.deviceName()<<selected.description();
    GimbalBridge bridge;HandTracker hand(&bridge);PersonTracker person;
    Sink sink;QCamera camera(selected);camera.setViewfinder(&sink);
    QCameraViewfinderSettings settings;settings.setResolution(640,480);settings.setPixelFormat(QVideoFrame::Format_YUYV);
    settings.setMinimumFrameRate(30);settings.setMaximumFrameRate(30);camera.setViewfinderSettings(settings);
    if(!hand.attach(&camera))qFatal("probe attach");
    int results=0;bool started=false,ready=false;QTimer end;
    end.setSingleShot(true);
    QObject::connect(&hand,&HandTracker::detectionFrame,&person,&PersonTracker::onFrame);
    QObject::connect(&hand,&HandTracker::previewReadyChanged,[&] {
        person.setFrameAvailable(hand.previewReady());
        if(hand.previewReady()&&!started) {
            started=true;hand.setPersonDetectionActive(QString::fromLocal8Bit(argv[1])=="candidate");person.start();
        }
    });
    QObject::connect(&person,&PersonTracker::statusChanged,[&] {
        if(!ready&&person.status().contains(QStringLiteral("等待画面"))) {ready=true;end.start(8000);}
    });
    QObject::connect(&person,&PersonTracker::detectionsChanged,[&] {if(person.resultMs()>0)++results;});
    QObject::connect(&end,&QTimer::timeout,[&] {person.stop();camera.stop();app.quit();});
    QTimer::singleShot(18000,&app,&QCoreApplication::quit);
    camera.start();int status=app.exec();person.stop();camera.stop();
    if(!ready||results<30)qFatal("insufficient real camera results");
    qInfo()<<"REAL_CAMERA_NPU_BENCH_PASS"<<argv[1]<<results;return status;
}
