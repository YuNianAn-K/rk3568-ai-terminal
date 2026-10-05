#ifndef PREVIEWITEM_H
#define PREVIEWITEM_H

#include <QImage>
#include <QQuickPaintedItem>

class PreviewItem : public QQuickPaintedItem
{
    Q_OBJECT
public:
    explicit PreviewItem(QQuickItem *parent = nullptr);
    void paint(QPainter *painter) override;

public slots:
    void setFrame(const QImage &frame);

private:
    QImage m_frame;
};

#endif
