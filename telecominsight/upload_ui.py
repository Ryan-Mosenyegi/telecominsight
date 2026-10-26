"""code learning note
The provider's upload tab.

A provider uploads their own CSV. The pipeline is:
  1. read the file                      (pandas)
  2. clean and validate it              (cleaning.clean_dataframe, which never silently drops data)
  3. show the cleaning summary + preview
  4. save ONLY the rows that belong to this provider   (db.save_provider_records)

The provider is always the one in the signed-in Session. Nothing in the uploaded file can change it.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import auth, cleaning, config, db


def render(engine, session, provider_name: str, on_data_changed) -> None:
    """Draw the upload tab. `on_data_changed` is called after a save so cached dashboards refresh."""
    if session.role != auth.ROLE_PROVIDER or session.provider_id is None:   # second lock
        st.error("Provider access required.")
        st.stop()

    if "upload_flash" in st.session_state:
        st.success(st.session_state.pop("upload_flash"))

    st.markdown("### Upload your data")
    st.caption("Required columns: " + ", ".join(config.REQUIRED_COLUMNS) +
               ". Optional: source, latitude, longitude. Do not upload personal information.")
    st.caption(f"The `provider` column must say **{provider_name}**. Rows that name a different provider "
               "are not saved.")

    up = st.file_uploader("CSV file", type=["csv"], key="provider_upload")
    sources = [s for s in config.SOURCE_LABELS if s != "sample"]       # real data is never "demo data"
    src = st.selectbox("Source of this data", sources, format_func=config.SOURCE_LABELS.get,
                       help="Used for rows that do not have their own 'source' value.")

    if up is not None:
        try:
            raw = pd.read_csv(up)
            cleaned, rep = cleaning.clean_dataframe(raw, default_source=src)
        except Exception as exc:
            st.error(f"This file could not be processed: {exc}")
        else:
            st.markdown("#### Cleaning summary")
            st.dataframe(rep.summary_frame(), hide_index=True, width="stretch")
            st.markdown("#### Preview of cleaned records")
            st.dataframe(cleaned.head(20), hide_index=True, width="stretch")

            own = cleaned["provider"].str.strip().str.lower() == provider_name.strip().lower()
            other = int((~own).sum())
            savable = int(own.sum())
            if other:
                names = ", ".join(sorted(set(cleaned.loc[~own, "provider"])))[:200]
                st.warning(f"{other:,} of {len(cleaned):,} cleaned rows name a different provider ({names}) "
                           f"and will NOT be saved. Fix the provider column and upload again if they are yours.")
            if cleaned.empty:
                st.warning("No usable records remain after cleaning.")
            elif savable == 0:
                st.error(f"None of the rows name {provider_name}, so nothing can be saved.")
            elif st.button(f"Save {savable:,} records for {provider_name}"):
                ins, skip, rej = db.save_provider_records(
                    engine, session.provider_id, cleaned, up.name, session.user_id)
                on_data_changed()
                st.session_state["upload_flash"] = (
                    f"Saved {ins:,} new records ({skip:,} duplicates skipped, {rej:,} rejected).")
                st.rerun()

    n_demo = db.count_provider_source(engine, session.provider_id, "sample")
    if n_demo:
        st.markdown("### Demo data")
        st.caption(f"{n_demo:,} fictional demo records are stored under {provider_name}.")
        if st.button("Remove fictional demo data"):
            n = db.delete_provider_source(engine, session.provider_id, "sample")
            on_data_changed()
            st.session_state["upload_flash"] = f"Removed {n:,} demo records."
            st.rerun()

    st.markdown("### Your upload history")
    st.dataframe(db.list_provider_uploads(engine, session.provider_id), hide_index=True, width="stretch")