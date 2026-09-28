"""Tests for the face-comparison layer. Everything here uses synthetic
embeddings, so no face model, GPU, images or network are needed.

Run with:
    pytest src/tests/ -v
"""
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database as db
import face_matching as fm
import matching_engine as me
from models import AnteMortemProfile, PostMortemObservation


def _vec(*xs):
    return fm._normalize([float(x) for x in xs])


def _rec(owner_type, owner_id, vector, quality=1.0, face_count=1, path="p.jpg"):
    return fm.FaceRecord(owner_type, owner_id, path, "ok", vector, 0.99, 200.0, face_count, quality)


def _ante(**kw):
    d = dict(reporter_name="R", reporter_relationship="sibling", reporter_contact="",
             missing_person_name="T", sex="male", age_min=25, age_max=35, height_cm_min=170,
             height_cm_max=180, build="average", hair_color="black", hair_length="short",
             eye_color="brown", marks=[], clothing=[], dental_notes="", blood_type="unknown",
             last_seen_location="", last_seen_date="")
    d.update(kw)
    return AnteMortemProfile.new(**d)


def _post(**kw):
    d = dict(case_number="T-1", location_found="", date_found="", sex="male", age_min=25,
             age_max=35, height_cm_min=170, height_cm_max=180, build="average",
             hair_color="black", hair_length="short", eye_color="brown", marks=[], clothing=[],
             dental_findings="", blood_type="unknown")
    d.update(kw)
    return PostMortemObservation.new(**d)


def test_identical_embeddings_score_100():
    v = _vec(1, 2, 3, 4)
    r = fm.compare([_rec("ante_mortem", "A", v)], [_rec("post_mortem", "P", v)])
    assert r.score == 100.0 and math.isclose(r.cosine, 1.0, abs_tol=1e-6)


def test_dissimilar_face_is_floored_never_zero():
    r = fm.compare([_rec("ante_mortem", "A", _vec(1, 0, 0))], [_rec("post_mortem", "P", _vec(0, 1, 0))])
    assert r.score == fm.SCORE_FLOOR


def test_no_photos_returns_none():
    assert fm.compare([], [_rec("post_mortem", "P", _vec(1, 0))]) is None
    no_vec = fm.FaceRecord("ante_mortem", "A", "x.jpg", "no_face")
    assert fm.compare([no_vec], [_rec("post_mortem", "P", _vec(1, 0))]) is None


def test_low_quality_photo_scales_weight_down():
    v = _vec(1, 1, 1)
    good = fm.compare([_rec("ante_mortem", "A", v)], [_rec("post_mortem", "P", v)])
    bad = fm.compare([_rec("ante_mortem", "A", v)], [_rec("post_mortem", "P", v, quality=0.2)])
    assert bad.weight < good.weight * 0.25
    assert good.weight <= fm.BASE_WEIGHT


def test_best_pair_across_multiple_photos_is_used():
    target = _vec(1, 0, 0)
    antes = [_rec("ante_mortem", "A", _vec(0, 1, 0), path="bad.jpg"),
             _rec("ante_mortem", "A", target, path="good.jpg")]
    r = fm.compare(antes, [_rec("post_mortem", "P", target)])
    assert r.ante_photo == "good.jpg" and r.n_pairs == 2


def test_engine_without_face_is_unchanged():
    base = me.score_pair(_ante(), _post())
    same = me.score_pair(_ante(), _post(), face=None)
    assert base.score == same.score and len(base.rationale) == 4


def test_engine_adds_face_component_and_rationale_line():
    v = _vec(1, 2, 3)
    face = fm.compare([_rec("ante_mortem", "A", v)], [_rec("post_mortem", "P", v)])
    result = me.score_pair(_ante(), _post(), face=face)
    assert len(result.rationale) == 5
    assert any("Facial similarity" in line for line in result.rationale)


def test_matching_face_raises_score_and_mismatch_lowers_it_modestly():
    a, p = _ante(), _post()
    v, other = _vec(1, 2, 3), _vec(3, -2, 1)
    base = me.score_pair(a, p).score
    hi = me.score_pair(a, p, fm.compare([_rec("ante_mortem", a.id, v)], [_rec("post_mortem", p.id, v)])).score
    lo = me.score_pair(a, p, fm.compare([_rec("ante_mortem", a.id, v)], [_rec("post_mortem", p.id, other)])).score
    assert hi > base > lo
    assert base - lo < 15          # a face mismatch alone can't sink a candidate


def test_face_never_excludes_a_candidate():
    a, p = _ante(), _post()
    face = fm.compare([_rec("ante_mortem", a.id, _vec(1, 0))], [_rec("post_mortem", p.id, _vec(0, 1))])
    assert not me.score_pair(a, p, face=face).excluded


def test_hard_exclusion_still_beats_a_perfect_face():
    v = _vec(1, 2, 3)
    face = fm.compare([_rec("ante_mortem", "A", v)], [_rec("post_mortem", "P", v)])
    assert me.score_pair(_ante(sex="female"), _post(sex="male"), face=face).excluded


def test_top_matches_ranks_face_evidence():
    p = _post()
    a1, a2 = _ante(missing_person_name="twin-A"), _ante(missing_person_name="twin-B")
    v, other = _vec(1, 2, 3), _vec(3, -2, 1)
    by_owner = {("ante_mortem", a1.id): [_rec("ante_mortem", a1.id, other)],
                ("ante_mortem", a2.id): [_rec("ante_mortem", a2.id, v)],
                ("post_mortem", p.id): [_rec("post_mortem", p.id, v)]}
    lookup = lambda a, po: fm.compare(by_owner.get(("ante_mortem", a.id), []),
                                      by_owner.get(("post_mortem", po.id), []))
    top = me.top_matches(p, [a1, a2], top_n=2, face_lookup=lookup)
    assert top[0].ante_id == a2.id


def test_database_roundtrip_and_build_lookup():
    old = db.DB_PATH
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = os.path.join(tmp, "t.db")
        try:
            db.init_db()
            a, p = _ante(), _post()
            db.add_ante_mortem(a)
            db.add_post_mortem(p)
            v = _vec(1, 2, 3)
            for owner_type, owner_id in (("ante_mortem", a.id), ("post_mortem", p.id)):
                db.add_photo({"owner_type": owner_type, "owner_id": owner_id, "photo_path": "x.jpg",
                              "status": "ok", "vector": v, "det_score": 0.99, "face_px": 200.0,
                              "face_count": 1, "quality": 1.0})
            db.add_photo({"owner_type": "post_mortem", "owner_id": p.id, "photo_path": "y.jpg",
                          "status": "no_face"})
            assert len(db.list_photos("post_mortem", p.id)) == 2
            r = fm.build_lookup()(a, p)
            assert r is not None and r.score == 100.0
        finally:
            db.DB_PATH = old


def test_unavailable_face_backend_never_creates_a_similarity_vector(monkeypatch):
    monkeypatch.setattr(fm, "_get_app", lambda: (_ for _ in ()).throw(fm.FaceBackendUnavailable("missing")))
    result = fm.extract_face("does-not-need-to-exist.jpg")
    assert result["status"] == "not_processed"
    assert result.get("vector") is None