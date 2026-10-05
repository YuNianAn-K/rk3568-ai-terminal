QT += core network testlib
CONFIG += testcase console c++11
CONFIG -= app_bundle
TARGET = voicebridge_test
SOURCES += test_voicebridge.cpp ../voicebridge.cpp
HEADERS += ../voicebridge.h
