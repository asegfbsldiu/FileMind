"""Local lock tests never read model settings or existing user credentials."""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from filemind.storage.local_lock import LocalLockError, LocalLockStore, WindowsTokenProtector


@pytest.fixture
def store(tmp_path: Path, test_protector) -> LocalLockStore:
    return LocalLockStore(tmp_path / "lock" / "auth.json", test_protector)


def test_setup_reload_random_salt_and_no_plaintext(store: LocalLockStore, tmp_path: Path,
                                                   test_protector) -> None:
    assert not store.is_configured()
    recovery = store.initialize("first password")
    record = store.path.read_text(encoding="utf-8")
    assert "first password" not in record
    assert recovery not in record
    assert len(recovery) == 32
    reloaded = LocalLockStore(store.path, test_protector)
    assert reloaded.is_configured()
    assert reloaded.unlock("first password")
    assert not reloaded.unlock("wrong password")
    second = LocalLockStore(tmp_path / "second" / "auth.json", test_protector)
    second.initialize("first password")
    assert json.loads(record)["password"] != json.loads(second.path.read_text())["password"]
    with pytest.raises(LocalLockError, match="已经设置"):
        store.initialize("new password")


def test_password_change_preserves_recovery_and_revokes_tokens(store: LocalLockStore) -> None:
    recovery = store.initialize("original password", remember=True)
    assert store.try_remembered_unlock()
    with pytest.raises(LocalLockError, match="当前密码"):
        store.change_password("wrong password", "changed password")
    store.change_password("original password", "changed password")
    assert not store.try_remembered_unlock()
    assert not store.unlock("original password")
    assert store.unlock("changed password")
    assert store.reset_password(recovery, "reset password")


def test_reset_requires_recovery_rotates_it_and_keeps_other_data(store: LocalLockStore) -> None:
    recovery = store.initialize("original password")
    unrelated = store.path.parent / "history.json"
    unrelated.write_text("keep me", encoding="utf-8")
    with pytest.raises(LocalLockError, match="恢复码不正确"):
        store.reset_password("invalid recovery", "reset password")
    replacement = store.reset_password(recovery, "reset password")
    assert replacement != recovery
    with pytest.raises(LocalLockError, match="恢复码不正确"):
        store.reset_password(recovery, "third password")
    assert store.unlock("reset password")
    assert unrelated.read_text() == "keep me"


def test_remember_expiry_tamper_and_explicit_lock(store: LocalLockStore) -> None:
    store.initialize("initial password", remember=True)
    assert store.try_remembered_unlock()
    now = time.time()
    with patch("filemind.storage.local_lock.time.time", return_value=now + 8 * 24 * 3600):
        assert not store.try_remembered_unlock()
    store.token_path.write_bytes(b"invalid token")
    assert not store.try_remembered_unlock()
    assert store.unlock("initial password", remember=True)
    store.revoke_remembered_unlock()
    assert not store.try_remembered_unlock()
    assert not store.token_path.exists()


def test_failed_attempts_have_persisted_cooldown(store: LocalLockStore, test_protector) -> None:
    store.initialize("initial password")
    for _ in range(5):
        assert not store.unlock("incorrect password")
    reloaded = LocalLockStore(store.path, test_protector)
    with pytest.raises(LocalLockError, match="等待"):
        reloaded.unlock("initial password")
    now = time.time()
    with patch("filemind.storage.local_lock.time.time", return_value=now + 31):
        assert reloaded.unlock("initial password")


@pytest.mark.parametrize("record", ["invalid json", "[]", '{"version": 2}',
                                    '{"version": 1, "iterations": 600000, "password": null}'])
def test_corrupt_record_never_becomes_first_run(store: LocalLockStore, record: str) -> None:
    store.path.parent.mkdir()
    store.path.write_text(record, encoding="utf-8")
    with pytest.raises(LocalLockError, match="损坏"):
        store.is_configured()


def test_short_password_and_permission_failure_do_not_create_record(store: LocalLockStore) -> None:
    with pytest.raises(LocalLockError, match="8–1024"):
        store.initialize("short")
    with patch("filemind.storage.local_lock._private_permissions", side_effect=PermissionError):
        with pytest.raises(LocalLockError, match="无法安全保存"):
            store.initialize("initial password")
    assert not store.path.exists()


def test_windows_dpapi_roundtrip_uses_only_a_generated_token() -> None:
    if os.name != "nt":
        return
    protector = WindowsTokenProtector()
    value = b"isolated-generated-ui-test-token"
    encrypted = protector.protect(value)
    assert value not in encrypted
    assert protector.unprotect(encrypted) == value
