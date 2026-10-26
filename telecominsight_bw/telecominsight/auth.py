"""code learning note 
Passwords, sessions and signing in: the access-control layer.

This file has three parts:
  1. Passwords  - turn a password into a safe hash, and check a typed password against it
  2. Sessions   - the Session object that remembers who is signed in and which provider they belong to
  3. Signing in - authenticate(): check a username and password and, if correct, start a session
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from . import db

# Settings
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1     # how hard the password scrambling is
SESSION_MINUTES = 60                            # a session stops working after this long
MIN_PASSWORD_LENGTH = 8

ROLE_PROVIDER = "provider_user"                 # belongs to one provider, sees only that provider
ROLE_ADMIN = "platform_admin"                   # manages accounts, sees no provider analytics

GENERIC_FAILURE = "Incorrect username or password."
DISABLED_MESSAGE = "This account is disabled. Contact the administrator."
SETUP_MESSAGE = "This account is not set up correctly. Contact the administrator."



# 1. Passwords
def hash_password(plain: str) -> str:
    """Scramble a password so it can be stored safely. It cannot be turned back into the password."""
    if len(plain) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(plain.encode("utf-8"), salt=salt,
                            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    """True if `plain` matches the stored hash. A malformed hash simply returns False."""
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(plain.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A hash of a password nobody has. Used so unknown usernames take as long to reject as real ones."""
    return hash_password("not-a-real-password")


# 2. Sessions
@dataclass(frozen=True)
class Session:
    """Who is signed in. `frozen=True` means it cannot be changed after it is created."""
    user_id: int
    provider_id: int | None      # None only for the platform administrator
    role: str
    expires_at: datetime


def new_session(user_id: int, provider_id: int | None, role: str) -> Session:
    expires = datetime.now(timezone.utc) + timedelta(minutes=SESSION_MINUTES)
    return Session(user_id, provider_id, role, expires)


def is_expired(session: Session) -> bool:
    return datetime.now(timezone.utc) >= session.expires_at


# 3. Signing in

def authenticate(engine, username: str, password: str) -> tuple[Session | None, str]:
    """Check a username and password. Returns (Session, message) on success or (None, message) on failure.

    The message is safe to show on screen: it never says whether the username exists.
    """
    user = db.get_user_by_username(engine, username)

    # Unknown username: do a dummy password check anyway so the reply takes the same time
    # as for a real user. Otherwise response time would reveal which usernames exist.
    if user is None:
        verify_password(password, _dummy_hash())
        db.log_event(engine, None, None, "login_failed", "unknown username")
        return None, GENERIC_FAILURE

    # Wrong password.
    if not verify_password(password, user["password_hash"]):
        db.log_event(engine, user["id"], user["provider_id"], "login_failed", "wrong password")
        return None, GENERIC_FAILURE

    # Right password, but the account may not be allowed in.
    if not user["active"] or user["provider_status"] not in (None, "active"):
        db.log_event(engine, user["id"], user["provider_id"], "login_blocked", "account or provider disabled")
        return None, DISABLED_MESSAGE
    if user["role"] not in (ROLE_PROVIDER, ROLE_ADMIN) or (
            user["role"] == ROLE_PROVIDER and user["provider_id"] is None):
        db.log_event(engine, user["id"], user["provider_id"], "login_blocked", "bad role or missing provider")
        return None, SETUP_MESSAGE

    db.touch_login(engine, user["id"])
    db.log_event(engine, user["id"], user["provider_id"], "login_ok")
    return new_session(user["id"], user["provider_id"], user["role"]), "Signed in."

    