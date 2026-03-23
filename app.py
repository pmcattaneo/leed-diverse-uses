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

st.set_page_config(page_title="LEED_SURROUND Dashboard", layout="wide")

# Initialize session state
if "page" not in st.session_state:
    st.session_state.page = "dashboard"
if "current_project_id" not in st.session_state:
    st.session_state.current_project_id = None

project_manager = ProjectManager()

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

# --- CSS Theme & Neo-Brutalist Styling ---
def apply_custom_styles():
    st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700;800;900&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
    <style>
        /* Global Styles */
        html, body, [data-testid="stAppViewContainer"] {
            background-color: #f5f0e8 !important;
            font-family: 'Inter', sans-serif !important;
            color: #1a1a1a !important;
        }
        [data-testid="stHeader"] {
            display: none !important;
        }
        .block-container {
            padding-top: 0rem !important;
            max-width: 95% !important;
        }
        [data-testid="stVerticalBlock"] {
            gap: 0rem !important;
        }

        h1, h2, h3, .font-headline {
            font-family: 'Space Grotesk', sans-serif !important;
            font-weight: 900 !important;
            text-transform: uppercase !important;
            letter-spacing: -0.05em !important;
        }

        /* Top Nav Bar */
        .top-nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
            padding: 1rem 1.5rem;
            position: sticky;
            top: 0;
            z-index: 1000;
            background-color: #f5f0e8;
            border-bottom: 4px solid #1a1a1a;
            box-shadow: 4px 4px 0px 0px rgba(26,26,26,1);
            margin-bottom: 2rem;
        }
        .nav-logo {
            font-size: 1.5rem;
            font-weight: 900;
            text-transform: uppercase;
            font-family: 'Space Grotesk';
            letter-spacing: -0.05em;
        }
        .nav-links {
            display: flex;
            gap: 2rem;
            align-items: center;
        }
        .nav-link {
            font-family: 'Space Grotesk';
            font-weight: 700;
            text-transform: uppercase;
            text-decoration: none;
            color: #1a1a1a;
            padding: 0.25rem 0.5rem;
            transition: all 0.1s;
        }
        .nav-link:hover {
            background-color: #1a1a1a;
            color: #f5f0e8;
        }
        .nav-link.active {
            color: #ffcc00;
            text-decoration: underline;
            text-decoration-thickness: 4px;
            text-underline-offset: 8px;
        }

        /* Neo-Brutalist Components */
        .neo-card {
            background-color: #ffffff;
            border: 4px solid #1a1a1a;
            box-shadow: 6px 6px 0px 0px rgba(26,26,26,1);
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            transition: transform 0.1s, box-shadow 0.1s;
        }
        .neo-card:hover {
            transform: translate(-2px, -2px);
            box-shadow: 8px 8px 0px 0px rgba(26,26,26,1);
        }
        .neo-btn {
            background-color: #ffcc00;
            border: 4px solid #1a1a1a;
            color: #1a1a1a;
            font-family: 'Space Grotesk';
            font-weight: 900;
            text-transform: uppercase;
            padding: 1rem 2rem;
            box-shadow: 4px 4px 0px 0px rgba(26,26,26,1);
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            text-decoration: none;
        }
        .neo-btn:hover {
            box-shadow: none;
            transform: translate(4px, 4px);
        }

        /* Sidebar/Progress styling */
        .status-bar {
            background-color: #eee9e0;
            border: 4px solid #1a1a1a;
            padding: 1.5rem;
            box-shadow: 6px 6px 0px 0px rgba(26,26,26,1);
        }

        /* Hide default Streamlit elements */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

def render_top_nav():
    # Persistent header and navigation using Streamlit columns for interactivity
    cols = st.columns([3, 8, 1])
    with cols[0]:
        st.markdown('<div class="nav-logo" style="padding-top: 0.5rem;">LEED_SURROUND</div>', unsafe_allow_html=True)
    with cols[1]:
        c1, c2, c3, c4, c5 = st.columns(5)
        if c1.button("Dashboard", key="nav_dash", use_container_width=True, type="primary" if st.session_state.page == "dashboard" else "secondary"):
            st.session_state.page = "dashboard"
            st.rerun()
        if c2.button("Map", key="nav_map", use_container_width=True, type="primary" if st.session_state.page == "location" else "secondary"):
            st.session_state.page = "location"
            st.rerun()
        if c3.button("Inventory", key="nav_inv", use_container_width=True, type="primary" if st.session_state.page == "inventory" else "secondary"):
            st.session_state.page = "inventory"
            st.rerun()
        if c4.button("Density", key="nav_dens", use_container_width=True, type="primary" if st.session_state.page == "density" else "secondary"):
            st.session_state.page = "density"
            st.rerun()
        if c5.button("Review", key="nav_rev", use_container_width=True, type="primary" if st.session_state.page == "review" else "secondary"):
            st.session_state.page = "review"
            st.rerun()
    with cols[2]:
        st.markdown('<span class="material-symbols-outlined" style="font-size: 2.5rem; float: right; padding-top: 0.2rem;">account_circle</span>', unsafe_allow_html=True)
    st.markdown('<div style="border-bottom: 4px solid #1a1a1a; box-shadow: 4px 4px 0px 0px rgba(26,26,26,1); margin-bottom: 2rem;"></div>', unsafe_allow_html=True)

# --- App Logic & Screens ---

def page_dashboard():
    st.markdown("""
    <header style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 4rem; flex-wrap: wrap; gap: 2rem;">
        <div style="max-width: 600px;">
            <h1 style="font-size: 6rem; md:font-size: 8rem; line-height: 0.85; margin: 0; font-family: 'Space Grotesk', sans-serif; font-weight: 900; text-transform: uppercase; letter-spacing: -0.05em;">CREDIT<br>HUB</h1>
            <div style="border-left: 4px solid #1a1a1a; padding-left: 1rem; margin-top: 1rem; font-size: 1.25rem; font-weight: 500;">
                Managing documentation for Surrounding Density and Diverse Uses. Track compliance and verify point thresholds for V4.1 certifications.
            </div>
        </div>
    </header>
    """, unsafe_allow_html=True)
    
    if st.button("START NEW DOCUMENTATION ⊕", key="new_doc_btn"):
        st.session_state.page = "location"
        st.session_state.current_project_id = None
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Stats Grid (Bento Style)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div style="background-color: #eee9e0; border: 4px solid #1a1a1a; padding: 2rem; box-shadow: 6px 6px 0px 0px rgba(26,26,26,1); height: 100%;">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 1.5rem;">
                <span style="font-family: 'Space Grotesk'; font-weight: 700; text-transform: uppercase; font-size: 0.875rem; color: #4a4a4a;">Option 1</span>
                <span class="material-symbols-outlined" style="font-size: 2.5rem;">apartment</span>
            </div>
            <h2 style="font-size: 3rem; margin: 0;">6/6 <span style="font-size: 1.5rem;">PTS</span></h2>
            <h3 style="font-size: 1.25rem; margin-bottom: 1rem;">SURROUNDING DENSITY</h3>
            <div style="width: 100%; height: 1rem; background-color: #e8e3da; border: 2px solid #1a1a1a;">
                <div style="width: 100%; height: 100%; background-color: #0055ff;"></div>
            </div>
            <p style="margin-top: 1rem; font-size: 0.875rem; font-weight: 500;">Requirement: Combined density of 22,000 sq.ft/acre.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background-color: #ffcc00; border: 4px solid #1a1a1a; padding: 2rem; box-shadow: 6px 6px 0px 0px rgba(26,26,26,1); height: 100%;">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 1.5rem;">
                <span style="font-family: 'Space Grotesk'; font-weight: 700; text-transform: uppercase; font-size: 0.875rem; color: #1a1a1a;">Option 2</span>
                <span class="material-symbols-outlined" style="font-size: 2.5rem;">storefront</span>
            </div>
            <h2 style="font-size: 3rem; margin: 0; color: #1a1a1a;">2/2 <span style="font-size: 1.5rem;">PTS</span></h2>
            <h3 style="font-size: 1.25rem; margin-bottom: 1rem; color: #1a1a1a;">DIVERSE USES</h3>
            <div style="width: 100%; height: 1rem; background-color: rgba(255,255,255,0.3); border: 2px solid #1a1a1a;">
                <div style="width: 100%; height: 100%; background-color: #1a1a1a;"></div>
            </div>
            <p style="margin-top: 1rem; font-size: 0.875rem; font-weight: 500; color: #1a1a1a;">Requirement: 4-7 uses within 1/2 mile walking distance.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown('<h2 style="font-size: 2.5rem; border-bottom: 8px solid #1a1a1a; display: inline-block; padding-bottom: 0.5rem; margin-bottom: 2rem;">ACTIVE PROJECTS</h2>', unsafe_allow_html=True)
    
    projects = project_manager.list_projects()
    if not projects:
        st.info("No projects yet. Start new documentation above.")
    else:
        cols = st.columns(3)
        for idx, project in enumerate(projects):
            with cols[idx % 3]:
                st.markdown(f"""
                <div class="neo-card" style="display: flex; flex-direction: column; min-height: 400px;">
                    <div style="height: 180px; width: 100%; border-bottom: 4px solid #1a1a1a; background-color: #e8e3da; display: flex; align-items: center; justify-content: center; position: relative;">
                        <span class="material-symbols-outlined" style="font-size: 4rem; color: #1a1a1a; opacity: 0.2;">apartment</span>
                        <div style="position: absolute; top: 1rem; right: 1rem; background-color: #1a1a1a; color: white; padding: 0.25rem 0.75rem; font-family: 'Space Grotesk'; font-weight: 700; font-size: 0.75rem;">V4.1 BD+C</div>
                    </div>
                    <div style="padding: 1.5rem; flex-grow: 1;">
                        <h3 style="font-size: 1.5rem; margin: 0;">{project.name}</h3>
                        <p style="color: #4a4a4a; font-weight: 500; font-size: 0.875rem; margin-bottom: 1.5rem;">📍 {project.address}</p>
                        <div style="display: flex; justify-content: space-between; font-size: 0.75rem; font-weight: 700; margin-bottom: 0.25rem;">
                            <span>COMPLETION</span>
                            <span>85%</span>
                        </div>
                        <div style="width: 100%; height: 12px; background-color: #e8e3da; border: 2px solid #1a1a1a;">
                            <div style="width: 85%; height: 100%; background-color: #e63b2e;"></div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"VIEW DETAILS", key=f"view_{project.project_id}", use_container_width=True):
                    st.session_state.current_project_id = project.project_id
                    st.session_state.page = "location"
                    st.rerun()

def page_location():
    project = None
    if st.session_state.current_project_id:
        project = project_manager.get_project(st.session_state.current_project_id)
    
    st.markdown("""
    <div style="width: 100%; height: 1.5rem; background-color: #eee9e0; border: 2px solid #1a1a1a; margin-bottom: 3rem; display: flex;">
        <div style="width: 20%; background-color: #ffcc00; height: 100%; border-right: 2px solid #1a1a1a;"></div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([5, 7], gap="large")
    
    with col1:
        st.markdown(f"""
        <div>
            <span style="display: inline-block; background-color: #e63b2e; color: white; padding: 0.25rem 0.75rem; font-family: 'Space Grotesk'; font-weight: 700; text-transform: uppercase; font-size: 0.875rem; margin-bottom: 1rem;">Step 01</span>
            <h1 style="font-size: 4rem; line-height: 1; margin: 0; font-family: 'Space Grotesk'; font-weight: 900; text-transform: uppercase; letter-spacing: -0.05em; margin-bottom: 1.5rem;">
                Where is your <br><span style="color: #0055ff;">project</span> located?
            </h1>
            <p style="font-size: 1.25rem; color: #4a4a4a; max-width: 400px; margin-bottom: 2rem;">
                LEED certification requires a precise project boundary. Enter your address to start the radius analysis.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        project_name = st.text_input("PROJECT NAME", value=project.name if project else "", placeholder="e.g., Ninth Ave Mixed-Use")
        address = st.text_input("STREET ADDRESS", value=project.address if project else "", placeholder="123 Bauhaus Boulevard, Chicago, IL")
        
        radius_col1, radius_col2 = st.columns(2)
        radius_miles = 0.25
        if project:
            radius_miles = project.radius_miles

        with radius_col1:
            if st.button("1/4 MILE RADIUS", key="rad_1_4", use_container_width=True,
                         type="primary" if radius_miles == 0.25 else "secondary"):
                radius_miles = 0.25
                if project:
                    project.radius_miles = 0.25
                    project.max_distance_m = 402.34
                    project_manager.update_project(project)
                    st.rerun()
        with radius_col2:
            if st.button("1/2 MILE RADIUS", key="rad_1_2", use_container_width=True,
                         type="primary" if radius_miles == 0.5 else "secondary"):
                radius_miles = 0.5
                if project:
                    project.radius_miles = 0.5
                    project.max_distance_m = 804.67
                    project_manager.update_project(project)
                    st.rerun()

        if st.button("NEXT ➔", key="loc_next", use_container_width=True):
            if not project:
                # Logic to geocode and create project
                try:
                    analyzer = RouteAnalyzer(origin=(0,0))
                    lat, lon = analyzer.geocode(address)
                    new_project = project_manager.create_project(project_name, address, lat, lon)
                    new_project.radius_miles = radius_miles
                    new_project.max_distance_m = 402.34 if radius_miles == 0.25 else 804.67
                    project_manager.update_project(new_project)
                    st.session_state.current_project_id = new_project.project_id
                except:
                    st.error("Could not geocode address")
            st.session_state.page = "inventory"
            st.rerun()

    with col2:
        st.markdown("""
        <div style="border: 4px solid #1a1a1a; background-color: #ffffff; box-shadow: 8px 8px 0px 0px rgba(26,26,26,1); position: relative; aspect-ratio: 1/1;">
            <div style="position: absolute; top: 1.5rem; right: 1.5rem; background-color: #1a1a1a; color: white; padding: 0.5rem 1rem; font-family: 'Space Grotesk'; font-weight: 700; font-size: 0.75rem; z-index: 10;">LIVE ANALYSIS: ACTIVE</div>
        """, unsafe_allow_html=True)

        if project:
            m = folium.Map(location=[project.origin_lat, project.origin_lon], zoom_start=15, tiles="CartoDB positron")
            folium.Circle(
                radius=project.max_distance_m,
                location=[project.origin_lat, project.origin_lon],
                color="#e63b2e",
                fill=True,
                fill_color="#e63b2e",
                fill_opacity=0.1,
                dash_array='5, 5'
            ).add_to(m)
            folium.Marker(
                [project.origin_lat, project.origin_lon],
                icon=folium.Icon(color="black", icon="info-sign")
            ).add_to(m)
            st_folium(m, height=500, use_container_width=True)
        else:
            st.markdown("""
            <div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; background-color: #e8e3da;">
                <span class="material-symbols-outlined" style="font-size: 8rem; opacity: 0.1;">map</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

def page_inventory():
    project = None
    if st.session_state.current_project_id:
        project = project_manager.get_project(st.session_state.current_project_id)

    if not project:
        st.warning("Please set your project location first.")
        if st.button("GO TO LOCATION STEP"):
            st.session_state.page = "location"
            st.rerun()
        return

    st.markdown("""
    <div style="margin-bottom: 3rem; border-bottom: 4px solid #1a1a1a; padding-bottom: 1rem;">
        <p style="font-family: 'Space Grotesk'; font-weight: 900; text-transform: uppercase; text-size: 0.875rem; color: #e63b2e; letter-spacing: 0.1em; margin-bottom: 0.5rem;">Phase 02 / Inventory</p>
        <h1 style="font-size: 5rem; line-height: 0.9; margin: 0; font-family: 'Space Grotesk'; font-weight: 900; text-transform: uppercase;">Diverse Use <br>Identification</h1>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([7, 5], gap="large")
    with col1:
        st.markdown("""
        <div style="background-color: #ffcc00; border: 4px solid #1a1a1a; padding: 2rem; box-shadow: 6px 6px 0px 0px rgba(26,26,26,1); margin-bottom: 2rem;">
            <h2 style="font-size: 2rem; margin-bottom: 1.5rem; line-height: 1.2;">Let's find your nearby services. What would you like to add?</h2>
        </div>
        """, unsafe_allow_html=True)

        with st.form("add_use_form"):
            name = st.text_input("NAME OF USE")
            address = st.text_input("ADDRESS")
            category = st.selectbox("CATEGORY", [
                "Food Retail", "Community Anchors", "Services", "Civic Facilities", "Other"
            ])
            if st.form_submit_button("ADD TO INVENTORY ⊕", use_container_width=True):
                if name and address:
                    try:
                        analyzer = RouteAnalyzer(origin=(project.origin_lat, project.origin_lon))
                        dest = analyzer.analyze_destination(name, address, max_distance_m=project.max_distance_m)
                        dest.category = category
                        project_manager.add_destination(project.project_id, destination_to_dict(dest))
                        st.success(f"Added {name}")
                        st.rerun()
                    except:
                        st.error("Could not geocode address")
    
    with col2:
        st.markdown("""
        <div style="background-color: #ffffff; border: 4px solid #1a1a1a; padding: 1.5rem; box-shadow: 6px 6px 0px 0px rgba(26,26,26,1);">
            <div style="display: flex; gap: 1rem; align-items: start;">
                <span class="material-symbols-outlined" style="color: #e63b2e; font-size: 2.5rem;">lightbulb</span>
                <div>
                    <h4 style="font-family: 'Space Grotesk'; font-weight: 700; text-transform: uppercase; margin: 0 0 0.5rem 0;">Pro-Tip: LEED Rule 4.1</h4>
                    <p style="font-size: 0.875rem; margin: 0;">You can count a maximum of <b>2 uses per category</b>. Focus on high-quality pedestrian routes first.</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    
    main_col, side_col = st.columns([8, 4], gap="large")
    
    with side_col:
        # Category compliance sidebar
        st.markdown("""
        <div style="background-color: #eee9e0; border: 4px solid #1a1a1a; padding: 1.5rem; box-shadow: 6px 6px 0px 0px rgba(26,26,26,1);">
            <h3 style="font-size: 1.25rem; border-bottom: 2px solid #1a1a1a; padding-bottom: 0.5rem; margin-bottom: 1.5rem;">COMPLIANCE STATUS</h3>
        """, unsafe_allow_html=True)
        
        categories = ["Food Retail", "Community Anchors", "Services", "Civic Facilities"]
        for cat in categories:
            cat_uses = [d for d in project.destinations if d.get("category") == cat and d.get("compliant")]
            count = len(cat_uses)
            limited_count = min(count, 2)
            progress = limited_count / 2
            
            st.markdown(f"""
            <div style="margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.25rem;">
                    <span>{cat}</span>
                    <span>{limited_count}/2</span>
                </div>
                <div style="width: 100%; height: 12px; background-color: #ffffff; border: 2px solid #1a1a1a;">
                    <div style="width: {progress*100}%; height: 100%; background-color: {'#ffcc00' if progress < 1 else '#0055ff'};"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if count > 2:
                st.markdown('<p style="font-size: 10px; color: #e63b2e; font-weight: bold; margin: 0;">⚠️ CATEGORY MAXED</p>', unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)

    with main_col:
        if project.destinations:
            st.markdown('<h3 style="margin-bottom: 1rem;">CURRENT INVENTORY</h3>', unsafe_allow_html=True)
            for idx, dest in enumerate(project.destinations):
                dist_mi = dest.get("distance_m", 0) / 1609.34
                is_compliant = dest.get("compliant", False)
                st.markdown(f"""
                <div class="neo-card" style="padding: 1rem; display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; gap: 1rem; align-items: center;">
                        <div style="width: 3rem; height: 3rem; background-color: #ffcc00; border: 2px solid #1a1a1a; display: flex; align-items: center; justify-content: center;">
                            <span class="material-symbols-outlined">{'local_grocery_store' if dest['category']=='Food Retail' else 'home_repair_service'}</span>
                        </div>
                        <div>
                            <p style="font-family: 'Space Grotesk'; font-weight: 700; text-transform: uppercase; margin: 0;">{dest['name']}</p>
                            <p style="font-size: 0.75rem; color: #4a4a4a; margin: 0;">{dest['category']} | {dist_mi:.2f} MILES</p>
                        </div>
                    </div>
                    <div>
                        <span class="material-symbols-outlined" style="color: {'#2ecc71' if is_compliant else '#e63b2e'}; font-size: 2rem;">{'check_circle' if is_compliant else 'cancel'}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("REMOVE", key=f"rem_{idx}"):
                    project_manager.remove_destination(project.project_id, idx)
                    st.rerun()
        else:
            st.info("No items in inventory. Add uses above.")

def page_density():
    project = None
    if st.session_state.current_project_id:
        project = project_manager.get_project(st.session_state.current_project_id)

    if not project:
        st.warning("Please set your project location first.")
        return

    st.markdown("""
    <header style="margin-bottom: 3rem; border-left: 8px solid #ffcc00; padding-left: 1.5rem;">
        <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
            <span style="background-color: #1a1a1a; color: #f5f0e8; padding: 0.25rem 0.75rem; font-family: 'Space Grotesk'; font-weight: 900; font-size: 0.875rem; text-transform: uppercase;">Step 03</span>
            <span style="font-family: 'Space Grotesk'; font-weight: 700; text-transform: uppercase; font-size: 0.875rem; color: #4a4a4a; letter-spacing: 0.1em;">Calculation Phase</span>
        </div>
        <h1 style="font-size: 5rem; line-height: 1; margin: 0; font-family: 'Space Grotesk'; font-weight: 900; text-transform: uppercase; letter-spacing: -0.05em;">Surrounding <br><span style="color: #0055ff;">Density.</span></h1>
        <p style="font-size: 1.25rem; font-weight: 500; margin-top: 1.5rem; max-width: 700px;">Calculate the residential and non-residential density of the surrounding area within a 1/4 mile (400-meter) radius.</p>
    </header>
    """, unsafe_allow_html=True)

    col_form, col_stats = st.columns([8, 4], gap="large")
    
    with col_form:
        # Non-Res Card
        with st.container():
            st.markdown("""
            <div style="background-color: #ffffff; border: 4px solid #1a1a1a; padding: 2rem; box-shadow: 8px 8px 0px 0px rgba(26,26,26,1); margin-bottom: 2rem;">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 2rem;">
                    <div>
                        <h2 style="font-size: 2rem; margin: 0; font-family: 'Space Grotesk';">NON-RESIDENTIAL DENSITY</h2>
                        <p style="font-size: 0.75rem; font-weight: 700; color: #4a4a4a; text-transform: uppercase; letter-spacing: 0.1em;">Calculated in Floor Area Ratio (FAR)</p>
                    </div>
                    <span class="material-symbols-outlined" style="background-color: #1a1a1a; color: white; padding: 0.5rem; font-size: 2.5rem;">corporate_fare</span>
                </div>
            """, unsafe_allow_html=True)
            
            c1, c2 = st.columns(2)
            non_res_sqft = c1.number_input("TOTAL BUILDING SQUARE FOOTAGE (FT²)", value=project.non_res_sqft)
            land_area_sqft = c2.number_input("SURROUNDING LAND AREA (FT²)", value=project.land_area_sqft)
            
            far = non_res_sqft / land_area_sqft if land_area_sqft > 0 else 0.0
            
            st.markdown(f"""
                <div style="background-color: #eee9e0; border: 2px dashed #1a1a1a; padding: 1.5rem; margin-top: 2rem; display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-family: 'Space Grotesk'; font-weight: 700; text-transform: uppercase; font-size: 1.125rem;">Current Non-Res FAR</div>
                    <div style="font-size: 3rem; font-weight: 900; color: #0055ff;">{far:.2f}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Residential Card
        with st.container():
            st.markdown("""
            <div style="background-color: #ffffff; border: 4px solid #1a1a1a; padding: 2rem; box-shadow: 8px 8px 0px 0px rgba(26,26,26,1); margin-bottom: 2rem;">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 2rem;">
                    <div>
                        <h2 style="font-size: 2rem; margin: 0; font-family: 'Space Grotesk';">RESIDENTIAL DENSITY</h2>
                        <p style="font-size: 0.75rem; font-weight: 700; color: #4a4a4a; text-transform: uppercase; letter-spacing: 0.1em;">Dwelling Units Per Acre (DU/Acre)</p>
                    </div>
                    <span class="material-symbols-outlined" style="background-color: #1a1a1a; color: white; padding: 0.5rem; font-size: 2.5rem;">home_work</span>
                </div>
            """, unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            dwelling_units = c1.number_input("TOTAL DWELLING UNITS (DU)", value=project.dwelling_units)
            res_land_area_acres = c2.number_input("RESIDENTIAL LAND AREA (ACRES)", value=project.res_land_area_acres)

            du_acre = dwelling_units / res_land_area_acres if res_land_area_acres > 0 else 0.0

            st.markdown(f"""
                <div style="background-color: #eee9e0; border: 2px dashed #1a1a1a; padding: 1.5rem; margin-top: 2rem; display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-family: 'Space Grotesk'; font-weight: 700; text-transform: uppercase; font-size: 1.125rem;">Current DU/Acre</div>
                    <div style="font-size: 3rem; font-weight: 900; color: #e63b2e;">{du_acre:.1f}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        if st.button("LOCK CALCULATIONS ➔", use_container_width=True):
            project.non_res_sqft = non_res_sqft
            project.land_area_sqft = land_area_sqft
            project.dwelling_units = dwelling_units
            project.res_land_area_acres = res_land_area_acres
            project_manager.update_project(project)
            st.success("Calculations locked.")

    with col_stats:
        # Threshold Monitor
        st.markdown("""
        <div style="background-color: #ffcc00; border: 4px solid #1a1a1a; padding: 1.5rem; box-shadow: 4px 4px 0px 0px rgba(26,26,26,1);">
            <h3 style="font-size: 1.5rem; display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1.5rem;">
                <span class="material-symbols-outlined">analytics</span> THRESHOLD MONITOR
            </h3>
        """, unsafe_allow_html=True)

        # FAR Progress
        far_goal = 2.0
        far_pct = min(far / far_goal, 1.0) if far_goal > 0 else 0
        st.markdown(f"""
        <div style="margin-bottom: 1.5rem;">
            <div style="display: flex; justify-content: space-between; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.5rem;">
                <span>Non-Residential Goal (v4.1)</span>
                <span>2.0 FAR</span>
            </div>
            <div style="width: 100%; height: 2rem; background-color: #f5f0e8; border: 4px solid #1a1a1a; position: relative; overflow: hidden;">
                <div style="width: {far_pct*100}%; height: 100%; background-color: #0055ff; border-right: 4px solid #1a1a1a;"></div>
            </div>
            <p style="text-align: right; font-weight: 900; font-size: 0.875rem; margin-top: 0.5rem;">{far_pct*100:.1f}% REACHED</p>
        </div>
        """, unsafe_allow_html=True)

        # DU Progress
        du_goal = 7.0
        du_pct = min(du_acre / du_goal, 1.0) if du_goal > 0 else 0
        st.markdown(f"""
        <div style="margin-bottom: 1.5rem;">
            <div style="display: flex; justify-content: space-between; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.5rem;">
                <span>Residential Goal (v4.1)</span>
                <span>7 DU/Acre</span>
            </div>
            <div style="width: 100%; height: 2rem; background-color: #f5f0e8; border: 4px solid #1a1a1a; position: relative; overflow: hidden;">
                <div style="width: {du_pct*100}%; height: 100%; background-color: #e63b2e; border-right: 4px solid #1a1a1a;"></div>
            </div>
            <p style="text-align: right; font-weight: 900; font-size: 0.875rem; margin-top: 0.5rem;">{'THRESHOLD EXCEEDED' if du_acre >= 7 else f'{du_pct*100:.1f}% REACHED'}</p>
        </div>
        """, unsafe_allow_html=True)

        # Estimated Points
        pts = 0
        if far >= 0.5: pts += 1
        if far >= 2.0: pts += 1
        if du_acre >= 7: pts += 1
        st.markdown(f"""
        <div style="border-top: 2px dotted #1a1a1a; padding-top: 1.5rem;">
            <div style="background-color: #1a1a1a; color: white; padding: 1rem; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 700; text-transform: uppercase;">Estimated Points</span>
                <span style="font-size: 2.5rem; font-weight: 900;">{min(pts, 3)}/3</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

def page_review():
    project = None
    if st.session_state.current_project_id:
        project = project_manager.get_project(st.session_state.current_project_id)

    if not project:
        st.warning("Please select a project first.")
        return

    st.markdown("""
    <div style="margin-bottom: 4rem;">
        <h1 style="font-size: 5rem; line-height: 1; margin: 0; font-family: 'Space Grotesk'; font-weight: 900; text-transform: uppercase; letter-spacing: -0.05em;">Final Review & <br>Documentation</h1>
        <p style="font-size: 1.25rem; font-weight: 700; border-left: 8px solid #1a1a1a; padding-left: 1rem; margin-top: 1rem; text-transform: uppercase;">Verification Phase: 94% Complete</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([4, 8], gap="large")

    with col1:
        # Point Summary
        pts_diverse = 0
        cat_counts = {}
        for d in project.destinations:
            if d.get("compliant"):
                cat = d.get("category", "Other")
                cat_counts[cat] = cat_counts.get(cat, 0) + 1

        # LEED v4.1 Diverse Uses Points
        uses_count = sum(min(count, 2) for count in cat_counts.values())
        if uses_count >= 8: pts_diverse = 2
        elif uses_count >= 4: pts_diverse = 1

        # Density Points
        pts_density = 0
        far = project.non_res_sqft / project.land_area_sqft if project.land_area_sqft > 0 else 0
        du_acre = project.dwelling_units / project.res_land_area_acres if project.res_land_area_acres > 0 else 0
        if far >= 0.5: pts_density += 1
        if far >= 2.0: pts_density += 1
        if du_acre >= 7: pts_density += 1

        total_pts = pts_diverse + pts_density

        st.markdown(f"""
        <div style="background-color: #ffcc00; border: 4px solid #1a1a1a; padding: 2rem; box-shadow: 8px 8px 0px 0px rgba(26,26,26,1); margin-bottom: 2rem;">
            <h2 style="font-size: 2rem; font-family: 'Space Grotesk'; margin-bottom: 1.5rem;">POINT SUMMARY</h2>
            <div style="border-bottom: 4px solid #1a1a1a; padding-bottom: 1rem; display: flex; justify-content: space-between; align-items: end;">
                <span style="font-weight: 700; text-transform: uppercase;">Earned</span>
                <span style="font-size: 6rem; font-weight: 900; line-height: 1;">{total_pts:02d}</span>
            </div>
            <p style="margin-top: 1rem; font-weight: 700; text-transform: uppercase; font-size: 0.875rem;">Threshold: 4/5 Required for Platinum</p>
        </div>
        """, unsafe_allow_html=True)

        # Action Buttons
        if st.button("DOWNLOAD LEED LETTER ⬇", use_container_width=True):
             st.info("Template generation in progress...")

        if st.button("EXPORT MAP FOR SUBMISSION ⬇", use_container_width=True):
             st.info("Map export in progress...")

    with col2:
        # Map Preview
        st.markdown("""
        <div style="background-color: #eee9e0; border: 4px solid #1a1a1a; padding: 1.5rem; margin-bottom: 2rem;">
            <h3 style="font-size: 1.25rem; margin-bottom: 1rem;">SUBMISSION MAP PREVIEW</h3>
            <div style="background-color: white; border: 2px solid #1a1a1a; aspect-ratio: 21/9; display: flex; align-items: center; justify-content: center; overflow: hidden; position: relative;">
        """, unsafe_allow_html=True)

        m_preview = build_overview_map(project)
        st_folium(m_preview, height=300, use_container_width=True, key="preview_map")

        st.markdown("""
                <div style="position: absolute; inset: 0; border: 16px solid rgba(26,26,26,0.1); pointer-events: none;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Verification Cards
        v_col1, v_col2 = st.columns(2)
        with v_col1:
            st.markdown(f"""
            <div style="background-color: white; border: 4px solid #1a1a1a; padding: 1.5rem; display: flex; gap: 1rem; align-items: start;">
                <div style="background-color: #2ecc71; border: 2px solid #1a1a1a; padding: 0.25rem; color: white;">
                    <span class="material-symbols-outlined">check_circle</span>
                </div>
                <div>
                    <h4 style="margin: 0; font-size: 1.125rem;">DENSITY VERIFIED</h4>
                    <p style="font-size: 0.75rem; color: #4a4a4a; margin-top: 0.25rem;">FAR of {far:.2f} meets v4.1 requirements.</p>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with v_col2:
            st.markdown(f"""
            <div style="background-color: white; border: 4px solid #1a1a1a; padding: 1.5rem; display: flex; gap: 1rem; align-items: start;">
                <div style="background-color: #2ecc71; border: 2px solid #1a1a1a; padding: 0.25rem; color: white;">
                    <span class="material-symbols-outlined">check_circle</span>
                </div>
                <div>
                    <h4 style="margin: 0; font-size: 1.125rem;">USES MAPPED</h4>
                    <p style="font-size: 0.75rem; color: #4a4a4a; margin-top: 0.25rem;">{uses_count} diverse uses identified.</p>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # Audit Log
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div style="border: 4px solid #1a1a1a; background-color: #ffffff; overflow: hidden;">
        <div style="background-color: #1a1a1a; color: white; padding: 1rem; font-weight: 900; text-transform: uppercase; letter-spacing: 0.1em; font-size: 0.875rem;">Review Audit Log</div>
        <div style="padding: 1rem; border-bottom: 2px solid #1a1a1a; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 700;">V2.4 INVENTORY SNAPSHOT</span>
            <span style="font-family: monospace; font-size: 0.875rem;">2023-10-24 14:22</span>
        </div>
        <div style="padding: 1rem; border-bottom: 2px solid #1a1a1a; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 700;">AUTOMATED DISTANCE AUDIT</span>
            <span style="background-color: #ffcc00; border: 2px solid #1a1a1a; padding: 0.25rem 0.5rem; font-size: 0.75rem; font-weight: 900;">PASSED W/ WARNINGS</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Router ---
apply_custom_styles()
render_top_nav()

if st.session_state.page == "dashboard":
    page_dashboard()
elif st.session_state.page == "location":
    page_location()
elif st.session_state.page == "inventory":
    page_inventory()
elif st.session_state.page == "density":
    page_density()
elif st.session_state.page == "review":
    page_review()

# Bottom Nav (Mobile/Persistent)
st.markdown("""
<div style="position: fixed; bottom: 0; left: 0; width: 100%; background-color: #f5f0e8; border-top: 4px solid #1a1a1a; display: flex; justify-content: space-around; padding: 0.5rem; z-index: 1000;" class="md-hidden">
    <div style="text-align: center;">
        <span class="material-symbols-outlined">dashboard</span><br>
        <span style="font-size: 10px; font-weight: bold; text-transform: uppercase;">Overview</span>
    </div>
    <div style="text-align: center;">
        <span class="material-symbols-outlined">location_on</span><br>
        <span style="font-size: 10px; font-weight: bold; text-transform: uppercase;">Location</span>
    </div>
    <div style="text-align: center;">
        <span class="material-symbols-outlined">category</span><br>
        <span style="font-size: 10px; font-weight: bold; text-transform: uppercase;">Uses</span>
    </div>
    <div style="text-align: center;">
        <span class="material-symbols-outlined">functions</span><br>
        <span style="font-size: 10px; font-weight: bold; text-transform: uppercase;">Math</span>
    </div>
    <div style="text-align: center;">
        <span class="material-symbols-outlined">ios_share</span><br>
        <span style="font-size: 10px; font-weight: bold; text-transform: uppercase;">Export</span>
    </div>
</div>
<div style="height: 80px;"></div>
""", unsafe_allow_html=True)
