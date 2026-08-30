QT += core dbus
QT -= gui

TARGET = connman_status_smoke
CONFIG += console
CONFIG -= app_bundle

SOURCES += \
    connman_status_smoke.cpp \
    ../connmanwificontroller.cpp

HEADERS += ../connmanwificontroller.h
INCLUDEPATH += ..
