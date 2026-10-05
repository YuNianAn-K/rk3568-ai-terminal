QT += core network
QT -= gui
CONFIG += console c++11
CONFIG -= app_bundle
TARGET = trackingcontrol-test
SOURCES += test_trackingcontrol.cpp ../trackingcontrol.cpp ../gimbalbridge.cpp
HEADERS += ../trackingcontrol.h ../gimbalbridge.h
INCLUDEPATH += ..
