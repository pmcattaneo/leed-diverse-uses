from __future__ import annotations

import math
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

    def reverse_geocode(self, lat: float, lon: float) -> str:
        """Reverse geocode a point to a human-readable address."""
        location = self.geolocator.reverse((lat, lon), exactly_one=True)
        if not location:
            raise ValueError(f"Could not reverse geocode coordinates: {lat}, {lon}")
        return location.address

    def analyze_destination(
        self,
        name: str,
        address: str,
        max_distance_m: float = 804.67,
    ) -> Destination:
        """Return a Destination with route info and compliance flag."""
        lat, lon = self.geocode(address)
        return self.analyze_destination_coords(
            name=name,
            lat=lat,
            lon=lon,
            address=address,
            max_distance_m=max_distance_m,
        )

    def analyze_destination_coords(
        self,
        name: str,
        lat: float,
        lon: float,
        address: Optional[str] = None,
        category: str = "Non-specified",
        max_distance_m: float = 804.67,
    ) -> Destination:
        """Return a Destination with route info for an already-known point."""
        route = self._get_walking_route(self.origin, (lat, lon))

        distance_m = float(route["distance"])
        duration_s = float(route["duration"])
        geometry = route["geometry"]

        compliant = distance_m <= max_distance_m

        return Destination(
            name=name,
            address=address or f"{lat:.6f}, {lon:.6f}",
            lat=lat,
            lon=lon,
            category=category,
            distance_m=distance_m,
            duration_s=duration_s,
            compliant=compliant,
            route_geometry=geometry,
        )

    def enrich_destination(
        self,
        destination: Destination,
        max_distance_m: float = 804.67,
    ) -> Destination:
        """Populate route details for an existing destination."""
        if (
            destination.route_geometry
            and destination.distance_m is not None
            and destination.duration_s is not None
            and self._geometry_matches_trip(
                destination.route_geometry,
                self.origin,
                (destination.lat, destination.lon),
            )
        ):
            return destination

        return self.analyze_destination_coords(
            name=destination.name,
            lat=destination.lat,
            lon=destination.lon,
            address=destination.address,
            category=destination.category,
            max_distance_m=max_distance_m,
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
            "shape_format": "polyline6",
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
                        coords = self._decode_route_shape(shape, origin, destination)
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

    def _decode_route_shape(
        self,
        encoded: str,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
    ) -> List[Tuple[float, float]]:
        """Decode route geometry, falling back if the service uses polyline5."""
        coords6 = self._decode_polyline(encoded, precision=6)
        if self._geometry_matches_trip(coords6, origin, destination):
            return coords6

        coords5 = self._decode_polyline(encoded, precision=5)
        if self._geometry_matches_trip(coords5, origin, destination):
            return coords5

        return coords6

    def _geometry_matches_trip(
        self,
        geometry: Optional[List[Tuple[float, float]]],
        origin: Tuple[float, float],
        destination: Tuple[float, float],
    ) -> bool:
        """Check whether decoded geometry plausibly matches the requested trip."""
        if not geometry:
            return False

        start = geometry[0]
        end = geometry[-1]
        origin_distance = self._point_distance_m(start, origin)
        destination_distance = self._point_distance_m(end, destination)

        return origin_distance <= 250 and destination_distance <= 250

    @staticmethod
    def _point_distance_m(point_a: Tuple[float, float], point_b: Tuple[float, float]) -> float:
        """Approximate meter distance between two lat/lon points."""
        lat_scale = 111_320
        mean_lat = (point_a[0] + point_b[0]) / 2
        lon_scale = 111_320 * abs(math.cos(math.radians(mean_lat)))
        delta_lat = (point_a[0] - point_b[0]) * lat_scale
        delta_lon = (point_a[1] - point_b[1]) * lon_scale
        return (delta_lat ** 2 + delta_lon ** 2) ** 0.5

    def _decode_polyline(self, encoded: str, precision: int = 6) -> List[Tuple[float, float]]:
        """Decode an encoded polyline to lat,lon coordinates."""
        coords = []
        index = 0
        lat = 0
        lng = 0
        scale = 10 ** precision
        
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
            
            coords.append((lat / scale, lng / scale))
        
        return coords

    def make_route_map(
        self,
        destination: Destination,
        zoom_start: int = 15,
        max_distance_m: float = 804.67,
    ) -> folium.Map:
        """Create a Folium map showing the route from origin to destination."""
        destination = self.enrich_destination(destination, max_distance_m=max_distance_m)
        m = folium.Map(
            location=self.origin,
            zoom_start=zoom_start,
            tiles="OpenStreetMap",
            control_scale=True,
        )

        # origin marker
        folium.Marker(
            location=self.origin,
            popup="Origin",
            icon=folium.Icon(color="blue", icon="home"),
        ).add_to(m)

        # destination marker
        folium.Marker(
            location=(destination.lat, destination.lon),
            popup=f"{destination.name}<br>{destination.address}",
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

        route_points = destination.route_geometry or [self.origin, (destination.lat, destination.lon)]
        m.fit_bounds(route_points)

        return m
