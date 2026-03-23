"""Project management for LEED Diverse Uses app."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .core import Destination
from .use_types import normalize_use_selection


@dataclass
class Project:
    """Represents a LEED project with walking distance analysis."""
    
    name: str
    address: str
    origin_lat: float
    origin_lon: float
    status: str = "Draft"
    destinations: List[Dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    max_distance_m: float = 804.67
    project_id: Optional[str] = None

    def __post_init__(self):
        if not self.project_id:
            self.project_id = f"proj_{int(datetime.now().timestamp() * 1000)}"
        self.updated_at = datetime.now().isoformat()

    @property
    def compliant_count(self) -> int:
        """Count compliant destinations."""
        return sum(1 for d in self.destinations if d.get("compliant") is True)

    @property
    def non_compliant_count(self) -> int:
        """Count mapped, non-compliant destinations."""
        return sum(1 for d in self.destinations if d.get("compliant") is False)

    @property
    def mapped_count(self) -> int:
        """Count destinations with an active mapped route."""
        return sum(
            1
            for d in self.destinations
            if d.get("route_geometry")
            and d.get("distance_m") is not None
            and d.get("duration_s") is not None
            and d.get("compliant") is not None
        )

    @property
    def unmapped_count(self) -> int:
        """Count destinations that need route recalculation."""
        return self.total_count - self.mapped_count

    @property
    def total_count(self) -> int:
        """Total destinations."""
        return len(self.destinations)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Project:
        """Create from dictionary."""
        return cls(**data)


class ProjectManager:
    """Manages project persistence and operations."""

    def __init__(self, projects_dir: Optional[Path] = None):
        self.projects_dir = projects_dir or Path.home() / ".leed_docs"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.projects_file = self.projects_dir / "projects.json"

    def _load_projects_data(self) -> dict:
        """Load all projects from file."""
        if not self.projects_file.exists():
            return {}
        
        try:
            with open(self.projects_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_projects_data(self, data: dict) -> None:
        """Save all projects to file."""
        with open(self.projects_file, "w") as f:
            json.dump(data, f, indent=2)

    def create_project(self, name: str, address: str, origin_lat: float, origin_lon: float) -> Project:
        """Create and save a new project."""
        project = Project(
            name=name,
            address=address,
            origin_lat=origin_lat,
            origin_lon=origin_lon
        )
        
        data = self._load_projects_data()
        data[project.project_id] = project.to_dict()
        self._save_projects_data(data)
        
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """Get a project by ID."""
        data = self._load_projects_data()
        if project_id in data:
            return Project.from_dict(data[project_id])
        return None

    def list_projects(self) -> List[Project]:
        """Get all projects."""
        data = self._load_projects_data()
        projects = [Project.from_dict(p) for p in data.values()]
        # Sort by updated_at descending (most recent first)
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def update_project(self, project: Project) -> None:
        """Update an existing project."""
        project.updated_at = datetime.now().isoformat()
        data = self._load_projects_data()
        data[project.project_id] = project.to_dict()
        self._save_projects_data(data)

    def delete_project(self, project_id: str) -> None:
        """Delete a project."""
        data = self._load_projects_data()
        if project_id in data:
            del data[project_id]
            self._save_projects_data(data)

    def add_destination(self, project_id: str, destination) -> None:
        """Add a destination to a project. Accepts Destination object or dict."""
        project = self.get_project(project_id)
        if not project:
            return
        
        # Handle both Destination objects and dictionaries
        if isinstance(destination, Destination):
            category, specific_use = normalize_use_selection(
                category=destination.category,
                specific_use=destination.specific_use,
            )
            dest_dict = {
                "name": destination.name,
                "address": destination.address,
                "lat": destination.lat,
                "lon": destination.lon,
                "category": category,
                "specific_use": specific_use,
                "distance_m": destination.distance_m,
                "duration_s": destination.duration_s,
                "compliant": destination.compliant,
                "route_geometry": destination.route_geometry,
            }
        elif isinstance(destination, dict):
            category, specific_use = normalize_use_selection(
                category=destination.get("category"),
                specific_use=destination.get("specific_use"),
            )
            dest_dict = {
                **destination,
                "category": category,
                "specific_use": specific_use,
            }
        else:
            raise TypeError(f"destination must be Destination or dict, got {type(destination)}")
        
        project.destinations.append(dest_dict)
        self.update_project(project)

    def remove_destination(self, project_id: str, index: int) -> None:
        """Remove a destination from a project."""
        project = self.get_project(project_id)
        if not project or index >= len(project.destinations):
            return
        
        project.destinations.pop(index)
        self.update_project(project)

    def get_stats(self) -> dict:
        """Get overall statistics across all projects."""
        projects = self.list_projects()
        all_compliant = sum(p.compliant_count for p in projects)
        all_non_compliant = sum(p.non_compliant_count for p in projects)
        all_addresses = sum(p.total_count for p in projects)
        
        return {
            "total_projects": len(projects),
            "total_addresses": all_addresses,
            "total_compliant": all_compliant,
            "total_non_compliant": all_non_compliant,
        }
