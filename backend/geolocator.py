"""Phase 3: GPS extraction, severity estimate, and 10 m clustering."""
import logging
import math
from datetime import datetime

from geopy.distance import distance
from PIL import Image
from PIL.ExifTags import GPSTAGS

log = logging.getLogger(__name__)

CLUSTER_RADIUS_M = 10
SEVERITY_RANK = {"small": 1, "medium": 2, "large": 3}


# ---------- GPS from EXIF ----------
def _to_degrees(dms):
    d, m, s = (float(x) for x in dms)
    return d + m / 60 + s / 3600


def extract_gps(image_path):
    """Return (lat, lng) from a photo's EXIF, or None if unavailable."""
    try:
        with Image.open(image_path) as img:
            gps_ifd = img.getexif().get_ifd(0x8825)  # GPSInfo
    except Exception as exc:
        log.warning("Could not read EXIF from %s: %s", image_path, exc)
        return None

    if not gps_ifd:
        log.warning("No GPS data in %s", image_path)
        return None

    gps = {GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
    try:
        lat = _to_degrees(gps["GPSLatitude"])
        lng = _to_degrees(gps["GPSLongitude"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        log.warning("Incomplete GPS data in %s", image_path)
        return None

    if str(gps.get("GPSLatitudeRef", "N")).upper().startswith("S"):
        lat = -lat
    if str(gps.get("GPSLongitudeRef", "E")).upper().startswith("W"):
        lng = -lng
    return lat, lng


# ---------- Severity ----------
def estimate_severity(bbox_area, image_area):
    """Approximate severity from bounding-box area relative to the frame.

    small < 2%, medium 2-8%, large > 8%. This is only an estimate: a distant
    large pothole can look small (state this in the report).
    """
    ratio = bbox_area / image_area
    if ratio < 0.02:
        return "small"
    if ratio <= 0.08:
        return "medium"
    return "large"


# ---------- Clustering ----------
def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def find_cluster(conn, lat, lng, radius_m=CLUSTER_RADIUS_M):
    """Nearest existing cluster centre within radius_m, or None."""
    pad_lat = 0.0002  # ~22 m: cheap pre-filter before exact geopy distance
    pad_lng = pad_lat / max(math.cos(math.radians(lat)), 0.01)
    rows = conn.execute(
        """SELECT * FROM pothole_clusters
           WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?""",
        (lat - pad_lat, lat + pad_lat, lng - pad_lng, lng + pad_lng),
    ).fetchall()

    best, best_d = None, radius_m
    for row in rows:
        d = distance((lat, lng), (row["latitude"], row["longitude"])).meters
        if d <= best_d:
            best, best_d = row, d
    return best


def attach_to_cluster(conn, det_id, lat, lng, damage_class, severity, when):
    cluster = find_cluster(conn, lat, lng)
    if cluster is None:
        cur = conn.execute(
            """INSERT INTO pothole_clusters
               (latitude, longitude, damage_class, max_severity,
                sighting_count, first_seen, last_seen)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (lat, lng, damage_class, severity, when, when),
        )
        cid = cur.lastrowid
    else:
        cid = cluster["cluster_id"]
        n = cluster["sighting_count"]
        new_lat = (cluster["latitude"] * n + lat) / (n + 1)  # running average
        new_lng = (cluster["longitude"] * n + lng) / (n + 1)
        max_sev = max(cluster["max_severity"], severity, key=SEVERITY_RANK.get)
        conn.execute(
            """UPDATE pothole_clusters
               SET latitude=?, longitude=?, max_severity=?, sighting_count=?,
                   first_seen=?, last_seen=?
               WHERE cluster_id=?""",
            (new_lat, new_lng, max_sev, n + 1,
             min(cluster["first_seen"], when), max(cluster["last_seen"], when), cid),
        )

    conn.execute("UPDATE detections SET cluster_id=? WHERE id=?", (cid, det_id))
    # most common damage class among the cluster's detections
    top = conn.execute(
        """SELECT damage_class FROM detections WHERE cluster_id=?
           GROUP BY damage_class ORDER BY COUNT(*) DESC LIMIT 1""",
        (cid,),
    ).fetchone()
    conn.execute("UPDATE pothole_clusters SET damage_class=? WHERE cluster_id=?",
                 (top["damage_class"], cid))
    return cid


def save_detection(conn, image_path, lat, lng, damage_class, confidence,
                   severity, bbox_area, when=None):
    """Insert a detection; if it has GPS, assign it to a cluster."""
    when = when or _now()
    cur = conn.execute(
        """INSERT INTO detections
           (image_path, latitude, longitude, damage_class, confidence,
            severity, bbox_area, detection_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(image_path), lat, lng, damage_class, confidence, severity, bbox_area, when),
    )
    det_id = cur.lastrowid
    if lat is not None and lng is not None:
        attach_to_cluster(conn, det_id, lat, lng, damage_class, severity, when)
    conn.commit()
    return det_id


def rebuild_clusters(conn):
    """Recompute all clusters from raw detections (sorted by latitude)."""
    conn.execute("UPDATE detections SET cluster_id=NULL")
    conn.execute("DELETE FROM pothole_clusters")
    rows = conn.execute(
        """SELECT * FROM detections WHERE latitude IS NOT NULL
           ORDER BY latitude"""
    ).fetchall()
    for r in rows:
        attach_to_cluster(conn, r["id"], r["latitude"], r["longitude"],
                          r["damage_class"], r["severity"], r["detection_date"])
    conn.commit()


def summary(conn):
    raw = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
    no_gps = conn.execute(
        "SELECT COUNT(*) FROM detections WHERE latitude IS NULL").fetchone()[0]
    clusters = conn.execute("SELECT COUNT(*) FROM pothole_clusters").fetchone()[0]
    return (f"{raw} raw detections clustered into {clusters} unique potholes. "
            f"{no_gps} detections had no GPS data.")
