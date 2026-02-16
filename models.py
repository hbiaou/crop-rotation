"""
models.py — Python dataclasses for the crop rotation application.

Maps to the SQLite tables defined in FEATURES_SPEC.md section 4.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Setting:
    """Global application setting (key-value pair)."""
    key: str
    value: str


@dataclass
class Garden:
    """Garden definition with configurable bed dimensions."""
    id: Optional[int] = None
    garden_code: str = ""
    name: str = ""
    beds: int = 0
    bed_length_m: float = 0.0
    bed_width_m: float = 1.0
    sub_beds_per_bed: int = 1
    active_sub_beds: int = 0
    created_at: Optional[str] = None


@dataclass
class SubBed:
    """Individual sub-bed within a garden bed."""
    id: Optional[int] = None
    garden_id: int = 0
    bed_number: int = 0
    sub_bed_position: int = 0
    is_reserve: bool = False

    @property
    def display_id(self) -> str:
        """Computed display ID: P{bed_number:02d}-S{position}."""
        return f"P{self.bed_number:02d}-S{self.sub_bed_position}"


@dataclass
class Crop:
    """Crop definition with category assignment."""
    id: Optional[int] = None
    crop_name: str = ""
    category: str = ""
    family: str = ""


@dataclass
class RotationStep:
    """One step in the rotation sequence."""
    position: int = 0
    category: str = ""


@dataclass
class CyclePlan:
    """Planned vs actual planting for a sub-bed in a specific cycle."""
    id: Optional[int] = None
    sub_bed_id: int = 0
    garden_id: int = 0
    cycle: str = ""
    planned_category: Optional[str] = None
    planned_crop_id: Optional[int] = None
    actual_category: Optional[str] = None
    actual_crop_id: Optional[int] = None
    is_override: bool = False
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class CyclePlanView:
    """Extended cycle plan with joined data from sub_beds, gardens, and crops."""
    id: Optional[int] = None
    sub_bed_id: int = 0
    garden_id: int = 0
    cycle: str = ""
    planned_category: Optional[str] = None
    planned_crop_id: Optional[int] = None
    actual_category: Optional[str] = None
    actual_crop_id: Optional[int] = None
    is_override: bool = False
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # Joined fields
    bed_number: int = 0
    sub_bed_position: int = 0
    is_reserve: bool = False
    garden_code: str = ""
    garden_name: str = ""
    planned_crop_name: Optional[str] = None
    actual_crop_name: Optional[str] = None


@dataclass
class DistributionProfile:
    """Percentage-based crop target for a garden/cycle combination."""
    id: Optional[int] = None
    garden_id: int = 0
    cycle: str = ""
    crop_id: int = 0
    target_percentage: float = 0.0
