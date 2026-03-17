import os
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

from leed_diverse_uses.core import RouteAnalyzer
from leed_diverse_uses.pdf_report import ReportGenerator


st.set_page_config(page_title="LEED Diverse Uses Router", layout="wide")

st.title("LEED Diverse Uses — Walking Routes")

st.markdown(
    """
Click on the map below to select your origin point, then provide a list of destinations.
The app will compute walking routes using OpenRouteService and evaluate compliance.
"""
)

ors_key = os.environ.get("ORS_API_KEY")
if not ors_key:
    st.warning("Set the ORS_API_KEY environment variable to use routing features.")

# Initialize session state for origin and previous locations
if "origin_lat" not in st.session_state:
    st.session_state.origin_lat = 40.748817
if "origin_lon" not in st.session_state:
    st.session_state.origin_lon = -73.985428

st.subheader("Step 1: Select Origin Point")
st.info("Click on the map to set your origin point (a marker will appear where you click).")

# Create interactive map
m = folium.Map(
    location=[st.session_state.origin_lat, st.session_state.origin_lon],
    zoom_start=13,
    tiles="OpenStreetMap",
)

# Add current origin marker
folium.Marker(
    location=[st.session_state.origin_lat, st.session_state.origin_lon],
    popup="Origin (click to change)",
    icon=folium.Icon(color="blue", icon="home"),
).add_to(m)

# Capture map clicks
map_data = st_folium(m, width=700, height=500)

# Update origin if user clicked on the map
if map_data and map_data.get("last_clicked"):
    st.session_state.origin_lat = map_data["last_clicked"]["lat"]
    st.session_state.origin_lon = map_data["last_clicked"]["lng"]
    st.success(f"✓ Origin set to: {st.session_state.origin_lat:.6f}, {st.session_state.origin_lon:.6f}")

st.markdown("---")

max_distance = st.number_input(
    "Max walking distance (meters)", min_value=100.0, value=804.67, step=10.0
)

st.subheader("Step 2: Enter Destinations")

dest_text = st.text_area(
    "Enter one destination per line in the format `Name | Address` (or just an address).",
    value="Empire State Building | 350 5th Ave, New York, NY\nTimes Square | Times Square, New York, NY",
    height=120,
)

if st.button("Analyze Routes"):
    if not ors_key:
        st.error("ORS_API_KEY is required to compute routes.")
        st.stop()

    origin_coord = (st.session_state.origin_lat, st.session_state.origin_lon)

    dest_lines = [l.strip() for l in dest_text.splitlines() if l.strip()]
    destinations = []
    for line in dest_lines:
        if "|" in line:
            name, address = line.split("|", 1)
        else:
            name, address = line, line
        destinations.append((name.strip(), address.strip()))

    analyzer = RouteAnalyzer(origin=origin_coord, ors_api_key=ors_key)
    results = analyzer.analyze_destinations(destinations, max_distance_m=max_distance)

    st.success(f"Analyzed {len(results)} destinations")

    cols = st.columns(2)
    for idx, dest in enumerate(results):
        col = cols[idx % len(cols)]
        status = "✅ Compliant" if dest.compliant else "⚠️ Non-compliant"
        col.markdown(f"### {dest.name} — {status}")
        col.markdown(f"**Address:** {dest.address}  ")
        col.markdown(f"**Distance:** {dest.distance_m:.0f} m / **Time:** {dest.duration_s/60:.1f} min")

        m = analyzer.make_route_map(dest)
        st_folium(m, width=350, height=300)

    if st.button("Generate PDF Report"):
        output_path = Path.cwd() / "leed_diverse_uses_report.pdf"
        map_paths = []
        for i, dest in enumerate(results, start=1):
            m = analyzer.make_route_map(dest)
            map_file = Path.cwd() / f"route_{i}_{dest.name.replace(' ', '_')}.html"
            ReportGenerator.save_map_html(m, map_file)
            map_paths.append(map_file)

        report = ReportGenerator(output_path=output_path)
        report.create_report(origin=origin_coord, destinations=results, map_html_paths=map_paths)
        st.success(f"PDF report created: {output_path}")
