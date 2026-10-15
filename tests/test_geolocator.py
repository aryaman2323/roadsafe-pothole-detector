import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from backend.db import SCHEMA
from backend.geolocator import (estimate_severity, extract_gps, rebuild_clusters,
                                save_detection, summary)


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def test_severity_thresholds():
    assert estimate_severity(10, 1000) == "small"     # 1%
    assert estimate_severity(50, 1000) == "medium"    # 5%
    assert estimate_severity(100, 1000) == "large"    # 10%


def test_nearby_detections_merge_far_ones_do_not():
    conn = make_conn()
    save_detection(conn, "a.jpg", 12.97160, 77.59460, "pothole", 0.9, "small", 1, "2026-10-01 10:00:00")
    save_detection(conn, "b.jpg", 12.97162, 77.59461, "pothole", 0.8, "large", 1, "2026-10-05 10:00:00")  # ~2 m
    save_detection(conn, "c.jpg", 12.97300, 77.59460, "pothole", 0.8, "medium", 1, "2026-10-06 10:00:00")  # ~150 m
    c = conn.execute("SELECT * FROM pothole_clusters ORDER BY cluster_id").fetchall()
    assert len(c) == 2
    assert c[0]["sighting_count"] == 2
    assert c[0]["max_severity"] == "large"
    assert c[0]["first_seen"] == "2026-10-01 10:00:00"
    assert c[0]["last_seen"] == "2026-10-05 10:00:00"


def test_no_gps_detection_is_stored_but_not_clustered():
    conn = make_conn()
    save_detection(conn, "x.jpg", None, None, "pothole", 0.7, "small", 1)
    assert conn.execute("SELECT COUNT(*) FROM pothole_clusters").fetchone()[0] == 0
    assert "1 detections had no GPS" in summary(conn)


def test_rebuild_matches_incremental():
    conn = make_conn()
    for i in range(5):
        save_detection(conn, "a.jpg", 12.9716 + i * 0.00001, 77.5946, "pothole", 0.9, "medium", 1)
    rebuild_clusters(conn)
    assert conn.execute("SELECT COUNT(*) FROM pothole_clusters").fetchone()[0] == 1


def test_extract_gps_missing_exif(tmp_path):
    p = tmp_path / "plain.jpg"
    Image.new("RGB", (10, 10)).save(p)
    assert extract_gps(p) is None


def test_extract_gps_reads_exif(tmp_path):
    p = tmp_path / "gps.jpg"
    img = Image.new("RGB", (10, 10))
    exif = img.getexif()
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", (12.0, 58.0, 17.76)      # 12.9716 N
    gps[3], gps[4] = "E", (77.0, 35.0, 40.56)      # 77.5946 E
    img.save(p, exif=exif)
    lat, lng = extract_gps(p)
    assert abs(lat - 12.9716) < 1e-4 and abs(lng - 77.5946) < 1e-4
