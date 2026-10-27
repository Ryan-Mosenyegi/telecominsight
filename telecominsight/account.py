"""code learning note
Changing your own password. Pure logic, no Streamlit, so it can be tested.

change_password() returns (True, "Password updated.") or (False, "reason shown on screen").
A wrong current password is logged as a failed sign-in, so the sign-in lockout also protects
this form from someone with a stolen session trying to guess the current password.
"""
from __future__ import annotations

from . import auth, db

MAX_FAILED_ATTEMPTS = 5          # same limits as the sign-in page (login_ui.py)
LOCKOUT_MINUTES = 15

WRONG_CURRENT = "Your current password is incorrect."
LOCKED = f"Too many failed attempts. Try again in {LOCKOUT_MINUTES} minutes."


def change_password(engine, user_id: int, current: str, new: str, confirm: str) -> tuple[bool, str]:
    stored = db.get_password_hash(engine, user_id)
    if stored is None:
        return False, "This account no longer exists."

    if db.recent_failed_logins(engine, user_id, LOCKOUT_MINUTES) >= MAX_FAILED_ATTEMPTS:
        db.log_event(engine, user_id, None, "password_change_locked", "too many failed attempts")
        return False, LOCKED

    if not auth.verify_password(current, stored):
        db.log_event(engine, user_id, None, "login_failed", "wrong current password (change form)")
        return False, WRONG_CURRENT

    if new != confirm:
        return False, "The new passwords do not match."
    if new == current:
        return False, "Choose a new password that is different from the current one."
    try:
        new_hash = auth.hash_password(new)          # raises ValueError if too short
    except ValueError as exc:
        return False, str(exc)

    db.set_password_hash(engine, user_id, new_hash)
    db.log_event(engine, user_id, None, "password_changed", "by the user")
    return True, "Password updated."