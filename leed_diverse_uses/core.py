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
        # Valhalla expects lon,lat format in locations but returns lat,lon in geometry
        req_payload = {
            "locations": [
                {"lat": origin[0], "lon": origin[1]},
                {"lat": destination[0], "lon": destination[1]},
            ],
            "costing": "pedestrian",
        }
        
        try:
            resp = requests.post(
                f"{self.valhalla_url}/route",
                json=req_payload,
                timeout=30
            )
            resp.raise_for_status()
            
            data = resp.json()
            
            # Check for error responses
            if "error" in data:
                raise ValueError(f"Valhalla API error: {data.get('error')}")
            
            # Try native Valhalla format first (with "trip" key)
            if "trip" in data:
                trip = data["trip"]
                
                # Extract duration and distance from legs
                total_distance = 0
                total_duration = 0
                all_coords = []
                
                for leg in trip.get("legs", []):
                    total_distance += leg.get("summary", {}).get("length", 0)
                    total_duration += leg.get("summary", {}).get("time", 0)
                    
                    # Extract coordinates from shape field (polyline6 encoded)
                    shape = leg.get("shape", "")
                    if shape:
                        coords = self._decode_polyline6(shape)
                        all_coords.extend(coords)
                
                if all_coords:
                    return {
                        "distance": total_distance * 1000,  # Convert km to meters
                        "duration": total_duration,  # Already in seconds
                        "geometry": all_coords
                    }
            
            # Try GeoJSON format (fallback)
            elif "features" in data and data["features"]:
                feature = data["features"][0]
                props = feature["properties"]
                geometry = feature["geometry"]["coordinates"]
                
                # Convert geometry to (lat, lon) pairs
                latlon = [(lat, lon) for lon, lat in geometry]
                
                return {
                    "distance": props.get("length"),
                    "duration": props.get("time"),
                    "geometry": latlon
                }
            
            raise ValueError("No route found in Valhalla response")
            
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Failed to connect to routing service at {self.valhalla_url}: {e}")
        except (KeyError, IndexError, ValueError) as e:
            raise ValueError(f"Error processing route response: {e}")

    def _decode_polyline6(self, encoded: str) -> List[Tuple[float, float]]:
        """Decode a polyline6 encoded string to lat,lon coordinates."""
        # Polyline6 encoding: https://valhalla.readthedocs.io/en/latest/api/map-matching/output-options/
        coords = []
        index = 0
        lat = 0
        lng = 0
        
        while index < len(encoded):
            result = 0
            shift = 0
            
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            
            dlat = ~(result >> 1) if (result & 1) else (result >> 1)
            lat += dlat
            
            result = 0
            shift = 0
            
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            
            dlng = ~(result >> 1) if (result & 1) else (result >> 1)
            lng += dlng
            
            coords.append((lat / 1e6, lng / 1e6))
        
        return coords

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
