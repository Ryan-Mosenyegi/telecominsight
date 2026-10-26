"""Central configuration: paths, database URL, vocabularies and map coordinates."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_CSV = BASE_DIR / "data" / "sample_telecom_data.csv"
DEFAULT_SQLITE = BASE_DIR / "telecominsight.db"

REQUIRED_COLUMNS = [
    "date", "provider", "location", "issue_type", "download_mbps",
    "upload_mbps", "latency_ms", "satisfaction", "complaint_reported",
]
OPTIONAL_COLUMNS = ["source", "latitude", "longitude"]
RECORD_COLUMNS = REQUIRED_COLUMNS + ["source", "latitude", "longitude"]

# Where a record came from (supports the "clear data origin" feature in the literature review).
SOURCE_LABELS = {
    "survey": "Survey response",
    "public_report": "Public report / statistics",
    "network_measurement": "Network measurement",
    "industry_data": "Authorised industry data",
    "sample": "Fictional demo data",
}
ALLOWED_SOURCES = set(SOURCE_LABELS)

# Plausibility limits used during cleaning.
LIMITS = {
    "download_mbps": (0, 2000),
    "upload_mbps": (0, 2000),
    "latency_ms": (0, 10000),
    "satisfaction": (1, 5),
}
BW_LAT_RANGE = (-27.5, -17.0)
BW_LON_RANGE = (19.0, 30.0)

# Approximate city-centre coordinates. NOT tower locations, GPS observations or coverage boundaries.
LOCATION_COORDS = {
    "Gaborone": (-24.6282, 25.9231), "Francistown": (-21.1702, 27.5144),
    "Maun": (-19.9833, 23.4167), "Palapye": (-22.5460, 27.1250),
    "Serowe": (-22.3875, 26.7100), "Kasane": (-17.8000, 25.1500),
    "Molepolole": (-24.4066, 25.4950), "Kanye": (-24.9833, 25.3500),
    "Mochudi": (-24.4167, 26.1500), "Lobatse": (-25.2167, 25.6833),
    "Ghanzi": (-21.7000, 21.6500), "Jwaneng": (-24.6000, 24.7333),
}


def normalise_db_url(url: str) -> str:
    """Accept common PostgreSQL URL spellings and map them to the psycopg2 driver."""
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def database_url() -> str:
    """Read DATABASE_URL at call time; fall back to a local SQLite file."""
    return normalise_db_url(os.getenv("DATABASE_URL") or f"sqlite:///{DEFAULT_SQLITE}")


def seed_demo_enabled() -> bool:
    """Should the fictional sample CSV be loaded on the very first run?
    Yes by default (matches the deployment diagram). Set SEED_DEMO_DATA=0 on a real deployment."""
    return os.getenv("SEED_DEMO_DATA", "1").strip().lower() not in ("0", "false", "no", "off")