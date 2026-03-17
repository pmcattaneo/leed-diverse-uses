from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

from .core import RouteAnalyzer
from .pdf_report import ReportGenerator


def parse_args(args: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate LEED Diverse Uses walking route report."
    )
    parser.add_argument(
        "--origin",
        required=True,
        help="Origin coordinate as 'lat,lon' (e.g. 40.748817,-73.985428).",
    )
    parser.add_argument(
        "--dest",
        action="append",
        required=True,
        help="Destination in the form 'Name|Address'. Can be provided multiple times.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output PDF file path.",
    )
    parser.add_argument(
        "--max-distance-m",
        type=float,
        default=804.67,
        help="Maximum walking distance in meters to be considered compliant (default 804.67 m / 0.5 mi).",
    )
    return parser.parse_args(args=args)


def _parse_origin(origin: str) -> Tuple[float, float]:
    lat_str, lon_str = origin.split(",")
    return float(lat_str.strip()), float(lon_str.strip())


def _parse_destinations(dest_list: List[str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for entry in dest_list:
        if "|" in entry:
            name, address = entry.split("|", 1)
        else:
            name, address = entry, entry
        out.append((name.strip(), address.strip()))
    return out


def main(args: List[str] | None = None) -> None:
    ns = parse_args(args)

    origin = _parse_origin(ns.origin)
    destinations = _parse_destinations(ns.dest)

    analyzer = RouteAnalyzer(origin=origin)
    results = analyzer.analyze_destinations(destinations, max_distance_m=ns.max_distance_m)

    output_pdf = Path(ns.output)
    output_dir = output_pdf.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    map_paths = []
    for i, dest in enumerate(results, start=1):
        map_obj = analyzer.make_route_map(dest)
        map_path = output_dir / f"route_{i}_{dest.name.replace(' ', '_')}.html"
        ReportGenerator.save_map_html(map_obj, map_path)
        map_paths.append(map_path)

    report = ReportGenerator(output_path=output_pdf)
    report.create_report(origin=origin, destinations=results, map_html_paths=map_paths)

    print(f"Created report: {output_pdf}")


if __name__ == "__main__":
    main()
