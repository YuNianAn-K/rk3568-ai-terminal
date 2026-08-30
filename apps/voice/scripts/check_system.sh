#!/bin/bash
# RK3568 System Environment Check Script
# Usage: bash check_system.sh

echo "=========================================="
echo "RK3568 System Environment Check"
echo "=========================================="

# 1. Linux Version
echo -e "\n[1] Linux Version:"
uname -a
cat /etc/os-release 2>/dev/null || cat /etc/issue 2>/dev/null

# 2. CPU Architecture
echo -e "\n[2] CPU Architecture:"
uname -m
cat /proc/cpuinfo | head -10

# 3. Python Environment
echo -e "\n[3] Python Environment:"
python3 --version 2>/dev/null || echo "Python3 not found"
python --version 2>/dev/null || echo "Python2 not found"
pip3 --version 2>/dev/null || echo "pip3 not found"

# 4. Audio Devices
echo -e "\n[4] Audio Devices:"
aplay -l 2>/dev/null || echo "aplay not found"
arecord -l 2>/dev/null || echo "arecord not found"

# 5. ALSA Configuration
echo -e "\n[5] ALSA Configuration:"
cat /proc/asound/cards 2>/dev/null || echo "No ALSA cards found"
cat /proc/asound/pcm 2>/dev/null || echo "No PCM devices found"

# 6. Check for audio playback tools
echo -e "\n[6] Audio Playback Tools:"
which aplay 2>/dev/null && echo "aplay: available" || echo "aplay: not found"
which mpv 2>/dev/null && echo "mpv: available" || echo "mpv: not found"
which ffplay 2>/dev/null && echo "ffplay: available" || echo "ffplay: not found"
which paplay 2>/dev/null && echo "paplay: available" || echo "paplay: not found"

# 7. Check for Python audio libraries
echo -e "\n[7] Python Audio Libraries:"
python3 -c "import pyaudio" 2>/dev/null && echo "pyaudio: installed" || echo "pyaudio: not installed"
python3 -c "import sounddevice" 2>/dev/null && echo "sounddevice: installed" || echo "sounddevice: not installed"
python3 -c "import pygame" 2>/dev/null && echo "pygame: installed" || echo "pygame: not installed"

# 8. Network connectivity
echo -e "\n[8] Network Connectivity:"
ping -c 2 8.8.8.8 2>/dev/null && echo "Internet: accessible" || echo "Internet: not accessible"

# 9. Disk space
echo -e "\n[9] Disk Space:"
df -h / | tail -1

echo -e "\n=========================================="
echo "Check Complete!"
echo "=========================================="