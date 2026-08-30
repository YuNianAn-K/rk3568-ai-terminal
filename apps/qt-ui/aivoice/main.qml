import QtQuick 2.12
import QtQuick.Window 2.12
import com.alientek.qmlcomponents 1.0

Window {
    id: appWindow
    visible: true
    width: Screen.desktopAvailableWidth
    height: Screen.desktopAvailableHeight
    x: 0
    y: 0
    color: "transparent"
    flags: Qt.FramelessWindowHint

    SystemUICommonApiClient {
        id: systemUiClient
        appName: "aivoice"

        onActionCommand: {
            if (cmd === SystemUICommonApiClient.Show) {
                appWindow.flags = Qt.FramelessWindowHint
                appMainBody.visible = false
                appWindow.requestActivate()
                systemUiClient.askSystemUItohideOrShow(SystemUICommonApiClient.Hide)
            }

            if (cmd === SystemUICommonApiClient.Quit)
                Qt.quit()
        }
    }

    AppMainBody {
        id: appMainBody
        anchors.fill: parent
        visible: false
    }


    Common {
        id: common
        m_appMainBody: appMainBody
        window: appWindow

        Connections {
            target: systemUiClient

            function onAppAppPropertyChanged(iconX, iconY, iconWidth,
                                              iconHeight, iconPath,
                                              callType, currentPage) {
                appMainBody.grabToImage(function(result) {
                    common.whenAppIsActive(iconX, iconY, iconWidth,
                                           iconHeight, iconPath, result.url,
                                           callType, currentPage)
                })
            }
        }

        onShowAppMainBody: {
            appMainBody.visible = show
        }

        onBackToSystemUi: {
            appMainBody.resetInteraction()

            systemUiClient.askSystemUItohideOrShow(SystemUICommonApiClient.Show)
        }

        onAppStateImageChange: {
            systemUiClient.sendVariantToServer(SystemUICommonApiClient.Image,
                                               image)
        }
    }
}
