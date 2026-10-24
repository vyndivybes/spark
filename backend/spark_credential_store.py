"""User-scoped secret storage for SPARK integrations.

Secrets are protected with Windows DPAPI in the current user's context and
written under ``%LOCALAPPDATA%\\SPARK\\credentials``, outside the Git checkout.
Only the same Windows user on this machine can decrypt them. Nothing here is
ever written to the messaging SQLite database or printed to a log.

The protector is injectable so tests can exercise storage logic without
touching the real credential directory or the operating-system DPAPI state.
"""
from __future__ import annotations

import base64
import ctypes
import os
import re
import sys
from ctypes import wintypes
from pathlib import Path

MAGIC = b"SPARK-DPAPI-1\n"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_SECRET_NAME = re.compile(r"[a-z0-9_]{1,64}")


class CredentialError(ValueError):
    """Credential storage could not complete safely."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buffer = ctypes.create_string_buffer(bytes(data), len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _dpapi_protect(data: bytes) -> bytes:
    if sys.platform != "win32":
        raise CredentialError("Windows DPAPI credential storage is unavailable on this platform.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    source, source_buffer = _blob(data)
    output = _DataBlob()
    if not crypt32.CryptProtectData(ctypes.byref(source), "SPARK integration credential",
                                    None, None, None, _CRYPTPROTECT_UI_FORBIDDEN,
                                    ctypes.byref(output)):
        raise CredentialError("Windows DPAPI could not protect this credential.")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)
        del source_buffer


def _dpapi_unprotect(blob: bytes) -> bytes:
    if sys.platform != "win32":
        raise CredentialError("Windows DPAPI credential storage is unavailable on this platform.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    source, source_buffer = _blob(blob)
    description = wintypes.LPWSTR()
    output = _DataBlob()
    if not crypt32.CryptUnprotectData(ctypes.byref(source), ctypes.byref(description),
                                      None, None, None, _CRYPTPROTECT_UI_FORBIDDEN,
                                      ctypes.byref(output)):
        raise CredentialError("Windows DPAPI could not decrypt this credential for the current user.")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        if description:
            kernel32.LocalFree(description)
        kernel32.LocalFree(output.pbData)
        del source_buffer


def default_credential_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".spark")
    return Path(base) / "SPARK" / "credentials"


class CredentialStore:
    """Small named-secret store backed by DPAPI by default."""

    def __init__(self, directory=None, *, protector=None, unprotector=None):
        self.directory = Path(directory) if directory is not None else default_credential_dir()
        self._protector = protector or _dpapi_protect
        self._unprotector = unprotector or _dpapi_unprotect

    def _path(self, name):
        if not isinstance(name, str) or not _SECRET_NAME.fullmatch(name):
            raise CredentialError("Credential names are short lowercase tokens.")
        return self.directory / f"{name}.bin"

    def save(self, name: str, secret: str) -> Path:
        if not isinstance(secret, str) or not secret:
            raise CredentialError("A non-empty secret is required.")
        path = self._path(name)
        if self.directory.is_symlink() or path.is_symlink():
            raise CredentialError("Linked credential storage is prohibited.")
        self.directory.mkdir(parents=True, exist_ok=True)
        protected = self._protector(secret.encode("utf-8"))
        payload = MAGIC + base64.b64encode(protected)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        try:
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
        return path

    def load(self, name: str):
        path = self._path(name)
        if path.is_symlink():
            raise CredentialError("Linked credential storage is prohibited.")
        if not path.is_file():
            return None
        payload = path.read_bytes()
        if not payload.startswith(MAGIC):
            raise CredentialError("Credential file has an unsupported format.")
        try:
            protected = base64.b64decode(payload[len(MAGIC):], validate=True)
            return self._unprotector(protected).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise CredentialError("Credential file is corrupted.") from error

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if path.is_file() and not path.is_symlink():
            path.unlink()
            return True
        return False

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()

    # Telegram convenience wrappers -------------------------------------
    def save_telegram_token(self, token: str) -> Path:
        return self.save("telegram_bot_token", token)

    def load_telegram_token(self):
        return self.load("telegram_bot_token")

    def delete_telegram_token(self) -> bool:
        return self.delete("telegram_bot_token")
