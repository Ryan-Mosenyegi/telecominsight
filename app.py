"""TelecomInsight BW - PROVIDER site (dashboard + the provider's own uploads).

Run:  python -m streamlit run app.py
The administration site is a separate file: admin_app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from telecominsight import analysis, auth, bootstrap, config, db, login_ui, report, theme, upload_ui
from telecominsight.theme import BORDER, CYAN, MUTED, PURPLE, ROYAL_BLUE, SCALE

st.set_page_config(page_title="TelecomInsight BW | Network Intelligence", page_icon="📡",
                   layout="wide", initial_sidebar_state="expanded")
theme.inject_css()


# ---------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------
@st.cache_resource
def engine():
    eng = db.get_engine()
    db.init_db(eng)
    bootstrap.ensure_admin(eng)      # first administrator from the environment, if configured
    db.seed_if_empty(eng)            # fictional sample data on the very first run (SEED_DEMO_DATA=0 to skip)
    return eng


# `provider_id` is an argument, so Streamlit keeps a separate cached copy per provider.
# If it were not an argument, the first provider to sign in would fill the cache and every
# later provider would be shown that provider's data. ttl=60: data changed elsewhere (for
# example demo data removed on the admin site) shows up within a minute.
@st.cache_data(ttl=60, show_spinner=False)
def load_data(provider_id: int) -> pd.DataFrame:
    return db.load_records(engine(), provider_id)


def style(fig, height=340):
    fig.update_layout(
        height=height, paper_bgcolor="#FFF", plot_bgcolor="#FFF", margin=dict(l=12, r=12, t=25, b=12),
        font=dict(family="DM Sans, sans-serif", color=MUTED, size=12),
        xaxis=dict(showgrid=False, linecolor=BORDER), yaxis=dict(gridcolor="#EDF0F5", linecolor=BORDER),
        colorway=[PURPLE, ROYAL_BLUE, CYAN, "#E6A23C", "#E66A58"], legend_title_text="")
    return fig


def plot(fig, height=340):
    st.plotly_chart(style(fig, height), width="stretch")


def banner(html):
    st.markdown(f'<div class="info-banner">{html}</div>', unsafe_allow_html=True)


def fmt(v, spec):
    return "n/a" if pd.isna(v) else format(v, spec)


# ---------------------------------------------------------------------------------------------
# Login gate: nothing below this line runs until a PROVIDER user has signed in
# ---------------------------------------------------------------------------------------------
session = login_ui.require_login(engine(), auth.ROLE_PROVIDER)

with st.sidebar:
    login_ui.sidebar_account("Network intelligence")

# Everything from here on belongs to ONE provider: the one in the signed-in Session.
provider_name = db.get_provider_name(engine(), session.provider_id)
if provider_name is None:        # provider row missing: refuse to show anything
    login_ui.sign_out("This account is not linked to a provider. Contact the administrator.")
    st.rerun()

all_df = load_data(session.provider_id)

with st.sidebar:
    st.caption(f"Provider: **{provider_name}**")
    st.markdown('<div class="section-label">FILTER THE ANALYSIS</div>', unsafe_allow_html=True)
    if all_df.empty:
        st.info("There are no records for your provider yet. Use the Upload data tab.")

filtered = all_df
filters_desc = {"Provider": provider_name}
if not all_df.empty:
    with st.sidebar:
        locations = sorted(all_df["location"].unique())
        issues = sorted(all_df["issue_type"].unique())
        sources = sorted(all_df["source"].unique())
        sel_l = st.multiselect("Location", locations, default=locations)
        sel_i = st.multiselect("Issue type", issues, default=issues)
        sel_s = st.multiselect("Data source", sources, default=sources,
                               format_func=lambda s: config.SOURCE_LABELS.get(s, s))
        dmin, dmax = all_df["date"].min().date(), all_df["date"].max().date()
        sel_d = st.date_input("Date range", value=(dmin, dmax), min_value=dmin, max_value=dmax)
        st.caption("Filters apply to every KPI, chart, the map, tables and the PDF report.")

    filtered = all_df[all_df["location"].isin(sel_l) & all_df["issue_type"].isin(sel_i)
                      & all_df["source"].isin(sel_s)]
    if isinstance(sel_d, (tuple, list)) and len(sel_d) == 2:
        filtered = filtered[filtered["date"].dt.date.between(sel_d[0], sel_d[1])]
        date_txt = f"{sel_d[0]:%d %b %Y} to {sel_d[1]:%d %b %Y}"
    else:
        date_txt = f"{dmin:%d %b %Y} to {dmax:%d %b %Y}"

    def _txt(sel, allv):
        return "All" if set(sel) == set(allv) else ", ".join(sel) or "None"
    filters_desc.update({"Location": _txt(sel_l, locations), "Issue type": _txt(sel_i, issues),
                         "Source": _txt(sel_s, sources), "Dates": date_txt})

# ---------------------------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------------------------
st.markdown('<div class="eyebrow">BOTSWANA · TELECOM SERVICE INTELLIGENCE</div>', unsafe_allow_html=True)
st.title("TelecomInsight BW")
st.markdown(f'<div class="hero-subtitle">Service quality, customer experience and location-level patterns '
            f'for <strong>{provider_name}</strong>.</div>', unsafe_allow_html=True)

tab_dash, tab_upload = st.tabs(["📊 Dashboard", "⬆️ Upload data"])

# =============================================================================================
# DASHBOARD
# =============================================================================================
with tab_dash:
    if all_df.empty:
        st.info(f"No data for {provider_name} yet. Upload a CSV in the **Upload data** tab.")
    elif filtered.empty:
        st.warning("No records match your selected filters. Adjust the filters in the sidebar.")
    else:
        present = set(filtered["source"].unique())
        if present == {"sample"}:
            banner("<strong>DEMO DATA</strong> · The records shown are fictional. Map points use approximate "
                   "city-centre coordinates and are not measured network coverage or tower locations.")
        else:
            names = ", ".join(config.SOURCE_LABELS.get(s, s) for s in sorted(present))
            banner(f"<strong>DATABASE DATA</strong> · Sources in this selection: {names}. Results describe this dataset "
                   "only. Map points use approximate city-centre coordinates unless coordinates were supplied.")

        k = analysis.kpis(filtered)
        st.markdown('<div class="section-label">SERVICE QUALITY SNAPSHOT</div>', unsafe_allow_html=True)
        m = st.columns(5)
        m[0].metric("Records analysed", f"{k['records']:,}")
        m[1].metric("Complaint reports", f"{k['complaints']:,}", f"{k['complaint_rate_pct']:.0f}% of records",
                    delta_color="off")
        m[2].metric("Avg. download", f"{fmt(k['avg_download'], '.1f')} Mbps")
        m[3].metric("Avg. latency", f"{fmt(k['avg_latency'], '.0f')} ms")
        m[4].metric("Avg. satisfaction", f"{fmt(k['avg_satisfaction'], '.1f')} / 5")

        # ---- insights + report
        st.markdown("## Key observations")
        with st.container(border=True):
            for line in analysis.generate_insights(filtered):
                st.markdown(f"- {line}")
            st.caption("Rule-based observations about the selected data only, not conclusions about all users or "
                       "providers. Small groups (under 3 records) are excluded from comparisons.")
        try:
            pdf_bytes = report.build_pdf(filtered, filters_desc,
                                         ", ".join(config.SOURCE_LABELS.get(s, s) for s in sorted(present)))
            st.download_button("⬇ Download PDF summary report", pdf_bytes, "telecominsight_report.pdf", "application/pdf")
        except Exception as exc:  # report must never break the dashboard
            st.warning(f"Report could not be generated: {exc}")

        # ---- geography
        st.markdown("## Geographic service analysis")
        geo, coord_src = analysis.location_summary(filtered)
        if geo.empty:
            st.info("No recognised Botswana locations or valid coordinates. Use known location names "
                    "(e.g. Gaborone, Francistown, Maun, Palapye) or include latitude/longitude columns.")
        else:
            metric_cols = {"Complaint rate (%)": "complaint_rate_pct", "Average download (Mbps)": "avg_download_mbps",
                           "Average latency (ms)": "avg_latency_ms", "Average satisfaction (1-5)": "avg_satisfaction",
                           "Records": "records"}
            left, right = st.columns([1.65, 1], gap="large")
            with left:
                st.markdown("### Botswana location map")
                st.caption(f"Positions use {coord_src}. Marker size = number of records, not coverage.")
                map_metric = st.selectbox("Colour markers by", list(metric_cols), key="map_metric")
                col = metric_cols[map_metric]
                fig = px.scatter_geo(
                    geo, lat="latitude", lon="longitude", size="records", color=col, hover_name="location",
                    hover_data={"records": True, "complaints": True, "complaint_rate_pct": ":.1f",
                                "avg_download_mbps": ":.1f", "avg_latency_ms": ":.0f", "latitude": False,
                                "longitude": False},
                    color_continuous_scale=SCALE, projection="mercator", fitbounds="locations", height=480)
                fig.update_layout(paper_bgcolor="#FFF", margin=dict(l=0, r=0, t=5, b=0),
                                  coloraxis_colorbar=dict(title=map_metric))
                st.plotly_chart(fig, width="stretch")
            with right:
                st.markdown("### Location comparison")
                cmp_metric = st.selectbox("Compare locations by", list(metric_cols)[:4], key="cmp_metric")
                col = metric_cols[cmp_metric]
                low_is_good = col in ("complaint_rate_pct", "avg_latency_ms")
                cmp = geo.sort_values(col, ascending=not low_is_good)
                fig = px.bar(cmp, x=col, y="location", orientation="h", text=cmp[col].round(1),
                             color=col, color_continuous_scale=SCALE, labels={col: cmp_metric, "location": ""})
                fig.update_traces(textposition="outside", cliponaxis=False)
                fig.update_layout(coloraxis_showscale=False)
                plot(fig, 480)
            with st.expander("Geographic summary table"):
                tbl = geo[["location", "records", "complaints", "complaint_rate_pct", "avg_download_mbps",
                           "avg_latency_ms", "avg_satisfaction"]].round(1)
                st.dataframe(tbl, hide_index=True, width="stretch")
                st.download_button("Download geographic summary CSV", tbl.to_csv(index=False).encode(),
                                   "telecominsight_geographic_summary.csv", "text/csv")

        # ---- issues (the old cross-provider comparison chart is gone: your data contains only
        # your own provider, and comparing with others would expose their data)
        st.markdown("## Issues")
        st.markdown("### Issue types")
        basis = st.radio("Count", ["Complaint reports", "All records"], horizontal=True, key="issue_basis")
        ic = analysis.issue_counts(filtered, complaints_only=(basis == "Complaint reports")).sort_values("count")
        fig = px.bar(ic, x="count", y="issue_type", orientation="h", text="count", color="count",
                     color_continuous_scale=["#DCD5FF", PURPLE], labels={"count": basis, "issue_type": ""})
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(coloraxis_showscale=False)
        plot(fig)

        # ---- trends
        st.markdown("## Trends over time")
        freq_default = analysis.default_freq(filtered)
        freq = st.radio("Group by", list(analysis.FREQ_LABELS), index=list(analysis.FREQ_LABELS).index(freq_default),
                        format_func=analysis.FREQ_LABELS.get, horizontal=True, key="freq")
        t1, t2 = st.columns(2, gap="large")
        with t1:
            st.markdown("### Complaint reports by issue")
            it = analysis.issue_trend(filtered, freq)
            if it.empty:
                st.info("No complaint reports in this selection.")
            else:
                fig = px.bar(it, x="period", y="complaints", color="issue_type", barmode="stack",
                             labels={"period": "", "complaints": "Complaint reports"})
                plot(fig, 360)
        with t2:
            st.markdown("### Network performance")
            pm = st.radio("Metric", ["Download speed (Mbps)", "Upload speed (Mbps)", "Latency (ms)"],
                          horizontal=True, key="perf_metric")
            pt = analysis.performance_trend(filtered, freq)
            ycol = {"Download": "download_mbps", "Upload": "upload_mbps", "Latency": "latency_ms"}[pm.split()[0]]
            fig = px.line(pt, x="period", y=ycol, markers=True, labels={"period": "", ycol: pm})
            fig.update_traces(line=dict(color=PURPLE, width=3), marker=dict(size=7, color=ROYAL_BLUE))
            plot(fig, 360)

        # ---- complaints vs measurements
        st.markdown("## Do complaints match measured conditions?")
        st.caption("Compares network measurements for records with and without a complaint, linking customer "
                   "experience to measurements.")
        v1, v2 = st.columns([1.2, 1], gap="large")
        with v1:
            mm = st.selectbox("Measurement", ["Download (Mbps)", "Upload (Mbps)", "Latency (ms)"], key="box_metric")
            ycol = {"Download": "download_mbps", "Upload": "upload_mbps", "Latency": "latency_ms"}[mm.split()[0]]
            bx = filtered.assign(Group=filtered["complaint_reported"].map({1: "Complaint reported", 0: "No complaint"}))
            fig = px.box(bx, x="Group", y=ycol, color="Group", points="all",
                         color_discrete_map={"Complaint reported": "#E66A58", "No complaint": CYAN},
                         labels={ycol: mm, "Group": ""})
            fig.update_layout(showlegend=False)
            plot(fig, 380)
        with v2:
            cv = analysis.complaint_vs_performance(filtered).round(1)
            st.dataframe(cv.rename(columns={"group": "Group", "records": "Records", "avg_download_mbps": "Avg download",
                                            "avg_upload_mbps": "Avg upload", "avg_latency_ms": "Avg latency",
                                            "avg_satisfaction": "Avg satisfaction"}),
                         hide_index=True, width="stretch")
            corr = analysis.performance_correlation(filtered)
            if corr is None:
                st.info("Not enough varied data (at least 10 records with both complaint and no-complaint cases) "
                        "to calculate a relationship.")
            else:
                names = {"download_mbps": "download speed", "upload_mbps": "upload speed", "latency_ms": "latency"}
                st.markdown("**Correlation with a complaint being reported** (-1 to +1)")
                for key, val in corr.items():
                    st.markdown(f"- {names[key].capitalize()}: **{val:+.2f}**")
                st.caption("Correlation is not causation, and small datasets give unstable values.")

        # ---- records
        with st.expander("View filtered records and export data"):
            shown = filtered.sort_values("date", ascending=False)
            st.dataframe(shown, hide_index=True, width="stretch")
            st.download_button("Download filtered data as CSV", shown.to_csv(index=False).encode(),
                               "telecominsight_filtered_data.csv", "text/csv")

# =============================================================================================
# UPLOAD DATA (provider's own data only)
# =============================================================================================
with tab_upload:
    upload_ui.render(engine(), session, provider_name, on_data_changed=load_data.clear)

st.markdown('<div class="footer-note">TELECOMINSIGHT BW · Service-quality analytics prototype · '
            'Validate data before making decisions</div>', unsafe_allow_html=True)
