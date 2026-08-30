#ifndef VOICEBRIDGE_H
#define VOICEBRIDGE_H

#include <QByteArray>
#include <QJsonObject>
#include <QLocalSocket>
#include <QObject>
#include <QString>
#include <QTimer>
#include <QVariantMap>

class VoiceBridge : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)
    Q_PROPERTY(QString state READ state NOTIFY stateChanged)
    Q_PROPERTY(QString message READ message NOTIFY messageChanged)
    Q_PROPERTY(QString transcript READ transcript NOTIFY transcriptChanged)
    Q_PROPERTY(QString answer READ answer NOTIFY answerChanged)
    Q_PROPERTY(QString errorMessage READ errorMessage NOTIFY errorMessageChanged)
    Q_PROPERTY(QVariantMap timings READ timings NOTIFY diagnosticsChanged)
    Q_PROPERTY(QVariantMap diagnostics READ diagnostics NOTIFY diagnosticsChanged)
    Q_PROPERTY(int roundId READ roundId NOTIFY diagnosticsChanged)

public:
    explicit VoiceBridge(QObject *parent = nullptr);
    ~VoiceBridge() override;

    bool connected() const;
    QString state() const;
    QString message() const;
    QString transcript() const;
    QString answer() const;
    QString errorMessage() const;
    QVariantMap timings() const;
    QVariantMap diagnostics() const;
    int roundId() const;

    Q_INVOKABLE void startRecording();
    Q_INVOKABLE void stopRecording();
    Q_INVOKABLE void cancel();
    Q_INVOKABLE void reconnectService();
    Q_INVOKABLE void refreshStatus();

signals:
    void connectedChanged();
    void stateChanged();
    void messageChanged();
    void transcriptChanged();
    void answerChanged();
    void errorMessageChanged();
    void diagnosticsChanged();

private slots:
    void connectService();
    void onConnected();
    void onDisconnected();
    void onReadyRead();
    void onSocketError(QLocalSocket::LocalSocketError error);

private:
    void sendCommand(const QString &command);
    void processMessage(const QByteArray &line);
    void setConnected(bool connected);
    void setState(const QString &state);
    void setMessage(const QString &message);
    void setTranscript(const QString &transcript);
    void setAnswer(const QString &answer);
    void setErrorMessage(const QString &errorMessage);
    void updateDiagnostics(const QJsonObject &object);

    QLocalSocket m_socket;
    QTimer m_reconnectTimer;
    QByteArray m_buffer;
    bool m_connected = false;
    QString m_state = QStringLiteral("offline");
    QString m_message = QStringLiteral("正在连接语音服务");
    QString m_transcript;
    QString m_answer;
    QString m_errorMessage;
    QVariantMap m_timings;
    QVariantMap m_diagnostics;
    int m_roundId = 0;
};

#endif // VOICEBRIDGE_H
