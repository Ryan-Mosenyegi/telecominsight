"""PDF summary report (FR10)."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from fpdf import FPDF

from . import analysis


def _t(text) -> str:
    """fpdf core fonts are latin-1 only; replace anything else and strip markdown bold."""
    return str(text).replace("**", "").encode("latin-1", "replace").decode("latin-1")


def _table(pdf: FPDF, df: pd.DataFrame, widths: list[float]) -> None:
    pdf.set_font("Helvetica", "B", 9)
    for h, w in zip(df.columns, widths):
        pdf.cell(w, 7, _t(h), border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for _, row in df.iterrows():
        for v, w in zip(row, widths):
            pdf.cell(w, 6, _t(v), border=1)
        pdf.ln()
    pdf.ln(3)


def _heading(pdf: FPDF, text: str) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _t(text), new_x="LMARGIN", new_y="NEXT")


def build_pdf(df: pd.DataFrame, filters: dict[str, str], sources_note: str) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_fill_color(240, 238, 255)

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "TelecomInsight BW - Summary Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Generated {datetime.now():%d %b %Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 5, _t("Data: " + sources_note), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    _heading(pdf, "Filters applied")
    pdf.set_font("Helvetica", "", 9)
    for k, v in filters.items():
        pdf.multi_cell(0, 5, _t(f"{k}: {v}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    k = analysis.kpis(df)
    _heading(pdf, "Key figures")
    _table(pdf, pd.DataFrame({
        "Records": [f"{k['records']:,}"], "Complaints": [f"{k['complaints']:,}"],
        "Complaint rate": [f"{k['complaint_rate_pct']:.0f}%"],
        "Avg download": [f"{k['avg_download']:.1f} Mbps"], "Avg latency": [f"{k['avg_latency']:.0f} ms"],
    }), [30, 32, 34, 40, 34])

    _heading(pdf, "Observations")
    pdf.set_font("Helvetica", "", 10)
    for line in analysis.generate_insights(df):
        pdf.multi_cell(0, 6, _t("- " + line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    _heading(pdf, "Complaints by provider")
    p = analysis.provider_summary(df)
    _table(pdf, pd.DataFrame({
        "Provider": p["provider"], "Records": p["records"], "Complaints": p["complaints"].astype(int),
        "Rate": p["complaint_rate_pct"].map("{:.0f}%".format),
        "Avg download": p["avg_download_mbps"].map("{:.1f}".format),
        "Avg latency": p["avg_latency_ms"].map("{:.0f}".format)}), [40, 25, 28, 22, 35, 30])

    _heading(pdf, "Complaints by issue type")
    i = analysis.issue_counts(df, complaints_only=True)
    _table(pdf, i.rename(columns={"issue_type": "Issue type", "count": "Complaints"}), [90, 40])

    loc, _src = analysis.location_summary(df)
    if not loc.empty:
        _heading(pdf, "Location summary")
        loc = loc.sort_values("complaint_rate_pct", ascending=False)
        _table(pdf, pd.DataFrame({
            "Location": loc["location"], "Records": loc["records"], "Complaints": loc["complaints"].astype(int),
            "Rate": loc["complaint_rate_pct"].map("{:.0f}%".format),
            "Avg download": loc["avg_download_mbps"].map("{:.1f}".format),
            "Avg latency": loc["avg_latency_ms"].map("{:.0f}".format)}), [40, 25, 28, 22, 35, 30])

    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 4, _t("These are observations about the selected dataset only. They do not describe all users "
                            "or providers. Validate data and use authorised real data before drawing conclusions."),
                   new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
