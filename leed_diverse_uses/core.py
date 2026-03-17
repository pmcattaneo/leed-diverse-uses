from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import folium
import openrouteservice
from geopy.geocoders import Nominatim
from openrouteservice import Client


@dataclass
class Destination:
    name: str
    address: str
    lat: float
    lon: float
    category: str = "Non-specified"
    distance_m: Optional[float] = None
    duration_s: Optional[float] = None
    compliant: Optional[bool] = None
    route_geometry: Optional[List[Tuple[float, float]]] = None


class RouteAnalyzer:
    """Analyzes walking routes from an origin point to destination addresses."""

    def __init__(self, origin: Tuple[float, float], ors_api_key: Optional[str] = None):
        self.origin = origin
        self.ors_api_key = ors_api_key or os.environ.get("ORS_API_KEY")
        if not self.ors_api_key:
            raise RuntimeError("OpenRouteService API key required (set ORS_API_KEY)")

        self.client = Client(key=self.ors_api_key)
        self.geolocator = Nominatim(user_agent="leed-diverse-uses")

    def geocode(self, address: str) -> Tuple[float, float]:
        """Geocode an address to (lat, lon)."""
        location = self.geolocator.geocode(address)
        if not location:
            raise ValueError(f"Could not geocode address: {address}")
        return location.latitude, location.longitude

    def analyze_destination(
        self,
        name: str,
        address: str,
        max_distance_m: float = 804.67,
    ) -> Destination:
        """Return a Destination with route info and compliance flag."""
        lat, lon = self.geocode(address)
        route = self._get_walking_route(self.origin, (lat, lon))

        distance_m = float(route["distance"])
        duration_s = float(route["duration"])
        geometry = route["geometry"]

        compliant = distance_m <= max_distance_m

        return Destination(
            name=name,
            address=address,
            lat=lat,
            lon=lon,
            distance_m=distance_m,
            duration_s=duration_s,
            compliant=compliant,
            route_geometry=geometry,
        )

    def analyze_destinations(
        self,
        destinations: List[Tuple[str, str]],
        max_distance_m: float = 804.67,
    ) -> List[Destination]:
        """Analyze a set of destination (name, address) pairs."""
        results: List[Destination] = []
        for name, address in destinations:
            dest = self.analyze_destination(name=name, address=address, max_distance_m=max_distance_m)
            results.append(dest)
        return results

    def _get_walking_route(self, origin: Tuple[float, float], destination: Tuple[float, float]):
        """Request walking directions from OpenRouteService."""
        coords = [(origin[1], origin[0]), (destination[1], destination[0])]
        resp = self.client.directions(
            coordinates=coords,
            profile="foot-walking",
            format_="geojson",
            instructions=False,
            optimize_waypoints=False,
        )
        # openrouteservice returns a FeatureCollection; the first feature contains properties
        feature = resp["features"][0]
        props = feature["properties"]
        geometry = feature["geometry"]["coordinates"]
        # Convert geometry to (lat, lon) pairs
        latlon = [(lat, lon) for lon, lat in geometry]
        return {"distance": props.get("summary", {}).get("distance"),
                "duration": props.get("summary", {}).get("duration"),
                "geometry": latlon}

    def make_route_map(self, destination: Destination, zoom_start: int = 15) -> folium.Map:
        """Create a Folium map showing the route from origin to destination."""
        m = folium.Map(location=self.origin, zoom_start=zoom_start, tiles="OpenStreetMap")

        # origin marker
        folium.Marker(
            location=self.origin,
            popup="Origin",
            icon=folium.Icon(color="blue", icon="home"),
        ).add_to(m)

        # destination marker
        folium.Marker(
            location=(destination.lat, destination.lon),
            popup=f"{destination.name}\n{destination.address}",
            icon=folium.Icon(color="red", icon="flag"),
        ).add_to(m)

        # route polyline
        if destination.route_geometry:
            folium.PolyLine(
                destination.route_geometry,
                color="green" if destination.compliant else "orange",
                weight=5,
                opacity=0.8,
            ).add_to(m)

        return m
