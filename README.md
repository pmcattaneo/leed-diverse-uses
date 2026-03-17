# LEED Diverse Uses Mapping Tool

A small Python application that helps evaluate LEED v4/v4.1 **Diverse Uses** credit compliance by calculating walking routes from an origin to a set of destinations and generating a PDF report with maps and distances.

## Features

- **Interactive origin point selection** — Click on an OSM map to select your starting point
- Uses OpenStreetMap (via OpenRouteService) to calculate walking directions.
- Calculates compliance based on configured walking distance thresholds.
- Builds interactive Folium maps for each origin-destination path.
- Generates a PDF report that includes the map, distance, destination description, and an embedded static route snapshot image.

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

### Command-line usage

```sh
python -m leed_diverse_uses.cli \
  --origin "40.748817,-73.985428" \
  --dest "350 5th Ave, New York, NY" \
  --dest "Times Square, New York, NY" \
  --output report.pdf
```

## Notes

- This is a starting point; you can extend compliance rules to match the exact LEED criteria for verbiage and scoring.
- The project is designed to be self-contained and use OpenStreetMap for routing and map rendering.
# leed-diverse-uses
