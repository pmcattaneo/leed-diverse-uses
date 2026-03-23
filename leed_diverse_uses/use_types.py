from __future__ import annotations

from typing import Dict, List, Tuple

DEFAULT_CATEGORY = "Non-specified"
DEFAULT_SPECIFIC_USE = ""

USE_CATEGORIES: Dict[str, List[str]] = {
    "Food Retail": [
        "Supermarket",
        "Grocery with Produce Section",
    ],
    "Community-Serving Retail": [
        "Convenience Store",
        "Farmers Market",
        "Hardware Store",
        "Pharmacy",
        "Other Retail",
    ],
    "Services": [
        "Bank",
        "Family Entertainment Venue",
        "Gym, Health Club, or Exercise Studio",
        "Hair Care",
        "Laundry or Dry Cleaner",
        "Restaurant, Cafe, or Diner",
    ],
    "Civic and Community Facilities": [
        "Adult or Senior Care Facility",
        "Child Care Facility",
        "Community or Recreation Center",
        "Cultural Arts Facility",
        "Education Facility",
        "Government Office Serving the Public",
        "Medical Clinic or Office",
        "Place of Worship",
        "Police or Fire Station",
        "Post Office",
        "Public Library",
        "Public Park",
        "Social Services Center",
    ],
    "Community Anchor Uses": [
        "Commercial Office",
        "Housing",
    ],
}

LEGACY_CATEGORY_MAP: Dict[str, Tuple[str, str]] = {
    "Food Retail": ("Food Retail", ""),
    "Community-Serving Retail": ("Community-Serving Retail", ""),
    "Services": ("Services", ""),
    "Recreation": ("Civic and Community Facilities", "Community or Recreation Center"),
    "Restaurant": ("Services", "Restaurant, Cafe, or Diner"),
    "Library": ("Civic and Community Facilities", "Public Library"),
    "Park": ("Civic and Community Facilities", "Public Park"),
    "School": ("Civic and Community Facilities", "Education Facility"),
    "Museum": ("Civic and Community Facilities", "Cultural Arts Facility"),
    "Other": ("Community-Serving Retail", "Other Retail"),
    DEFAULT_CATEGORY: (DEFAULT_CATEGORY, ""),
}

SPECIFIC_USE_TO_CATEGORY = {
    specific_use: category
    for category, specific_uses in USE_CATEGORIES.items()
    for specific_use in specific_uses
}


def category_options() -> List[str]:
    """Return the supported LEED use categories in display order."""
    return list(USE_CATEGORIES.keys())


def specific_use_options(category: str) -> List[str]:
    """Return valid specific uses for a LEED category."""
    normalized_category, _ = normalize_use_selection(category=category)
    return USE_CATEGORIES.get(normalized_category, [])


def normalize_use_selection(
    category: str | None = None,
    specific_use: str | None = None,
) -> Tuple[str, str]:
    """Normalize broad/specific use values and backfill legacy saved categories."""
    normalized_category = (category or "").strip()
    normalized_specific_use = (specific_use or "").strip()

    if normalized_category in USE_CATEGORIES:
        if (
            normalized_specific_use
            and normalized_specific_use not in USE_CATEGORIES[normalized_category]
        ):
            inferred_category = SPECIFIC_USE_TO_CATEGORY.get(normalized_specific_use)
            if inferred_category:
                return inferred_category, normalized_specific_use
        return normalized_category, normalized_specific_use

    if normalized_category in LEGACY_CATEGORY_MAP and not normalized_specific_use:
        return LEGACY_CATEGORY_MAP[normalized_category]

    if normalized_specific_use:
        inferred_category = SPECIFIC_USE_TO_CATEGORY.get(normalized_specific_use)
        if inferred_category:
            return inferred_category, normalized_specific_use

    if not normalized_category:
        return DEFAULT_CATEGORY, normalized_specific_use

    return normalized_category, normalized_specific_use
