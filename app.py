import os
from pathlib import Path

import streamlit as st
from streamlit.components.v1 import html

from leed_diverse_uses.core import RouteAnalyzer
from leed_diverse_uses.pdf_report import ReportGenerator


st.set_page_config(page_title="LEED Diverse Uses Router", layout="wide")

st.title("LEED Diverse Uses — Walking Routes")

st.markdown(
    """
Provide an origin point and a list of destinations. The app will compute walking routes using OpenRouteService
and evaluate whether each destination is compliant with the specified walking-distance threshold.
"""
)

ors_key = os.environ.get("ORS_API_KEY")
if not ors_key:
    st.warning("Set the ORS_API_KEY environment variable to use routing features.")

origin = st.text_input("Origin (lat,lon)", "40.748817,-73.985428")
max_distance = st.number_input(
    "Max walking distance (meters)", min_value=100.0, value=804.67, step=10.0
)

st.markdown("---")

st.subheader("Destinations")

dest_text = st.text_area(
    "Enter one destination per line in the format `Name | Address` (or just an address).",
    value="Empire State Building | 350 5th Ave, New York, NY\nTimes Square | Times Square, New York, NY",
    height=120,
)

if st.button("Analyze Routes"):
    if not ors_key:
        st.error("ORS_API_KEY is required to compute routes.")
        st.stop()

    try:
        lat_str, lon_str = origin.split(",")
        origin_coord = (float(lat_str.strip()), float(lon_str.strip()))
    except Exception:
        st.error("Origin must be in the format: lat,lon")
        st.stop()

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
        map_html = m._repr_html_()
        html(map_html, height=350)

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
