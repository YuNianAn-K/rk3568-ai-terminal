QT += quick multimedia remoteobjects network
CONFIG += c++11

TARGET = gimbal-joystick
SOURCES += main.cpp gimbalbridge.cpp cameramonitor.cpp handtracker.cpp previewitem.cpp persontracker.cpp trackingcontrol.cpp ../aivoice/voicebridge.cpp
HEADERS += gimbalbridge.h cameramonitor.h handtracker.h previewitem.h persontracker.h trackingcontrol.h ../aivoice/voicebridge.h
INCLUDEPATH += ../aivoice
RESOURCES += qml.qrc

SOURCES += ../../../platform/qt-system/client/systemuicommonapiclient.cpp
HEADERS += ../../../platform/qt-system/client/systemuicommonapiclient.h
INCLUDEPATH += ../../../platform/qt-system/client
REPC_REPLICA += systemuicommonapi.rep
