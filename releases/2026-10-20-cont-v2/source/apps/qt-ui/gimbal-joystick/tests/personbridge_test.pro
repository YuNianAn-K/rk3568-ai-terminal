QT += core
QT -= gui
CONFIG += console c++11
CONFIG -= app_bundle
TARGET = personbridge-test
SOURCES += test_personbridge.cpp ../gimbalbridge.cpp
HEADERS += ../gimbalbridge.h
INCLUDEPATH += ..
