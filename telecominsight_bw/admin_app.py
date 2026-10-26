"""TelecomInsight BW - ADMINISTRATION site (accounts, access and oversight).

Run:  python -m streamlit run admin_app.py --server.port 8502
Providers use a different file (app.py). Each site refuses the other's accounts.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from telecominsight import admin_ui, auth, bootstrap, db, login_ui, theme

st.set_page_config(page_title="TelecomInsight BW | Administration", page_icon="🛡️",
                   layout="wide", initial_sidebar_state="expanded")
theme.inject_css()


@st.cache_resource
def engine():
    eng = db.get_engine()
    db.init_db(eng)
    bootstrap.ensure_admin(eng)      # first administrator from the environment, if configured
    return eng


session = login_ui.require_login(engine(), auth.ROLE_ADMIN)

with st.sidebar:
    login_ui.sidebar_account("Administration")

admin_ui.render(engine(), session)

st.markdown('<div class="footer-note">TELECOMINSIGHT BW · Administration · Access and accounts only</div>',
            unsafe_allow_html=True)