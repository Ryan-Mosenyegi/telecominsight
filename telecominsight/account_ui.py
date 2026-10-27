"""The 'Change password' form, shown in the sidebar of BOTH sites."""
import streamlit as st

from . import account


def render(engine, session) -> None:
    with st.form("change_password_form", clear_on_submit=True):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        confirm = st.text_input("Repeat new password", type="password")
        submitted = st.form_submit_button("Change password")
    if submitted:
        ok, message = account.change_password(engine, session.user_id, current, new, confirm)
        if ok:
            st.success(message)
        else:
            st.error(message)