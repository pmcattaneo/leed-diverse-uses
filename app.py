import os
from io import StringIO
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from leed_diverse_uses.core import Destination, RouteAnalyzer
from leed_diverse_uses.pdf_report import ReportGenerator
from leed_diverse_uses.projects import ProjectManager

st.set_page_config(page_title="LEED Diverse Uses", layout="wide")

# Initialize session state
if "page" not in st.session_state:
    st.session_state.page = "dashboard"
if "current_project_id" not in st.session_state:
    st.session_state.current_project_id = None

project_manager = ProjectManager()

# ============= DASHBOARD PAGE =============
def page_dashboard():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        st.markdown("### 📋 LEED Docs")
    
    with col3:
        if st.button("➕ New Project", use_container_width=True, key="new_proj_btn"):
            st.session_state.page = "create_project"
            st.rerun()
    
    st.markdown("---")
    st.markdown("# Dashboard")
    st.markdown("LEED Walking Distance Documentation")
    
    # Statistics
    stats = project_manager.get_stats()
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Projects", stats["total_projects"])
    with col2:
        st.metric("Addresses Tracked", stats["total_addresses"])
    with col3:
        st.metric("Compliant", stats["total_compliant"])
    with col4:
        st.metric("Non-Compliant", stats["total_non_compliant"])
    
    st.markdown("---")
    st.markdown("## Recent Projects")
    
    projects = project_manager.list_projects()
    
    if not projects:
        st.info("No projects yet. Click '➕ New Project' to get started.")
    else:
        cols = st.columns(2)
        for idx, project in enumerate(projects):
            col = cols[idx % 2]
            with col:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"### {project.name}")
                        st.markdown(f"*{project.address}*")
                        st.markdown(f"{project.total_count} addresses • {project.compliant_count} compliant")
                    
                    with col2:
                        status_color = {"Draft": "🔵", "In Progress": "🟡", "Approved": "🟢"}.get(project.status, "⚪")
                        st.markdown(f"{status_color} **{project.status.lower()}**")
                    
                    if st.button("Open", key=f"proj_{project.project_id}", use_container_width=True):
                        st.session_state.current_project_id = project.project_id
                        st.session_state.page = "project"
                        st.rerun()

# ============= CREATE PROJECT PAGE =============
def page_create_project():
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Dashboard"):
            st.session_state.page = "dashboard"
            st.rerun()
    
    with col2:
        st.markdown("## New Project")
    
    st.markdown("---")
    
    with st.form("create_project_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            project_name = st.text_input("Project Name*", placeholder="e.g., VAHW Building")
            project_address = st.text_input("Project Address*", placeholder="e.g., 950 Campbell Ave")
        
        with col2:
            origin_lat = st.number_input("Origin Latitude", value=40.748817, format="%.6f")
            origin_lon = st.number_input("Origin Longitude", value=-73.985428, format="%.6f")
        
        if st.form_submit_button("Create Project", use_container_width=True):
            if project_name and project_address:
                project = project_manager.create_project(
                    name=project_name,
                    address=project_address,
                    origin_lat=origin_lat,
                    origin_lon=origin_lon
                )
                st.success(f"✓ Project '{project.name}' created!")
                st.session_state.current_project_id = project.project_id
                st.session_state.page = "project"
                st.rerun()
            else:
                st.error("Project name and address are required")

# ============= PROJECT DETAIL PAGE =============
def page_project():
    project = project_manager.get_project(st.session_state.current_project_id)
    if not project:
        st.error("Project not found")
        return
    
    # Header
    col1, col2, col3 = st.columns([1, 4, 1])
    with col1:
        if st.button("← Dashboard"):
            st.session_state.page = "dashboard"
            st.rerun()
    
    with col2:
        st.markdown("## LEED Docs — WALKING DISTANCE")
    
    st.markdown("---")
    
    # Project info
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        project.name = st.text_input("Project Name", value=project.name, label_visibility="collapsed")
        project.address = st.text_input("Project Address", value=project.address, label_visibility="collapsed")
    
    with col2:
        project.status = st.selectbox("Status", ["Draft", "In Progress", "Approved"], 
                                       index=["Draft", "In Progress", "Approved"].index(project.status),
                                       key="status_select")
    
    with col3:
        if st.button("+ Add Address"):
            st.session_state.show_add_form = True
    
    project_manager.update_project(project)
    
    st.markdown("---")
    
    # Credit info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("**v4**")
    with col2:
        st.write("**LTc4 - Surrounding Density and Diverse Uses**")
    with col3:
        max_distance_mi = project.max_distance_m / 1609.34
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
                    try:
                        analyzer = RouteAnalyzer(
                            origin=(project.origin_lat, project.origin_lon)
                        )
                        dest = analyzer.analyze_destination(
                            name=name,
                            address=address,
                            max_distance_m=project.max_distance_m
                        )
                        dest.category = category
                        dest_dict = {
                            "name": dest.name,
                            "address": dest.address,
                            "lat": dest.lat,
                            "lon": dest.lon,
                            "category": dest.category,
                            "distance_m": dest.distance_m,
                            "duration_s": dest.duration_s,
                            "compliant": dest.compliant,
                        }
                        project_manager.add_destination(project.project_id, dest_dict)
                        st.session_state.show_add_form = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error adding address: {e}")
            
            st.markdown("---")
        
        # Display table
        if project.destinations:
            df_data = []
            for dest in project.destinations:
                distance_mi = dest["distance_m"] / 1609.34 if dest.get("distance_m") else 0
                time_min = dest["duration_s"] / 60 if dest.get("duration_s") else 0
                df_data.append({
                    "Name": dest["name"],
                    "Category": dest.get("category", ""),
                    "Address": dest["address"],
                    "Distance (mi)": f"{distance_mi:.2f}",
                    "Time (min)": f"{time_min:.0f}",
                    "Route": "✓ Mapped",
                    "Compliant": "✓" if dest.get("compliant") else "✗"
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Compliance summary
            compliant_count = project.compliant_count
            total_count = project.total_count
            
            st.markdown("---")
            st.subheader("Export LEED Documentation")
            
            col1, col2 = st.columns(2)
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
                    file_name=f"{project.name.replace(' ', '_')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col2:
                if st.button("📄 Generate PDF Package", use_container_width=True):
                    with st.spinner("Generating PDF..."):
                        try:
                            output_path = Path.cwd() / f"{project.name.replace(' ', '_')}_report.pdf"
                            map_paths = []
                            
                            for i, dest_dict in enumerate(project.destinations, start=1):
                                dest = Destination(
                                    name=dest_dict["name"],
                                    address=dest_dict["address"],
                                    lat=dest_dict["lat"],
                                    lon=dest_dict["lon"],
                                    category=dest_dict.get("category", ""),
                                    distance_m=dest_dict.get("distance_m"),
                                    duration_s=dest_dict.get("duration_s"),
                                    compliant=dest_dict.get("compliant"),
                                )
                                
                                analyzer = RouteAnalyzer(
                                    origin=(project.origin_lat, project.origin_lon)
                                )
                                m = analyzer.make_route_map(dest)
                                map_file = Path.cwd() / f"route_{i}_{dest.name.replace(' ', '_')}.html"
                                ReportGenerator.save_map_html(m, map_file)
                                map_paths.append(map_file)
                            
                            # Convert dict to Destination objects for report
                            destinations = [
                                Destination(
                                    name=d["name"],
                                    address=d["address"],
                                    lat=d["lat"],
                                    lon=d["lon"],
                                    category=d.get("category", ""),
                                    distance_m=d.get("distance_m"),
                                    duration_s=d.get("duration_s"),
                                    compliant=d.get("compliant"),
                                )
                                for d in project.destinations
                            ]
                            
                            report = ReportGenerator(output_path=output_path)
                            report.create_report(
                                origin=(project.origin_lat, project.origin_lon),
                                destinations=destinations,
                                map_html_paths=map_paths
                            )
                            st.success(f"✓ PDF report created: {output_path.name}")
                        except Exception as e:
                            st.error(f"Error generating PDF: {e}")
        else:
            st.info("No addresses added yet. Click '+ Add Address' to get started.")
    
    with tab2:
        st.subheader("Routes")
        if project.destinations:
            selected_idx = st.selectbox(
                "Select a route to view",
                range(len(project.destinations)),
                format_func=lambda i: project.destinations[i]["name"]
            )
            
            if selected_idx is not None:
                dest_dict = project.destinations[selected_idx]
                dest = Destination(
                    name=dest_dict["name"],
                    address=dest_dict["address"],
                    lat=dest_dict["lat"],
                    lon=dest_dict["lon"],
                    category=dest_dict.get("category", ""),
                    distance_m=dest_dict.get("distance_m"),
                    duration_s=dest_dict.get("duration_s"),
                    compliant=dest_dict.get("compliant"),
                    route_geometry=None,
                )
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    analyzer = RouteAnalyzer(
                        origin=(project.origin_lat, project.origin_lon)
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
        if project.destinations:
            compliant_count = project.compliant_count
            non_compliant_count = project.total_count - compliant_count
            
            chart_data = pd.DataFrame({
                "Status": ["Compliant", "Non-compliant"],
                "Count": [compliant_count, non_compliant_count]
            })
            
            st.bar_chart(chart_data.set_index("Status"))
            
            st.markdown("---")
            st.write("### Distance Distribution")
            distances_mi = [d["distance_m"] / 1609.34 for d in project.destinations if d.get("distance_m")]
            distance_df = pd.DataFrame({
                "Name": [d["name"] for d in project.destinations],
                "Distance (mi)": [d["distance_m"] / 1609.34 for d in project.destinations]
            })
            st.bar_chart(distance_df.set_index("Name"))
        else:
            st.info("No data to display. Add addresses first.")
    
    with tab4:
        st.subheader("Overview Map")
        if project.destinations:
            m = folium.Map(
                location=[project.origin_lat, project.origin_lon],
                zoom_start=13,
                tiles="OpenStreetMap"
            )
            
            # Add origin marker
            folium.Marker(
                location=[project.origin_lat, project.origin_lon],
                popup="Project Origin",
                icon=folium.Icon(color="blue", icon="home"),
            ).add_to(m)
            
            # Add destination markers
            for dest_dict in project.destinations:
                color = "green" if dest_dict.get("compliant") else "red"
                folium.Marker(
                    location=[dest_dict["lat"], dest_dict["lon"]],
                    popup=f"{dest_dict['name']}<br>{dest_dict['address']}",
                    icon=folium.Icon(color=color, icon="map-pin"),
                ).add_to(m)
            
            st_folium(m, width=700, height=500)
        else:
            st.info("No routes to display on the map. Add addresses first.")

# ============= ROUTER =============
if st.session_state.page == "dashboard":
    page_dashboard()
elif st.session_state.page == "create_project":
    page_create_project()
elif st.session_state.page == "project":
    page_project()
