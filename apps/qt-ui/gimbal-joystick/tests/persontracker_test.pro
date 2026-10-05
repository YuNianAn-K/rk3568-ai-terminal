QT += core gui
QT -= widgets
CONFIG += console c++11
CONFIG -= app_bundle
TARGET = persontracker-test
SOURCES += test_persontracker.cpp ../persontracker.cpp
HEADERS += ../persontracker.h
INCLUDEPATH += ..
