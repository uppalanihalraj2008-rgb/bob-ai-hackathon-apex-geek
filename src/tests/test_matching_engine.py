"""
Unit tests for the deterministic matching engine. These run with zero
external dependencies (no database, no MCP, no network, no Streamlit) --
exactly the auditability property described in matching_engine.py's
docstring: the score is a pure function of two records.

Run with:
    pytest src/tests/ -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import matching_engine as me
from models import AnteMortemProfile, PostMortemObservation


def _ante(**kw):
    defaults = dict(
        reporter_name="Test Reporter", reporter_relationship="sibling", reporter_contact="",
        missing_person_name="Test Person", sex="male", age_min=25, age_max=35,
        height_cm_min=170, height_cm_max=180, build="average", hair_color="black",
        hair_length="short", eye_color="brown", marks=[], clothing=[],
        dental_notes="", blood_type="unknown", last_seen_location="", last_seen_date="",
    )
    defaults.update(kw)
    return AnteMortemProfile.new(**defaults)


def _post(**kw):
    defaults = dict(
        case_number="TEST-1", location_found="", date_found="", sex="male",
        age_min=25, age_max=35, height_cm_min=170, height_cm_max=180, build="average",
        hair_color="black", hair_length="short", eye_color="brown", marks=[], clothing=[],
        dental_findings="", blood_type="unknown",
    )
    defaults.update(kw)
    return PostMortemObservation.new(**defaults)


def test_sex_mismatch_is_excluded():
    result = me.score_pair(_ante(sex="female"), _post(sex="male"))
    assert result.excluded
    assert result.score == 0.0
    assert "sex" in result.exclusion_reason.lower()


def test_incompatible_blood_type_is_excluded():
    result = me.score_pair(_ante(blood_type="A+"), _post(blood_type="O-"))
    assert result.excluded


def test_disjoint_age_ranges_are_excluded():
    result = me.score_pair(_ante(age_min=20, age_max=25), _post(age_min=70, age_max=80))
    assert result.excluded


def test_age_ranges_within_estimation_buffer_are_not_excluded():
    # 25-30 vs 31-36 don't literally overlap, but are within the 4-year
    # skeletal age-estimation buffer, so this should NOT be auto-excluded.
    result = me.score_pair(_ante(age_min=25, age_max=30), _post(age_min=31, age_max=36))
    assert not result.excluded


def test_strong_dental_and_mark_match_scores_high():
    ante = _ante(
        dental_notes="missing lower right molar, gold crown on canine",
        marks=[{"type": "scar", "location": "left forearm",
                "description": "3cm curved scar from childhood bike accident"}],
        clothing=["blue denim jacket"],
    )
    post = _post(
        dental_findings="lower right molar missing, gold crown present on canine",
        marks=[{"type": "scar", "location": "left forearm",
                "description": "curved scar, approx 3cm, old injury"}],
        clothing=["blue denim jacket fragment"],
    )
    result = me.score_pair(ante, post)
    assert not result.excluded
    assert result.score >= 65


def test_weak_match_scores_lower_than_strong_match():
    strong_ante = _ante(
        dental_notes="missing lower right molar, gold crown on canine",
        marks=[{"type": "scar", "location": "left forearm", "description": "3cm curved scar"}],
    )
    weak_ante = _ante(
        dental_notes="full upper dentures",
        marks=[{"type": "tattoo", "location": "right ankle", "description": "small star"}],
    )
    post = _post(
        dental_findings="lower right molar missing, gold crown present on canine",
        marks=[{"type": "scar", "location": "left forearm", "description": "curved scar, approx 3cm"}],
    )
    strong = me.score_pair(strong_ante, post)
    weak = me.score_pair(weak_ante, post)
    assert strong.score > weak.score


def test_top_matches_ranks_and_filters_excluded_candidates():
    post = _post(sex="male")
    candidates = [
        _ante(sex="female"),  # excluded, must not appear in results
        _ante(dental_notes="full dentures"),  # weak match
        _ante(dental_notes="", marks=[{"type": "scar", "location": "left forearm", "description": "old scar"}]),
    ]
    results = me.top_matches(post, candidates, top_n=3)
    assert all(not r.excluded for r in results)
    assert len(results) == 2
    assert results[0].score >= results[1].score


def test_no_data_either_side_is_neutral_not_zero():
    # An empty field on both sides shouldn't tank the score to 0 -- it's
    # "no evidence," not "contradicting evidence."
    result = me.score_pair(_ante(marks=[], dental_notes=""), _post(marks=[], dental_findings=""))
    assert not result.excluded
    assert result.score > 0


def test_rationale_is_always_populated_for_non_excluded_pairs():
    result = me.score_pair(_ante(), _post())
    assert not result.excluded
    assert len(result.rationale) == 4  # one line per scoring component


def test_database_filters_work_independently():
    import tempfile
    import database as db

    old = db.DB_PATH
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = os.path.join(tmp, "filters.db")
        try:
            db.init_db()
            a1, a2 = _ante(missing_person_name="A1"), _ante(missing_person_name="A2")
            p1 = _post(case_number="P1")
            for a in (a1, a2):
                db.add_ante_mortem(a)
            db.add_post_mortem(p1)
            db.add_photo({"owner_type": "ante_mortem", "owner_id": a1.id, "photo_path": "a1.jpg", "status": "no_face"})
            db.add_photo({"owner_type": "ante_mortem", "owner_id": a2.id, "photo_path": "a2.jpg", "status": "no_face"})
            db.add_photo({"owner_type": "post_mortem", "owner_id": p1.id, "photo_path": "p1.jpg", "status": "no_face"})
            assert len(db.list_photos(owner_type="ante_mortem")) == 2
            assert len(db.list_photos(owner_id=a1.id)) == 1
            assert len(db.list_photos(owner_type="post_mortem")) == 1
        finally:
            db.DB_PATH = old