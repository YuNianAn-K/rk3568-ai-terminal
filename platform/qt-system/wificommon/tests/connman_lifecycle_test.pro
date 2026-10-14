QT += core dbus
QT -= gui

TARGET = connman_lifecycle_test
CONFIG += console
CONFIG -= app_bundle

SOURCES += \
    connman_lifecycle_test.cpp \
    ../connmanwificontroller.cpp

HEADERS += ../connmanwificontroller.h
INCLUDEPATH += ..
