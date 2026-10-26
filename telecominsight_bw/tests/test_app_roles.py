"""Runs the real app.py and admin_app.py with a pretend signed-in session and checks who sees what."""
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from telecominsight import auth, db

ROOT = Path(__file__).resolve().parent.parent
PW = {"mascom_user": "mascom-pass-1", "boss": "boss-password-1"}


@pytest.fixture()
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("SEED_DEMO_DATA", "0")
    monkeypatch.delenv("BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    st.cache_resource.clear()
    st.cache_data.clear()

    engine = db.get_engine()
    db.init_db(engine)
    pid = db.create_provider(engine, "Mascom")
    db.create_user(engine, "mascom_user", auth.hash_password(PW["mascom_user"]), auth.ROLE_PROVIDER, pid)
    db.create_user(engine, "boss", auth.hash_password(PW["boss"]), auth.ROLE_ADMIN)
    n = 12
    rows = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * n), "provider": ["Mascom"] * n,
        "location": ["Gaborone"] * n, "issue_type": ["Slow data"] * n,
        "download_mbps": [10.0 + i for i in range(n)], "upload_mbps": [5.0] * n,
        "latency_ms": [50.0 + i for i in range(n)], "satisfaction": [3.0] * n,
        "complaint_reported": [i % 2 for i in range(n)], "source": ["survey"] * n,
        "latitude": [float("nan")] * n, "longitude": [float("nan")] * n})
    db.save_records(rows, engine, "t.csv")

    def session_for(username):
        s, _ = auth.authenticate(engine, username, PW[username])
        assert s is not None
        return s

    yield session_for
    engine.dispose()


def _run(script: str, session=None, username=""):
    at = AppTest.from_file(str(ROOT / script), default_timeout=60)
    if session is not None:
        at.session_state["auth_session"] = session
        at.session_state["auth_username"] = username
    return at.run()


def _metric_labels(at):
    return [m.label for m in at.metric]


def test_provider_sees_the_dashboard_on_the_provider_site(site):
    at = _run("app.py", site("mascom_user"), "mascom_user")
    assert not at.exception
    assert "Records analysed" in _metric_labels(at)


def test_admin_sees_admin_tabs_and_no_dashboard_on_the_admin_site(site):
    at = _run("admin_app.py", site("boss"), "boss")
    assert not at.exception
    assert any("Accounts" in t.label for t in at.tabs)
    assert "Records analysed" not in _metric_labels(at)


def test_admin_account_is_turned_away_from_the_provider_site(site):
    at = _run("app.py", site("boss"), "boss")
    assert not at.exception
    assert "auth_session" not in at.session_state
    assert len(at.text_input) == 2                      # the login form is shown instead


def test_provider_account_is_turned_away_from_the_admin_site(site):
    at = _run("admin_app.py", site("mascom_user"), "mascom_user")
    assert not at.exception
    assert "auth_session" not in at.session_state
    assert len(at.text_input) == 2


def test_signed_out_visitors_see_only_the_login_form_on_both_sites(site):
    for script in ("app.py", "admin_app.py"):
        at = _run(script)
        assert not at.exception
        assert len(at.text_input) == 2
        assert "Records analysed" not in _metric_labels(at)