"""code learning note
Signing in and out, shared by BOTH sites.

require_login() is the single gate at the top of app.py and admin_app.py. It does five checks in
order and either returns a valid Session or draws the login page and stops the script:

  1. Is there a session at all?
  2. Has it expired?
  3. Is it the right KIND of account for this site? (providers on the provider site, admins on the
     admin site; each site refuses the other's accounts)
  4. Is the account still enabled? (re-checked on every page load, so disabling is immediate)
  5. Otherwise the person is shown the login form.

The login form also has a lockout: 5 failed attempts on an existing account in 15 minutes blocks
further attempts for that account until the window passes.
"""
from __future__ import annotations

import streamlit as st

from . import auth, db, theme

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
LOCKED_MESSAGE = f"Too many failed sign-in attempts. Try again in {LOCKOUT_MINUTES} minutes."

_WRONG_SITE = {
    auth.ROLE_PROVIDER: "This is the provider site. Administrators sign in on the administration site.",
    auth.ROLE_ADMIN: "This is the administration site. Provider accounts sign in on the provider site.",
}
_HEADINGS = {
    auth.ROLE_PROVIDER: ("BOTSWANA · TELECOM SERVICE INTELLIGENCE", "Sign in with your provider account."),
    auth.ROLE_ADMIN: ("PLATFORM ADMINISTRATION", "Administrator sign-in."),
}


def sign_out(message: str | None = None) -> None:
    """Forget everything about this browser session, then optionally leave a message for the login page.
    Clearing it all means nothing (filters, cached choices) can carry over to the next person."""
    st.session_state.clear()
    if message:
        st.session_state["login_message"] = message


def show_login_page(engine, required_role: str) -> None:
    """Draw the sign-in form. The rest of the app never runs unless this succeeds."""
    st.markdown("<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'] "
                "{display:none}</style>", unsafe_allow_html=True)
    eyebrow, caption = _HEADINGS[required_role]
    _, middle, _ = st.columns([1, 1.2, 1])
    with middle:
        st.markdown(f'<div class="eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
        st.title("TelecomInsight BW")
        st.caption(caption)
        if st.session_state.get("login_message"):
            st.warning(st.session_state.pop("login_message"))
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in")

        if not submitted:
            return

        wanted = username.strip().lower()
        known = db.get_user_by_username(engine, wanted) if wanted else None
        if known is not None and db.recent_failed_logins(
                engine, known["id"], LOCKOUT_MINUTES) >= MAX_FAILED_LOGINS:
            db.log_event(engine, known["id"], known["provider_id"], "login_locked",
                         "too many failed attempts")
            st.error(LOCKED_MESSAGE)
            return

        new_session, message = auth.authenticate(engine, username, password)
        if new_session is None:
            st.error(message)
        elif new_session.role != required_role:
            db.log_event(engine, new_session.user_id, new_session.provider_id, "login_wrong_site",
                         f"{new_session.role} tried the {required_role} site")
            st.error(_WRONG_SITE[required_role])
        else:
            st.session_state["auth_session"] = new_session
            st.session_state["auth_username"] = wanted        # for display only
            st.rerun()


def require_login(engine, required_role: str) -> auth.Session:
    """Return the signed-in Session, or show the login page and stop the script."""
    session = st.session_state.get("auth_session")
    if session is not None:
        if auth.is_expired(session):
            sign_out("Your session expired. Please sign in again.")
            session = None
        elif session.role != required_role:
            sign_out("That account cannot use this site.")
            session = None
        elif not db.is_account_active(engine, session.user_id):
            sign_out("Your account is disabled or no longer exists. Contact the administrator.")
            session = None
    if session is None:
        show_login_page(engine, required_role)
        st.stop()          # nothing after this line runs for a signed-out visitor
    return session


def sidebar_account(subtitle: str = "Network intelligence") -> None:
    """Logo, 'signed in as', and the sign-out button. Call inside `with st.sidebar:`."""
    st.markdown(theme.brand_lockup(subtitle), unsafe_allow_html=True)
    st.caption(f"Signed in as **{st.session_state.get('auth_username', '')}**")
    if st.button("Sign out", key="sign_out_button"):
        sign_out()
        st.rerun()