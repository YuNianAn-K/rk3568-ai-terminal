QT += quick network remoteobjects

TARGET = aivoice_lifecycle_test

SOURCES += \
        lifecycle_app_main.cpp \
        ../voicebridge.cpp \
        ../../client/systemuicommonapiclient.cpp \
        ../../client/volumemonitor.cpp

HEADERS += \
        ../voicebridge.h \
        ../../client/systemuicommonapiclient.h \
        ../../client/volumemonitor.h

RESOURCES += \
        ../qml.qrc \
        ../../client/common.qrc

REPC_REPLICA += ../../Repcs/systemuicommonapi.rep
INCLUDEPATH += ../ ../../client
