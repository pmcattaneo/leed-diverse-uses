from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

import folium
import pandas as pd
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from leed_diverse_uses.core import (
    Destination,
    RouteAnalyzer,
    add_responsive_bounds,
    bounds_from_points,
)
from leed_diverse_uses.pdf_report import ReportGenerator
from leed_diverse_uses.projects import ProjectManager
from leed_diverse_uses.use_types import (
    DEFAULT_CATEGORY,
    category_options,
    normalize_use_selection,
    specific_use_options,
)

st.set_page_config(page_title="LEED Diverse Uses", layout="wide")

# Initialize session state
if "page" not in st.session_state:
    st.session_state.page = "dashboard"
if "current_project_id" not in st.session_state:
    st.session_state.current_project_id = None

project_manager = ProjectManager()


def destination_from_dict(dest_dict: dict) -> Destination:
    """Convert stored destination data into a Destination object."""
    category, specific_use = normalize_use_selection(
        category=dest_dict.get("category"),
        specific_use=dest_dict.get("specific_use"),
    )
    return Destination(
        name=dest_dict["name"],
        address=dest_dict["address"],
        lat=dest_dict["lat"],
        lon=dest_dict["lon"],
        category=category,
        specific_use=specific_use,
        distance_m=dest_dict.get("distance_m"),
        duration_s=dest_dict.get("duration_s"),
        compliant=dest_dict.get("compliant"),
        route_geometry=dest_dict.get("route_geometry"),
    )


def destination_to_dict(dest: Destination) -> dict:
    """Convert a Destination object to the stored JSON shape."""
    category, specific_use = normalize_use_selection(
        category=dest.category,
        specific_use=dest.specific_use,
    )
    return {
        "name": dest.name,
        "address": dest.address,
        "lat": dest.lat,
        "lon": dest.lon,
        "category": category,
        "specific_use": specific_use,
        "distance_m": dest.distance_m,
        "duration_s": dest.duration_s,
        "compliant": dest.compliant,
        "route_geometry": dest.route_geometry,
    }


def is_destination_mapped(dest_dict: dict) -> bool:
    """Return True when a destination has a current route mapping."""
    return (
        bool(dest_dict.get("route_geometry"))
        and dest_dict.get("distance_m") is not None
        and dest_dict.get("duration_s") is not None
        and dest_dict.get("compliant") is not None
    )


def route_status_label(dest_dict: dict) -> str:
    """Human-readable route status for tables and selectors."""
    return "✓ Mapped" if is_destination_mapped(dest_dict) else "⚪ Unmapped"


def clear_destination_route(
    dest_dict: dict,
    *,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    address: Optional[str] = None,
) -> dict:
    """Clear calculated route data while preserving the destination record."""
    cleared = dict(dest_dict)
    if lat is not None:
        cleared["lat"] = lat
    if lon is not None:
        cleared["lon"] = lon
    if address is not None:
        cleared["address"] = address

    cleared["distance_m"] = None
    cleared["duration_s"] = None
    cleared["compliant"] = None
    cleared["route_geometry"] = None
    return cleared


def destination_edit_state_key(project_id: str) -> str:
    """Return the session-state key for the currently edited destination."""
    return f"edit_destination_index_{project_id}"


def start_destination_edit(project, destination_index: int) -> None:
    """Seed session state for editing an existing destination."""
    dest = destination_from_dict(project.destinations[destination_index])
    state_key = destination_edit_state_key(project.project_id)
    st.session_state[state_key] = destination_index
    st.session_state[f"edit_address_name_{project.project_id}"] = dest.name
    st.session_state[f"edit_address_value_{project.project_id}"] = dest.address
    st.session_state[f"edit_address_category_{project.project_id}"] = dest.category

    edit_specific_key = f"edit_address_specific_use_{project.project_id}"
    category_specific_options = specific_use_options(dest.category)
    if dest.specific_use in category_specific_options:
        st.session_state[edit_specific_key] = dest.specific_use
    else:
        st.session_state[edit_specific_key] = category_specific_options[0]


def stop_destination_edit(project_id: str) -> None:
    """Clear the active destination edit state for a project."""
    st.session_state.pop(destination_edit_state_key(project_id), None)


def destination_map_signature(dest: Destination) -> str:
    """Create a stable signature for a destination map extent."""
    geometry_count = len(dest.route_geometry or [])
    distance = round(dest.distance_m or 0, 2)
    duration = round(dest.duration_s or 0, 2)
    return (
        f"{dest.name}:{dest.lat:.6f}:{dest.lon:.6f}:"
        f"{distance}:{duration}:{geometry_count}"
    )


def project_map_signature(project) -> str:
    """Create a stable signature for overview map extent changes."""
    parts = [f"origin:{project.origin_lat:.6f}:{project.origin_lon:.6f}"]
    for dest_dict in project.destinations:
        dest = destination_from_dict(dest_dict)
        parts.append(destination_map_signature(dest))
    return "|".join(parts)


def set_create_project_coords(lat: float, lon: float) -> None:
    """Update the canonical create-project coordinates."""
    st.session_state.create_form_lat = lat
    st.session_state.create_form_lon = lon


def queue_create_project_coords(lat: float, lon: float) -> None:
    """Queue coordinate changes so widget state can be updated on the next rerun."""
    st.session_state.create_project_pending_coords = (lat, lon)


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
        try:
            refreshed = analyzer.enrich_destination(
                destination_from_dict(dest_dict),
                max_distance_m=project.max_distance_m,
            )
            refreshed_dict = destination_to_dict(refreshed)
            refreshed_destinations.append(refreshed_dict)
            if refreshed_dict != dest_dict:
                updated = True
        except Exception:
            refreshed_destinations.append(dest_dict)

    if updated:
        project.destinations = refreshed_destinations
        project_manager.update_project(project)

    return updated


def normalize_project_destinations(project) -> bool:
    """Persist normalized LEED use category data for saved destinations."""
    if not project.destinations:
        return False

    normalized_destinations = []
    updated = False

    for dest_dict in project.destinations:
        normalized_dict = destination_to_dict(destination_from_dict(dest_dict))
        normalized_destinations.append(normalized_dict)
        if normalized_dict != dest_dict:
            updated = True

    if updated:
        project.destinations = normalized_destinations
        project_manager.update_project(project)

    return updated


def remap_project_destinations(project) -> int:
    """Recalculate routes for destinations currently marked as unmapped."""
    if not project.destinations:
        return 0

    analyzer = RouteAnalyzer(origin=(project.origin_lat, project.origin_lon))
    refreshed_destinations = []
    remapped_count = 0

    for dest_dict in project.destinations:
        if is_destination_mapped(dest_dict):
            refreshed_destinations.append(dest_dict)
            continue

        normalized_dest = destination_from_dict(dest_dict)
        refreshed = analyzer.analyze_destination_coords(
            name=dest_dict["name"],
            lat=dest_dict["lat"],
            lon=dest_dict["lon"],
            address=dest_dict.get("address"),
            category=normalized_dest.category,
            specific_use=normalized_dest.specific_use,
            max_distance_m=project.max_distance_m,
        )
        refreshed_destinations.append(destination_to_dict(refreshed))
        remapped_count += 1

    project.destinations = refreshed_destinations
    project_manager.update_project(project)
    return remapped_count


def build_overview_map(
    project,
    exclude_origin: bool = False,
    exclude_destination_index: Optional[int] = None,
) -> folium.Map:
    """Create a map with the origin, all destinations, and saved routes."""
    m = folium.Map(
        location=[project.origin_lat, project.origin_lon],
        zoom_start=13,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    if not exclude_origin:
        folium.Marker(
            location=[project.origin_lat, project.origin_lon],
            popup="Project Origin",
            tooltip="Project Origin",
            icon=folium.Icon(color="blue", icon="home"),
        ).add_to(m)

    all_points = [(project.origin_lat, project.origin_lon)]

    for idx, dest_dict in enumerate(project.destinations):
        dest = destination_from_dict(dest_dict)
        color = "green" if dest.compliant is True else "red" if dest.compliant is False else "gray"

        if idx != exclude_destination_index:
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
        overview_bounds = bounds_from_points(all_points)
        add_responsive_bounds(m, overview_bounds)

    return m


def extract_drawn_point(map_data: Optional[dict]) -> Optional[tuple[float, float]]:
    """Extract a single point from a Draw/Leaflet GeoJSON payload."""
    if not map_data:
        return None

    candidates = [
        map_data.get("last_active_drawing"),
        map_data.get("all_drawings"),
    ]

    for candidate in candidates:
        if not candidate:
            continue

        features = []
        if isinstance(candidate, list):
            features = candidate
        elif not isinstance(candidate, dict):
            continue
        elif candidate.get("type") == "Feature":
            features = [candidate]
        elif candidate.get("type") == "FeatureCollection":
            features = candidate.get("features", [])

        for feature in features:
            if not isinstance(feature, dict):
                continue
            geometry = feature.get("geometry", {})
            if not isinstance(geometry, dict):
                continue
            if geometry.get("type") != "Point":
                continue

            coords = geometry.get("coordinates", [])
            if len(coords) >= 2:
                lon, lat = coords[:2]
                return lat, lon

    return None


def coords_changed(current_lat: float, current_lon: float, new_lat: float, new_lon: float) -> bool:
    """Ignore tiny coordinate differences from frontend serialization."""
    return round(current_lat, 6) != round(new_lat, 6) or round(current_lon, 6) != round(new_lon, 6)


def build_editable_overview_map(project, move_target: str, destination_index: Optional[int]) -> folium.Map:
    """Create an overview map with one editable marker for dragging."""
    m = build_overview_map(
        project,
        exclude_origin=move_target == "Project origin",
        exclude_destination_index=destination_index if move_target == "Destination" else None,
    )
    editable_group = folium.FeatureGroup(name="Editable marker")

    if move_target == "Project origin":
        marker_lat = project.origin_lat
        marker_lon = project.origin_lon
        popup = "Project Origin"
        tooltip = "Drag this origin marker"
        icon = folium.Icon(color="blue", icon="home")
    else:
        dest = project.destinations[destination_index]
        marker_lat = dest["lat"]
        marker_lon = dest["lon"]
        popup = f"{dest['name']}<br>{dest['address']}"
        tooltip = f"Drag '{dest['name']}'"
        icon_color = "green" if dest.get("compliant") is True else "red" if dest.get("compliant") is False else "gray"
        icon = folium.Icon(color=icon_color, icon="map-pin")

    folium.Marker(
        location=[marker_lat, marker_lon],
        popup=popup,
        tooltip=tooltip,
        icon=icon,
    ).add_to(editable_group)
    editable_group.add_to(m)

    Draw(
        feature_group=editable_group,
        draw_options={
            "polyline": False,
            "polygon": False,
            "rectangle": False,
            "circle": False,
            "circlemarker": False,
            "marker": False,
        },
        edit_options={
            "edit": True,
            "remove": False,
        },
        show_geometry_on_click=False,
    ).add_to(m)

    return m


def move_project_origin(project, lat: float, lon: float) -> None:
    """Move the project origin and mark all routes as unmapped."""
    project.origin_lat = lat
    project.origin_lon = lon

    project.destinations = [
        clear_destination_route(dest_dict)
        for dest_dict in project.destinations
    ]
    project_manager.update_project(project)


def move_destination_point(project, destination_index: int, lat: float, lon: float) -> None:
    """Move one destination and mark its route as unmapped."""
    analyzer = RouteAnalyzer(origin=(project.origin_lat, project.origin_lon))
    dest_dict = project.destinations[destination_index]

    try:
        address = analyzer.reverse_geocode(lat, lon)
    except Exception:
        address = f"{lat:.6f}, {lon:.6f}"

    project.destinations[destination_index] = clear_destination_route(
        dest_dict,
        lat=lat,
        lon=lon,
        address=address,
    )
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
    pending_coords = st.session_state.pop("create_project_pending_coords", None)
    if pending_coords:
        pending_lat, pending_lon = pending_coords
        st.session_state.create_form_lat = pending_lat
        st.session_state.create_form_lon = pending_lon
        st.session_state.lat_input = pending_lat
        st.session_state.lon_input = pending_lon
    if "lat_input" not in st.session_state:
        st.session_state.lat_input = st.session_state.create_form_lat
    if "lon_input" not in st.session_state:
        st.session_state.lon_input = st.session_state.create_form_lon
    if "geocode_attempted" not in st.session_state:
        st.session_state.geocode_attempted = False
    if "create_project_geocode_message" not in st.session_state:
        st.session_state.create_project_geocode_message = None
    
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
                    queue_create_project_coords(lat, lon)
                    st.session_state.geocode_attempted = True
                    st.session_state.create_project_geocode_message = f"Found: {lat:.4f}, {lon:.4f}"
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not geocode: {e}")
            else:
                st.error("Enter an address first")

        if st.session_state.create_project_geocode_message:
            st.success(f"✓ {st.session_state.create_project_geocode_message}")
    
    with col2:
        st.write("**Project Location**")
        st.info("💡 Enter address above and click 'Locate Address', or click the map to set coordinates manually")
        origin_lat = st.number_input(
            "Latitude", 
            format="%.6f",
            key="lat_input"
        )
        origin_lon = st.number_input(
            "Longitude", 
            format="%.6f",
            key="lon_input"
        )
        set_create_project_coords(origin_lat, origin_lon)
    
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
        queue_create_project_coords(origin_lat, origin_lon)
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

    normalize_project_destinations(project)
    
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
    col1, col2 = st.columns([3, 1])
    with col1:
        project.name = st.text_input("Project Name", value=project.name, label_visibility="collapsed")
        project.address = st.text_input("Project Address", value=project.address, label_visibility="collapsed")
    
    with col2:
        project.status = st.selectbox("Status", ["Draft", "In Progress", "Approved"], 
                                       index=["Draft", "In Progress", "Approved"].index(project.status),
                                       key="status_select")
    
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

    remap_notice_key = f"project_remap_notice_{project.project_id}"
    remap_notice = st.session_state.pop(remap_notice_key, None)
    if remap_notice:
        st.success(remap_notice)

    unmapped_count = project.unmapped_count
    total_count = project.total_count

    add_col, remap_col, status_col = st.columns([1, 1, 3])
    with add_col:
        if st.button("+ Add Address", use_container_width=True):
            st.session_state.show_add_form = True

    with remap_col:
        if st.button(
            "🗺️ Remap Routes",
            use_container_width=True,
            disabled=unmapped_count == 0,
        ):
            try:
                with st.spinner("Rebuilding walking routes..."):
                    remapped_count = remap_project_destinations(project)
                st.session_state[remap_notice_key] = (
                    f"Remapped {remapped_count} destination"
                    f"{'' if remapped_count == 1 else 's'}."
                )
                st.rerun()
            except Exception as e:
                st.error(f"Could not remap routes: {e}")

    with status_col:
        if total_count == 0:
            st.caption("Add destinations to start mapping walking routes.")
        elif unmapped_count == 0:
            st.caption("All destinations are currently mapped.")
        else:
            st.caption(
                f"{unmapped_count} destination"
                f"{'' if unmapped_count == 1 else 's'}"
                " need remapping after pin changes."
            )

    st.markdown("---")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📍 Addresses", "🗺️ Routes", "📊 Chart", "🗺️ Overview Map"])
    
    with tab1:
        st.subheader("Addresses")
        
        # Add address form
        if st.session_state.get("show_add_form", False):
            name_key = f"add_address_name_{project.project_id}"
            address_key = f"add_address_value_{project.project_id}"
            category_key = f"add_address_category_{project.project_id}"
            specific_use_key = f"add_address_specific_use_{project.project_id}"
            reset_form_key = f"reset_add_address_form_{project.project_id}"

            if st.session_state.pop(reset_form_key, False):
                st.session_state.pop(name_key, None)
                st.session_state.pop(address_key, None)
                st.session_state.pop(category_key, None)
                st.session_state.pop(specific_use_key, None)

            if category_key not in st.session_state:
                st.session_state[category_key] = category_options()[0]

            current_category = st.session_state[category_key]
            current_specific_options = specific_use_options(current_category)
            if (
                specific_use_key not in st.session_state
                or st.session_state[specific_use_key] not in current_specific_options
            ):
                st.session_state[specific_use_key] = current_specific_options[0]

            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name", key=name_key)
                address = st.text_input("Address", key=address_key)
            with col2:
                category = st.selectbox(
                    "Use Category",
                    category_options(),
                    key=category_key,
                )
                specific_use = st.selectbox(
                    "Specific Use",
                    specific_use_options(category),
                    key=specific_use_key,
                )

            action_col1, action_col2 = st.columns(2)
            with action_col1:
                submit_btn = st.button("Add Address", use_container_width=True, type="primary")
            with action_col2:
                cancel_btn = st.button("Cancel", use_container_width=True)

            if cancel_btn:
                st.session_state.show_add_form = False
                st.rerun()

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
                    dest.specific_use = specific_use
                    dest_dict = destination_to_dict(dest)
                    project_manager.add_destination(project.project_id, dest_dict)

                    st.session_state[reset_form_key] = True
                    st.session_state.show_add_form = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding address: {e}")
            
            st.markdown("---")
        
        # Display table
        if project.destinations:
            df_data = []
            for dest in project.destinations:
                normalized_dest = destination_from_dict(dest)
                distance_m = dest.get("distance_m")
                duration_s = dest.get("duration_s")
                distance_mi = distance_m / 1609.34 if distance_m is not None else None
                time_min = duration_s / 60 if duration_s is not None else None
                df_data.append({
                    "Name": dest["name"],
                    "Category": normalized_dest.category,
                    "Specific Use": normalized_dest.specific_use or "—",
                    "Address": dest["address"],
                    "Distance (mi)": f"{distance_mi:.2f}" if distance_mi is not None else "—",
                    "Time (min)": f"{time_min:.0f}" if time_min is not None else "—",
                    "Route": route_status_label(dest),
                    "Compliant": (
                        "✓" if dest.get("compliant") is True else
                        "✗" if dest.get("compliant") is False else
                        "—"
                    ),
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption("Manage saved addresses below.")

            edit_index = st.session_state.get(destination_edit_state_key(project.project_id))
            if edit_index is not None and edit_index >= len(project.destinations):
                stop_destination_edit(project.project_id)
                edit_index = None

            for idx, dest_dict in enumerate(project.destinations):
                normalized_dest = destination_from_dict(dest_dict)
                summary_col, edit_col, delete_col = st.columns([8, 1, 1])

                with summary_col:
                    st.markdown(
                        f"**{normalized_dest.name}**  \n"
                        f"{normalized_dest.category} | {normalized_dest.specific_use or '—'}  \n"
                        f"{normalized_dest.address}"
                    )

                with edit_col:
                    if st.button("✏️", key=f"edit_dest_{project.project_id}_{idx}", use_container_width=True):
                        start_destination_edit(project, idx)
                        st.rerun()

                with delete_col:
                    if st.button("🗑️", key=f"delete_dest_{project.project_id}_{idx}", use_container_width=True):
                        project_manager.remove_destination(project.project_id, idx)

                        active_edit_index = st.session_state.get(
                            destination_edit_state_key(project.project_id)
                        )
                        if active_edit_index == idx:
                            stop_destination_edit(project.project_id)
                        elif active_edit_index is not None and active_edit_index > idx:
                            st.session_state[destination_edit_state_key(project.project_id)] = (
                                active_edit_index - 1
                            )

                        st.rerun()

                if edit_index == idx:
                    edit_name_key = f"edit_address_name_{project.project_id}"
                    edit_address_key = f"edit_address_value_{project.project_id}"
                    edit_category_key = f"edit_address_category_{project.project_id}"
                    edit_specific_use_key = f"edit_address_specific_use_{project.project_id}"

                    if edit_category_key not in st.session_state:
                        st.session_state[edit_category_key] = normalized_dest.category

                    current_edit_category = st.session_state[edit_category_key]
                    current_edit_specific_options = specific_use_options(current_edit_category)
                    if (
                        edit_specific_use_key not in st.session_state
                        or st.session_state[edit_specific_use_key] not in current_edit_specific_options
                    ):
                        st.session_state[edit_specific_use_key] = current_edit_specific_options[0]

                    st.markdown("#### Edit Address")
                    edit_col1, edit_col2 = st.columns(2)
                    with edit_col1:
                        edited_name = st.text_input("Name", key=edit_name_key)
                        edited_address = st.text_input("Address", key=edit_address_key)
                    with edit_col2:
                        edited_category = st.selectbox(
                            "Use Category",
                            category_options(),
                            key=edit_category_key,
                        )
                        edited_specific_use = st.selectbox(
                            "Specific Use",
                            specific_use_options(edited_category),
                            key=edit_specific_use_key,
                        )

                    save_col, cancel_col = st.columns(2)
                    with save_col:
                        save_edit = st.button(
                            "Save Changes",
                            key=f"save_dest_{project.project_id}_{idx}",
                            use_container_width=True,
                            type="primary",
                        )
                    with cancel_col:
                        cancel_edit = st.button(
                            "Cancel Edit",
                            key=f"cancel_dest_{project.project_id}_{idx}",
                            use_container_width=True,
                        )

                    if cancel_edit:
                        stop_destination_edit(project.project_id)
                        st.rerun()

                    if save_edit and edited_name and edited_address:
                        try:
                            address_changed = edited_address.strip() != normalized_dest.address.strip()

                            if address_changed:
                                analyzer = RouteAnalyzer(
                                    origin=(project.origin_lat, project.origin_lon)
                                )
                                updated_dest = analyzer.analyze_destination(
                                    name=edited_name,
                                    address=edited_address,
                                    max_distance_m=project.max_distance_m,
                                )
                            else:
                                updated_dest = destination_from_dict(dest_dict)
                                updated_dest.name = edited_name
                                updated_dest.address = edited_address

                            updated_dest.name = edited_name
                            updated_dest.category = edited_category
                            updated_dest.specific_use = edited_specific_use
                            project.destinations[idx] = destination_to_dict(updated_dest)
                            project_manager.update_project(project)
                            stop_destination_edit(project.project_id)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error updating address: {e}")

                st.markdown("---")
            
            # Compliance summary
            compliant_count = project.compliant_count
            mapped_count = project.mapped_count
            unmapped_count = project.unmapped_count
            pdf_data_key = f"project_pdf_data_{project.project_id}"
            pdf_name_key = f"project_pdf_name_{project.project_id}"
            
            st.markdown("---")
            st.subheader("Export LEED Documentation")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Compliant", f"{compliant_count}/{mapped_count}" if mapped_count else "0/0")
            with col2:
                st.metric("Routes Ready", f"{mapped_count}/{project.total_count}")

            if unmapped_count:
                st.info(
                    f"{unmapped_count} destination"
                    f"{'' if unmapped_count == 1 else 's'}"
                    " are currently unmapped. Remap routes before exporting a PDF package."
                )
            
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
                    if unmapped_count:
                        st.error("Remap routes before generating the PDF package.")
                    else:
                        with st.spinner("Generating PDF..."):
                            try:
                                with TemporaryDirectory() as temp_dir:
                                    temp_path = Path(temp_dir)
                                    output_path = temp_path / f"{project.name.replace(' ', '_')}_report.pdf"
                                    map_paths = []

                                    for i, dest_dict in enumerate(project.destinations, start=1):
                                        analyzer = RouteAnalyzer(
                                            origin=(project.origin_lat, project.origin_lon)
                                        )
                                        dest = destination_from_dict(dest_dict)
                                        m = analyzer.make_route_map(
                                            dest,
                                            max_distance_m=project.max_distance_m,
                                            enrich=False,
                                        )
                                        map_file = temp_path / f"route_{i}_{dest.name.replace(' ', '_')}.html"
                                        ReportGenerator.save_map_html(m, map_file)
                                        map_paths.append(map_file)

                                    destinations = [destination_from_dict(d) for d in project.destinations]

                                    report = ReportGenerator(output_path=output_path)
                                    report.create_report(
                                        origin=(project.origin_lat, project.origin_lon),
                                        destinations=destinations,
                                        map_html_paths=map_paths
                                    )
                                    st.session_state[pdf_data_key] = output_path.read_bytes()
                                    st.session_state[pdf_name_key] = output_path.name

                                st.success("✓ PDF package is ready to download.")
                            except Exception as e:
                                st.error(f"Error generating PDF: {e}")

            if st.session_state.get(pdf_data_key) and st.session_state.get(pdf_name_key):
                st.download_button(
                    label="⬇️ Download PDF Package",
                    data=st.session_state[pdf_data_key],
                    file_name=st.session_state[pdf_name_key],
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"download_pdf_{project.project_id}",
                )
        else:
            st.info("No addresses added yet. Click '+ Add Address' to get started.")
    
    with tab2:
        st.subheader("Routes")
        if project.destinations:
            selected_idx = st.selectbox(
                "Select a route to view",
                range(len(project.destinations)),
                format_func=lambda i: (
                    project.destinations[i]["name"]
                    if is_destination_mapped(project.destinations[i])
                    else f"{project.destinations[i]['name']} (unmapped)"
                ),
            )
            
            if selected_idx is not None:
                dest_dict = project.destinations[selected_idx]
                dest = destination_from_dict(dest_dict)
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    if is_destination_mapped(dest_dict):
                        analyzer = RouteAnalyzer(
                            origin=(project.origin_lat, project.origin_lon)
                        )
                        m = analyzer.make_route_map(
                            dest,
                            max_distance_m=project.max_distance_m,
                            enrich=False,
                        )
                        st_folium(
                            m,
                            key=f"route_map_{project.project_id}_{selected_idx}_{destination_map_signature(dest)}",
                            height=500,
                            use_container_width=True,
                            returned_objects=[],
                        )
                    else:
                        st.info(
                            "This destination is currently unmapped. "
                            "Use 'Remap Routes' above to rebuild the walking route."
                        )
                
                with col2:
                    distance_mi = dest.distance_m / 1609.34 if dest.distance_m is not None else None
                    time_min = dest.duration_s / 60 if dest.duration_s is not None else None
                    
                    st.markdown(f"### {dest.name}")
                    st.markdown(
                        f"**Category:** {dest.category if dest.category != DEFAULT_CATEGORY else '—'}"
                    )
                    st.markdown(f"**Specific Use:** {dest.specific_use or '—'}")
                    st.markdown(f"**Address:** {dest.address}")
                    st.metric("Distance", f"{distance_mi:.2f} mi" if distance_mi is not None else "Unmapped")
                    st.metric("Walking Time", f"{time_min:.0f} min" if time_min is not None else "Unmapped")
                    
                    if dest.compliant is True:
                        st.success("✓ Compliant")
                    elif dest.compliant is False:
                        st.warning("⚠️ Non-compliant")
                    else:
                        st.info("Route not mapped")
        else:
            st.info("No routes to display. Add addresses first.")
    
    with tab3:
        st.subheader("Compliance Chart")
        if project.destinations:
            compliant_count = project.compliant_count
            non_compliant_count = project.non_compliant_count
            unmapped_count = project.unmapped_count
            
            chart_data = pd.DataFrame({
                "Status": ["Compliant", "Non-compliant", "Unmapped"],
                "Count": [compliant_count, non_compliant_count, unmapped_count]
            })
            
            st.bar_chart(chart_data.set_index("Status"))
            
            st.markdown("---")
            st.write("### Distance Distribution")
            distance_df = pd.DataFrame({
                "Name": [d["name"] for d in project.destinations if d.get("distance_m") is not None],
                "Distance (mi)": [
                    d["distance_m"] / 1609.34
                    for d in project.destinations
                    if d.get("distance_m") is not None
                ]
            })
            if distance_df.empty:
                st.info("No mapped route distances yet. Remap routes to populate this chart.")
            else:
                st.bar_chart(distance_df.set_index("Name"))
        else:
            st.info("No data to display. Add addresses first.")
    
    with tab4:
        st.subheader("Overview Map")
        notice_key = f"overview_notice_{project.project_id}"
        drag_memory_key = f"overview_last_drag_{project.project_id}"

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
                f"Click the edit tool on the map, drag '{selected_name}' to its new location, then click Save."
            )
        else:
            st.caption("Click the edit tool on the map, drag the origin marker, then click Save.")

        m = build_editable_overview_map(project, move_target, destination_index)
        overview_signature = project_map_signature(project)
        map_data = st_folium(
            m,
            key=f"overview_map_{project.project_id}_{move_target}_{destination_index}_{overview_signature}",
            height=550,
            use_container_width=True,
            returned_objects=["all_drawings", "last_active_drawing"],
        )

        dragged_point = extract_drawn_point(map_data)
        if dragged_point:
            new_lat, new_lon = dragged_point
            drag_signature = f"{move_target}:{destination_index}:{new_lat:.6f},{new_lon:.6f}"

            if drag_signature != st.session_state.get(drag_memory_key):
                try:
                    if move_target == "Project origin":
                        if coords_changed(project.origin_lat, project.origin_lon, new_lat, new_lon):
                            with st.spinner("Updating location..."):
                                move_project_origin(project, new_lat, new_lon)
                            st.session_state[notice_key] = (
                                "Project origin moved. Existing routes were marked as unmapped "
                                "so you can remap them from the button above."
                            )
                    else:
                        current_dest = project.destinations[destination_index]
                        if coords_changed(current_dest["lat"], current_dest["lon"], new_lat, new_lon):
                            with st.spinner("Updating location..."):
                                move_destination_point(project, destination_index, new_lat, new_lon)
                            moved_name = current_dest["name"]
                            st.session_state[notice_key] = (
                                f"Destination '{moved_name}' moved and marked as unmapped. "
                                "Use the remap button above to rebuild its route."
                            )

                    st.session_state[drag_memory_key] = drag_signature
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not update the dragged marker: {e}")

        if not project.destinations:
            st.info("You can still drag the origin marker here even before any destinations are added.")

# ============= ROUTER =============
if st.session_state.page == "dashboard":
    page_dashboard()
elif st.session_state.page == "create_project":
    page_create_project()
elif st.session_state.page == "project":
    page_project()
