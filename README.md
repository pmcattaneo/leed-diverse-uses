# LEED Diverse Uses Mapping Tool

A comprehensive Python application for evaluating LEED v4/v4.1 **Diverse Uses** credit compliance by calculating walking routes from an origin to a set of destinations and generating detailed reports with maps and distances.

## Features

- **Interactive origin point selection** — Click on an OSM map to select your starting point
- **Add multiple destinations** — Button-driven interface with name, address, and category selection
- **Uses OpenStreetMap** (via OpenRouteService) to calculate walking directions
- **Calculates compliance** based on configured walking distance thresholds
- **Tabbed interface** with 4 views:
  - **Addresses**: Display destinations in a table with distances, times, and compliance status
  - **Routes**: View individual route maps with detailed information
  - **Chart**: Visualize compliance rates and distance distribution
  - **Overview Map**: See all routes on a single interactive map
- **Builds interactive Folium maps** for each origin-destination path
- **Generates PDF reports** with routes, distances, destination descriptions, and embedded static map snapshots
- **Export functionality** — Download route data as CSV or PDF package

## Getting Started

### Requirements

- Python 3.10+ (recommended)
- An OpenRouteService API key (set as `ORS_API_KEY` environment variable)

### Install dependencies

```sh
python -m pip install -r requirements.txt
```

### Run the Streamlit app

```sh
export ORS_API_KEY="your_openrouteservice_api_key"
python -m streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`.

### App Workflow

1. **Set Project Info** — Enter project name and address at the top
2. **Click "+ Add Address"** — Open the form to add a new destination:
   - Name: Name of the destination
   - Address: Full address (will be geocoded)
   - Category: Select from predefined categories (Services, Food Retail, Restaurant, etc.)
3. **View Destinations** — All addresses appear in the "Addresses" tab with a table showing:
   - Name, Category, Address
   - Distance (miles) and Walking Time (minutes)
   - Compliance status (✓ or ✗)
4. **View Routes** — Select individual routes in the "Routes" tab to see interactive maps
5. **Export Results** — Download as CSV or generate a PDF package with all route maps embedded

## Notes

- This is a starting point; you can extend compliance rules to match the exact LEED criteria for verbiage and scoring.
- The project is designed to be self-contained and use OpenStreetMap for routing and map rendering.
# leed-diverse-uses
