"""Application-local password verification, recovery, and DPAPI unlock tokens."""

from __future__ import annotations

import base64
import csv
import ctypes
import hashlib
import hmac
import json
import math
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Protocol, cast

from filemind.storage.paths import data_dir


ITERATIONS = 600_000
REMEMBER_SECONDS = 7 * 24 * 3600


class LocalLockError(RuntimeError):
    """A safe-to-display local lock or persistence failure."""


class TokenProtector(Protocol):
    """Protect only this application's random remember token, never a password."""

    def protect(self, data: bytes) -> bytes: ...
    def unprotect(self, data: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ulong), ("data", ctypes.c_void_p)]


class WindowsTokenProtector:
    """Use Windows DPAPI under the current Windows user's identity."""

    def protect(self, data: bytes) -> bytes:
        """Encrypt a newly generated random token using user-scoped DPAPI."""
        return self._transform(data, False)

    def unprotect(self, data: bytes) -> bytes:
        """Decrypt only the app's token, without accessing Credential Manager."""
        return self._transform(data, True)

    @staticmethod
    def _transform(data: bytes, decrypt: bool) -> bytes:
        if os.name != "nt":
            raise LocalLockError("当前系统不支持 Windows 安全记住解锁。")
        buffer = ctypes.create_string_buffer(data)
        source = _DataBlob(len(data), ctypes.cast(buffer, ctypes.c_void_p))
        output = _DataBlob()
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        function.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                             ctypes.POINTER(_DataBlob)]
        function.restype = ctypes.c_int
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
            raise LocalLockError("Windows 无法保护或读取记住解锁状态，请使用密码解锁。")
        try:
            return ctypes.string_at(output.data, output.length)
        finally:
            kernel.LocalFree(output.data)


def _credential(value: str) -> dict[str, str]:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, ITERATIONS)
    return {"salt": base64.b64encode(salt).decode(), "verifier": derived.hex()}


def _matches(value: str, credential: dict[str, str]) -> bool:
    salt = base64.b64decode(credential["salt"], validate=True)
    derived = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, ITERATIONS)
    return hmac.compare_digest(derived.hex(), credential["verifier"])


def _private_permissions(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)
        return
    flags = subprocess.CREATE_NO_WINDOW
    system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    identity = subprocess.run([str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              check=True, creationflags=flags, timeout=10)
    sid = next(csv.reader(identity.stdout.splitlines()))[-1]
    if not sid.startswith("S-1-"):
        raise LocalLockError("无法确认本机文件权限，未保存密码设置。")
    subprocess.run([str(system / "icacls.exe"), str(path), "/inheritance:r", "/grant:r", f"*{sid}:(F)"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
                   creationflags=flags, timeout=10)


def _atomic_private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink() or path.parent.is_junction():
        raise LocalLockError("锁屏配置路径不能是链接。")
    descriptor, name = tempfile.mkstemp(prefix="lock-", dir=path.parent)
    staging = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            _private_permissions(staging)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        staging.replace(path)
    finally:
        staging.unlink(missing_ok=True)


class LocalLockStore:
    """Keep password verifiers separate from all model/API settings."""

    def __init__(self, path: Path | None = None, protector: TokenProtector | None = None) -> None:
        self.path = path or data_dir() / "lock" / "auth.json"
        self.token_path = self.path.with_name("remember_unlock.bin")
        self.protector = protector or (WindowsTokenProtector() if os.name == "nt" else None)

    def is_configured(self) -> bool:
        """Validate the record; a damaged configuration never silently unlocks."""
        return self._read() is not None

    def initialize(self, password: str, remember: bool = False) -> str:
        """Set the initial password and return a one-time recovery code."""
        self._validate_password(password)
        if self.is_configured():
            raise LocalLockError("已经设置过密码，请先解锁或使用恢复码。")
        recovery = secrets.token_hex(16)
        state: dict[str, object] = {"version": 1, "iterations": ITERATIONS,
                                    "password": _credential(password), "recovery": _credential(recovery),
                                    "failed_attempts": 0, "retry_after": 0}
        self._remember(state, remember)
        self._write(state)
        return recovery

    def unlock(self, password: str, remember: bool = False) -> bool:
        """Verify a password and optionally remember this user for seven days."""
        state = self._required_state()
        self._check_cooldown(state)
        if len(password) > 1024 or not _matches(password, cast(dict[str, str], state["password"])):
            self._record_failure(state)
            return False
        state.update(failed_attempts=0, retry_after=0)
        self._remember(state, remember)
        self._write(state)
        return True

    def change_password(self, current: str, password: str) -> None:
        """Change the password after verification and revoke remembered access."""
        self._validate_password(password)
        if not self.unlock(current):
            raise LocalLockError("当前密码不正确。")
        state = self._required_state()
        state["password"] = _credential(password)
        self._write(state)

    def reset_password(self, recovery: str, password: str) -> str:
        """Reset using the recovery code and rotate that code without deleting data."""
        self._validate_password(password)
        state = self._required_state()
        self._check_cooldown(state)
        if len(recovery) > 256 or not _matches(recovery.strip(), cast(dict[str, str], state["recovery"])):
            self._record_failure(state)
            raise LocalLockError("恢复码不正确。")
        replacement = secrets.token_hex(16)
        state.update(password=_credential(password), recovery=_credential(replacement),
                     failed_attempts=0, retry_after=0)
        self._remember(state, False)
        self._write(state)
        return replacement

    def try_remembered_unlock(self) -> bool:
        """Accept only an unexpired DPAPI token bound to the current verifier."""
        state = self._read()
        if not state or not self.protector or float(state.get("remember_until", 0)) <= time.time():
            return False
        if not self.token_path.is_file() or self.token_path.is_symlink():
            return False
        try:
            if self.token_path.stat().st_size > 16_384:
                return False
            token = self.protector.unprotect(self.token_path.read_bytes())
        except (OSError, LocalLockError):
            return False
        return hmac.compare_digest(hashlib.sha256(token).hexdigest(), str(state.get("remember_hash", "")))

    def revoke_remembered_unlock(self) -> None:
        """Require a password on the next launch or explicit manual lock."""
        state = self._required_state()
        self._remember(state, False)
        self._write(state)

    def _remember(self, state: dict[str, object], enabled: bool) -> None:
        state.pop("remember_hash", None)
        state.pop("remember_until", None)
        if enabled:
            if not self.protector:
                raise LocalLockError("当前系统无法安全记住解锁，请取消勾选后继续。")
            token = secrets.token_bytes(32)
            _atomic_private_write(self.token_path, self.protector.protect(token))
            state.update(remember_hash=hashlib.sha256(token).hexdigest(),
                         remember_until=time.time() + REMEMBER_SECONDS)
        else:
            self.token_path.unlink(missing_ok=True)

    def _required_state(self) -> dict[str, object]:
        state = self._read()
        if state is None:
            raise LocalLockError("请先设置本机密码。")
        return state

    def _read(self) -> dict[str, object] | None:
        if not self.path.exists():
            return None
        try:
            if self.path.is_symlink() or self.path.stat().st_size > 16_384:
                raise ValueError("invalid record")
            state = json.loads(self.path.read_text(encoding="utf-8"))
            self._validate_state(state)
            return state
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise LocalLockError("本机锁屏配置无法读取或已损坏，未解锁。请保留文件并检查配置。") from error

    @staticmethod
    def _validate_state(state: object) -> None:
        if not isinstance(state, dict) or state.get("version") != 1 or state.get("iterations") != ITERATIONS:
            raise ValueError("invalid version")
        for name in ("password", "recovery"):
            credential = state[name]
            if len(base64.b64decode(credential["salt"], validate=True)) != 16:
                raise ValueError("invalid salt")
            if len(bytes.fromhex(credential["verifier"])) != 32:
                raise ValueError("invalid verifier")
        for name in ("failed_attempts", "retry_after", "remember_until"):
            number = state.get(name, 0)
            if not isinstance(number, (int, float)) or not math.isfinite(number) or not 0 <= number <= 10**12:
                raise ValueError("invalid counter")
        if "remember_hash" in state and len(bytes.fromhex(state["remember_hash"])) != 32:
            raise ValueError("invalid token verifier")

    def _write(self, state: dict[str, object]) -> None:
        try:
            _atomic_private_write(self.path, json.dumps(state).encode("utf-8"))
        except (OSError, subprocess.SubprocessError) as error:
            raise LocalLockError("无法安全保存本机密码配置，请检查当前用户的目录权限。") from error

    @staticmethod
    def _validate_password(password: str) -> None:
        if not 8 <= len(password) <= 1024:
            raise LocalLockError("密码需要 8–1024 个字符。")

    @staticmethod
    def _check_cooldown(state: dict[str, object]) -> None:
        seconds = int(float(state.get("retry_after", 0)) - time.time())
        if seconds >= 0:
            raise LocalLockError(f"尝试次数过多，请等待 {seconds + 1} 秒后重试。")

    def _record_failure(self, state: dict[str, object]) -> None:
        attempts = int(state.get("failed_attempts", 0)) + 1
        state.update(failed_attempts=attempts, retry_after=time.time() + 30 if attempts % 5 == 0 else 0)
        self._write(state)
