#include <QCoreApplication>
#include <QDebug>
#include <QTimer>

#include "connmanwificontroller.h"

int main(int argc, char *argv[])
{
    QCoreApplication app(argc, argv);
    if (argc != 2) {
        qCritical() << "service id required";
        return 2;
    }

    ConnmanWifiController controller;
    QObject::connect(&controller, &ConnmanWifiController::connectionSucceeded,
                     &app, [&app](const QString &ssid) {
        qInfo().noquote() << "connect_success ssid_utf8="
                          << QString::fromLatin1(ssid.toUtf8().toHex());
        app.exit(0);
    });
    QObject::connect(&controller, &ConnmanWifiController::connectionFailed,
                     &app, [&app](const QString &message) {
        qCritical().noquote() << "connect_failed" << message;
        app.exit(1);
    });

    QTimer::singleShot(300, &app, [&controller, argv]() {
        controller.connectService(QString::fromLocal8Bit(argv[1]),
                                  QStringLiteral("current"), QString());
    });
    QTimer::singleShot(5000, &app, [&app]() { app.exit(3); });
    return app.exec();
}
