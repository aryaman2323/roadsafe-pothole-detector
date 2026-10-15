"""SQLite storage: raw detections + deduplicated pothole clusters."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "roadsafe.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pothole_clusters (
    cluster_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    latitude       REAL NOT NULL,
    longitude      REAL NOT NULL,
    damage_class   TEXT,
    max_severity   TEXT,
    sighting_count INTEGER NOT NULL DEFAULT 1,
    first_seen     TEXT,
    last_seen      TEXT
);

CREATE TABLE IF NOT EXISTS detections (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path     TEXT,
    latitude       REAL,          -- NULL when the photo had no GPS EXIF
    longitude      REAL,
    damage_class   TEXT NOT NULL,
    confidence     REAL,
    severity       TEXT,
    bbox_area      REAL,
    detection_date TEXT,
    cluster_id     INTEGER REFERENCES pothole_clusters(cluster_id)
);
"""


def get_conn(db_path=DB_PATH):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
