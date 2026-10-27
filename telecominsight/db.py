"""code learning note
Database layer.

This file is the only place that talks to the database. It has six parts, top to bottom:
  1. Imports       - tools borrowed from other libraries
  2. Tables        - the shape of the database (what columns each table has)
  3. Engine        - how we connect to the database and create the tables
  4. Data          - saving, loading and deleting complaint/measurement records
  5. Accounts      - providers, users and the access log (used for logging in)
  6. Admin helpers - listing, changing and deleting accounts, counts for the admin site

SQLite is used by default; set the DATABASE_URL setting to use PostgreSQL instead.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

import pandas as pd
from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer,
                        MetaData, SmallInteger, String, Table, create_engine, delete, func,
                        or_, select, update)

from . import cleaning, config

# 2. TABLES
# `metadata` is a shared list. Every Table below registers itself in it, which is how
# init_db() later knows which tables to create.
metadata = MetaData()

# Data tables
# One row per file upload: what the file was called, when, and how many rows were new or skipped.
batches = Table(
    "upload_batches", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("label", String(255), nullable=False),
    Column("uploaded_at", DateTime, nullable=False),
    Column("rows_submitted", Integer, nullable=False, default=0),
    Column("rows_inserted", Integer, nullable=False, default=0),
    Column("rows_skipped", Integer, nullable=False, default=0),
)

# One row per measurement/complaint record.
records = Table(
    "records", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("batch_id", Integer, ForeignKey("upload_batches.id")),   # which upload it came from
    Column("date", Date, nullable=False),
    Column("provider", String(100), nullable=False),
    Column("location", String(100), nullable=False),
    Column("issue_type", String(100), nullable=False),
    Column("download_mbps", Float, nullable=False),
    Column("upload_mbps", Float),
    Column("latency_ms", Float, nullable=False),
    Column("satisfaction", Float),
    Column("complaint_reported", SmallInteger, nullable=False),     # 1 = complaint, 0 = none
    Column("source", String(30), nullable=False),
    Column("latitude", Float),
    Column("longitude", Float),
    Index("ix_records_date", "date"),                                # speeds up searching by date
    Index("ix_records_provider_location", "provider", "location"),
)

# Account tables
# One row per telecom company.
providers = Table(
    "providers", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False, unique=True),       # no two providers share a name
    Column("status", String(20), nullable=False, default="active"),
    Column("created_at", DateTime, nullable=False),
)

# One row per person who can sign in. Each user points to their provider.
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("provider_id", Integer, ForeignKey("providers.id")),     # empty only for the administrator
    Column("username", String(100), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),           # scrambled password, never the real one
    Column("role", String(20), nullable=False),                     # "provider_user" or "platform_admin"
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False),
    Column("last_login", DateTime),
)

# One row per notable event: sign-in, failed sign-in, upload...
access_log = Table(
    "access_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("provider_id", Integer, ForeignKey("providers.id")),
    Column("action", String(50), nullable=False),
    Column("detail", String(255)),
    Column("occurred_at", DateTime, nullable=False),
)

# Must equal auth.ROLE_ADMIN (a test checks this). auth.py imports this file, so we cannot import it back.
_ADMIN_ROLE = "platform_admin"


# 3. ENGINE (the connection to the database)
@lru_cache(maxsize=4)
def _engine_for(url: str):
    # Create the connection for a database address. lru_cache remembers it, so we connect once.
    return create_engine(url, pool_pre_ping=True, future=True)


def get_engine(url: str | None = None):
    # Return the connection. With no address given, use the one from config (SQLite by default).
    return _engine_for(config.normalise_db_url(url) if url else config.database_url())


def init_db(engine) -> None:
    # Create any table that does not exist yet. Existing tables are left as they are.
    metadata.create_all(engine)


def _now() -> datetime:
    # Current UTC time without a timezone label (how we store times in the database).
    return datetime.now(timezone.utc).replace(tzinfo=None)


# 4. DATA (complaint and measurement records)
def count_records(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(records)).scalar_one()


def _batch_count(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(batches)).scalar_one()


_FLOAT_COLS = ["download_mbps", "upload_mbps", "latency_ms", "satisfaction", "latitude", "longitude"]


def _normalise_types(df: pd.DataFrame) -> pd.DataFrame:
    # Give frames from the CSV and from the database identical column types.
    # Needed so the duplicate check in save_records() compares like with like.
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).astype("datetime64[ns]")
    for c in _FLOAT_COLS:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)
    out["complaint_reported"] = out["complaint_reported"].astype(int)
    return out


def save_records(df: pd.DataFrame, engine, label: str) -> tuple[int, int]:
    # Insert cleaned rows, skipping any that already exist. Returns (inserted, skipped).
    # Low-level: it saves whatever provider names the frame contains. The provider site never
    # calls this directly; it goes through save_provider_records() below.
    init_db(engine)
    with engine.begin() as conn:                      # everything inside succeeds or nothing is saved
        batch_id = conn.execute(batches.insert().values(
            label=label[:255], uploaded_at=_now(),
            rows_submitted=len(df), rows_inserted=0, rows_skipped=0)).inserted_primary_key[0]

        # Compare the new rows with what is already stored, and keep only the genuinely new ones.
        new = _normalise_types(df)
        existing = pd.read_sql(select(*[records.c[c] for c in config.RECORD_COLUMNS]), conn)
        if not existing.empty and not new.empty:
            existing = _normalise_types(existing).drop_duplicates()
            merged = new.merge(existing, on=config.RECORD_COLUMNS, how="left", indicator=True)
            new = new[(merged["_merge"] == "left_only").to_numpy()]

        inserted = len(new)
        if inserted:
            out = new.assign(batch_id=batch_id)
            out["date"] = out["date"].dt.date
            out.to_sql("records", conn, if_exists="append", index=False, chunksize=500)
        skipped = len(df) - inserted
        conn.execute(update(batches).where(batches.c.id == batch_id)
                     .values(rows_inserted=inserted, rows_skipped=skipped))
    return inserted, skipped


def get_provider_name(engine, provider_id: int | None) -> str | None:
    """The name of a provider, or None if there is no such provider."""
    if provider_id is None:
        return None
    init_db(engine)
    with engine.connect() as conn:
        return conn.execute(
            select(providers.c.name).where(providers.c.id == provider_id)).scalar_one_or_none()


def _is_provider(name: str):
    # records.provider is free text from uploaded CSVs, so compare ignoring upper/lower case.
    return func.lower(records.c.provider) == name.strip().lower()


def load_records(engine, provider_id: int) -> pd.DataFrame:
    """Read ONE provider's records into a table (DataFrame) for the dashboard.

    This is the wall between providers. The filter happens inside the database query, so rows
    that belong to other providers are never even loaded into the app's memory.
    `provider_id` has no default on purpose: forgetting to pass it is an error, not a data leak.
    An unknown provider id gets an empty table, never everyone's data.
    """
    init_db(engine)
    name = get_provider_name(engine, provider_id)
    if name is None:
        return _normalise_types(pd.DataFrame(columns=config.RECORD_COLUMNS))
    query = select(*[records.c[c] for c in config.RECORD_COLUMNS]).where(_is_provider(name))
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return _normalise_types(df)


def save_provider_records(engine, provider_id: int, df: pd.DataFrame, label: str,
                          user_id: int | None = None) -> tuple[int, int, int]:
    """A provider saves THEIR OWN uploaded data. Returns (inserted, skipped, rejected).

    Never trust the file: its `provider` column is typed by whoever made the CSV. So:
      - rows whose provider name is not this provider's are rejected, not saved
      - rows that do match are stored with the provider's exact account spelling
    The provider id comes from the signed-in session, never from the file.
    """
    name = get_provider_name(engine, provider_id)
    if name is None:
        raise ValueError("Unknown provider: nothing was saved.")

    mine = df["provider"].astype(str).str.strip().str.lower() == name.strip().lower()
    rejected = int((~mine).sum())
    keep = df[mine].copy()
    keep["provider"] = name

    inserted = skipped = 0
    if not keep.empty:
        inserted, skipped = save_records(keep, engine, label)

    log_event(engine, user_id, provider_id, "upload",
              f"{label[:120]}: {inserted} new, {skipped} duplicates, {rejected} rejected")
    return inserted, skipped, rejected


def list_provider_uploads(engine, provider_id: int, limit: int = 50) -> pd.DataFrame:
    """One provider's upload history. Built from the access log (which stores the provider id),
    so a provider can never see another provider's file names."""
    init_db(engine)
    with engine.connect() as conn:
        return pd.read_sql(
            select(access_log.c.occurred_at, users.c.username.label("uploaded_by"),
                   access_log.c.detail.label("result"))
            .select_from(access_log.outerjoin(users, access_log.c.user_id == users.c.id))
            .where(access_log.c.provider_id == provider_id, access_log.c.action == "upload")
            .order_by(access_log.c.id.desc()).limit(limit), conn)


def count_provider_source(engine, provider_id: int, source: str) -> int:
    """How many of ONE provider's records come from a given source (e.g. 'sample')."""
    name = get_provider_name(engine, provider_id)
    if name is None:
        return 0
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(records)
                            .where(_is_provider(name), records.c.source == source)).scalar_one()


def delete_provider_source(engine, provider_id: int, source: str) -> int:
    """Delete ONE provider's records from a given source. Other providers' rows are untouched."""
    name = get_provider_name(engine, provider_id)
    if name is None:
        return 0
    with engine.begin() as conn:
        return conn.execute(delete(records).where(
            _is_provider(name), records.c.source == source)).rowcount


def list_batches(engine) -> pd.DataFrame:
    """The upload batches of EVERYONE (D2 in the data-flow diagram). Admin site only."""
    init_db(engine)
    with engine.connect() as conn:
        return pd.read_sql(select(batches).order_by(batches.c.id.desc()), conn)


def count_source(engine, source: str) -> int:
    """How many records, across ALL providers, come from a given source. Admin site only."""
    init_db(engine)
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(records)
                            .where(records.c.source == source)).scalar_one()


def delete_source(engine, source: str) -> int:
    """Delete every record from one source across ALL providers (e.g. the fictional demo data).
    Admin site only. Returns how many were deleted."""
    with engine.begin() as conn:
        return conn.execute(delete(records).where(records.c.source == source)).rowcount


def seed_if_empty(engine) -> bool:
    """Load the fictional sample file the very first time only (never after data was removed).
    Skipped entirely when SEED_DEMO_DATA=0."""
    init_db(engine)
    if not config.seed_demo_enabled():
        return False
    if count_records(engine) or _batch_count(engine) or not config.SAMPLE_CSV.exists():
        return False
    cleaned, _ = cleaning.clean_dataframe(pd.read_csv(config.SAMPLE_CSV), default_source="sample")
    save_records(cleaned, engine, config.SAMPLE_CSV.name)
    return True


# 5. ACCOUNTS (providers, users and the access log)
def create_provider(engine, name: str) -> int:
    """Add a provider and return its new id. Fails if that name already exists."""
    init_db(engine)
    with engine.begin() as conn:
        result = conn.execute(providers.insert().values(
            name=name.strip(), status="active", created_at=_now()))
        return result.inserted_primary_key[0]


def create_user(engine, username: str, password_hash: str, role: str,
                provider_id: int | None = None) -> int:
    """Add a user and return the new id. Store the HASH of the password, never the password."""
    init_db(engine)
    with engine.begin() as conn:
        result = conn.execute(users.insert().values(
            provider_id=provider_id, username=username.strip().lower(),
            password_hash=password_hash, role=role, active=True, created_at=_now()))
        return result.inserted_primary_key[0]


def get_user_by_username(engine, username: str) -> dict | None:
    """Find a user (and their provider's status) by username. Returns None if there is no such user."""
    init_db(engine)
    with engine.connect() as conn:
        row = conn.execute(
            select(users.c.id, users.c.provider_id, users.c.username, users.c.password_hash,
                   users.c.role, users.c.active, providers.c.status.label("provider_status"))
            .select_from(users.outerjoin(providers, users.c.provider_id == providers.c.id))
            .where(users.c.username == username.strip().lower())
        ).mappings().first()
    return dict(row) if row else None


def is_account_active(engine, user_id: int) -> bool:
    """Is this user still allowed in? False if the user is disabled, their provider is disabled,
    or the user no longer exists. Checked on every page load, so disabling or deleting takes
    effect at once."""
    init_db(engine)
    with engine.connect() as conn:
        row = conn.execute(
            select(users.c.active, providers.c.status)
            .select_from(users.outerjoin(providers, users.c.provider_id == providers.c.id))
            .where(users.c.id == user_id)).first()
    if row is None:
        return False
    return bool(row[0]) and row[1] in (None, "active")


def touch_login(engine, user_id: int) -> None:
    """Record the time of this user's latest successful sign-in."""
    with engine.begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(last_login=_now()))


def log_event(engine, user_id: int | None, provider_id: int | None, action: str,
              detail: str | None = None) -> None:
    """Write one line to the access log (sign-ins, failures, uploads...)."""
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(access_log.insert().values(
            user_id=user_id, provider_id=provider_id, action=action, detail=detail,
            occurred_at=_now()))


def recent_failed_logins(engine, user_id: int, minutes: int) -> int:
    """How many failed sign-ins this user had in the last `minutes` minutes (used for lockout)."""
    init_db(engine)
    cutoff = _now() - timedelta(minutes=minutes)
    with engine.connect() as conn:
        return conn.execute(
            select(func.count()).select_from(access_log)
            .where(access_log.c.user_id == user_id, access_log.c.action == "login_failed",
                   access_log.c.occurred_at >= cutoff)).scalar_one()


def admin_exists(engine) -> bool:
    """Is there at least one administrator account (active or not)?"""
    init_db(engine)
    with engine.connect() as conn:
        n = conn.execute(select(func.count()).select_from(users)
                         .where(users.c.role == _ADMIN_ROLE)).scalar_one()
    return n > 0


# 6. ADMIN HELPERS (accounts and oversight; none returns a password hash or provider rows)
def list_providers(engine) -> pd.DataFrame:
    """Every provider with its status."""
    init_db(engine)
    with engine.connect() as conn:
        return pd.read_sql(
            select(providers.c.id, providers.c.name, providers.c.status, providers.c.created_at)
            .order_by(providers.c.name), conn)


def list_users(engine) -> pd.DataFrame:
    """Every user with their provider's name. The password hash is deliberately NOT selected."""
    init_db(engine)
    with engine.connect() as conn:
        return pd.read_sql(
            select(users.c.id, users.c.username, users.c.role, users.c.active,
                   providers.c.name.label("provider"), users.c.created_at, users.c.last_login)
            .select_from(users.outerjoin(providers, users.c.provider_id == providers.c.id))
            .order_by(users.c.id), conn)


def set_provider_status(engine, provider_id: int, status: str) -> None:
    """Set a provider to "active" or "disabled". A disabled provider's users cannot sign in."""
    with engine.begin() as conn:
        conn.execute(update(providers).where(providers.c.id == provider_id).values(status=status))


def set_user_active(engine, user_id: int, active: bool) -> None:
    """Enable or disable one user."""
    with engine.begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(active=active))


def set_password_hash(engine, user_id: int, password_hash: str) -> None:
    """Replace a user's password hash (the caller has already hashed the new password)."""
    with engine.begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(password_hash=password_hash))


def record_counts_by_provider(engine) -> pd.DataFrame:
    """How many records exist under each provider name. Counts only, never the rows."""
    init_db(engine)
    with engine.connect() as conn:
        return pd.read_sql(
            select(records.c.provider, func.count().label("records"))
            .group_by(records.c.provider).order_by(records.c.provider), conn)


def recent_access_log(engine, limit: int = 300) -> pd.DataFrame:
    """The newest access-log lines, with the username and provider name filled in."""
    init_db(engine)
    with engine.connect() as conn:
        return pd.read_sql(
            select(access_log.c.occurred_at, users.c.username, providers.c.name.label("provider"),
                   access_log.c.action, access_log.c.detail)
            .select_from(access_log
                         .outerjoin(users, access_log.c.user_id == users.c.id)
                         .outerjoin(providers, access_log.c.provider_id == providers.c.id))
            .order_by(access_log.c.id.desc()).limit(limit), conn)


# ---- deleting users and providers (permanent) -------------------------------------------------
def count_user_log_entries(engine, user_id: int) -> int:
    """How many access-log lines belong to one user."""
    init_db(engine)
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(access_log)
                            .where(access_log.c.user_id == user_id)).scalar_one()


def delete_user(engine, user_id: int, acting_user_id: int | None = None) -> dict:
    """Permanently delete one user and their access-log lines.

    Records they uploaded stay: records belong to the provider, not to the person.
    Refuses to delete yourself or the only administrator. Raises ValueError with a message
    that is safe to show on screen.
    """
    init_db(engine)
    if acting_user_id is not None and user_id == acting_user_id:
        raise ValueError("You cannot delete your own account.")
    with engine.begin() as conn:
        row = conn.execute(select(users.c.username, users.c.role)
                           .where(users.c.id == user_id)).first()
        if row is None:
            raise ValueError("No such user.")
        username, role = row[0], row[1]
        if role == _ADMIN_ROLE:
            n_admins = conn.execute(select(func.count()).select_from(users)
                                    .where(users.c.role == _ADMIN_ROLE)).scalar_one()
            if n_admins <= 1:
                raise ValueError("You cannot delete the only administrator account.")
        log_n = conn.execute(delete(access_log).where(access_log.c.user_id == user_id)).rowcount
        conn.execute(delete(users).where(users.c.id == user_id))
    return {"username": username, "role": role, "log_entries": log_n}


def _provider_scope(conn, provider_id: int):
    """Work out what belongs to a provider: (name, its user ids, upload batches that can go).

    A batch can go only if none of its records belong to another provider (the demo-data
    batch, for example, holds several providers' rows, so it must stay).
    """
    name = conn.execute(select(providers.c.name)
                        .where(providers.c.id == provider_id)).scalar_one_or_none()
    if name is None:
        raise ValueError("No such provider.")
    user_ids = [r[0] for r in conn.execute(select(users.c.id).where(users.c.provider_id == provider_id))]
    batch_ids = {r[0] for r in conn.execute(
        select(records.c.batch_id).where(_is_provider(name), records.c.batch_id.is_not(None)).distinct())}
    shared = set()
    if batch_ids:
        shared = {r[0] for r in conn.execute(
            select(records.c.batch_id).where(~_is_provider(name), records.c.batch_id.in_(batch_ids)).distinct())}
    return name, user_ids, batch_ids - shared


def _provider_log_filter(provider_id: int, user_ids: list):
    return or_(access_log.c.provider_id == provider_id, access_log.c.user_id.in_(user_ids))


def provider_deletion_preview(engine, provider_id: int) -> dict | None:
    """What deleting this provider would remove (counts only). None if there is no such provider."""
    init_db(engine)
    with engine.connect() as conn:
        try:
            name, user_ids, removable = _provider_scope(conn, provider_id)
        except ValueError:
            return None
        n_records = conn.execute(select(func.count()).select_from(records)
                                 .where(_is_provider(name))).scalar_one()
        n_log = conn.execute(select(func.count()).select_from(access_log)
                             .where(_provider_log_filter(provider_id, user_ids))).scalar_one()
    return {"name": name, "users": len(user_ids), "records": n_records,
            "log_entries": n_log, "batches": len(removable)}


def delete_provider(engine, provider_id: int) -> dict:
    """Permanently delete a provider and everything that belongs to it, in ONE transaction:
    access-log lines, records, upload batches that are only theirs, users, then the provider.
    The order matters: on PostgreSQL a row cannot be deleted while another row still points at it.
    """
    init_db(engine)
    with engine.begin() as conn:
        name, user_ids, removable = _provider_scope(conn, provider_id)
        log_n = conn.execute(delete(access_log)
                             .where(_provider_log_filter(provider_id, user_ids))).rowcount
        rec_n = conn.execute(delete(records).where(_is_provider(name))).rowcount
        batch_n = 0
        if removable:
            batch_n = conn.execute(delete(batches).where(batches.c.id.in_(removable))).rowcount
        user_n = conn.execute(delete(users).where(users.c.provider_id == provider_id)).rowcount
        conn.execute(delete(providers).where(providers.c.id == provider_id))
    return {"name": name, "users": user_n, "records": rec_n,
            "log_entries": log_n, "batches": batch_n}
