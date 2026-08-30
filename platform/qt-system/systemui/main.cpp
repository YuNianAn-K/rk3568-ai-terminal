#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QTextCodec>
#include <QQmlContext>
#include <QFile>
#include "apklistmodel.h"
#include "applistmodel.h"
#include "appstateimage.h"
#include "systemuicommonapiserver.h"
#include "launchintent.h"
#include "connmanwificontroller.h"
#include <QScreen>

int main(int argc, char *argv[])
{
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    QCoreApplication::setAttribute(Qt::AA_EnableHighDpiScaling);
#endif
    QGuiApplication app(argc, argv);
    qputenv("QT_QUICK_BACKEND", "");
    QTextCodec::setCodecForLocale(QTextCodec::codecForName("UTF-8"));

    QLocale locale(QLocale::Chinese);
    QLocale::setDefault(locale);

    QString hostName;
    QFile file("/etc/hostname");
    if (file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        hostName =  file.readLine().simplified();
        file.close();
        if (hostName == "ATK-DLRK3568") {
            }
    }

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("appCurrtentDir", QCoreApplication::applicationDirPath());
    engine.rootContext()->setContextProperty("hostName", hostName);
    qmlRegisterType<ApkListModel>("com.alientek.qmlcomponents", 1, 0, "ApkListModel");
    qmlRegisterType<AppListModel>("com.alientek.qmlcomponents", 1, 0, "AppListModel");
    qmlRegisterType<AppStateImage>("com.alientek.qmlcomponents", 1, 0, "AppStateImage");
    qmlRegisterType<SystemUICommonApiServer>("com.alientek.qmlcomponents", 1, 0, "SystemUICommonApiServer");
    qmlRegisterType<ConnmanWifiController>("com.alientek.wifi", 1, 0,
                                           "ConnmanWifiController");
    const QUrl url(QStringLiteral("qrc:/main.qml"));
    QObject::connect(
                &engine,
                &QQmlApplicationEngine::objectCreated,
                &app,
                [url](QObject *obj, const QUrl &objUrl) {
        if (!obj && url == objUrl)
            QCoreApplication::exit(-1);
    },
    Qt::QueuedConnection);
    engine.load(url);

    return app.exec();
}
