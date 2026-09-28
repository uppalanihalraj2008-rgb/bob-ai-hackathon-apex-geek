"""
MCP server exposing the DVI coordination tool's capabilities as tools that
IBM Bob (or any MCP-compatible assistant) can call.

Run with:
    python mcp_server.py

Bob's role in this architecture: a family liaison or investigator talks to
Bob in natural language -- e.g. "the family said he had a 2-inch scar on
his left forearm from a childhood bike accident." Bob extracts the
structured fields from that sentence and calls `add_ante_mortem_profile`.
Bob never computes a match score itself -- that's `matching_engine.py`,
which is deterministic and independently unit-tested (see src/tests/).
Bob's other job is turning `generate_reconciliation_report`'s output into
plain-language narration for non-technical stakeholders. See
docs/solution-overview.md for the full division of responsibilities.
"""
from __future__ import annotations

import os
from importlib import import_module
from typing import Optional, List, Dict, Any

try:
    FastMCP = import_module("mcp.server.fastmcp").FastMCP
except ImportError:  # Keep the module importable when the optional MCP package is absent.
    class FastMCP:
        """Small fallback used for local utilities and tests without MCP installed."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        @staticmethod
        def tool():
            def decorator(func):
                return func
            return decorator

        def run(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("The MCP package is required to run this server")

import database as db
import document_parser as dp
import face_matching as fm
import fingerprint_matching as fpm
import matching_engine as me
import report_generator as rg
from models import AnteMortemProfile, PostMortemObservation

mcp = FastMCP("dvi-coordinator")
db.init_db()


@mcp.tool()
def extract_text_from_document(file_path: str) -> dict:
    """Extract raw text content from an uploaded PDF, Word document, or text file."""
    if not os.path.isfile(file_path):
        return {"error": f"File not found: {file_path}"}
    
    with open(file_path, "rb") as f:
        content = f.read()
    
    extracted_text = dp.extract_text_from_file(content, os.path.basename(file_path))
    return {
        "file_name": os.path.basename(file_path),
        "text": extracted_text,
        "character_count": len(extracted_text)
    }


@mcp.tool()
def check_missing_entries(record_data: dict, record_type: str = "ante_mortem") -> dict:
    """Analyze a profile or case payload and return a list of missing required and recommended fields."""
    missing_alerts = dp.validate_extracted_fields(record_data, record_type=record_type)
    return {
        "status": "complete" if not missing_alerts else "incomplete",
        "missing_count": len(missing_alerts),
        "alerts": missing_alerts
    }


@mcp.tool()
def add_ante_mortem_profile(
    reporter_name: str,
    reporter_relationship: str,
    reporter_contact: str = "",
    missing_person_name: str = "",
    sex: str = "unknown",
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    height_cm_min: Optional[float] = None,
    height_cm_max: Optional[float] = None,
    build: str = "",
    hair_color: str = "",
    hair_length: str = "",
    eye_color: str = "",
    marks: Optional[list] = None,
    clothing: Optional[list] = None,
    dental_notes: str = "",
    blood_type: str = "unknown",
    last_seen_location: str = "",
    last_seen_date: str = "",
    physical_description: str = "",
    other_notes: str = "",
) -> dict:
    """Log a family-provided ante-mortem profile of a missing person.

    Call this after extracting structured fields from the family member's
    natural-language description. `marks` is a list of
    {"type": ..., "location": ..., "description": ...} objects for scars,
    tattoos, birthmarks, old fractures, etc. `clothing` is a list of short
    strings describing items last seen (e.g. "blue denim jacket").
    """
    profile = AnteMortemProfile.new(
        reporter_name=reporter_name, reporter_relationship=reporter_relationship,
        reporter_contact=reporter_contact, missing_person_name=missing_person_name,
        sex=sex, age_min=age_min, age_max=age_max,
        height_cm_min=height_cm_min, height_cm_max=height_cm_max,
        build=build, hair_color=hair_color, hair_length=hair_length, eye_color=eye_color,
        marks=marks or [], clothing=clothing or [], dental_notes=dental_notes,
        blood_type=blood_type, last_seen_location=last_seen_location,
        last_seen_date=last_seen_date, physical_description=physical_description,
        other_notes=other_notes,
    )
    db.add_ante_mortem(profile)
    return {"id": profile.id, "status": "logged"}


@mcp.tool()
def add_post_mortem_observation(
    case_number: str,
    location_found: str = "",
    date_found: str = "",
    sex: str = "unknown",
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    height_cm_min: Optional[float] = None,
    height_cm_max: Optional[float] = None,
    build: str = "",
    hair_color: str = "",
    hair_length: str = "",
    eye_color: str = "",
    marks: Optional[list] = None,
    clothing: Optional[list] = None,
    dental_findings: str = "",
    blood_type: str = "unknown",
    physical_description: str = "",
    other_findings: str = "",
) -> dict:
    """Log a forensic post-mortem observation for an unidentified body/case."""
    obs = PostMortemObservation.new(
        case_number=case_number, location_found=location_found, date_found=date_found,
        sex=sex, age_min=age_min, age_max=age_max,
        height_cm_min=height_cm_min, height_cm_max=height_cm_max,
        build=build, hair_color=hair_color, hair_length=hair_length, eye_color=eye_color,
        marks=marks or [], clothing=clothing or [], dental_findings=dental_findings,
        blood_type=blood_type, physical_description=physical_description,
        other_findings=other_findings,
    )
    db.add_post_mortem(obs)
    return {"id": obs.id, "status": "logged"}


@mcp.tool()
def list_profiles() -> dict:
    """List every ante-mortem profile and post-mortem case currently on file."""
    return {
        "ante_mortem": [{"id": a.id, "name": a.missing_person_name} for a in db.list_ante_mortem()],
        "post_mortem": [{"id": p.id, "case_number": p.case_number} for p in db.list_post_mortem()],
    }


@mcp.tool()
def add_photo(owner_type: str, owner_id: str, image_path: str) -> dict:
    """Attach a face photo to a profile or case and index its face locally.

    owner_type is "ante_mortem" or "post_mortem". image_path is a
    .jpg/.jpeg/.png/.webp/.bmp file on the machine running this server.
    """
    getter = db.get_ante if owner_type == "ante_mortem" else db.get_post
    if owner_type not in ("ante_mortem", "post_mortem"):
        return {"error": "owner_type must be 'ante_mortem' or 'post_mortem'"}
    if not getter(owner_id):
        return {"error": f"No {owner_type} record with id {owner_id}"}
    try:
        return fm.ingest_photo(owner_type, owner_id, image_path)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def add_fingerprint(
    owner_type: str, 
    owner_id: str, 
    image_path: str, 
    finger: str = "unknown", 
    source: str = "other"
) -> dict:
    """Attach a fingerprint image to a profile or case and extract minutiae locally.

    owner_type is "ante_mortem" or "post_mortem". finger is e.g. "right_index", "left_thumb".
    source is e.g. "authorised_record", "latent_from_belongings", "post_mortem_capture".
    """
    getter = db.get_ante if owner_type == "ante_mortem" else db.get_post
    if owner_type not in ("ante_mortem", "post_mortem"):
        return {"error": "owner_type must be 'ante_mortem' or 'post_mortem'"}
    if not getter(owner_id):
        return {"error": f"No {owner_type} record with id {owner_id}"}
    try:
        return fpm.ingest_file(owner_type, owner_id, image_path, finger=finger, source=source)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def compare_faces(ante_mortem_id: str, post_mortem_id: str) -> dict:
    """Compare the face photos of one ante-mortem profile with one
    post-mortem case. Returns similarity score and metadata."""
    result = fm.compare(fm.photos_for("ante_mortem", ante_mortem_id),
                        fm.photos_for("post_mortem", post_mortem_id))
    if result is None:
        return {"error": "Need at least one usable face photo on BOTH sides."}
    return {
        "face_score": result.score, "cosine_similarity": result.cosine,
        "photo_quality": result.quality, "effective_weight": result.weight,
        "best_ante_photo": result.ante_photo, "best_post_photo": result.post_photo,
        "note": result.detail,
    }


@mcp.tool()
def compare_fingerprints(ante_mortem_id: str, post_mortem_id: str) -> dict:
    """Compare the fingerprints of one ante-mortem profile with one post-mortem case."""
    result = fpm.compare(fpm.prints_for("ante_mortem", ante_mortem_id),
                         fpm.prints_for("post_mortem", post_mortem_id))
    if result is None:
        return {"error": "Need at least one usable fingerprint on BOTH sides."}
    return {
        "fingerprint_score": result.score, "matched_minutiae": result.matched,
        "print_quality": result.quality, "effective_weight": result.weight,
        "ante_finger": result.ante_finger, "post_finger": result.post_finger,
        "note": result.detail,
    }


@mcp.tool()
def compute_top_matches(post_mortem_id: str, top_n: int = 3) -> dict:
    """Compute top-N candidate ante-mortem matches for one unidentified body,
    factoring in all text, dental, clothing, face, and fingerprint evidence."""
    post = db.get_post(post_mortem_id)
    if not post:
        return {"error": f"No post-mortem case found with id {post_mortem_id}"}

    ante_profiles = db.list_ante_mortem()
    face_lookup = fm.build_lookup()
    fingerprint_lookup = fpm.build_lookup()

    for a in ante_profiles:
        f_res = face_lookup(a, post)
        fp_res = fingerprint_lookup(a, post)
        r = me.score_pair(a, post, face=f_res, fingerprint=fp_res)
        
        notes = []
        if f_res:
            notes.append(f"face: {f_res.detail}")
        if fp_res:
            notes.append(f"fingerprint: {fp_res.detail}")
            
        db.log_match_audit(r.post_id, r.ante_id, r.score, r.excluded,
                           r.exclusion_reason or ("; ".join(notes) if notes else None))

    matches = me.top_matches(
        post, 
        ante_profiles, 
        top_n=top_n, 
        face_lookup=face_lookup, 
        fingerprint_lookup=fingerprint_lookup
    )
    return {
        "post_mortem_id": post_mortem_id,
        "candidates": [
            {"ante_mortem_id": m.ante_id, "score": m.score, "rationale": m.rationale}
            for m in matches
        ],
    }


@mcp.tool()
def generate_reconciliation_report() -> str:
    """Generate the full reconciliation report across every open case, ready
    to hand to a forensic examiner for confirmation."""
    return rg.generate_reconciliation_report(
        db.list_ante_mortem(), 
        db.list_post_mortem(), 
        face_lookup=fm.build_lookup(),
        fingerprint_lookup=fpm.build_lookup()
    )


if __name__ == "__main__":
    mcp.run()