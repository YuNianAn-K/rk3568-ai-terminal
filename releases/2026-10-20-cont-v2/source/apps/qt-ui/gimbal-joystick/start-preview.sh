#!/bin/sh
set -eu
app_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if python3 "$app_dir/show-preview.py"; then
    exit 0
fi
export GIMBAL_STANDALONE_PREVIEW=1
export PERSON_DETECTOR_BACKEND=rknn-v8-head
export PYTHONDONTWRITEBYTECODE=1
exec flock -n /var/run/gimbal-camera-ui.lock "$app_dir/start.sh"
