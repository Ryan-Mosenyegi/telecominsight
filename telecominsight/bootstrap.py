"""Creating the very first administrator on a server.

On a hosted server you often cannot open a terminal to run create_admin.py. Instead, set two
environment variables and this file creates the administrator the first time the app starts:

    BOOTSTRAP_ADMIN_USERNAME   BOOTSTRAP_ADMIN_PASSWORD

It does nothing if an administrator already exists, so it is safe to leave switched on. After the
first start, remove BOOTSTRAP_ADMIN_PASSWORD from the environment.
"""
from __future__ import annotations

import os

from sqlalchemy.exc import IntegrityError

from . import auth, db


def ensure_admin(engine) -> bool:
    """Create the first administrator from the environment. Returns True only if one was created."""
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip().lower()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username or not password:
        return False
    if db.admin_exists(engine):
        return False
    try:
        user_id = db.create_user(engine, username, auth.hash_password(password), auth.ROLE_ADMIN)
    except ValueError as exc:                      # password too short
        raise ValueError(f"BOOTSTRAP_ADMIN_PASSWORD cannot be used: {exc}") from exc
    except IntegrityError as exc:                  # username already taken by a provider user
        raise ValueError(f"Cannot create the first administrator: the username '{username}' "
                         "already belongs to another account.") from exc
    db.log_event(engine, user_id, None, "admin_created", "bootstrap from environment")
    return True