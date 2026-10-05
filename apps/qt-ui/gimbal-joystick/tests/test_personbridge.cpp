#include <QCoreApplication>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QFile>
#include <QTemporaryDir>
#include <QThread>
#include <QDebug>
#include <functional>
#include <limits>
#include "gimbalbridge.h"

static bool waitFor(const std::function<bool()> &condition)
{
    QElapsedTimer timer;
    timer.start();
    while (!condition() && timer.elapsed() < 2000) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
        QThread::msleep(10);
    }
    return condition();
}

static void check(bool value, const char *message)
{
    if (!value) qFatal("FAIL: %s", message);
}

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    QTemporaryDir temp;
    check(temp.isValid(), "temporary log directory");
    const QString path = temp.filePath("commands.txt");
    qputenv("PERSON_BRIDGE_TEST_LOG", path.toUtf8());
    auto commands = [&]() {
        QFile log(path);
        return log.open(QIODevice::ReadOnly) ? log.readAll() : QByteArray();
    };
    GimbalBridge bridge;
    int ended = 0;
    QObject::connect(&bridge, &GimbalBridge::trackingEnded, [&]() { ++ended; });
    check(waitFor([&]() { return bridge.connected(); }), "worker ready");
    QElapsedTimer clock;
    clock.start();
    auto stamp = [&]() { return clock.msecsSinceReference(); };
    bridge.personSample(.2, .3, .72, stamp(), stamp());
    check(commands().isEmpty(), "samples without explicit start ignored");
    bridge.personStart();
    check(waitFor([&]() { return bridge.status().contains(QStringLiteral("确认选中目标")); }), "person status");
    const qint64 now = stamp();
    bridge.personSample(.2, .3, .72, now - 150, now);
    check(waitFor([&]() { return commands().contains("PERSON 0.2000 0.3000 0.720 0 "); }), "real score and timing forwarded");
    const int samples = commands().count("PERSON ");
    bridge.personSample(.2, .3, .72, now - 600, now);
    check(ended == 1, "stale result ends tracking");
    check(waitFor([&]() { return commands().contains("STOP\n"); }), "stale result requests stop");
    bridge.personSample(.2, .3, .72, stamp(), stamp());
    QThread::msleep(30);
    check(commands().count("PERSON ") == samples, "no automatic restart");
    bridge.personStart();
    bridge.personSample(std::numeric_limits<double>::quiet_NaN(), .3, .72, stamp(), stamp());
    check(ended == 2, "non-finite coordinate ends tracking");
    qInfo() << "PASS: explicit start; person label; original score/timing; stale/non-finite stop; no automatic restart";
    return 0;
}
