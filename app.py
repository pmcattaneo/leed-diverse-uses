from io import StringIO
from pathlib import Path
from typing import Optional

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


def destination_from_dict(dest_dict: dict) -> Destination:
    """Convert stored destination data into a Destination object."""
    return Destination(
        name=dest_dict["name"],
        address=dest_dict["address"],
        lat=dest_dict["lat"],
        lon=dest_dict["lon"],
        category=dest_dict.get("category", ""),
        distance_m=dest_dict.get("distance_m"),
        duration_s=dest_dict.get("duration_s"),
        compliant=dest_dict.get("compliant"),
        route_geometry=dest_dict.get("route_geometry"),
    )


def destination_to_dict(dest: Destination) -> dict:
    """Convert a Destination object to the stored JSON shape."""
    return {
        "name": dest.name,
        "address": dest.address,
        "lat": dest.lat,
        "lon": dest.lon,
        "category": dest.category,
        "distance_m": dest.distance_m,
        "duration_s": dest.duration_s,
        "compliant": dest.compliant,
        "route_geometry": dest.route_geometry,
    }


def click_signature(map_data: Optional[dict]) -> Optional[str]:
    """Build a stable click signature for map interactions."""
    if not map_data or not map_data.get("last_clicked"):
        return None

    clicked = map_data["last_clicked"]
    return f"{clicked['lat']:.6f},{clicked['lng']:.6f}"


def repair_project_routes(project) -> bool:
    """Backfill route details for legacy saved destinations."""
    if not project.destinations:
        return False

    analyzer = RouteAnalyzer(origin=(project.origin_lat, project.origin_lon))
    updated = False
    refreshed_destinations = []

    for dest_dict in project.destinations:
        needs_refresh = (
            not dest_dict.get("route_geometry")
            or dest_dict.get("distance_m") is None
            or dest_dict.get("duration_s") is None
            or dest_dict.get("compliant") is None
        )

        if needs_refresh:
            try:
                refreshed = analyzer.analyze_destination_coords(
                    name=dest_dict["name"],
                    lat=dest_dict["lat"],
                    lon=dest_dict["lon"],
                    address=dest_dict.get("address"),
                    category=dest_dict.get("category", ""),
                    max_distance_m=project.max_distance_m,
                )
                refreshed_destinations.append(destination_to_dict(refreshed))
                updated = True
            except Exception:
                refreshed_destinations.append(dest_dict)
        else:
            refreshed_destinations.append(dest_dict)

    if updated:
        project.destinations = refreshed_destinations
        project_manager.update_project(project)

    return updated


def build_overview_map(project) -> folium.Map:
    """Create a map with the origin, all destinations, and saved routes."""
    m = folium.Map(
        location=[project.origin_lat, project.origin_lon],
        zoom_start=13,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    folium.Marker(
        location=[project.origin_lat, project.origin_lon],
        popup="Project Origin",
        tooltip="Project Origin",
        icon=folium.Icon(color="blue", icon="home"),
    ).add_to(m)

    all_points = [(project.origin_lat, project.origin_lon)]

    for dest_dict in project.destinations:
        dest = destination_from_dict(dest_dict)
        color = "green" if dest.compliant else "red"

        folium.Marker(
            location=[dest.lat, dest.lon],
            popup=f"{dest.name}<br>{dest.address}",
            tooltip=dest.name,
            icon=folium.Icon(color=color, icon="map-pin"),
        ).add_to(m)

        all_points.append((dest.lat, dest.lon))

        if dest.route_geometry:
            folium.PolyLine(
                dest.route_geometry,
                color="green" if dest.compliant else "orange",
                weight=4,
                opacity=0.75,
            ).add_to(m)
            all_points.extend(dest.route_geometry)

    if len(all_points) > 1:
        m.fit_bounds(all_points)

    return m


def move_project_origin(project, lat: float, lon: float) -> None:
    """Move the project origin and recalculate all destination routes."""
    analyzer = RouteAnalyzer(origin=(lat, lon))
    project.origin_lat = lat
    project.origin_lon = lon

    try:
        project.address = analyzer.reverse_geocode(lat, lon)
    except Exception:
        project.address = f"{lat:.6f}, {lon:.6f}"

    refreshed_destinations = []
    for dest_dict in project.destinations:
        refreshed = analyzer.analyze_destination_coords(
            name=dest_dict["name"],
            lat=dest_dict["lat"],
            lon=dest_dict["lon"],
            address=dest_dict.get("address"),
            category=dest_dict.get("category", ""),
            max_distance_m=project.max_distance_m,
        )
        refreshed_destinations.append(destination_to_dict(refreshed))

    project.destinations = refreshed_destinations
    project_manager.update_project(project)


def move_destination_point(project, destination_index: int, lat: float, lon: float) -> None:
    """Move one destination and recalculate its route from the current origin."""
    analyzer = RouteAnalyzer(origin=(project.origin_lat, project.origin_lon))
    dest_dict = project.destinations[destination_index]

    try:
        address = analyzer.reverse_geocode(lat, lon)
    except Exception:
        address = f"{lat:.6f}, {lon:.6f}"

    refreshed = analyzer.analyze_destination_coords(
        name=dest_dict["name"],
        lat=lat,
        lon=lon,
        address=address,
        category=dest_dict.get("category", ""),
        max_distance_m=project.max_distance_m,
    )
    project.destinations[destination_index] = destination_to_dict(refreshed)
    project_manager.update_project(project)

# ============= DASHBOARD PAGE =============
def page_dashboard():
    # Header with logo and controls
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 10px;">
            <div style="font-size: 32px; font-weight: bold; color: #27AE60;">LEED Docs</div>
            <div style="font-size: 12px; color: #666; font-weight: 500;">WALKING DISTANCE</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        if st.button("➕ New Project", use_container_width=True):
            st.session_state.page = "create_project"
            st.rerun()
    
    st.markdown("---")
    
    # Page title
    st.markdown("""
    <h1 style="margin-bottom: 10px;">Dashboard</h1>
    <p style="color: #666; margin-top: -10px;">Track LEED Diverse Uses compliance across your projects</p>
    """, unsafe_allow_html=True)
    
    # Statistics
    stats = project_manager.get_stats()
    col1, col2, col3, col4 = st.columns(4, gap="medium")
    
    with col1:
        with st.container(border=False):
            st.markdown(f"""
            <div style="text-align: center; padding: 20px;">
                <div style="font-size: 36px; font-weight: bold; color: #27AE60;">{stats['total_projects']}</div>
                <div style="color: #666; font-size: 14px; margin-top: 8px;">Projects</div>
            </div>
            """, unsafe_allow_html=True)
    
    with col2:
        with st.container(border=False):
            st.markdown(f"""
            <div style="text-align: center; padding: 20px;">
                <div style="font-size: 36px; font-weight: bold; color: #2980B9;">{stats['total_addresses']}</div>
                <div style="color: #666; font-size: 14px; margin-top: 8px;">Addresses Tracked</div>
            </div>
            """, unsafe_allow_html=True)
    
    with col3:
        with st.container(border=False):
            st.markdown(f"""
            <div style="text-align: center; padding: 20px;">
                <div style="font-size: 36px; font-weight: bold; color: #27AE60;">{stats['total_compliant']}</div>
                <div style="color: #666; font-size: 14px; margin-top: 8px;">Compliant</div>
            </div>
            """, unsafe_allow_html=True)
    
    with col4:
        with st.container(border=False):
            st.markdown(f"""
            <div style="text-align: center; padding: 20px;">
                <div style="font-size: 36px; font-weight: bold; color: #E74C3C;">{stats['total_non_compliant']}</div>
                <div style="color: #666; font-size: 14px; margin-top: 8px;">Non-Compliant</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("""
    <h2 style="margin-bottom: 20px;">Recent Projects</h2>
    """, unsafe_allow_html=True)
    
    projects = project_manager.list_projects()
    
    if not projects:
        st.info("📌 No projects yet. Click '➕ New Project' to get started.")
    else:
        cols = st.columns(2, gap="large")
        for idx, project in enumerate(projects):
            col = cols[idx % 2]
            with col:
                with st.container(border=True):
                    # Project header with status
                    col_name, col_status = st.columns([3, 1], gap="small")
                    with col_name:
                        st.markdown(f"""
                        <div style="font-size: 18px; font-weight: bold; color: #222;">{project.name}</div>
                        """, unsafe_allow_html=True)
                    
                    with col_status:
                        status_color = {"Draft": "#3498DB", "In Progress": "#F39C12", "Approved": "#27AE60"}.get(project.status, "#95A5A6")
                        status_emoji = {"Draft": "🔵", "In Progress": "🟡", "Approved": "🟢"}.get(project.status, "⚪")
                        st.markdown(f"""
                        <div style="text-align: right; font-size: 12px; color: {status_color}; font-weight: bold;">
                            {status_emoji} {project.status}
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Project address
                    st.markdown(f"""
                    <div style="color: #666; font-size: 13px; margin: 8px 0;">📍 {project.address}</div>
                    """, unsafe_allow_html=True)
                    
                    # Metrics
                    metric_col1, metric_col2 = st.columns(2)
                    with metric_col1:
                        st.markdown(f"""
                        <div style="font-size: 14px; color: #666;">
                            <span style="font-weight: bold; color: #222;">{project.total_count}</span> addresses
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with metric_col2:
                        compliance_pct = (project.compliant_count / project.total_count * 100) if project.total_count > 0 else 0
                        st.markdown(f"""
                        <div style="font-size: 14px; color: #666;">
                            <span style="font-weight: bold; color: #27AE60;">{project.compliant_count}</span> compliant
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Open button
                    st.markdown("")
                    if st.button("→ Open Project", key=f"proj_{project.project_id}", use_container_width=True):
                        st.session_state.current_project_id = project.project_id
                        st.session_state.page = "project"
                        st.rerun()

# ============= CREATE PROJECT PAGE =============
def page_create_project():
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Dashboard", use_container_width=True):
            st.session_state.page = "dashboard"
            st.rerun()
    
    with col2:
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 10px;">
            <div style="font-size: 24px; font-weight: bold; color: #27AE60;">LEED Docs</div>
            <div style="font-size: 12px; color: #666;">/ NEW PROJECT</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Initialize session state for form (outside form to work with map)
    if "create_project_name" not in st.session_state:
        st.session_state.create_project_name = ""
    if "create_project_address" not in st.session_state:
        st.session_state.create_project_address = ""
    if "create_form_lat" not in st.session_state:
        st.session_state.create_form_lat = 40.748817
    if "create_form_lon" not in st.session_state:
        st.session_state.create_form_lon = -73.985428
    if "geocode_attempted" not in st.session_state:
        st.session_state.geocode_attempted = False
    
    # Project info section
    col1, col2 = st.columns(2)
    
    with col1:
        project_name = st.text_input(
            "Project Name*", 
            value=st.session_state.create_project_name,
            placeholder="e.g., VAHW Building",
            key="proj_name_input"
        )
        st.session_state.create_project_name = project_name
        
        project_address = st.text_input(
            "Project Address*", 
            value=st.session_state.create_project_address,
            placeholder="e.g., 950 Campbell Ave, New York, NY",
            key="proj_address_input"
        )
        st.session_state.create_project_address = project_address
        
        # Geocode button
        if st.button("📍 Locate Address", use_container_width=True):
            if project_address:
                try:
                    analyzer = RouteAnalyzer(origin=(0, 0))
                    lat, lon = analyzer.geocode(project_address)
                    st.session_state.create_form_lat = lat
                    st.session_state.create_form_lon = lon
                    st.session_state.geocode_attempted = True
                    st.success(f"✓ Found: {lat:.4f}, {lon:.4f}")
                except Exception as e:
                    st.error(f"Could not geocode: {e}")
            else:
                st.error("Enter an address first")
    
    with col2:
        st.write("**Project Location**")
        st.info("💡 Enter address above and click 'Locate Address', or click the map to set coordinates manually")
        origin_lat = st.number_input(
            "Latitude", 
            value=st.session_state.create_form_lat, 
            format="%.6f",
            key="lat_input"
        )
        origin_lon = st.number_input(
            "Longitude", 
            value=st.session_state.create_form_lon, 
            format="%.6f",
            key="lon_input"
        )
        st.session_state.create_form_lat = origin_lat
        st.session_state.create_form_lon = origin_lon
    
    st.markdown("---")
    
    # Interactive map to select location
    st.markdown("**Click on the map to adjust the project origin point:**")
    m = folium.Map(
        location=[origin_lat, origin_lon],
        zoom_start=14,
        tiles="OpenStreetMap",
        control_scale=True,
    )
    folium.Marker(
        location=[origin_lat, origin_lon],
        popup="Project Origin",
        icon=folium.Icon(color="blue", icon="home"),
    ).add_to(m)
    
    map_data = st_folium(
        m,
        key="create_project_map",
        height=400,
        use_container_width=True,
        returned_objects=["last_clicked"],
    )
    
    # Handle map click
    current_click = click_signature(map_data)
    if current_click and current_click != st.session_state.get("create_project_map_click"):
        origin_lat = map_data["last_clicked"]["lat"]
        origin_lon = map_data["last_clicked"]["lng"]
        st.session_state.create_form_lat = origin_lat
        st.session_state.create_form_lon = origin_lon
        st.session_state.create_project_map_click = current_click
        st.rerun()
    
    st.markdown("---")
    
    # Submit button
    if st.button("✅ Create Project", use_container_width=True, type="primary"):
        if project_name and project_address:
            try:
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
            except Exception as e:
                st.error(f"Error creating project: {e}")
        else:
            st.error("Project name and address are required")

# ============= PROJECT DETAIL PAGE =============
def page_project():
    project = project_manager.get_project(st.session_state.current_project_id)
    if not project:
        st.error("Project not found")
        return

    if project.destinations and repair_project_routes(project):
        project = project_manager.get_project(project.project_id) or project
    
    # Header with back button
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Dashboard", use_container_width=True):
            st.session_state.page = "dashboard"
            st.rerun()
    
    with col2:
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 10px;">
            <div style="font-size: 24px; font-weight: bold; color: #27AE60;">LEED Docs</div>
            <div style="font-size: 12px; color: #666;">/ WALKING DISTANCE</div>
        </div>
        """, unsafe_allow_html=True)
    
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
                            **destination_to_dict(dest),
                            "category": category,
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
                                analyzer = RouteAnalyzer(
                                    origin=(project.origin_lat, project.origin_lon)
                                )
                                dest = analyzer.enrich_destination(
                                    destination_from_dict(dest_dict),
                                    max_distance_m=project.max_distance_m,
                                )
                                m = analyzer.make_route_map(dest, max_distance_m=project.max_distance_m)
                                map_file = Path.cwd() / f"route_{i}_{dest.name.replace(' ', '_')}.html"
                                ReportGenerator.save_map_html(m, map_file)
                                map_paths.append(map_file)
                                project.destinations[i - 1] = destination_to_dict(dest)
                            
                            # Convert dict to Destination objects for report
                            destinations = [destination_from_dict(d) for d in project.destinations]
                            project_manager.update_project(project)
                            
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
                dest = destination_from_dict(dest_dict)
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    analyzer = RouteAnalyzer(
                        origin=(project.origin_lat, project.origin_lon)
                    )
                    dest = analyzer.enrich_destination(dest, max_distance_m=project.max_distance_m)
                    m = analyzer.make_route_map(dest, max_distance_m=project.max_distance_m)
                    st_folium(
                        m,
                        key=f"route_map_{project.project_id}_{selected_idx}",
                        height=500,
                        use_container_width=True,
                        returned_objects=[],
                    )
                
                with col2:
                    distance_mi = (dest.distance_m or 0) / 1609.34
                    time_min = (dest.duration_s or 0) / 60
                    
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
            distance_df = pd.DataFrame({
                "Name": [d["name"] for d in project.destinations],
                "Distance (mi)": [(d.get("distance_m") or 0) / 1609.34 for d in project.destinations]
            })
            st.bar_chart(distance_df.set_index("Name"))
        else:
            st.info("No data to display. Add addresses first.")
    
    with tab4:
        st.subheader("Overview Map")
        notice_key = f"overview_notice_{project.project_id}"
        pending_click_key = f"overview_pending_click_{project.project_id}"
        click_memory_key = f"overview_last_click_{project.project_id}"

        notice = st.session_state.pop(notice_key, None)
        if notice:
            st.success(notice)

        move_options = ["Project origin"]
        if project.destinations:
            move_options.append("Destination")

        move_target = st.radio(
            "Point to reposition",
            move_options,
            horizontal=True,
            key=f"overview_move_target_{project.project_id}",
        )

        destination_index = None
        if move_target == "Destination":
            destination_index = st.selectbox(
                "Destination to move",
                range(len(project.destinations)),
                format_func=lambda i: project.destinations[i]["name"],
                key=f"overview_destination_target_{project.project_id}",
            )
            selected_name = project.destinations[destination_index]["name"]
            st.caption(
                f"Click the map to choose a new location for '{selected_name}', then apply the change below."
            )
        else:
            st.caption("Click the map to choose a new location for the project origin, then apply the change below.")

        m = build_overview_map(project)
        map_data = st_folium(
            m,
            key=f"overview_map_{project.project_id}",
            height=550,
            use_container_width=True,
            returned_objects=["last_clicked"],
        )

        current_click = click_signature(map_data)
        if current_click and current_click != st.session_state.get(click_memory_key):
            st.session_state[pending_click_key] = map_data["last_clicked"]
            st.session_state[click_memory_key] = current_click

        pending_click = st.session_state.get(pending_click_key)
        if pending_click:
            st.info(
                f"Selected map point: {pending_click['lat']:.6f}, {pending_click['lng']:.6f}"
            )

            apply_label = "Apply New Origin" if move_target == "Project origin" else "Apply New Destination Location"
            if st.button(apply_label, use_container_width=True, type="primary"):
                with st.spinner("Updating routes..."):
                    try:
                        if move_target == "Project origin":
                            move_project_origin(
                                project,
                                pending_click["lat"],
                                pending_click["lng"],
                            )
                            st.session_state[notice_key] = "Project origin moved and all walking routes were recalculated."
                        else:
                            move_destination_point(
                                project,
                                destination_index,
                                pending_click["lat"],
                                pending_click["lng"],
                            )
                            moved_name = project.destinations[destination_index]["name"]
                            st.session_state[notice_key] = f"Destination '{moved_name}' moved and its route was recalculated."

                        st.session_state.pop(pending_click_key, None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not update the map point: {e}")

        if not project.destinations:
            st.info("Add destinations to display walking routes on the overview map.")

# ============= ROUTER =============
if st.session_state.page == "dashboard":
    page_dashboard()
elif st.session_state.page == "create_project":
    page_create_project()
elif st.session_state.page == "project":
    page_project()
