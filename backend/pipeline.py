"""Shared detection logic used by the API and the batch script."""
import logging
from pathlib import Path

from .db import ROOT
from .geolocator import estimate_severity, extract_gps, save_detection

log = logging.getLogger(__name__)

MODEL_PATH = ROOT / "model" / "best.pt"

# RDD2022 codes and our own class names -> the four project classes
CLASS_MAP = {
    "d00": "longitudinal_crack", "longitudinal_crack": "longitudinal_crack",
    "d10": "transverse_crack",   "transverse_crack": "transverse_crack",
    "d20": "alligator_crack",    "alligator_crack": "alligator_crack",
    "d40": "pothole",            "pothole": "pothole",
}


def normalise_class(name):
    return CLASS_MAP.get(str(name).strip().lower())


def load_model():
    from ultralytics import YOLO  # imported lazily so the dashboard needn't install it

    if MODEL_PATH.exists():
        path = str(MODEL_PATH)
    else:
        log.warning("model/best.pt not found - using pretrained yolov8n.pt. "
                    "It does NOT know potholes; train on RDD2022 and save best.pt.")
        path = "yolov8n.pt"
    model = YOLO(path)
    if not any(normalise_class(n) for n in model.names.values()):
        log.warning("Model classes %s match none of the road-damage classes; "
                    "every detection will be ignored.", list(model.names.values()))
    return model


def detect_image(model, image_path, conn, min_conf=0.25):
    """Run YOLO on one image, store detections, update clusters.

    Returns (detections, gps_found).
    """
    gps = extract_gps(image_path)
    lat, lng = gps if gps else (None, None)

    result = model(str(image_path), conf=min_conf, verbose=False)[0]
    height, width = result.orig_shape

    detections = []
    for box in result.boxes:
        damage_class = normalise_class(model.names[int(box.cls)])
        if damage_class is None:
            continue
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        area = (x2 - x1) * (y2 - y1)
        severity = estimate_severity(area, width * height)
        conf = float(box.conf)
        save_detection(conn, Path(image_path).name, lat, lng,
                       damage_class, conf, severity, area)
        detections.append({
            "class": damage_class,
            "confidence": round(conf, 3),
            "severity": severity,
            "lat": lat,
            "lng": lng,
        })
    return detections, gps is not None
