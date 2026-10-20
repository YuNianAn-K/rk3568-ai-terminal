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
    bridge.press(QStringLiteral("PAN_LEFT"));
    check(waitFor([&]() { return commands().count("MANUAL PAN_LEFT ") >= 3; }),
          "held manual input repeats without recenter");
    bridge.stop();
    check(waitFor([&]() { return commands().contains("STOP\n"); }), "manual release stop");
    const int heldCount = commands().count("MANUAL ");
    QElapsedTimer released;
    released.start();
    while (released.elapsed() < 450) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
        QThread::msleep(10);
    }
    check(commands().count("MANUAL ") == heldCount, "no heartbeat after release");
    check(!commands().contains("CENTER"), "manual press never recenters");
    const QByteArray manualCommands = commands();
    QElapsedTimer clock;
    clock.start();
    auto stamp = [&]() { return clock.msecsSinceReference(); };
    bridge.personSample(.2, .3, .72, stamp(), stamp());
    check(commands() == manualCommands, "samples without explicit start ignored");
    bridge.personStart();
    check(waitFor([&]() { return bridge.status().contains(QStringLiteral("确认选中目标")); }), "person status");
    const qint64 now = stamp();
    bridge.personSample(.2, .3, .72, now - 150, now);
    check(waitFor([&]() { return commands().contains("PERSON 0.2000 0.3000 0.720 0 "); }), "real score and timing forwarded");
    const int samples = commands().count("PERSON ");
    bridge.personPause();
    check(waitFor([&]() { return commands().contains("PERSON_PAUSE\n"); }), "pause forwarded");
    bridge.personSample(.2, .3, .45, stamp(), stamp());
    check(waitFor([&]() { return commands().contains("PERSON 0.2000 0.3000 0.450 0 "); }), "weak associated sample forwarded");
    bridge.personFramingSample(.25,.33,.72,stamp(),stamp(),.5,.33);
    check(waitFor([&]() { return commands().contains("0.5000 0.3300\n"); }), "explicit framing reference forwarded");
    bridge.personFramingSample(.25,.33,.72,now-600,now,.5,.33);
    check(ended == 1, "stale result ends tracking");
    check(waitFor([&]() { return commands().contains("STOP\n"); }), "stale result requests stop");
    bridge.personSample(.2, .3, .72, stamp(), stamp());
    QThread::msleep(30);
    check(commands().count("PERSON ") == samples + 2, "no automatic restart");
    bridge.personStart();
    bridge.personSample(std::numeric_limits<double>::quiet_NaN(), .3, .72, stamp(), stamp());
    check(ended == 2, "non-finite coordinate ends tracking");
    bridge.personStart();
    bridge.personFramingSample(.25,.33,.72,stamp(),stamp(),.5,.99);
    check(ended == 3, "invalid framing reference stops tracking");
    qInfo() << "PASS: explicit start; person label; original score/timing; stale/non-finite stop; no automatic restart";
    return 0;
}
