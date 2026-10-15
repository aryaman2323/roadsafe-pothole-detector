# RoadSafe AI – basic version

Phone photo → YOLOv8 → GPS + severity → 10 m clustering → SQLite → Streamlit map.  
Stack follows the project PDF: FastAPI, SQLite, Streamlit + Folium, geopy.

## Setup

```bash
python -m venv .venv
```

On **Windows PowerShell**:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Then install the required packages:

```bash
pip install -r requirements.txt
```

**What this does:** creates an isolated Python environment, activates it, and installs all required libraries.

---

## 1. See the dashboard with fake data (no model needed)

```bash
python -m backend.seed_data
```

This creates fake pothole detections, fake GPS coordinates, severity values, repeated sightings, and 10 m clusters, then stores them in:

```text
data/roadsafe.db
```

Now run the dashboard:

```bash
streamlit run dashboard/app.py
```

This starts the Streamlit frontend.

Open the local URL shown in the terminal, usually:

```text
http://localhost:8501
```

Then select:

```text
Sidebar → Interactive Map
```

You will see:
- pothole markers
- severity colours
- marker sizes based on sightings
- density heatmap

---

## 2. Show the heatmap

After running:

```bash
python -m backend.seed_data
streamlit run dashboard/app.py
```

open:

```text
Interactive Map
```

The heatmap uses data in this form:

```text
[latitude, longitude, intensity]
```

Severity weights are:

```text
small  = 0.3
medium = 0.6
large  = 1.0
```

Nearby potholes overlap visually, so areas with more or more severe potholes appear hotter.

The map also lets you toggle:

```text
Pothole markers
Density heatmap
```

---

## 3. Run the API

Open a second terminal and activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then run:

```bash
uvicorn backend.main:app --reload
```

This starts the FastAPI backend.

Open:

```text
http://localhost:8000/docs
```

| Endpoint | What it does |
|---|---|
| `POST /detect` | Upload a road photo → run detection → store results → update clusters |
| `GET /potholes` | Return pothole clusters as GeoJSON |
| `GET /heatmap` | Return heatmap-ready `[lat, lng, intensity]` data |

---

## 4. `POST /detect`

In `/docs`, open:

```text
POST /detect
```

Click:

```text
Try it out
```

Upload a road image and click:

```text
Execute
```

The backend does:

```text
image upload
→ validate image
→ save image
→ extract GPS from EXIF
→ run YOLOv8
→ calculate severity
→ save detection
→ update 10 m cluster
→ return JSON
```

Example response:

```json
{
  "image": "abc123.jpg",
  "gps_found": true,
  "detections": [
    {
      "class": "pothole",
      "confidence": 0.91,
      "severity": "large",
      "lat": 12.9716,
      "lng": 77.5946
    }
  ]
}
```

---

## 5. `GET /potholes`

Use:

```text
GET /potholes
```

and click:

```text
Try it out → Execute
```

This reads pothole clusters from the database and returns them as GeoJSON.

Optional filters include:

```text
severity
damage_class
start_date
end_date
min_lat
max_lat
min_lng
max_lng
```

---

## 6. `GET /heatmap`

Use:

```text
GET /heatmap
```

and click:

```text
Try it out → Execute
```

Example response:

```json
[
  [12.9716, 77.5946, 0.8],
  [12.9352, 77.6245, 0.5]
]
```

Each row means:

```text
[latitude, longitude, intensity]
```

Important:

```text
GET /heatmap
```

returns only the heatmap data.

To see the actual visual heatmap:

```bash
streamlit run dashboard/app.py
```

Then open:

```text
Interactive Map
```

---

## 7. Use the real YOLOv8 pothole model

The project expects:

```text
model/best.pt
```

If `best.pt` is missing, the code falls back to:

```text
yolov8n.pt
```

Normal YOLOv8n does not know the pothole classes used by this project.

For real pothole detection:

```text
train YOLOv8 on pothole data
→ get best.pt
→ place it inside model/
→ restart FastAPI
→ use POST /detect
```

---

## 8. Process a folder of images

```bash
python -m backend.batch_detect path/to/photos
```

This:

```text
loads YOLO
→ processes every image
→ extracts GPS
→ estimates severity
→ stores detections
→ updates clusters
```

Then run:

```bash
streamlit run dashboard/app.py
```

to view the results.

---

## 9. Run tests

```bash
pytest tests
```

This checks severity calculation, clustering, GPS extraction, missing-GPS handling, and cluster rebuilding.

---

## Quickest way to get the heatmap

```bash
python -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

```bash
pip install -r requirements.txt
python -m backend.seed_data
streamlit run dashboard/app.py
```

Then:

```text
Open the Streamlit URL
→ select Interactive Map
→ view the heatmap
```

You do **not** need FastAPI or a trained YOLO model just to display the fake-data heatmap.
