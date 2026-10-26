"""Analysis functions (FR05, FR09). Pure pandas: no Streamlit, so everything is unit-testable."""
from __future__ import annotations

import pandas as pd

from . import config

FREQ_LABELS = {"D": "Daily", "W": "Weekly", "M": "Monthly"}


def default_freq(df: pd.DataFrame) -> str:
    if df.empty:
        return "D"
    span = (df["date"].max() - df["date"].min()).days
    return "M" if span >= 60 else "W" if span >= 14 else "D"


def _period(df: pd.DataFrame, freq: str) -> pd.Series:
    return df["date"].dt.to_period(freq).dt.start_time


def period_label(ts: pd.Timestamp, freq: str) -> str:
    return {"M": ts.strftime("%b %Y"), "W": "week of " + ts.strftime("%d %b %Y")}.get(freq, ts.strftime("%d %b %Y"))


def kpis(df: pd.DataFrame) -> dict:
    n = len(df)
    complaints = int(df["complaint_reported"].sum()) if n else 0
    return {
        "records": n,
        "complaints": complaints,
        "complaint_rate_pct": (complaints / n * 100) if n else 0.0,
        "avg_download": df["download_mbps"].mean() if n else float("nan"),
        "avg_upload": df["upload_mbps"].mean() if n else float("nan"),
        "avg_latency": df["latency_ms"].mean() if n else float("nan"),
        "avg_satisfaction": df["satisfaction"].mean() if n else float("nan"),
    }


def issue_counts(df: pd.DataFrame, complaints_only: bool = True) -> pd.DataFrame:
    base = df[df["complaint_reported"] == 1] if complaints_only else df
    out = base.groupby("issue_type").size().reset_index(name="count")
    return out.sort_values("count", ascending=False).reset_index(drop=True)


def _group_summary(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(by).agg(
        records=("complaint_reported", "size"),
        complaints=("complaint_reported", "sum"),
        avg_download_mbps=("download_mbps", "mean"),
        avg_upload_mbps=("upload_mbps", "mean"),
        avg_latency_ms=("latency_ms", "mean"),
        avg_satisfaction=("satisfaction", "mean"),
    ).reset_index()
    g["complaint_rate_pct"] = g["complaints"] / g["records"] * 100
    return g


def provider_summary(df: pd.DataFrame) -> pd.DataFrame:
    return _group_summary(df, "provider").sort_values("complaints", ascending=False).reset_index(drop=True)


def location_summary(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Per-location summary with map coordinates. Returns (summary, description of coordinate source)."""
    d = df.copy()
    has_real = d["latitude"].notna() & d["longitude"].notna()
    approx = d["location"].map(config.LOCATION_COORDS)
    d["latitude"] = d["latitude"].where(has_real, approx.map(lambda t: t[0] if isinstance(t, tuple) else None))
    d["longitude"] = d["longitude"].where(has_real, approx.map(lambda t: t[1] if isinstance(t, tuple) else None))
    d = d.dropna(subset=["latitude", "longitude"])
    if d.empty:
        return pd.DataFrame(), "no recognised locations"
    g = _group_summary(d, "location")
    coords = d.groupby("location")[["latitude", "longitude"]].mean().reset_index()
    g = g.merge(coords, on="location")
    if has_real.all():
        src = "supplied coordinates"
    elif has_real.any():
        src = "supplied coordinates where available, otherwise approximate city-centre coordinates"
    else:
        src = "approximate city-centre coordinates"
    return g, src


def complaint_trend(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    d = df.assign(period=_period(df, freq))
    out = d.groupby("period").agg(records=("complaint_reported", "size"),
                                  complaints=("complaint_reported", "sum")).reset_index()
    out["complaint_rate_pct"] = out["complaints"] / out["records"] * 100
    return out


def issue_trend(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Complaint reports per issue type per period: shows which issues are rising or falling."""
    c = df[df["complaint_reported"] == 1]
    if c.empty:
        return pd.DataFrame(columns=["period", "issue_type", "complaints"])
    return (c.assign(period=_period(c, freq)).groupby(["period", "issue_type"])
            .size().reset_index(name="complaints"))


def performance_trend(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    d = df.assign(period=_period(df, freq))
    return d.groupby("period").agg(download_mbps=("download_mbps", "mean"),
                                   upload_mbps=("upload_mbps", "mean"),
                                   latency_ms=("latency_ms", "mean")).reset_index()


def complaint_vs_performance(df: pd.DataFrame) -> pd.DataFrame:
    """Average measurements for records with and without a complaint (links complaints to measurements)."""
    d = df.assign(group=df["complaint_reported"].map({1: "Complaint reported", 0: "No complaint"}))
    out = d.groupby("group").agg(
        records=("group", "size"), avg_download_mbps=("download_mbps", "mean"),
        avg_upload_mbps=("upload_mbps", "mean"), avg_latency_ms=("latency_ms", "mean"),
        avg_satisfaction=("satisfaction", "mean")).reset_index()
    return out


def performance_correlation(df: pd.DataFrame, min_rows: int = 10) -> dict | None:
    """Pearson correlation between complaint flag (0/1) and each measurement. None if too little data."""
    if len(df) < min_rows or df["complaint_reported"].nunique() < 2:
        return None
    res = {}
    for col in ("download_mbps", "upload_mbps", "latency_ms"):
        if df[col].nunique() > 1:
            res[col] = float(df["complaint_reported"].corr(df[col]))
    return res or None


def generate_insights(df: pd.DataFrame, min_records: int = 3) -> list[str]:
    """Rule-based plain-language observations about the selected data (FR09)."""
    if df.empty:
        return []
    out: list[str] = []
    k = kpis(df)
    out.append(f"{k['records']:,} records in this selection; {k['complaints']:,} "
               f"({k['complaint_rate_pct']:.0f}%) include a complaint report.")

    ic = issue_counts(df, complaints_only=True)
    if not ic.empty:
        out.append(f"The most frequently complained-about issue is **{ic.iloc[0]['issue_type']}** "
                   f"({int(ic.iloc[0]['count'])} of {k['complaints']} complaints).")

    for label, summ, col in (("provider", provider_summary(df), "provider"),
                             ("location", _group_summary(df, "location"), "location")):
        s = summ[summ["records"] >= min_records]
        if len(s) >= 2:
            hi = s.sort_values("complaint_rate_pct", ascending=False).iloc[0]
            lo = s.sort_values("complaint_rate_pct", ascending=True).iloc[0]
            if hi["complaint_rate_pct"] > lo["complaint_rate_pct"]:
                out.append(f"Highest complaint rate by {label}: **{hi[col]}** ({hi['complaint_rate_pct']:.0f}% of "
                           f"{int(hi['records'])} records); lowest: **{lo[col]}** ({lo['complaint_rate_pct']:.0f}% of "
                           f"{int(lo['records'])} records).")

    cv = complaint_vs_performance(df).set_index("group")
    if {"Complaint reported", "No complaint"} <= set(cv.index) and \
            cv["records"].min() >= min_records:
        c, n = cv.loc["Complaint reported"], cv.loc["No complaint"]
        out.append(f"Records with a complaint average {c['avg_download_mbps']:.1f} Mbps download and "
                   f"{c['avg_latency_ms']:.0f} ms latency, compared with {n['avg_download_mbps']:.1f} Mbps and "
                   f"{n['avg_latency_ms']:.0f} ms for records without one.")

    freq = default_freq(df)
    tr = complaint_trend(df, freq)
    if len(tr) >= 2:
        a, b = tr.iloc[-2], tr.iloc[-1]
        verb = "rose" if b["complaints"] > a["complaints"] else "fell" if b["complaints"] < a["complaints"] else "stayed the same"
        out.append(f"Complaint reports {verb} from {int(a['complaints'])} ({period_label(a['period'], freq)}) to "
                   f"{int(b['complaints'])} ({period_label(b['period'], freq)}); the latest period may be incomplete.")
    return out
