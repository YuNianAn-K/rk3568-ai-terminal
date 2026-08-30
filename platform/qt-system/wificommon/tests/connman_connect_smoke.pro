QT += core dbus
QT -= gui

TARGET = connman_connect_smoke
CONFIG += console
CONFIG -= app_bundle

SOURCES += \
    connman_connect_smoke.cpp \
    ../connmanwificontroller.cpp

HEADERS += ../connmanwificontroller.h
INCLUDEPATH += ..
