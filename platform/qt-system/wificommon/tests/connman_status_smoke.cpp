#include <QCoreApplication>
#include <QDebug>
#include <QTimer>

#include "connmanwificontroller.h"

int main(int argc, char *argv[])
{
    QCoreApplication app(argc, argv);
    ConnmanWifiController controller;

    QTimer::singleShot(1500, &app, [&app, &controller]() {
        qInfo().noquote() << "connected=" << controller.connected()
                          << "ssid=" << controller.ssid()
                          << "strength=" << controller.strength();
        app.exit(controller.connected() && !controller.ssid().isEmpty() ? 0 : 1);
    });

    return app.exec();
}
