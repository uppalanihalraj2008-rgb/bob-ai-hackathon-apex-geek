"""Data models for the DVI coordination tool.

Plain dataclasses on purpose -- no ORM, no pydantic. Keeping the record
shape visible in one place makes it easy for a judge (or a teammate) to see
exactly what a "profile" is without chasing definitions across files.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@dataclass
class Mark:
    """A single distinguishing mark: a scar, tattoo, birthmark, old fracture, etc."""
    type: str            # scar | tattoo | birthmark | deformity | piercing | fracture | other
    location: str        # free text, e.g. "left forearm, ~3cm above wrist"
    description: str     # free text detail


@dataclass
class AnteMortemProfile:
    """A family-provided profile of a missing person."""
    id: str
    reporter_name: str
    reporter_relationship: str
    reporter_contact: str
    missing_person_name: str
    sex: str                        # male | female | unknown
    age_min: Optional[int]
    age_max: Optional[int]
    height_cm_min: Optional[float]
    height_cm_max: Optional[float]
    build: str
    hair_color: str
    hair_length: str
    eye_color: str
    marks: List[Mark]               # list[Mark]
    clothing: List[str]             # list[str]
    dental_notes: str
    blood_type: str                 # e.g. "O+", or "unknown"
    last_seen_location: str
    last_seen_date: str
    physical_description: str = ""
    other_notes: str = ""
    face_image_path: Optional[str] = None
    fingerprint_image_path: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def new(**kwargs) -> "AnteMortemProfile":
        kwargs.setdefault("id", _new_id("AM"))
        kwargs["marks"] = [m if isinstance(m, Mark) else Mark(**m) for m in kwargs.get("marks", [])]
        return AnteMortemProfile(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnteMortemProfile":
        data_copy = dict(data)
        if "marks" in data_copy and isinstance(data_copy["marks"], list):
            data_copy["marks"] = [m if isinstance(m, Mark) else Mark(**m) for m in data_copy["marks"]]
        return cls(**data_copy)


@dataclass
class PostMortemObservation:
    """Forensic observations recorded for an unidentified body / case."""
    id: str
    case_number: str
    location_found: str
    date_found: str
    sex: str
    age_min: Optional[int]
    age_max: Optional[int]
    height_cm_min: Optional[float]
    height_cm_max: Optional[float]
    build: str
    hair_color: str
    hair_length: str
    eye_color: str
    marks: List[Mark]               # list[Mark]
    clothing: List[str]             # list[str]
    dental_findings: str
    blood_type: str
    physical_description: str = ""
    other_findings: str = ""
    face_image_path: Optional[str] = None
    fingerprint_image_path: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def new(**kwargs) -> "PostMortemObservation":
        kwargs.setdefault("id", _new_id("PM"))
        kwargs["marks"] = [m if isinstance(m, Mark) else Mark(**m) for m in kwargs.get("marks", [])]
        return PostMortemObservation(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PostMortemObservation":
        data_copy = dict(data)
        if "marks" in data_copy and isinstance(data_copy["marks"], list):
            data_copy["marks"] = [m if isinstance(m, Mark) else Mark(**m) for m in data_copy["marks"]]
        return cls(**data_copy)