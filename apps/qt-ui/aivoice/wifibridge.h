#ifndef WIFIBRIDGE_H
#define WIFIBRIDGE_H

#include <QProcess>
#include <QObject>
#include <QString>
#include <QStringList>
#include <QVariantMap>
#include <QTimer>
#include <QVariantList>

class WifiBridge : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool online READ online NOTIFY statusChanged)
    Q_PROPERTY(bool connected READ connected NOTIFY statusChanged)
    Q_PROPERTY(QString ssid READ ssid NOTIFY statusChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString errorMessage READ errorMessage NOTIFY errorMessageChanged)
    Q_PROPERTY(QVariantList networks READ networks NOTIFY networksChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(bool connecting READ connecting NOTIFY connectingChanged)

public:
    explicit WifiBridge(QObject *parent = nullptr);
    ~WifiBridge() override;

    bool online() const;
    bool connected() const;
    QString ssid() const;
    QString status() const;
    QString errorMessage() const;
    QVariantList networks() const;
    bool busy() const;
    bool connecting() const;

    Q_INVOKABLE void refresh();
    Q_INVOKABLE void scan();
    Q_INVOKABLE void connectNetwork(const QString &service,
                                    const QString &password);

signals:
    void statusChanged();
    void errorMessageChanged();
    void networksChanged();
    void busyChanged();
    void connectingChanged();

private slots:
    void onCommandReadyRead();
    void onCommandFinished(int exitCode, QProcess::ExitStatus exitStatus);
    void onConnectStarted();
    void onConnectReadyRead();
    void onConnectFinished(int exitCode, QProcess::ExitStatus exitStatus);
    void onConnectTimeout();

private:
    enum class Operation { None, State, Services, Scan };

    void startCommand(const QStringList &arguments, Operation operation);
    void parseState(const QByteArray &output);
    void parseServices(const QByteArray &output);
    void setErrorMessage(const QString &message);
    void setBusy(bool busy);
    void setConnecting(bool connecting);
    void finishServiceCommand();

    QProcess m_commandProcess;
    QProcess m_connectProcess;
    QTimer m_connectTimeout;
    Operation m_operation = Operation::None;
    QByteArray m_commandOutput;
    QByteArray m_connectOutput;
    QVariantList m_networks;
    bool m_online = false;
    bool m_connected = false;
    bool m_busy = false;
    bool m_connecting = false;
    bool m_passphraseSent = false;
    QString m_ssid;
    QString m_status = QStringLiteral("正在检查 Wi-Fi");
    QString m_errorMessage;
    QString m_connectService;
    QString m_connectPassword;
};

#endif // WIFIBRIDGE_H
