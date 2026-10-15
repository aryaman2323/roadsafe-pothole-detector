"""Phase 4: FastAPI backend.   Run:  uvicorn backend.main:app --reload"""
import io
import uuid
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image

from .db import ROOT, get_conn
from .pipeline import detect_image, load_model

app = FastAPI(title="RoadSafe AI", description="Pothole detection + map API")

UPLOAD_DIR = ROOT / "data" / "uploads"
MAX_BYTES = 10 * 1024 * 1024
EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

_model = None


def get_model():
    global _model
    if _model is None:
        _model = load_model()
    return _model


@app.post("/detect")
def detect(file: UploadFile = File(...)):
    """Upload a road photo -> detections (JSON). Stores them + updates clusters."""
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image larger than 10 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.verify()
    except Exception:
        raise HTTPException(400, "File is not a valid image.")
    if fmt not in EXT:
        raise HTTPException(400, "Only JPEG, PNG or WEBP images are supported.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{EXT[fmt]}"
    path.write_bytes(data)

    conn = get_conn()
    try:
        detections, gps_found = detect_image(get_model(), path, conn)
    finally:
        conn.close()

    resp = {"image": path.name, "gps_found": gps_found, "detections": detections}
    if not gps_found:
        resp["warning"] = ("No GPS data in image: detections returned but "
                           "not placed on the map.")
    return resp


def _cluster_rows(conn, severity, damage_class, start_date, end_date,
                  min_lat, max_lat, min_lng, max_lng):
    where, args = [], []
    if severity:
        where.append("max_severity = ?"); args.append(severity)
    if damage_class:
        where.append("damage_class = ?"); args.append(damage_class)
    if start_date:
        where.append("last_seen >= ?"); args.append(start_date)
    if end_date:
        where.append("first_seen <= ?"); args.append(end_date + " 23:59:59")
    if None not in (min_lat, max_lat, min_lng, max_lng):  # map viewport
        where.append("latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?")
        args += [min_lat, max_lat, min_lng, max_lng]
    sql = "SELECT * FROM pothole_clusters"
    if where:
        sql += " WHERE " + " AND ".join(where)
    return conn.execute(sql, args).fetchall()


@app.get("/potholes")
def potholes(severity: Optional[str] = None, damage_class: Optional[str] = None,
             start_date: Optional[str] = None, end_date: Optional[str] = None,
             min_lat: Optional[float] = None, max_lat: Optional[float] = None,
             min_lng: Optional[float] = None, max_lng: Optional[float] = None):
    """All pothole clusters as GeoJSON (optional severity/date/bbox filters)."""
    conn = get_conn()
    try:
        rows = _cluster_rows(conn, severity, damage_class, start_date, end_date,
                             min_lat, max_lat, min_lng, max_lng)
    finally:
        conn.close()
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
            "properties": {k: r[k] for k in (
                "cluster_id", "damage_class", "max_severity",
                "sighting_count", "first_seen", "last_seen")},
        } for r in rows],
    }


SEVERITY_WEIGHT = {"small": 0.3, "medium": 0.6, "large": 1.0}


@app.get("/heatmap")
def heatmap(severity: Optional[str] = None):
    """[[lat, lng, intensity], ...] - the format Leaflet.heat / Folium HeatMap take.

    Intensity = severity weight, scaled up a little for well-confirmed spots
    (more sightings = more trustworthy).
    """
    conn = get_conn()
    try:
        rows = _cluster_rows(conn, severity, None, None, None, None, None, None, None)
    finally:
        conn.close()
    return [[r["latitude"], r["longitude"],
             round(SEVERITY_WEIGHT[r["max_severity"]]
                   * (0.5 + 0.5 * min(r["sighting_count"] / 10, 1)), 3)]
            for r in rows]
