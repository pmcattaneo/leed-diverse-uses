import os
from io import StringIO
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from leed_diverse_uses.core import Destination, RouteAnalyzer
from leed_diverse_uses.pdf_report import ReportGenerator

st.set_page_config(page_title="LEED Diverse Uses Router", layout="wide")

ors_key = os.environ.get("ORS_API_KEY")

# Initialize session state
if "origin_lat" not in st.session_state:
    st.session_state.origin_lat = 40.748817
if "origin_lon" not in st.session_state:
    st.session_state.origin_lon = -73.985428
if "project_name" not in st.session_state:
    st.session_state.project_name = "LEED Project"
if "project_address" not in st.session_state:
    st.session_state.project_address = ""
if "destinations" not in st.session_state:
    st.session_state.destinations = []
if "results" not in st.session_state:
    st.session_state.results = []
if "max_distance_m" not in st.session_state:
    st.session_state.max_distance_m = 804.67

# Header with back button
col1, col2 = st.columns([1, 4])
with col1:
    if st.button("← Dashboard"):
        st.session_state.clear()
        st.rerun()

with col2:
    st.markdown("## LEED Docs — WALKING DISTANCE")

# Project info
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    st.session_state.project_name = st.text_input(
        "Project Name", 
        value=st.session_state.project_name,
        label_visibility="collapsed"
    )
    st.session_state.project_address = st.text_input(
        "Project Address",
        value=st.session_state.project_address,
        label_visibility="collapsed"
    )

with col2:
    status = st.selectbox("Status", ["Draft", "Submitted", "Approved"], key="status_select")

with col3:
    if st.button("+ Add Address"):
        st.session_state.show_add_form = True

st.markdown("---")

# Credit info
col1, col2, col3 = st.columns(3)
with col1:
    st.write("**v4**")
with col2:
    st.write("**LTc4 - Surrounding Density and Diverse Uses**")
with col3:
    max_distance_mi = st.session_state.max_distance_m / 1609.34
    st.write(f"**Threshold: {max_distance_mi:.2f} mi**")

st.markdown("---")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📍 Addresses", "🗺️ Routes", "📊 Chart", "🗺️ Overview Map"])

with tab1:
    st.subheader("Addresses")
    
    # Add address form
    if st.session_state.get("show_add_form", False):
        with st.form("add_address_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name")
                address = st.text_input("Address")
            with col2:
                category_options = [
                    "Services", "Food Retail", "Community-Serving Retail",
                    "Recreation", "Restaurant", "Library", "Park", "School",
                    "Museum", "Other"
                ]
                category = st.selectbox("Category", category_options)
            
            submit_btn = st.form_submit_button("Add Address", use_container_width=True)
            
            if submit_btn and name and address:
                if not ors_key:
                    st.error("ORS_API_KEY required")
                else:
                    try:
                        analyzer = RouteAnalyzer(
                            origin=(st.session_state.origin_lat, st.session_state.origin_lon),
                            ors_api_key=ors_key
                        )
                        dest = analyzer.analyze_destination(
                            name=name,
                            address=address,
                            max_distance_m=st.session_state.max_distance_m
                        )
                        dest.category = category
                        st.session_state.results.append(dest)
                        st.session_state.show_add_form = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error adding address: {e}")
        
        st.markdown("---")
    
    # Display table
    if st.session_state.results:
        df_data = []
        for dest in st.session_state.results:
            distance_mi = dest.distance_m / 1609.34 if dest.distance_m else 0
            time_min = dest.duration_s / 60 if dest.duration_s else 0
            df_data.append({
                "Name": dest.name,
                "Category": dest.category,
                "Address": dest.address,
                "Distance (mi)": f"{distance_mi:.2f}",
                "Time (min)": f"{time_min:.0f}",
                "Route": "✓ Mapped",
                "Compliant": "✓" if dest.compliant else "✗"
            })
        
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Compliance summary
        compliant_count = sum(1 for d in st.session_state.results if d.compliant)
        total_count = len(st.session_state.results)
        
        st.markdown("---")
        st.subheader("Export LEED Documentation")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Compliant", f"{compliant_count}/{total_count}")
        with col2:
            st.metric("Routes Ready", f"{total_count}")
        
        col1, col2 = st.columns(2)
        with col1:
            csv_buffer = StringIO()
            df.to_csv(csv_buffer, index=False)
            st.download_button(
                label="📥 Export CSV",
                data=csv_buffer.getvalue(),
                file_name="leed_diverse_uses.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            if st.button("📄 Generate PDF Package", use_container_width=True):
                with st.spinner("Generating PDF..."):
                    try:
                        output_path = Path.cwd() / "leed_diverse_uses_report.pdf"
                        map_paths = []
                        for i, dest in enumerate(st.session_state.results, start=1):
                            analyzer = RouteAnalyzer(
                                origin=(st.session_state.origin_lat, st.session_state.origin_lon),
                                ors_api_key=ors_key
                            )
                            m = analyzer.make_route_map(dest)
                            map_file = Path.cwd() / f"route_{i}_{dest.name.replace(' ', '_')}.html"
                            ReportGenerator.save_map_html(m, map_file)
                            map_paths.append(map_file)
                        
                        report = ReportGenerator(output_path=output_path)
                        report.create_report(
                            origin=(st.session_state.origin_lat, st.session_state.origin_lon),
                            destinations=st.session_state.results,
                            map_html_paths=map_paths
                        )
                        st.success(f"✓ PDF report created: {output_path.name}")
                    except Exception as e:
                        st.error(f"Error generating PDF: {e}")
    else:
        st.info("No addresses added yet. Click '+ Add Address' to get started.")

with tab2:
    st.subheader("Routes")
    if st.session_state.results:
        selected_idx = st.selectbox(
            "Select a route to view",
            range(len(st.session_state.results)),
            format_func=lambda i: st.session_state.results[i].name
        )
        
        if selected_idx is not None:
            dest = st.session_state.results[selected_idx]
            col1, col2 = st.columns([2, 1])
            
            with col1:
                if not ors_key:
                    st.error("ORS_API_KEY required")
                else:
                    analyzer = RouteAnalyzer(
                        origin=(st.session_state.origin_lat, st.session_state.origin_lon),
                        ors_api_key=ors_key
                    )
                    m = analyzer.make_route_map(dest)
                    st_folium(m, width=700, height=500)
            
            with col2:
                distance_mi = dest.distance_m / 1609.34
                time_min = dest.duration_s / 60
                
                st.markdown(f"### {dest.name}")
                st.markdown(f"**Category:** {dest.category}")
                st.markdown(f"**Address:** {dest.address}")
                st.metric("Distance", f"{distance_mi:.2f} mi")
                st.metric("Walking Time", f"{time_min:.0f} min")
                
                if dest.compliant:
                    st.success("✓ Compliant")
                else:
                    st.warning("⚠️ Non-compliant")
    else:
        st.info("No routes to display. Add addresses first.")

with tab3:
    st.subheader("Compliance Chart")
    if st.session_state.results:
        compliant_count = sum(1 for d in st.session_state.results if d.compliant)
        non_compliant_count = len(st.session_state.results) - compliant_count
        
        chart_data = pd.DataFrame({
            "Status": ["Compliant", "Non-compliant"],
            "Count": [compliant_count, non_compliant_count]
        })
        
        st.bar_chart(chart_data.set_index("Status"))
        
        st.markdown("---")
        st.write("### Distance Distribution")
        distances_mi = [d.distance_m / 1609.34 for d in st.session_state.results]
        distance_df = pd.DataFrame({
            "Name": [d.name for d in st.session_state.results],
            "Distance (mi)": distances_mi
        })
        st.bar_chart(distance_df.set_index("Name"))
    else:
        st.info("No data to display. Add addresses first.")

with tab4:
    st.subheader("Overview Map")
    if st.session_state.results:
        m = folium.Map(
            location=[st.session_state.origin_lat, st.session_state.origin_lon],
            zoom_start=13,
            tiles="OpenStreetMap"
        )
        
        # Add origin marker
        folium.Marker(
            location=[st.session_state.origin_lat, st.session_state.origin_lon],
            popup="Project Origin",
            icon=folium.Icon(color="blue", icon="home"),
        ).add_to(m)
        
        # Add destination markers
        for dest in st.session_state.results:
            color = "green" if dest.compliant else "red"
            folium.Marker(
                location=[dest.lat, dest.lon],
                popup=f"{dest.name}<br>{dest.address}",
                icon=folium.Icon(color=color, icon="map-pin"),
            ).add_to(m)
            
            # Add route line
            if dest.route_geometry:
                folium.PolyLine(
                    dest.route_geometry,
                    color="green" if dest.compliant else "orange",
                    weight=3,
                    opacity=0.7,
                ).add_to(m)
        
        st_folium(m, width=700, height=500)
    else:
        st.info("No routes to display on the map. Add addresses first.")
