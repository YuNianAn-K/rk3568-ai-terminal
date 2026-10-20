#!/bin/sh
set -eu

cd "$(dirname "$0")"
export QT_QPA_PLATFORM=wayland
export XDG_RUNTIME_DIR=/var/run
export WAYLAND_DISPLAY=wayland-0
exec ./gimbal-joystick
