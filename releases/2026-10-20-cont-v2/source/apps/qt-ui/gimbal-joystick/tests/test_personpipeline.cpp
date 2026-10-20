#include <QCoreApplication>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QThread>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>
#include <QDebug>
#include <functional>
#include "persontracker.h"

static qint64 stamp() { QElapsedTimer t; t.start(); return t.msecsSinceReference(); }
static void check(bool c, const char *s) { if (!c) qFatal("FAIL: %s", s); }
static bool waitFor(const std::function<bool()> &c, int timeout=2000) {
    QElapsedTimer t; t.start();
    while (!c() && t.elapsed()<timeout) { QCoreApplication::processEvents(QEventLoop::AllEvents,2); QThread::msleep(1); }
    return c();
}
static void spin(int ms) { const qint64 end=stamp()+ms; waitFor([&] { return stamp()>=end; },ms+100); }
static QList<int> audit(const QString &p) {
    QFile f(p); if (!f.open(QIODevice::ReadOnly)) return {};
    QList<int> ids; for (const auto &line:f.readAll().split('\n'))
        if (!line.isEmpty()) ids.append(QJsonDocument::fromJson(line).object().value("id").toInt());
    return ids;
}
static QImage image(int id) { QImage im(640,480,QImage::Format_RGB32); im.fill(QColor(255,id,0)); return im; }
static void ready(PersonTracker &t, const QString &path, const char *delay=".18") {
    QFile::remove(path); qputenv("PERSON_TEST_AUDIT",path.toUtf8());qputenv("PERSON_TEST_DELAY",delay);
    qputenv("PERSON_TEST_MODE","pipeline"); t.setFrameAvailable(true);t.start();
    check(waitFor([&] { return t.status().contains(QStringLiteral("等待画面")); }),"ready");
}
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);QTemporaryDir dir;check(dir.isValid(),"temporary audit directory");
    PersonTracker t;QString p=dir.filePath("received.jsonl");int results=0;
    QObject::connect(&t,&PersonTracker::detectionsChanged,[&] { if (!t.detections().isEmpty()) ++results; });
    ready(t,p);t.onFrame(image(1),stamp());spin(100);t.onFrame(image(2),stamp());spin(40);
    const qint64 third=stamp();t.onFrame(image(3),third);
    check(waitFor([&] { return results>=2; }),"latest queued image gets a result");
    check(audit(p)==QList<int>({1,3}),"intermediate image discarded, newest image used");
    check(t.resultProbeMs()==third,"queued result retains capture timestamp");spin(120);
    check(audit(p)==QList<int>({1,3}),"a captured image is never inferred twice");t.stop();

    ready(t,p);t.onFrame(image(1),stamp());spin(40);t.onFrame(image(2),stamp());spin(230);
    check(audit(p)==QList<int>({1}),"queued images older than 80 ms discarded");
    t.onFrame(image(3),stamp());check(waitFor([&] { return audit(p).size()==2; }),"new image resumes after stale cache discard");
    check(audit(p)==QList<int>({1,3}),"stale frame not resurrected");t.stop();

    ready(t,p);const qint64 first=stamp();t.onFrame(image(1),first);
    t.onFrame(image(2),first);t.onFrame(image(3),first-1);t.onFrame(image(4),stamp()+100);t.onFrame(image(5),stamp()-100);spin(230);
    check(audit(p)==QList<int>({1}),"duplicate, old and future capture timestamps rejected");t.stop();

    ready(t,p);t.onFrame(image(1),stamp());spin(100);t.onFrame(image(2),stamp());t.stop();spin(220);
    check(audit(p)==QList<int>({1})&&!t.active()&&t.detections().isEmpty(),"stop cancels pending cache");

    ready(t,p,".02");t.onFrame(image(1),stamp());spin(35);t.onFrame(image(2),stamp());spin(15);t.stop();spin(110);
    check(audit(p)==QList<int>({1}),"stop cancels rate-limit dispatch timer");
    ready(t,p,".02");spin(120);check(audit(p).isEmpty(),"restart cannot reuse previous session cache");
    const qint64 last=stamp();t.onFrame(image(3),last);check(waitFor([&] { return t.resultProbeMs()==last; }),"restart consumes fresh frame");
    spin(510);check(!t.resultFresh(),"original 500 ms result freshness retained");t.stop();

    ready(t,p,".02");t.onFrame(image(1),stamp());spin(35);t.onFrame(image(2),stamp());t.setFrameAvailable(false);spin(120);
    check(audit(p)==QList<int>({1})&&!t.active(),"camera loss cancels timer/cache");
    qunsetenv("PERSON_TEST_AUDIT");qunsetenv("PERSON_TEST_MODE");qunsetenv("PERSON_TEST_DELAY");
    qInfo()<<"PASS: newest only; no replay; capture timestamps; 80ms discard; stop/timer/camera cancellation; restart; 500ms freshness";
    return 0;
}
