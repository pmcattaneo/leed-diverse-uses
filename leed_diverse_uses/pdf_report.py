from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from staticmap import CircleMarker, Line, StaticMap

from .core import Destination
from .use_types import DEFAULT_CATEGORY


@dataclass
class ReportGenerator:
    """Generate a PDF report for a set of destinations."""

    output_path: Path

    def create_report(
        self,
        origin: tuple[float, float],
        destinations: List[Destination],
        map_html_paths: Optional[List[Path]] = None,
    ) -> None:
        """Create a PDF report summarizing routes and compliance."""
        doc = SimpleDocTemplate(str(self.output_path), pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("LEED Diverse Uses Walking Routes Report", styles["Title"]))
        story.append(Spacer(1, 0.25 * inch))

        story.append(
            Paragraph(
                f"Origin: {origin[0]:.6f}, {origin[1]:.6f}",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 0.15 * inch))

        for i, dest in enumerate(destinations, start=1):
            category_line = (
                f"Category: {dest.category}<br/>"
                if dest.category and dest.category != DEFAULT_CATEGORY
                else ""
            )
            specific_use_line = (
                f"Specific Use: {dest.specific_use}<br/>"
                if dest.specific_use
                else ""
            )
            story.append(Paragraph(f"{i}. {dest.name}", styles["Heading2"]))
            story.append(
                Paragraph(
                    f"Address: {dest.address}<br/>"
                    f"{category_line}"
                    f"{specific_use_line}"
                    f"Distance (m): {dest.distance_m:.1f}<br/>"
                    f"Walking time (min): {dest.duration_s / 60:.1f}<br/>"
                    f"Compliant: {'Yes' if dest.compliant else 'No'}",
                    styles["Normal"],
                )
            )
            story.append(Spacer(1, 0.2 * inch))

            if dest.route_geometry:
                story.append(Paragraph("Route snapshot:", styles["Italic"]))
                story.append(Spacer(1, 0.1 * inch))
                preview_img = self._render_route_image(origin, dest)
                story.append(preview_img)
                story.append(Spacer(1, 0.2 * inch))

            if map_html_paths and i - 1 < len(map_html_paths):
                story.append(
                    Paragraph(
                        f"Map file: {map_html_paths[i-1].name}",
                        styles["Italic"],
                    )
                )
                story.append(Spacer(1, 0.15 * inch))

        doc.build(story)

    @staticmethod
    def save_map_html(map_obj, output_path: Path) -> None:
        """Save a Folium map object to an HTML file."""
        map_obj.save(str(output_path))

    @staticmethod
    def _route_snapshot_view(route_coords: list[tuple[float, float]]) -> tuple[int, tuple[float, float]]:
        """Calculate a route-focused zoom and center for PDF snapshots."""
        fit_map = StaticMap(
            700,
            450,
            padding_x=20,
            padding_y=20,
            url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        )
        fit_map.add_line(Line(route_coords, "blue", 4))

        min_lon = min(lon for lon, _ in route_coords)
        max_lon = max(lon for lon, _ in route_coords)
        min_lat = min(lat for _, lat in route_coords)
        max_lat = max(lat for _, lat in route_coords)
        center = ((min_lon + max_lon) / 2, (min_lat + max_lat) / 2)

        return fit_map._calculate_zoom(), center

    def _render_route_image(self, origin: tuple[float, float], dest: Destination) -> Image:
        """Render a static map image (PNG) showing the walking route."""
        # staticmap expects (lon, lat)
        route_coords = [(lon, lat) for lat, lon in dest.route_geometry]
        zoom, center = self._route_snapshot_view(route_coords)

        m = StaticMap(
            700,
            450,
            url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        )
        m.add_line(Line(route_coords, "blue", 4))
        m.add_marker(CircleMarker((origin[1], origin[0]), "green", 12))
        m.add_marker(CircleMarker((dest.lon, dest.lat), "red", 12))

        image = m.render(zoom=zoom, center=center)
        bio = BytesIO()
        image.save(bio, format="PNG")
        bio.seek(0)

        return Image(bio, width=6.5 * inch, height=4.0 * inch)
