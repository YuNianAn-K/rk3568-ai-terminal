#ifndef PREVIEWITEM_H
#define PREVIEWITEM_H

#include <QImage>
#include <QQuickPaintedItem>

class PreviewItem : public QQuickPaintedItem
{
    Q_OBJECT
    Q_PROPERTY(qreal cornerRadius READ cornerRadius WRITE setCornerRadius NOTIFY cornerRadiusChanged)
public:
    explicit PreviewItem(QQuickItem *parent = nullptr);
    void paint(QPainter *painter) override;
    qreal cornerRadius() const { return m_cornerRadius; }
    void setCornerRadius(qreal radius);

signals:
    void cornerRadiusChanged();

public slots:
    void setFrame(const QImage &frame);

private:
    QImage m_frame;
    qreal m_cornerRadius = 0;
};

#endif
