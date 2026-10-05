#include "previewitem.h"

#include <QPainter>

PreviewItem::PreviewItem(QQuickItem *parent) : QQuickPaintedItem(parent)
{
}

void PreviewItem::setFrame(const QImage &frame)
{
    m_frame = frame;
    update();
}

void PreviewItem::paint(QPainter *painter)
{
    painter->fillRect(boundingRect(), Qt::black);
    if (m_frame.isNull())
        return;
    QSizeF size = m_frame.size();
    size.scale(boundingRect().size(), Qt::KeepAspectRatio);
    const QRectF target((width() - size.width()) / 2,
                        (height() - size.height()) / 2,
                        size.width(), size.height());
    painter->drawImage(target, m_frame);
}
