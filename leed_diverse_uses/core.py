from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import folium
import requests
from geopy.geocoders import Nominatim


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
    """Analyzes walking routes from an origin point to destination addresses using Valhalla API."""

    def __init__(self, origin: Tuple[float, float], valhalla_url: str = "https://valhalla1.openstreetmap.de"):
        self.origin = origin
        self.valhalla_url = valhalla_url
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
        """Request walking directions from Valhalla public API."""
        # Valhalla expects lon,lat format
        req_payload = {
            "locations": [
                {"lat": origin[0], "lon": origin[1]},
                {"lat": destination[0], "lon": destination[1]},
            ],
            "costing": "pedestrian",
            "format": "geojson",
        }
        
        resp = requests.post(
            f"{self.valhalla_url}/route",
            json=req_payload,
            timeout=30
        )
        resp.raise_for_status()
        
        data = resp.json()
        
        # Extract geometry from GeoJSON feature
        feature = data["features"][0]
        props = feature["properties"]
        geometry = feature["geometry"]["coordinates"]
        
        # Convert geometry to (lat, lon) pairs
        latlon = [(lat, lon) for lon, lat in geometry]
        
        # Valhalla returns duration in seconds and distance in meters
        return {
            "distance": props.get("length"),
            "duration": props.get("time"),
            "geometry": latlon
        }

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
