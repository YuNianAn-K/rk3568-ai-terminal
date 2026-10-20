"""Opt-in Windows user-scoped DPAPI storage; never write plaintext credentials."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import tempfile


def protect_bytes(data, entropy, *, decrypt=False):
    if os.name != "nt":
        raise OSError("Windows credential protection required")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    source_buffer = ctypes.create_string_buffer(data)
    entropy_buffer = ctypes.create_string_buffer(entropy)
    source = Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    extra = Blob(len(entropy), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32.dll", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        # No LOCAL_MACHINE flag: only the current Windows identity can unlock it.
        if not function(ctypes.byref(source), None, ctypes.byref(extra), None, None,
                        0x1, ctypes.byref(output)):  # CRYPTPROTECT_UI_FORBIDDEN
            raise OSError("Windows credential protection failed")
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.memset(source_buffer, 0, ctypes.sizeof(source_buffer))
        if output.data:
            ctypes.memset(output.data, 0, output.size)
            kernel.LocalFree(output.data)


class CredentialStore:
    def __init__(self, path, config):
        self.path = Path(path)
        self.binding = {key: config[key] for key in ("instance_id", "public_ip")}
        self.entropy = hashlib.sha256(("ecs-traffic-monitor:v1:" + json.dumps(
            self.binding, sort_keys=True)).encode()).digest()

    def exists(self):
        return self.path.is_file()

    def save(self, credentials):
        if set(credentials) != {"access_id", "secret", "token"} or credentials["token"]:
            raise ValueError("Temporary credentials cannot be remembered")
        if any(not isinstance(value, str) or len(value) > 2048 for value in credentials.values()):
            raise ValueError("Invalid credentials")
        if not credentials["access_id"] or not credentials["secret"]:
            raise ValueError("Missing credentials")
        payload = json.dumps({"version": 1, "binding": self.binding,
                              "credentials": credentials}).encode()
        # Encrypt before creating a file; failure never falls back to plaintext.
        encrypted = protect_bytes(payload, self.entropy)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".credentials-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def load(self):
        with self.path.open("rb") as stream:
            encrypted = stream.read(65537)
        if not encrypted or len(encrypted) > 65536:
            raise ValueError("Invalid credential file")
        payload = json.loads(protect_bytes(encrypted, self.entropy, decrypt=True))
        if payload.get("version") != 1 or payload.get("binding") != self.binding:
            raise ValueError("Credential target mismatch")
        credentials = payload["credentials"]
        if not isinstance(credentials, dict) or set(credentials) != {"access_id", "secret", "token"}:
            raise ValueError("Invalid credential file")
        if any(not isinstance(v, str) or len(v) > 2048 for v in credentials.values()):
            raise ValueError("Invalid credential file")
        if not credentials["access_id"] or not credentials["secret"] or credentials["token"]:
            raise ValueError("Invalid remembered credentials")
        return credentials

    def forget(self):
        self.path.unlink(missing_ok=True)
