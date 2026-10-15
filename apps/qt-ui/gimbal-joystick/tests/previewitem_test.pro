QT += quick
CONFIG += console c++11
CONFIG -= app_bundle
TARGET = previewitem-test
SOURCES += test_previewitem.cpp ../previewitem.cpp
HEADERS += ../previewitem.h
INCLUDEPATH += ..
