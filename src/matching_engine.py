"""
matching_engine.py
-------------------
Deterministic, auditable scoring engine that compares an ante-mortem
(family-reported) profile against a post-mortem (recovered remains)
observation and produces:

  - a 0-100 match-probability score
  - a component breakdown (so every point of the score is explainable)
  - a human-readable rationale (bullet points)
  - a hard "excluded" flag for biologically impossible pairings

Design intent
-------------
Human identification is a high-stakes, legally and emotionally
consequential decision. We deliberately keep the *scoring* logic fully
deterministic and free of any LLM call, so every score is reproducible,
auditable, and defensible to a forensic reviewer -- re-running this module
on the same two records always produces the same number. IBM Bob (the LLM)
sits on top of this engine: it handles natural-language intake (turning a
family member's spoken description into the structured fields below) and
narrating the final report -- not the scoring decision itself. See
docs/solution-overview.md for the full rationale.

This module has zero dependencies on the rest of the codebase (no database,
no MCP, no network) so it can be unit-tested and audited in complete
isolation. See src/tests/test_matching_engine.py.

IMPORTANT: nothing in this file produces an "identification." It produces
ranked investigative leads for a qualified forensic examiner to confirm
using primary identifiers (DNA, dental radiographs, fingerprints), per
standard DVI protocol (e.g. INTERPOL DVI guidelines).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional, List, Any, Callable

# ---------------------------------------------------------------------------
# Vocabulary used to pull structured signal out of free-text fields
# ---------------------------------------------------------------------------

BODY_PARTS = [
    "forehead", "scalp", "ear", "eyebrow", "eyelid", "cheek", "nose", "lip", "chin", "jaw", "neck",
    "shoulder", "upper arm", "forearm", "elbow", "wrist", "hand", "finger", "thumb", "palm", "knuckle",
    "chest", "sternum", "abdomen", "back", "spine", "hip", "lower back",
    "thigh", "knee", "shin", "calf", "ankle", "foot", "heel", "toe", "sole",
    "face", "arm", "leg", "torso",
]

SIDE_WORDS = {"left": "left", "right": "right", "bilateral": "bilateral", "both": "bilateral"}

DENTAL_KEYWORDS = [
    "missing", "extracted", "extraction", "crown", "filling", "cavity", "braces",
    "denture", "dentures", "implant", "root canal", "gold", "silver", "chipped",
    "broken tooth", "bridge", "wisdom tooth", "molar", "premolar", "canine", "incisor",
    "upper", "lower", "gap", "gold tooth", "cap",
]


def _norm(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()


def _extract_side(text: str) -> Optional[str]:
    for word, side in SIDE_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            return side
    return None


def _extract_body_parts(text: str) -> set:
    return {part for part in BODY_PARTS if part in text}


def _extract_keywords(text: str, vocab: list) -> set:
    return {kw for kw in vocab if kw in text}


def _text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _jaccard(a: set, b: set) -> Optional[float]:
    """Returns None when neither side has any signal (i.e. no evidence to compare)."""
    if not a and not b:
        return None
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class ComponentScore:
    name: str
    score: float   # 0-100
    weight: float  # 0-1
    detail: str


@dataclass
class MatchResult:
    ante_id: str
    post_id: str
    score: float
    excluded: bool
    exclusion_reason: Optional[str]
    components: List[ComponentScore]
    rationale: List[str]


# ---------------------------------------------------------------------------
# Hard exclusion rules -- never suggest a biologically impossible pairing
# ---------------------------------------------------------------------------

def _check_exclusion(ante, post) -> Optional[str]:
    if getattr(ante, 'sex', None) and getattr(post, 'sex', None):
        if ante.sex != "unknown" and post.sex != "unknown" and ante.sex != post.sex:
            return f"Sex mismatch (ante: {ante.sex}, post: {post.sex})"

    if getattr(ante, 'blood_type', None) and getattr(post, 'blood_type', None):
        if ante.blood_type != "unknown" and post.blood_type != "unknown" and ante.blood_type != post.blood_type:
            return f"Blood type incompatible (ante: {ante.blood_type}, post: {post.blood_type})"

    # Age: allow a +/- 4 year buffer to account for skeletal age-estimation error
    a_min, a_max = getattr(ante, 'age_min', None), getattr(ante, 'age_max', None)
    p_min, p_max = getattr(post, 'age_min', None), getattr(post, 'age_max', None)

    if None not in (a_min, a_max, p_min, p_max):
        if p_min - 4 > a_max or p_max + 4 < a_min:
            return (f"Age ranges do not overlap even with a 4-year estimation buffer "
                    f"(ante: {a_min}-{a_max}, post: {p_min}-{p_max})")

    return None


# ---------------------------------------------------------------------------
# Component scorers -- each returns 0-100 plus a plain-English detail string
# ---------------------------------------------------------------------------

def _score_demographics(ante, post) -> ComponentScore:
    subscores, notes = [], []

    a_min, a_max = getattr(ante, 'age_min', None), getattr(ante, 'age_max', None)
    p_min, p_max = getattr(post, 'age_min', None), getattr(post, 'age_max', None)
    if None not in (a_min, a_max, p_min, p_max):
        overlap = min(a_max, p_max) - max(a_min, p_min)
        span = max(a_max, p_max) - min(a_min, p_min)
        age_score = max(0.0, overlap / span) * 100 if span > 0 else 100.0
        subscores.append(age_score)
        notes.append(f"age range overlap {age_score:.0f}%")

    ah_min, ah_max = getattr(ante, 'height_cm_min', None), getattr(ante, 'height_cm_max', None)
    ph_min, ph_max = getattr(post, 'height_cm_min', None), getattr(post, 'height_cm_max', None)
    if None not in (ah_min, ah_max, ph_min, ph_max):
        overlap = min(ah_max, ph_max) - max(ah_min, ph_min)
        span = max(ah_max, ph_max) - min(ah_min, ph_min)
        h_score = max(0.0, overlap / span) * 100 if span > 0 else 100.0
        subscores.append(h_score)
        notes.append(f"height range overlap {h_score:.0f}%")

    for a_val, p_val, label in (
        (getattr(ante, 'build', ''), getattr(post, 'build', ''), "build"),
        (getattr(ante, 'hair_color', ''), getattr(post, 'hair_color', ''), "hair color"),
        (getattr(ante, 'eye_color', ''), getattr(post, 'eye_color', ''), "eye color"),
    ):
        if a_val and p_val and a_val != "unknown" and p_val != "unknown":
            s = 100.0 if _norm(a_val) == _norm(p_val) else _text_similarity(_norm(a_val), _norm(p_val)) * 100
            subscores.append(s)
            notes.append(f"{label} {'matches' if s > 80 else 'differs'}")

    a_phys = getattr(ante, 'physical_description', '')
    p_phys = getattr(post, 'physical_description', '')
    if a_phys and p_phys:
        phys_score = _text_similarity(_norm(a_phys), _norm(p_phys)) * 100
        subscores.append(phys_score)
        notes.append(f"physical description similarity {phys_score:.0f}%")

    score = sum(subscores) / len(subscores) if subscores else 50.0  # neutral when nothing to compare
    return ComponentScore("Demographics", score, 0.15, "; ".join(notes) or "insufficient data on both sides")


def _score_marks(ante, post) -> ComponentScore:
    ante_marks = getattr(ante, 'marks', [])
    post_marks = getattr(post, 'marks', [])

    if not ante_marks and not post_marks:
        return ComponentScore("Distinguishing marks", 50.0, 0.35, "no marks recorded on either side")
    if not ante_marks or not post_marks:
        return ComponentScore("Distinguishing marks", 30.0, 0.35,
                               "marks recorded on only one side -- remains may be incomplete or decomposed")

    pair_scores, matched_pairs, used_ante = [], [], set()
    for p_mark in post_marks:
        p_type = getattr(p_mark, 'type', '')
        p_loc = getattr(p_mark, 'location', '')
        p_desc = getattr(p_mark, 'description', '')
        p_text = _norm(f"{p_type} {p_loc} {p_desc}")
        p_side, p_parts = _extract_side(p_text), _extract_body_parts(p_text)
        best = (0.0, None)
        for i, a_mark in enumerate(ante_marks):
            if i in used_ante:
                continue
            a_type = getattr(a_mark, 'type', '')
            a_loc = getattr(a_mark, 'location', '')
            a_desc = getattr(a_mark, 'description', '')
            a_text = _norm(f"{a_type} {a_loc} {a_desc}")
            a_side, a_parts = _extract_side(a_text), _extract_body_parts(a_text)

            type_score = (100.0 if _norm(p_type) == _norm(a_type)
                          else _text_similarity(_norm(p_type), _norm(a_type)) * 100)
            side_score = 100.0 if (p_side and a_side and p_side == a_side) else (50.0 if not p_side or not a_side else 0.0)
            j = _jaccard(p_parts, a_parts)
            part_score = 100.0 if j is None else j * 100
            desc_score = _text_similarity(_norm(p_desc), _norm(a_desc)) * 100

            pair_score = 0.25 * type_score + 0.20 * side_score + 0.25 * part_score + 0.30 * desc_score
            if pair_score > best[0]:
                best = (pair_score, i)

        if best[1] is not None:
            used_ante.add(best[1])
            matched_pairs.append((p_mark, ante_marks[best[1]], best[0]))
        pair_scores.append(best[0])

    avg = sum(pair_scores) / len(pair_scores) if pair_scores else 30.0
    detail = "; ".join(
        f"'{getattr(p, 'description', '')}' ({getattr(p, 'location', '')}) ~ '{getattr(a, 'description', '')}' ({getattr(a, 'location', '')}) = {s:.0f}%"
        for p, a, s in matched_pairs
    )
    return ComponentScore("Distinguishing marks", avg, 0.35, detail or "no comparable mark pairs found")


def _score_dental(ante, post) -> ComponentScore:
    a_notes = getattr(ante, 'dental_notes', '')
    p_notes = getattr(post, 'dental_findings', getattr(post, 'dental_notes', ''))
    
    a_text, p_text = _norm(a_notes), _norm(p_notes)
    if not a_text and not p_text:
        return ComponentScore("Dental", 50.0, 0.30, "no dental data recorded on either side")
    if not a_text or not p_text:
        return ComponentScore("Dental", 30.0, 0.30, "dental data recorded on only one side")

    a_kw, p_kw = _extract_keywords(a_text, DENTAL_KEYWORDS), _extract_keywords(p_text, DENTAL_KEYWORDS)
    j = _jaccard(a_kw, p_kw)
    kw_score = 100.0 if j is None else j * 100
    text_score = _text_similarity(a_text, p_text) * 100
    score = 0.6 * kw_score + 0.4 * text_score
    shared = ", ".join(sorted(a_kw & p_kw)) or "none"
    return ComponentScore("Dental", score, 0.30, f"shared dental features: {shared}")


def _score_clothing(ante, post) -> ComponentScore:
    a_clothing = getattr(ante, 'clothing', [])
    p_clothing = getattr(post, 'clothing', [])

    if not a_clothing and not p_clothing:
        return ComponentScore("Clothing / personal effects", 50.0, 0.15, "no items recorded on either side")
    if not a_clothing or not p_clothing:
        return ComponentScore("Clothing / personal effects", 35.0, 0.15, "items recorded on only one side")

    best_scores, matched, used = [], [], set()
    for p_item in p_clothing:
        p_norm = _norm(p_item)
        best = (0.0, None)
        for i, a_item in enumerate(a_clothing):
            if i in used:
                continue
            s = _text_similarity(p_norm, _norm(a_item)) * 100
            if s > best[0]:
                best = (s, i)
        if best[1] is not None:
            used.add(best[1])
            matched.append((p_item, a_clothing[best[1]], best[0]))
        best_scores.append(best[0])

    avg = sum(best_scores) / len(best_scores) if best_scores else 35.0
    detail = "; ".join(f"'{p}' ~ '{a}' ({s:.0f}%)" for p, a, s in matched) or "no comparable items"
    return ComponentScore("Clothing / personal effects", avg, 0.15, detail)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_pair(ante, post, face=None, fingerprint=None) -> MatchResult:
    """Score one ante-mortem profile against one post-mortem observation.

    `face` and `fingerprint` are optional precomputed biometric comparison objects
    exposing `.score` (0-100) or `.match_probability` (0.0-1.0), `.weight`, and `.detail`.
    """
    exclusion = _check_exclusion(ante, post)
    if exclusion:
        return MatchResult(ante.id, post.id, 0.0, True, exclusion, [], [f"Excluded: {exclusion}"])

    components = [
        _score_demographics(ante, post),
        _score_marks(ante, post),
        _score_dental(ante, post),
        _score_clothing(ante, post),
    ]

    # Process optional face biometric score
    if face is not None:
        f_score = getattr(face, 'score', getattr(face, 'match_probability', 0.0))
        if f_score <= 1.0 and f_score > 0.0:
            f_score *= 100.0
        f_weight = getattr(face, 'weight', 0.25)
        f_detail = getattr(face, 'detail', f"Facial match score: {f_score:.1f}%")
        components.append(ComponentScore("Facial similarity", f_score, f_weight, f_detail))

    # Process optional fingerprint biometric score
    if fingerprint is not None:
        fp_score = getattr(fingerprint, 'score', getattr(fingerprint, 'match_probability', 0.0))
        if fp_score <= 1.0 and fp_score > 0.0:
            fp_score *= 100.0
        fp_weight = getattr(fingerprint, 'weight', 0.25)
        fp_detail = getattr(fingerprint, 'detail', f"Fingerprint match score: {fp_score:.1f}%")
        components.append(ComponentScore("Fingerprint similarity", fp_score, fp_weight, fp_detail))

    total = sum(c.score * c.weight for c in components) / sum(c.weight for c in components)

    rationale = [
        f"{c.name} ({c.weight * 100:.0f}% weight, {c.score:.0f}/100): {c.detail}"
        for c in sorted(components, key=lambda c: -c.weight)
    ]
    return MatchResult(ante.id, post.id, round(total, 1), False, None, components, rationale)


def top_matches(post, ante_profiles, top_n: int = 3, face_lookup: Optional[Callable] = None, fingerprint_lookup: Optional[Callable] = None) -> list:
    """Score `post` against every profile in `ante_profiles`, drop biologically
    excluded pairs, and return the top `top_n` ranked by score, descending.
    `face_lookup(ante, post)` and `fingerprint_lookup(ante, post)` may return biometric comparison objects."""
    results = [
        score_pair(
            a, 
            post, 
            face=face_lookup(a, post) if face_lookup else None,
            fingerprint=fingerprint_lookup(a, post) if fingerprint_lookup else None
        )
        for a in ante_profiles
    ]
    viable = [r for r in results if not r.excluded]
    viable.sort(key=lambda r: -r.score)
    return viable[:top_n]