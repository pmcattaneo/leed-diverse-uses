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
            story.append(Paragraph(f"{i}. {dest.name}", styles["Heading2"]))
            story.append(
                Paragraph(
                    f"Address: {dest.address}<br/>"
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

    def _render_route_image(self, origin: tuple[float, float], dest: Destination) -> Image:
        """Render a static map image (PNG) showing the walking route."""
        # staticmap expects (lon, lat)
        route_coords = [(lon, lat) for lat, lon in dest.route_geometry]

        m = StaticMap(
            700,
            450,
            padding_x=40,
            padding_y=40,
            url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        )
        m.add_line(Line(route_coords, "blue", 4))
        m.add_marker(CircleMarker((origin[1], origin[0]), "green", 12))
        m.add_marker(CircleMarker((dest.lon, dest.lat), "red", 12))

        image = m.render()
        bio = BytesIO()
        image.save(bio, format="PNG")
        bio.seek(0)

        return Image(bio, width=6.5 * inch, height=4.0 * inch)
