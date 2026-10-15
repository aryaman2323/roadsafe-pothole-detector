"""Fill the DB with fake Bengaluru detections so the dashboard works
before the YOLO model exists.   Run:  python -m backend.seed_data
(Wipes existing detections and clusters.)"""
import random
from datetime import datetime, timedelta

from .db import get_conn
from .geolocator import estimate_severity, save_detection, summary

random.seed(7)

HOTSPOTS = [  # (name, lat, lng)
    ("Centre", 12.9716, 77.5946),
    ("Koramangala", 12.9352, 77.6245),
    ("Indiranagar", 12.9784, 77.6408),
    ("HSR Layout", 12.9121, 77.6446),
]
CLASSES = ["pothole"] * 7 + ["longitudinal_crack", "transverse_crack", "alligator_crack"]
POTHOLES_PER_HOTSPOT = 12
JITTER = 0.00003  # ~3 m typical phone GPS error


def main():
    conn = get_conn()
    conn.executescript("DELETE FROM detections; DELETE FROM pothole_clusters;")
    now = datetime.now()
    img_area = 1_000_000

    for _, lat0, lng0 in HOTSPOTS:
        for _ in range(POTHOLES_PER_HOTSPOT):
            lat = lat0 + random.uniform(-0.003, 0.003)   # within ~300 m
            lng = lng0 + random.uniform(-0.003, 0.003)
            damage = random.choice(CLASSES)
            true_ratio = random.choice([0.01, 0.03, 0.05, 0.1, 0.15])
            first = now - timedelta(days=random.randint(0, 90))
            for _ in range(random.randint(1, 6)):         # repeat sightings
                when = min(now, first + timedelta(days=random.randint(0, 30),
                                                  minutes=random.randint(0, 600)))
                area = true_ratio * img_area * random.uniform(0.7, 1.3)
                save_detection(
                    conn, "seed.jpg",
                    lat + random.gauss(0, JITTER), lng + random.gauss(0, JITTER),
                    damage, round(random.uniform(0.4, 0.95), 2),
                    estimate_severity(area, img_area), area,
                    when.strftime("%Y-%m-%d %H:%M:%S"))
    print(summary(conn))


if __name__ == "__main__":
    main()
