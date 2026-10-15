"""Fallback if you skip the API:  python -m backend.batch_detect path/to/images"""
import logging
import sys
from pathlib import Path

from .db import get_conn
from .geolocator import summary
from .pipeline import detect_image, load_model

logging.basicConfig(level=logging.WARNING)


def main(folder):
    model = load_model()
    conn = get_conn()
    images = [p for p in sorted(Path(folder).iterdir())
              if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    for path in images:
        dets, _ = detect_image(model, path, conn)
        print(f"{path.name}: {len(dets)} detection(s)")
    print(summary(conn))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m backend.batch_detect <image_folder>")
    main(sys.argv[1])
