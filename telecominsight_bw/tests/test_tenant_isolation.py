"""Tests that one provider can never see or change another provider's data.

Each test gets a brand-new temporary database, so tests cannot affect each other or your real data.
"""
import pandas as pd
import pytest

from telecominsight import analysis, auth, db

MASCOM_PW, ORANGE_PW, ADMIN_PW = "mascom-pass-1", "orange-pass-1", "admin-pass-123"


def make_rows(provider: str, n: int, start: float = 0.0, source: str = "survey") -> pd.DataFrame:
    """n valid records for one provider. `start` makes the download speeds differ so
    rows are not treated as duplicates of each other."""
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * n),
        "provider": [provider] * n,
        "location": ["Gaborone"] * n,
        "issue_type": ["Slow data"] * n,
        "download_mbps": [10.0 + start + i for i in range(n)],
        "upload_mbps": [5.0] * n,
        "latency_ms": [50.0] * n,
        "satisfaction": [3.0] * n,
        "complaint_reported": [1] * n,
        "source": [source] * n,
        "latitude": [float("nan")] * n,
        "longitude": [float("nan")] * n,
    })


@pytest.fixture()
def env(tmp_path):
    engine = db.get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    db.init_db(engine)

    mascom = db.create_provider(engine, "Mascom")
    orange = db.create_provider(engine, "Orange")
    db.create_user(engine, "mascom_user", auth.hash_password(MASCOM_PW), auth.ROLE_PROVIDER, mascom)
    db.create_user(engine, "orange_user", auth.hash_password(ORANGE_PW), auth.ROLE_PROVIDER, orange)
    db.create_user(engine, "boss", auth.hash_password(ADMIN_PW), auth.ROLE_ADMIN)

    all_rows = pd.concat([
        make_rows("Mascom", 3),
        make_rows("MASCOM", 1, start=100),             # same provider, different capitals
        make_rows("Orange", 2, start=200),
        make_rows("Botswana Telecom", 2, start=300),   # a provider with no account
    ], ignore_index=True)
    db.save_records(all_rows, engine, "test.csv")

    yield {"engine": engine, "mascom": mascom, "orange": orange}
    engine.dispose()


# ---- the data wall ----------------------------------------------------------------------------
def test_provider_only_gets_own_rows(env):
    m = db.load_records(env["engine"], env["mascom"])
    o = db.load_records(env["engine"], env["orange"])
    assert set(m["provider"].str.lower()) == {"mascom"}
    assert set(o["provider"].str.lower()) == {"orange"}
    assert len(o) == 2


def test_provider_match_ignores_capitals(env):
    assert len(db.load_records(env["engine"], env["mascom"])) == 4     # 3 "Mascom" + 1 "MASCOM"


def test_unknown_provider_id_gets_nothing(env):
    assert db.load_records(env["engine"], 99999).empty


def test_load_records_cannot_be_called_without_a_provider(env):
    with pytest.raises(TypeError):
        db.load_records(env["engine"])          # unscoped loading must be impossible


def test_analysis_on_scoped_data_contains_only_that_provider(env):
    df = db.load_records(env["engine"], env["orange"])
    assert analysis.kpis(df)["records"] == 2
    assert set(analysis.provider_summary(df)["provider"]) == {"Orange"}


# ---- provider uploads -------------------------------------------------------------------------
def test_upload_saves_only_the_providers_own_rows(env):
    upload = pd.concat([
        make_rows("Mascom", 2, start=500),
        make_rows("mascom ", 1, start=600),            # own rows, sloppy spelling
        make_rows("Orange", 2, start=700),             # someone else's name: must be rejected
    ], ignore_index=True)
    ins, skip, rej = db.save_provider_records(env["engine"], env["mascom"], upload, "mine.csv")
    assert (ins, skip, rej) == (3, 0, 2)

    mascom = db.load_records(env["engine"], env["mascom"])
    assert len(mascom) == 4 + 3
    assert set(mascom["provider"]) <= {"Mascom", "MASCOM"}      # new rows use the exact account spelling
    assert len(db.load_records(env["engine"], env["orange"])) == 2     # Orange gained nothing


def test_upload_cannot_target_an_unknown_provider(env):
    before = db.count_records(env["engine"])
    with pytest.raises(ValueError):
        db.save_provider_records(env["engine"], 99999, make_rows("Mascom", 1, start=800), "x.csv")
    assert db.count_records(env["engine"]) == before


def test_upload_of_only_foreign_rows_saves_nothing(env):
    before = db.count_records(env["engine"])
    ins, skip, rej = db.save_provider_records(env["engine"], env["mascom"],
                                              make_rows("Orange", 2, start=900), "wrong.csv")
    assert (ins, rej) == (0, 2)
    assert db.count_records(env["engine"]) == before


def test_uploading_the_same_file_twice_skips_duplicates(env):
    data = make_rows("Mascom", 2, start=1000)
    assert db.save_provider_records(env["engine"], env["mascom"], data, "a.csv")[:2] == (2, 0)
    assert db.save_provider_records(env["engine"], env["mascom"], data, "a.csv")[:2] == (0, 2)


def test_upload_history_is_private_to_each_provider(env):
    user = db.get_user_by_username(env["engine"], "mascom_user")
    db.save_provider_records(env["engine"], env["mascom"], make_rows("Mascom", 1, start=1100),
                             "mascom_secret_file.csv", user["id"])
    mine = db.list_provider_uploads(env["engine"], env["mascom"])
    theirs = db.list_provider_uploads(env["engine"], env["orange"])
    assert len(mine) == 1 and "mascom_secret_file.csv" in mine.iloc[0]["result"]
    assert theirs.empty


def test_removing_demo_data_only_touches_own_provider(env):
    demo = pd.concat([make_rows("Mascom", 2, start=1200, source="sample"),
                      make_rows("Orange", 2, start=1300, source="sample")], ignore_index=True)
    db.save_records(demo, env["engine"], "demo.csv")
    assert db.count_provider_source(env["engine"], env["mascom"], "sample") == 2

    assert db.delete_provider_source(env["engine"], env["mascom"], "sample") == 2
    assert db.count_provider_source(env["engine"], env["mascom"], "sample") == 0
    assert db.count_provider_source(env["engine"], env["orange"], "sample") == 2    # untouched


# ---- who can sign in --------------------------------------------------------------------------
def test_session_carries_the_right_provider(env):
    s, _ = auth.authenticate(env["engine"], "mascom_user", MASCOM_PW)
    assert s is not None and s.provider_id == env["mascom"] and s.role == auth.ROLE_PROVIDER
    s, _ = auth.authenticate(env["engine"], "orange_user", ORANGE_PW)
    assert s is not None and s.provider_id == env["orange"]


def test_admin_session_has_no_provider(env):
    s, _ = auth.authenticate(env["engine"], "boss", ADMIN_PW)
    assert s is not None and s.role == auth.ROLE_ADMIN and s.provider_id is None


def test_wrong_password_and_unknown_user_get_the_same_message(env):
    s1, m1 = auth.authenticate(env["engine"], "mascom_user", "not-the-password")
    s2, m2 = auth.authenticate(env["engine"], "nobody", "whatever-123")
    assert s1 is None and s2 is None and m1 == m2 == auth.GENERIC_FAILURE


def test_disabled_user_cannot_sign_in(env):
    user = db.get_user_by_username(env["engine"], "mascom_user")
    db.set_user_active(env["engine"], user["id"], False)
    s, msg = auth.authenticate(env["engine"], "mascom_user", MASCOM_PW)
    assert s is None and msg == auth.DISABLED_MESSAGE


def test_disabled_provider_blocks_its_users_only(env):
    db.set_provider_status(env["engine"], env["mascom"], "disabled")
    s, msg = auth.authenticate(env["engine"], "mascom_user", MASCOM_PW)
    assert s is None and msg == auth.DISABLED_MESSAGE
    s, _ = auth.authenticate(env["engine"], "orange_user", ORANGE_PW)
    assert s is not None


# ---- admin helpers ----------------------------------------------------------------------------
def test_user_listing_never_exposes_password_hashes(env):
    listing = db.list_users(env["engine"])
    assert "password_hash" not in listing.columns
    assert not listing.astype(str).apply(lambda c: c.str.contains("scrypt")).any().any()


def test_password_reset_replaces_the_old_password(env):
    user = db.get_user_by_username(env["engine"], "mascom_user")
    db.set_password_hash(env["engine"], user["id"], auth.hash_password("brand-new-pass-9"))
    assert auth.authenticate(env["engine"], "mascom_user", MASCOM_PW)[0] is None
    assert auth.authenticate(env["engine"], "mascom_user", "brand-new-pass-9")[0] is not None


def test_failed_login_is_logged(env):
    auth.authenticate(env["engine"], "mascom_user", "wrong-password")
    log = db.recent_access_log(env["engine"])
    assert "login_failed" in set(log["action"])