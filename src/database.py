"""SQLite persistence layer for ante-mortem profiles and post-mortem observations.

Kept intentionally simple (stdlib sqlite3, no ORM) so the whole persistence
layer fits in one readable file. Structured fields a production system
would want to filter or index on (sex, age range, height range, blood type)
get real columns; free-form fields (marks, clothing, dental notes) are
stored as JSON, since their shape varies case to case. See
docs/architecture.md ("Scalability Notes") for how this would evolve past
hackathon scale (e.g. Postgres + a real migrations tool + those same
columns indexed for pre-filtering before scoring).
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict

from models import AnteMortemProfile, PostMortemObservation, Mark

DB_PATH = os.environ.get(
    "DVI_DB_PATH", os.path.join(os.path.dirname(__file__), "dvi.db")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ante_mortem (
    id TEXT PRIMARY KEY,
    sex TEXT, age_min INTEGER, age_max INTEGER,
    height_cm_min REAL, height_cm_max REAL, blood_type TEXT,
    data TEXT NOT NULL,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS post_mortem (
    id TEXT PRIMARY KEY,
    case_number TEXT,
    sex TEXT, age_min INTEGER, age_max INTEGER,
    height_cm_min REAL, height_cm_max REAL, blood_type TEXT,
    data TEXT NOT NULL,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS photo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type TEXT NOT NULL,          -- 'ante_mortem' | 'post_mortem'
    owner_id TEXT NOT NULL,
    photo_path TEXT NOT NULL,
    status TEXT NOT NULL,              -- ok | low_quality | no_face | unreadable | not_processed
    model TEXT, vector TEXT,           -- vector = JSON list of floats (L2-normalised)
    det_score REAL, face_px REAL, face_count INTEGER, quality REAL,
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_photo_owner ON photo(owner_type, owner_id);
CREATE TABLE IF NOT EXISTS fingerprint (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type TEXT NOT NULL,          -- 'ante_mortem' | 'post_mortem'
    owner_id TEXT NOT NULL,
    image_path TEXT NOT NULL,
    finger TEXT, source TEXT,
    status TEXT NOT NULL,
    algo TEXT,
    template TEXT,                     -- JSON: {"minutiae": [...], "bbox": [...]}
    quality REAL, n_minutiae INTEGER,
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_fp_owner ON fingerprint(owner_type, owner_id);
CREATE TABLE IF NOT EXISTS match_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT, ante_id TEXT, score REAL, excluded INTEGER,
    reason TEXT, generated_at REAL
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def _to_json(obj) -> str:
    return json.dumps(asdict(obj))


def add_ante_mortem(profile: AnteMortemProfile) -> str:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ante_mortem VALUES (?,?,?,?,?,?,?,?,?)",
            (profile.id, profile.sex, profile.age_min, profile.age_max,
             profile.height_cm_min, profile.height_cm_max, profile.blood_type,
             _to_json(profile), profile.created_at),
        )
    return profile.id


def add_post_mortem(obs: PostMortemObservation) -> str:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO post_mortem VALUES (?,?,?,?,?,?,?,?,?,?)",
            (obs.id, obs.case_number, obs.sex, obs.age_min, obs.age_max,
             obs.height_cm_min, obs.height_cm_max, obs.blood_type,
             _to_json(obs), obs.created_at),
        )
    return obs.id


def _row_to_ante(row) -> AnteMortemProfile:
    d = json.loads(row["data"])
    d["marks"] = [Mark(**m) for m in d.get("marks", [])]
    return AnteMortemProfile(**d)


def _row_to_post(row) -> PostMortemObservation:
    d = json.loads(row["data"])
    d["marks"] = [Mark(**m) for m in d.get("marks", [])]
    return PostMortemObservation(**d)


def list_ante_mortem() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM ante_mortem ORDER BY created_at").fetchall()
    return [_row_to_ante(r) for r in rows]


def list_post_mortem() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM post_mortem ORDER BY created_at").fetchall()
    return [_row_to_post(r) for r in rows]


def get_ante(ante_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM ante_mortem WHERE id=?", (ante_id,)).fetchone()
    return _row_to_ante(row) if row else None


def get_post(post_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM post_mortem WHERE id=?", (post_id,)).fetchone()
    return _row_to_post(row) if row else None


def log_match_audit(post_id: str, ante_id: str, score: float, excluded: bool, reason: str | None):
    """Append-only audit trail of every match computed -- including excluded
    pairs and why -- so a reviewer can later see exactly what the system
    considered, not just what it recommended."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO match_audit_log (post_id, ante_id, score, excluded, reason, generated_at) "
            "VALUES (?,?,?,?,?,strftime('%s','now'))",
            (post_id, ante_id, score, int(excluded), reason),
        )


def add_photo(row: dict) -> None:
    """Store one photo record (embedding may be absent, e.g. no face found)."""
    vec = row.get("vector")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO photo (owner_type, owner_id, photo_path, status, model, vector, "
            "det_score, face_px, face_count, quality, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,strftime('%s','now'))",
            (row["owner_type"], row["owner_id"], row["photo_path"], row["status"],
             row.get("model"), json.dumps(vec) if vec else None, row.get("det_score"),
             row.get("face_px"), row.get("face_count"), row.get("quality")),
        )


def list_photos(owner_type: str | None = None, owner_id: str | None = None) -> list:
    q, args = "SELECT * FROM photo", []
    filters = []
    if owner_type is not None:
        filters.append("owner_type=?")
        args.append(owner_type)
    if owner_id is not None:
        filters.append("owner_id=?")
        args.append(owner_id)
    if filters:
        q += " WHERE " + " AND ".join(filters)
    with get_conn() as conn:
        rows = conn.execute(q + " ORDER BY id", args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["vector"] = json.loads(d["vector"]) if d["vector"] else None
        out.append(d)
    return out


def add_fingerprint(row: dict) -> None:
    """Store one fingerprint record (template may be absent if extraction failed)."""
    tpl = row.get("template")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO fingerprint (owner_type, owner_id, image_path, finger, source, status, "
            "algo, template, quality, n_minutiae, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,strftime('%s','now'))",
            (row["owner_type"], row["owner_id"], row["image_path"], row.get("finger"),
             row.get("source"), row["status"], row.get("algo"),
             json.dumps(tpl) if tpl else None, row.get("quality"), row.get("n_minutiae")),
        )


def list_fingerprints(owner_type: str | None = None, owner_id: str | None = None) -> list:
    q, args = "SELECT * FROM fingerprint", []
    filters = []
    if owner_type is not None:
        filters.append("owner_type=?")
        args.append(owner_type)
    if owner_id is not None:
        filters.append("owner_id=?")
        args.append(owner_id)
    if filters:
        q += " WHERE " + " AND ".join(filters)
    with get_conn() as conn:
        rows = conn.execute(q + " ORDER BY id", args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["template"] = json.loads(d["template"]) if d["template"] else None
        out.append(d)
    return out


def list_match_audit(limit: int = 20) -> list:
    """Most recent audit-log rows (newest first) -- used by the Overview activity feed."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM match_audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
