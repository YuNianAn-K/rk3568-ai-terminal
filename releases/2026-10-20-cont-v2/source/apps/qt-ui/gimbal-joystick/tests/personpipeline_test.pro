QT += core gui
QT -= widgets
CONFIG += console c++11
CONFIG -= app_bundle
TARGET = personpipeline-test
SOURCES += test_personpipeline.cpp ../persontracker.cpp
HEADERS += ../persontracker.h
INCLUDEPATH += ..
