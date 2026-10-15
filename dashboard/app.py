"""Phase 5: Streamlit dashboard.   Run:  streamlit run dashboard/app.py"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from folium.plugins import HeatMap
from geopy.distance import distance
from streamlit_folium import st_folium

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "roadsafe.db"
SEV_COLOR = {"small": "green", "medium": "orange", "large": "red"}
SEV_ORDER = ["small", "medium", "large"]
HEAT_WEIGHT = {"small": 0.3, "medium": 0.6, "large": 1.0}
RANK_WEIGHT = {"small": 1, "medium": 3, "large": 6}  # 3 large (18) outrank 10 small (10)

st.set_page_config(page_title="RoadSafe AI", page_icon="🕳️", layout="wide")


@st.cache_data(ttl=30)
def load_clusters():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query("SELECT * FROM pothole_clusters", conn)
    df["first_seen"] = pd.to_datetime(df["first_seen"])
    df["last_seen"] = pd.to_datetime(df["last_seen"])
    return df


if not DB_PATH.exists():
    st.error("No database yet. Run `python -m backend.seed_data` "
             "(fake data) or `python -m backend.batch_detect <folder>`.")
    st.stop()

df = load_clusters()
if df.empty:
    st.warning("The database has no pothole clusters yet.")
    st.stop()

# ---------- sidebar ----------
st.sidebar.title("RoadSafe AI")
page = st.sidebar.radio("Page", ["Overview", "Interactive Map", "Worst Roads"])
st.sidebar.header("Filters")
sev_sel = st.sidebar.multiselect("Severity", SEV_ORDER, default=SEV_ORDER)
cls_options = sorted(df["damage_class"].dropna().unique())
cls_sel = st.sidebar.multiselect("Damage class", cls_options, default=cls_options)
dmin, dmax = df["first_seen"].min().date(), df["last_seen"].max().date()
dates = st.sidebar.date_input("First detected between", (dmin, dmax),
                              min_value=dmin, max_value=dmax)
start, end = (dates[0], dates[-1]) if len(dates) else (dmin, dmax)

view = df[
    df["max_severity"].isin(sev_sel)
    & df["damage_class"].isin(cls_sel)
    & (df["first_seen"].dt.date >= start)
    & (df["first_seen"].dt.date <= end)
]

st.caption(f"Last updated: {datetime.now():%Y-%m-%d %H:%M}")
if view.empty:
    st.info("No potholes match the current filters.")
    st.stop()

# ---------- Page 1: overview ----------
if page == "Overview":
    st.title("Overview")
    total_det = int(view["sighting_count"].sum())
    n_large = int((view["max_severity"] == "large").sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Unique potholes / locations", len(view))
    c2.metric("Raw detections", total_det)
    c3.metric("Large severity", n_large)
    st.write(f"RoadSafe AI has detected **{total_det}** road damage points across "
             f"**{len(view)}** locations. **{n_large}** are rated large severity.")

    left, right = st.columns(2)
    sev_counts = (view["max_severity"].value_counts()
                  .reindex(SEV_ORDER, fill_value=0).rename_axis("severity")
                  .reset_index(name="count"))
    left.plotly_chart(px.bar(sev_counts, x="severity", y="count", color="severity",
                             color_discrete_map=SEV_COLOR, title="By severity"),
                      use_container_width=True)
    cls_counts = view["damage_class"].value_counts().rename_axis("class").reset_index(name="count")
    right.plotly_chart(px.pie(cls_counts, names="class", values="count",
                              title="By damage class"), use_container_width=True)

    now = pd.Timestamp.now()
    age = now - view["first_seen"]
    st.subheader("When first detected")
    a, b, c = st.columns(3)
    a.metric("This week", int((age <= timedelta(days=7)).sum()))
    b.metric("This month", int(((age > timedelta(days=7)) & (age <= timedelta(days=30))).sum()))
    c.metric("Older", int((age > timedelta(days=30)).sum()))

# ---------- Page 2: map ----------
elif page == "Interactive Map":
    st.title("Interactive Map")
    m = folium.Map(location=[view["latitude"].mean(), view["longitude"].mean()],
                   zoom_start=13, tiles="OpenStreetMap")

    markers = folium.FeatureGroup(name="Pothole markers")
    for r in view.itertuples():
        popup = (f"<b>{r.damage_class}</b><br>Severity: {r.max_severity}<br>"
                 f"Sightings: {r.sighting_count}<br>"
                 f"First detected: {r.first_seen:%Y-%m-%d}<br>"
                 f"Last seen: {r.last_seen:%Y-%m-%d}")
        folium.CircleMarker(
            [r.latitude, r.longitude],
            radius=4 + min(r.sighting_count, 20) * 0.7,   # more sightings = bigger
            color=SEV_COLOR[r.max_severity], fill=True, fill_opacity=0.7,
            popup=folium.Popup(popup, max_width=250),
        ).add_to(markers)
    markers.add_to(m)

    heat = folium.FeatureGroup(name="Density heatmap")
    HeatMap([[r.latitude, r.longitude, HEAT_WEIGHT[r.max_severity]]
             for r in view.itertuples()],
            radius=25, blur=20, max_zoom=17).add_to(heat)
    heat.add_to(m)

    folium.LayerControl().add_to(m)
    st_folium(m, height=600, use_container_width=True, returned_objects=[])
    st.caption("Marker colour = severity (green small, orange medium, red large). "
               "Marker size = number of sightings.")

# ---------- Page 3: worst roads ----------
else:
    st.title("Worst Roads Ranking")
    st.caption("Clusters within 100 m of each other are grouped into one segment. "
               "Score weights severity: small 1, medium 3, large 6.")

    segments = []  # each: {"lat", "lng", "members": [row, ...]}
    for r in view.sort_values("latitude").itertuples():
        for seg in segments:
            if distance((r.latitude, r.longitude), (seg["lat"], seg["lng"])).meters <= 100:
                seg["members"].append(r)
                break
        else:
            segments.append({"lat": r.latitude, "lng": r.longitude, "members": [r]})

    rows = []
    for seg in segments:
        mem = seg["members"]
        rank = [SEV_ORDER.index(x.max_severity) + 1 for x in mem]
        rows.append({
            "Location (lat, lng)": f"{seg['lat']:.4f}, {seg['lng']:.4f}",
            "Potholes": len(mem),
            "Avg severity (1-3)": round(sum(rank) / len(rank), 2),
            "Score": sum(RANK_WEIGHT[x.max_severity] for x in mem),
            "Oldest detected (days)": int((pd.Timestamp.now()
                                           - min(x.first_seen for x in mem)).days),
        })
    ranking = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)
    ranking.index += 1
    st.dataframe(ranking.head(25), use_container_width=True)
