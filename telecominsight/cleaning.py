"""Data cleaning and validation (FR04, NFR02).

`clean_dataframe` never silently discards data: every dropped or corrected row is counted
in the returned `CleaningReport`, which the app shows to the user before saving.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import config

_BOOL_MAP = {"1": 1, "1.0": 1, "true": 1, "yes": 1, "y": 1, "t": 1,
             "0": 0, "0.0": 0, "false": 0, "no": 0, "n": 0, "f": 0}


@dataclass
class CleaningReport:
    rows_in: int = 0
    rows_out: int = 0
    dropped: dict = field(default_factory=dict)   # reason -> rows removed
    fixes: dict = field(default_factory=dict)     # description -> values corrected / blanked

    def _drop(self, reason: str, n: int) -> None:
        if n:
            self.dropped[reason] = self.dropped.get(reason, 0) + int(n)

    def _fix(self, what: str, n: int) -> None:
        if n:
            self.fixes[what] = self.fixes.get(what, 0) + int(n)

    def summary_frame(self) -> pd.DataFrame:
        rows = [("Rows received", self.rows_in, "")]
        rows += [("Dropped", n, why) for why, n in self.dropped.items()]
        rows += [("Corrected", n, what) for what, n in self.fixes.items()]
        rows.append(("Rows kept", self.rows_out, ""))
        return pd.DataFrame(rows, columns=["Action", "Count", "Detail"])


def _standardise_text(series: pd.Series, report: CleaningReport, label: str) -> pd.Series:
    s = series.fillna("").astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    blank = s == ""
    report._fix(f"{label}: blank value set to 'Unknown'", blank.sum())
    s = s.mask(blank, "Unknown")
    if s.empty:
        return s
    # Merge spelling/case variants ("gaborone", "Gaborone ") onto the most common spelling.
    key = s.str.lower()
    canon = s.groupby(key).agg(lambda x: x.value_counts().idxmax())
    out = key.map(canon)
    report._fix(f"{label}: spelling/case variants merged", (out != s).sum())
    return out


def clean_dataframe(raw: pd.DataFrame, default_source: str = "survey") -> tuple[pd.DataFrame, CleaningReport]:
    """Validate and clean a raw dataset. Raises ValueError if required columns are missing."""
    if default_source not in config.ALLOWED_SOURCES:
        raise ValueError(f"Unknown source '{default_source}'.")

    df = raw.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in config.REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("CSV is missing required columns: " + ", ".join(missing))

    report = CleaningReport(rows_in=len(df))
    df = df.reset_index(drop=True)

    # --- text fields -------------------------------------------------------------------------
    for col in ("provider", "location", "issue_type"):
        df[col] = _standardise_text(df[col], report, col)

    # --- dates -------------------------------------------------------------------------------
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    keep = df["date"].notna()
    report._drop("missing or unreadable date", (~keep).sum())
    df = df[keep]

    # --- numeric measurements ----------------------------------------------------------------
    for col in ("download_mbps", "upload_mbps", "latency_ms", "satisfaction"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Core measurements: a row without a usable download speed or latency is dropped.
    for col in ("download_mbps", "latency_ms"):
        lo, hi = config.LIMITS[col]
        bad = ~df[col].between(lo, hi)  # NaN is also "not between"
        report._drop(f"{col} missing or outside {lo}-{hi}", bad.sum())
        df = df[~bad]

    # Secondary fields: an invalid value is blanked, the row is kept.
    for col in ("upload_mbps", "satisfaction"):
        lo, hi = config.LIMITS[col]
        bad = df[col].notna() & ~df[col].between(lo, hi)
        report._fix(f"{col}: value outside {lo}-{hi} blanked", bad.sum())
        df.loc[bad, col] = float("nan")

    # --- complaint flag ----------------------------------------------------------------------
    df["complaint_reported"] = df["complaint_reported"].astype(str).str.strip().str.lower().map(_BOOL_MAP)
    bad = df["complaint_reported"].isna()
    report._drop("complaint_reported not recognisable as yes/no", bad.sum())
    df = df[~bad]
    df["complaint_reported"] = df["complaint_reported"].astype(int)

    # --- source ------------------------------------------------------------------------------
    if "source" in df.columns:
        src = df["source"].fillna("").astype(str).str.strip().str.lower().str.replace(r"[\s-]+", "_", regex=True)
        invalid = ~src.isin(config.ALLOWED_SOURCES)
        report._fix(f"source: missing/unknown value replaced with '{default_source}'", invalid.sum())
        df["source"] = src.mask(invalid, default_source)
    else:
        df["source"] = default_source

    # --- optional coordinates ----------------------------------------------------------------
    for col in ("latitude", "longitude"):
        df[col] = pd.to_numeric(df[col], errors="coerce") if col in df.columns else float("nan")
    (lat_lo, lat_hi), (lon_lo, lon_hi) = config.BW_LAT_RANGE, config.BW_LON_RANGE
    outside = df["latitude"].notna() & df["longitude"].notna() & ~(
        df["latitude"].between(lat_lo, lat_hi) & df["longitude"].between(lon_lo, lon_hi))
    half = df["latitude"].isna() != df["longitude"].isna()
    report._fix("coordinates outside Botswana or incomplete: blanked", (outside | half).sum())
    df.loc[outside | half, ["latitude", "longitude"]] = float("nan")

    # --- duplicates --------------------------------------------------------------------------
    dup = df.duplicated(subset=config.RECORD_COLUMNS, keep="first")
    report._drop("exact duplicate row", dup.sum())
    df = df[~dup]

    df = df[config.RECORD_COLUMNS].sort_values("date").reset_index(drop=True)
    report.rows_out = len(df)
    return df, report
