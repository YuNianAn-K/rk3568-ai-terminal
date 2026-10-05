#include <QCoreApplication>
#include <QDebug>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QThread>
#include <functional>
#include "persontracker.h"

static bool waitFor(const std::function<bool()> &condition, int timeout = 2500)
{
    QElapsedTimer timer;
    timer.start();
    while (!condition() && timer.elapsed() < timeout) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
        QThread::msleep(10);
    }
    return condition();
}

static void check(bool condition, const char *message)
{
    if (!condition)
        qFatal("FAIL: %s", message);
}

static qint64 stamp()
{
    QElapsedTimer clock;
    clock.start();
    return clock.msecsSinceReference();
}

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    QImage image(640, 480, QImage::Format_RGB32);
    image.fill(Qt::red);
    PersonTracker tracker;
    tracker.start();
    check(!tracker.active(), "unavailable video must not start a detector");
    tracker.setFrameAvailable(true);
    qputenv("PERSON_TEST_MODE", "ok");
    tracker.start();
    check(waitFor([&]() { return tracker.status().contains(QStringLiteral("等待画面")); }), "ready event");
    tracker.onFrame(image, stamp());
    tracker.onFrame(image, stamp()); // Must be discarded while a result is pending.
    check(waitFor([&]() { return tracker.detections().size() == 1; }), "RGB frame result");
    check(tracker.detections().first().toMap().value("left").toDouble() == .1, "normalized box decoding");
    check(tracker.resultProbeMs() > 0 && tracker.resultMs() >= tracker.resultProbeMs(),
          "published boxes carry their own capture/result timestamps");
    check(tracker.active(), "detector remains active after a valid result");
    check(tracker.resultFresh(), "a current selected result permits a start request");
    QThread::msleep(510);
    check(!tracker.resultFresh(), "an old displayed result cannot permit a start request");
    tracker.setFrameAvailable(false);
    check(!tracker.active() && tracker.detections().isEmpty(), "camera loss clears boxes and stops process");
    check(!tracker.resultFresh(), "camera loss prevents a start request");

    tracker.setFrameAvailable(true);
    qputenv("PERSON_TEST_MODE", "bad_seq");
    tracker.start();
    check(waitFor([&]() { return tracker.status().contains(QStringLiteral("等待画面")); }), "restart after stop");
    tracker.onFrame(image, stamp());
    check(waitFor([&]() { return !tracker.active(); }), "out-of-order result stops process");
    check(tracker.detections().isEmpty(), "invalid output never creates a box");

    qputenv("PERSON_TEST_MODE", "late");
    tracker.start();
    check(waitFor([&]() { return tracker.status().contains(QStringLiteral("等待画面")); }), "late test ready");
    tracker.onFrame(image, stamp());
    check(waitFor([&]() { return tracker.status().contains(QStringLiteral("结果过期")); }), "stale result rejected");
    check(tracker.detections().isEmpty(), "stale result never creates a box");
    tracker.stop();

    qputenv("PERSON_TEST_MODE", "crash");
    tracker.start();
    check(waitFor([&]() { return !tracker.active(); }), "process crash visible");
    check(tracker.detections().isEmpty(), "crash leaves no boxes");
    qunsetenv("PERSON_TEST_MODE");
    qInfo() << "PASS: RGB pipe; pending frame discard; camera loss; restart; bad sequence; stale result; detector crash";
    return 0;
}
