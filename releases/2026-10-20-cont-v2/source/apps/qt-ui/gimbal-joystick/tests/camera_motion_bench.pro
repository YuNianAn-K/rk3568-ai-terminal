QT += core gui multimedia qml
CONFIG += console c++11
CONFIG -= app_bundle
TARGET = camera-motion-bench
SOURCES += camera_motion_bench.cpp ../persontracker.cpp ../handtracker.cpp ../gimbalbridge.cpp ../cameramonitor.cpp
HEADERS += ../persontracker.h ../handtracker.h ../gimbalbridge.h ../cameramonitor.h
INCLUDEPATH += ..
