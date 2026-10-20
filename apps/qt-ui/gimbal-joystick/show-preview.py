"""Raise an existing matching preview; never issues a hardware command."""
from pathlib import Path
import socket,sys
release=Path(__file__).with_name('release-id.txt').read_text().strip()
try:
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as channel:
        channel.settimeout(1)
        channel.connect('/tmp/gimbal-preview-window.sock')
        channel.sendall(('SHOW '+release+'\n').encode())
        with channel.makefile('rb') as stream:reply=stream.readline(128).decode().strip()
    sys.exit(0 if reply==release else 1)
except (OSError,UnicodeError):
    sys.exit(1)
