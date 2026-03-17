- [x] Verify that the copilot-instructions.md file in the .github directory is created.

- [x] Clarify Project Requirements

- [x] Scaffold the Project

- [x] Customize the Project

- [x] Install Required Extensions

- [x] Compile the Project

- [x] Create and Run Task

- [ ] Launch the Project

- [x] Ensure Documentation is Complete

## Project Summary

**LEED Diverse Uses Mapping Tool** — A Python application for evaluating LEED v4/v4.1 Diverse Uses credit compliance.

### Key Features
- Interactive Streamlit UI with origin point selection on an OSM map
- Multi-destination address management with categories
- Walking route calculation via OpenRouteService
- Compliance checking based on distance thresholds
- Tabbed interface (Addresses, Routes, Chart, Overview Map)
- PDF report generation with embedded route snapshots
- CSV export functionality

### Getting Started
1. Set `ORS_API_KEY` environment variable
2. Run: `python -m streamlit run app.py`
3. Add project info and destinations through the interface
4. Export results as CSV or PDF

### Project Structure
- `app.py` — Main Streamlit UI
- `leed_diverse_uses/core.py` — Routing and analysis logic
- `leed_diverse_uses/pdf_report.py` — PDF generation with embedded map snapshots
- `leed_diverse_uses/cli.py` — Command-line interface
- `requirements.txt` — Python dependencies

