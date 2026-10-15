#include "previewitem.h"
#include <QGuiApplication>
#include <QImage>
#include <QPainter>
#include <QDebug>

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    PreviewItem preview;
    preview.setWidth(120);
    preview.setHeight(90);
    QImage frame(640, 480, QImage::Format_ARGB32);
    frame.fill(QColor("#4989d4"));
    preview.setFrame(frame);
    for (qreal radius : {qreal(0), qreal(26)}) {
        preview.setCornerRadius(radius);
        QImage output(120, 90, QImage::Format_ARGB32);
        output.fill(Qt::transparent);
        QPainter painter(&output);
        preview.paint(&painter);
        painter.end();
        if (output.pixelColor(60, 45) != QColor("#4989d4"))
            qFatal("Preview changed the camera image center");
        if ((radius == 0 && output.pixelColor(0, 0).alpha() != 255) ||
            (radius > 0 && output.pixelColor(0, 0).alpha() != 0))
            qFatal("Camera corner clipping failed");
    }
    qInfo() << "PASS: native Qt5 preview center preserved; default rectangular and rounded transparent corners";
    return 0;
}
