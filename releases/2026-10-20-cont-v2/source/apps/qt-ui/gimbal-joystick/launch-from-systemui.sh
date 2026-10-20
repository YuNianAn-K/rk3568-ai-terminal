#!/bin/sh
set -eu

# A second tap must not open a second camera or UART owner.
exec flock -n /var/run/gimbal-camera-ui.lock \
    /opt/ui/gimbal-joystick/start.sh >>/tmp/gimbal-camera-launch.log 2>&1
