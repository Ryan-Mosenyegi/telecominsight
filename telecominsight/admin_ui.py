"""code learning note
The administrator's pages. Shown ONLY on the admin site (admin_app.py).

The administrator controls access and oversees the platform, but never sees a provider's rows,
charts or analytics, and does not upload data (providers upload their own).
render() checks the role again: two locks on the same door.

Three tabs:
  1. Accounts      - add providers and users, enable/disable, reset passwords, delete (permanent)
  2. Data overview - counts per provider, upload batches, remove the fictional demo data
  3. Access log    - sign-ins, failures, uploads, admin actions
"""
from __future__ import annotations

import streamlit as st
from sqlalchemy.exc import IntegrityError

from . import auth, db


def _flash(message: str) -> None:
    """Remember a message across the st.rerun() that follows a successful action."""
    st.session_state["admin_flash"] = message


def render(engine, session) -> None:
    if session.role != auth.ROLE_ADMIN:           # second lock
        st.error("Administrator access required.")
        st.stop()

    st.markdown('<div class="eyebrow">PLATFORM ADMINISTRATION</div>', unsafe_allow_html=True)
    st.title("Administration")
    st.caption("Manage provider accounts and access. Providers upload and see their own data; "
               "administrators never see provider records or analytics.")
    if "admin_flash" in st.session_state:
        st.success(st.session_state.pop("admin_flash"))

    tab_accounts, tab_data, tab_log = st.tabs(["👥 Accounts", "🗄️ Data overview", "📜 Access log"])
    with tab_accounts:
        _accounts_tab(engine, session)
    with tab_data:
        _data_tab(engine, session)
    with tab_log:
        st.caption("Newest first. Passwords are never logged.")
        st.dataframe(db.recent_access_log(engine), hide_index=True, width="stretch")


# ---------------------------------------------------------------------------------------------
# 1. Accounts
# ---------------------------------------------------------------------------------------------
def _accounts_tab(engine, session) -> None:
    prov = db.list_providers(engine)
    usr = db.list_users(engine)
    prov_ids = prov["id"].tolist()
    prov_names = dict(zip(prov_ids, prov["name"].tolist()))

    st.markdown("### Providers")
    st.dataframe(prov, hide_index=True, width="stretch")

    with st.form("new_provider", clear_on_submit=True):
        name = st.text_input("New provider name",
                             help="Providers upload data whose 'provider' column matches this name.")
        if st.form_submit_button("Add provider"):
            name = name.strip()
            if not name:
                st.error("Enter a provider name.")
            elif name.lower() in {n.lower() for n in prov_names.values()}:
                st.error("A provider with that name already exists.")
            else:
                try:
                    db.create_provider(engine, name)
                except IntegrityError:
                    st.error("A provider with that name already exists.")
                else:
                    db.log_event(engine, session.user_id, None, "provider_created", name)
                    _flash(f"Provider '{name}' added.")
                    st.rerun()

    if prov_ids:
        with st.form("provider_status"):
            pid = st.selectbox("Provider", prov_ids, format_func=prov_names.get)
            status = st.selectbox("Set status to", ["active", "disabled"])
            if st.form_submit_button("Update provider status"):
                db.set_provider_status(engine, int(pid), status)
                db.log_event(engine, session.user_id, int(pid), "provider_status", status)
                _flash(f"{prov_names[pid]} is now {status}."
                       + (" Its users can no longer sign in." if status == "disabled" else ""))
                st.rerun()

    st.markdown("### Users")
    st.dataframe(usr, hide_index=True, width="stretch")

    with st.form("new_user", clear_on_submit=True):
        st.markdown("**Add a user**")
        username = st.text_input("Username")
        password = st.text_input("Temporary password", type="password",
                                 help=f"At least {auth.MIN_PASSWORD_LENGTH} characters.")
        role = st.selectbox("Role", [auth.ROLE_PROVIDER, auth.ROLE_ADMIN])
        provider_id = st.selectbox("Provider (required for provider users)", [None] + prov_ids,
                                   format_func=lambda i: "(none)" if i is None else prov_names[i])
        if st.form_submit_button("Add user"):
            if not username.strip():
                st.error("Enter a username.")
            elif role == auth.ROLE_PROVIDER and provider_id is None:
                st.error("A provider user must belong to a provider.")
            elif role == auth.ROLE_ADMIN and provider_id is not None:
                st.error("An administrator must not belong to a provider. Choose (none).")
            else:
                try:
                    pw_hash = auth.hash_password(password)
                    new_id = db.create_user(engine, username, pw_hash, role,
                                            None if role == auth.ROLE_ADMIN else provider_id)
                except ValueError as exc:          # password too short
                    st.error(str(exc))
                except IntegrityError:
                    st.error("That username is already taken.")
                else:
                    db.log_event(engine, session.user_id, provider_id, "user_created",
                                 f"{username.strip().lower()} ({role})")
                    _flash(f"User '{username.strip().lower()}' added (id {new_id}).")
                    st.rerun()

    if not usr.empty:
        user_ids = usr["id"].tolist()
        labels = {i: f"{u} ({r})" for i, u, r in zip(user_ids, usr["username"], usr["role"])}

        with st.form("user_active"):
            uid = st.selectbox("User", user_ids, format_func=labels.get, key="active_user")
            action = st.selectbox("Action", ["Disable", "Enable"])
            if st.form_submit_button("Apply"):
                if uid == session.user_id and action == "Disable":
                    st.error("You cannot disable your own account.")
                else:
                    db.set_user_active(engine, int(uid), action == "Enable")
                    db.log_event(engine, session.user_id, None, "user_" + action.lower() + "d", labels[uid])
                    _flash(f"{labels[uid]}: {action.lower()}d.")
                    st.rerun()

        with st.form("reset_password", clear_on_submit=True):
            uid = st.selectbox("User", user_ids, format_func=labels.get, key="reset_user")
            new_pw = st.text_input("New password", type="password")
            if st.form_submit_button("Reset password"):
                try:
                    db.set_password_hash(engine, int(uid), auth.hash_password(new_pw))
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    db.log_event(engine, session.user_id, None, "password_reset", labels[uid])
                    _flash(f"Password reset for {labels[uid]}.")
                    st.rerun()

    _danger_zone(engine, session, prov, usr)


# ---------------------------------------------------------------------------------------------
# Permanent deletion
# ---------------------------------------------------------------------------------------------
def _danger_zone(engine, session, prov, usr) -> None:
    """Delete a user or a whole provider. Permanent, so: preview first, then type the name to confirm.

    The widgets carry a counter ("nonce") in their keys. After a successful delete the counter goes
    up, which gives every widget a fresh empty state. (Streamlit does not let you clear a text box
    after it has been drawn.)
    """
    nonce = st.session_state.setdefault("delete_nonce", 0)

    with st.expander("🗑️ Delete users and providers (permanent)"):
        st.warning("Deleting cannot be undone. To block someone but keep their data, use **Disable** "
                   "above instead. Make a database backup before deleting a provider.")

        # ---- delete a user
        st.markdown("#### Delete a user")
        if usr.empty:
            st.caption("There are no users.")
        else:
            user_ids = usr["id"].tolist()
            names = dict(zip(user_ids, usr["username"].tolist()))
            roles = dict(zip(user_ids, usr["role"].tolist()))
            uid = st.selectbox("User to delete", user_ids, key=f"del_user_pick_{nonce}",
                               format_func=lambda i: f"{names[i]} ({roles[i]})")
            n_log = db.count_user_log_entries(engine, int(uid))
            st.caption(f"This removes the account **{names[uid]}** and its {n_log:,} access-log entries. "
                       "Records this person uploaded stay with their provider.")
            typed = st.text_input(f"Type  {names[uid]}  and press Enter to confirm",
                                  key=f"del_user_confirm_{nonce}")
            matches = typed.strip().lower() == names[uid].lower()
            if st.button("Delete user permanently", key=f"del_user_btn_{nonce}", disabled=not matches):
                try:
                    result = db.delete_user(engine, int(uid), acting_user_id=session.user_id)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    db.log_event(engine, session.user_id, None, "user_deleted",
                                 f"{result['username']} ({result['role']})")
                    st.session_state["delete_nonce"] = nonce + 1
                    _flash(f"User '{result['username']}' deleted "
                           f"({result['log_entries']:,} log entries removed).")
                    st.rerun()

        # ---- delete a provider
        st.markdown("#### Delete a provider and everything related to it")
        if prov.empty:
            st.caption("There are no providers.")
        else:
            prov_ids = prov["id"].tolist()
            pnames = dict(zip(prov_ids, prov["name"].tolist()))
            pid = st.selectbox("Provider to delete", prov_ids, format_func=pnames.get,
                               key=f"del_prov_pick_{nonce}")
            preview = db.provider_deletion_preview(engine, int(pid))
            if preview is not None:
                st.error(f"Deleting **{preview['name']}** will permanently remove: "
                         f"{preview['users']:,} user account(s), {preview['records']:,} record(s), "
                         f"{preview['log_entries']:,} access-log entr(ies) and "
                         f"{preview['batches']:,} upload batch(es) that belong only to this provider.")
                typed = st.text_input(f"Type  {preview['name']}  and press Enter to confirm",
                                      key=f"del_prov_confirm_{nonce}")
                matches = typed.strip().lower() == preview["name"].lower()
                if st.button("Delete provider permanently", key=f"del_prov_btn_{nonce}",
                             disabled=not matches):
                    try:
                        result = db.delete_provider(engine, int(pid))
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        db.log_event(engine, session.user_id, None, "provider_deleted",
                                     f"{result['name']}: {result['users']} users, "
                                     f"{result['records']} records")
                        st.session_state["delete_nonce"] = nonce + 1
                        _flash(f"Provider '{result['name']}' deleted: {result['users']:,} user(s), "
                               f"{result['records']:,} record(s), {result['log_entries']:,} log "
                               f"entries, {result['batches']:,} batch(es).")
                        st.rerun()


# ---------------------------------------------------------------------------------------------
# 2. Data overview (counts and batches only, never the rows themselves)
# ---------------------------------------------------------------------------------------------
def _data_tab(engine, session) -> None:
    prov = db.list_providers(engine)
    m = st.columns(3)
    m[0].metric("Providers", f"{len(prov):,}")
    m[1].metric("Users", f"{len(db.list_users(engine)):,}")
    m[2].metric("Records stored", f"{db.count_records(engine):,}")

    st.markdown("### Records per provider name")
    counts = db.record_counts_by_provider(engine)
    known = {n.lower() for n in prov["name"]}
    counts["has_provider_account"] = counts["provider"].str.lower().isin(known)
    st.dataframe(counts, hide_index=True, width="stretch")
    if not counts.empty and not counts["has_provider_account"].all():
        st.warning("Some records use a provider name that has no provider account. Nobody can see those "
                   "records until a provider with exactly that name (ignoring capitals) is added.")

    n_demo = db.count_source(engine, "sample")
    if n_demo:
        st.markdown("### Fictional demo data")
        st.caption(f"{n_demo:,} demo records are stored. Provider dashboards refresh within a minute "
                   "of removal.")
        if st.button("Remove all fictional demo data"):
            n = db.delete_source(engine, "sample")
            db.log_event(engine, session.user_id, None, "demo_data_removed", f"{n} records")
            _flash(f"Removed {n:,} demo records.")
            st.rerun()

    st.markdown("### Upload batches (all providers)")
    st.dataframe(db.list_batches(engine), hide_index=True, width="stretch")