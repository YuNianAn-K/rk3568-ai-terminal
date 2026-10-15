#include "previewitem.h"

#include <QPainter>
#include <QPainterPath>

PreviewItem::PreviewItem(QQuickItem *parent) : QQuickPaintedItem(parent)
{
}

void PreviewItem::setFrame(const QImage &frame)
{
    m_frame = frame;
    update();
}

void PreviewItem::setCornerRadius(qreal radius)
{
    radius = qMax(qreal(0), radius);
    if (qFuzzyCompare(m_cornerRadius, radius))
        return;
    m_cornerRadius = radius;
    update();
    emit cornerRadiusChanged();
}

void PreviewItem::paint(QPainter *painter)
{
    painter->save();
    if (m_cornerRadius > 0) {
        QPainterPath boundary;
        boundary.addRoundedRect(boundingRect(), m_cornerRadius, m_cornerRadius);
        painter->setRenderHint(QPainter::Antialiasing);
        painter->setClipPath(boundary);
    }
    painter->fillRect(boundingRect(), Qt::black);
    if (!m_frame.isNull()) {
        QSizeF size = m_frame.size();
        size.scale(boundingRect().size(), Qt::KeepAspectRatio);
        const QRectF target((width() - size.width()) / 2,
                            (height() - size.height()) / 2,
                            size.width(), size.height());
        painter->drawImage(target, m_frame);
    }
    painter->restore();
}
