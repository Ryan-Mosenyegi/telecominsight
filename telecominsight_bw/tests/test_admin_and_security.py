"""Tests for the admin helpers, account checks, lockout counting, first-admin setup and demo seeding."""
import pandas as pd
import pytest

from telecominsight import auth, bootstrap, config, db


def make_rows(provider: str, n: int, start: float = 0.0, source: str = "survey") -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * n), "provider": [provider] * n,
        "location": ["Gaborone"] * n, "issue_type": ["Slow data"] * n,
        "download_mbps": [10.0 + start + i for i in range(n)], "upload_mbps": [5.0] * n,
        "latency_ms": [50.0] * n, "satisfaction": [3.0] * n, "complaint_reported": [1] * n,
        "source": [source] * n, "latitude": [float("nan")] * n, "longitude": [float("nan")] * n,
    })


@pytest.fixture()
def engine(tmp_path):
    eng = db.get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    db.init_db(eng)
    yield eng
    eng.dispose()


def test_admin_role_constants_agree():
    assert db._ADMIN_ROLE == auth.ROLE_ADMIN


# ---- first administrator -----------------------------------------------------------------------
def test_bootstrap_creates_admin_once(engine, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "Root")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "a-long-password-1")
    assert not db.admin_exists(engine)
    assert bootstrap.ensure_admin(engine) is True
    assert db.admin_exists(engine)
    assert bootstrap.ensure_admin(engine) is False            # second start does nothing
    s, _ = auth.authenticate(engine, "root", "a-long-password-1")
    assert s is not None and s.role == auth.ROLE_ADMIN and s.provider_id is None


def test_bootstrap_does_nothing_without_settings(engine, monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    assert bootstrap.ensure_admin(engine) is False
    assert not db.admin_exists(engine)


def test_bootstrap_rejects_a_short_password(engine, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "root")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "short")
    with pytest.raises(ValueError):
        bootstrap.ensure_admin(engine)


# ---- is_account_active -------------------------------------------------------------------------
def _provider_user(engine):
    pid = db.create_provider(engine, "Mascom")
    uid = db.create_user(engine, "mascom_user", auth.hash_password("mascom-pass-1"),
                         auth.ROLE_PROVIDER, pid)
    return pid, uid


def test_active_account_is_allowed(engine):
    _, uid = _provider_user(engine)
    assert db.is_account_active(engine, uid) is True


def test_disabled_user_is_not_active(engine):
    _, uid = _provider_user(engine)
    db.set_user_active(engine, uid, False)
    assert db.is_account_active(engine, uid) is False


def test_disabled_provider_makes_its_users_inactive(engine):
    pid, uid = _provider_user(engine)
    db.set_provider_status(engine, pid, "disabled")
    assert db.is_account_active(engine, uid) is False


def test_unknown_user_is_not_active(engine):
    assert db.is_account_active(engine, 99999) is False


def test_admin_without_provider_is_active(engine):
    uid = db.create_user(engine, "boss", auth.hash_password("boss-password-1"), auth.ROLE_ADMIN)
    assert db.is_account_active(engine, uid) is True


# ---- failed-login counting (the lockout) -------------------------------------------------------
def test_failed_logins_are_counted_per_user(engine):
    _, uid = _provider_user(engine)
    other = db.create_user(engine, "other", auth.hash_password("other-pass-123"), auth.ROLE_ADMIN)
    for _ in range(3):
        auth.authenticate(engine, "mascom_user", "wrong-password")
    assert db.recent_failed_logins(engine, uid, 15) == 3
    assert db.recent_failed_logins(engine, other, 15) == 0


# ---- admin overview helpers --------------------------------------------------------------------
def test_counts_and_demo_removal(engine):
    db.save_records(pd.concat([make_rows("Mascom", 2),
                               make_rows("Orange", 3, start=100, source="sample")],
                              ignore_index=True), engine, "x.csv")
    counts = db.record_counts_by_provider(engine).set_index("provider")["records"].to_dict()
    assert counts == {"Mascom": 2, "Orange": 3}
    assert db.count_source(engine, "sample") == 3
    assert db.delete_source(engine, "sample") == 3
    assert db.count_source(engine, "sample") == 0
    assert db.count_records(engine) == 2


def test_list_batches_shows_every_upload(engine):
    db.save_records(make_rows("Mascom", 1), engine, "a.csv")
    db.save_records(make_rows("Orange", 1, start=50), engine, "b.csv")
    assert set(db.list_batches(engine)["label"]) == {"a.csv", "b.csv"}


# ---- demo seeding switch -----------------------------------------------------------------------
def test_seed_switch(engine, monkeypatch):
    monkeypatch.setenv("SEED_DEMO_DATA", "0")
    assert config.seed_demo_enabled() is False
    assert db.seed_if_empty(engine) is False
    assert db.count_records(engine) == 0
    monkeypatch.setenv("SEED_DEMO_DATA", "1")
    assert config.seed_demo_enabled() is True