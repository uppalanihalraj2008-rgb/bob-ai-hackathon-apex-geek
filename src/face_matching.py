"""Face-comparison layer for the DVI coordination tool.

What it does
------------
1. Takes a family-provided photo (ante-mortem) or a post-mortem photo,
   finds the face, and turns it into an embedding using
   InsightFace's ArcFace model ("buffalo_l"), running LOCALLY. If the
   biometric backend is unavailable, the photo is retained but is not used
   for facial matching.
2. Stores the embedding + photo quality signals in SQLite (table `photo`).
3. Compares an ante-mortem profile's photos against a post-mortem case's
   photos (cosine similarity, best pair wins) and returns a
   `FaceComparison` that `matching_engine.score_pair` folds in as one more
   scoring component, "Facial similarity".

Design rules
------------
* SUPPLEMENTARY, never decisive. Face is a low-weight component (default 20%).
* NEVER an exclusion rule.
* Deterministic after ingestion.
"""
from __future__ import annotations

import math
import os
import uuid
from dataclasses import dataclass
from typing import Callable, Optional, List, Dict, Any

HERE = os.path.dirname(__file__)
PHOTO_DIR = os.environ.get("DVI_PHOTO_DIR", os.path.join(HERE, "photos"))

MODEL_TAG = "insightface-buffalo_l"

# --- Calibration knobs -------------------------------------------------------
DIFFERENT_COS = float(os.environ.get("DVI_FACE_DIFFERENT_COS", "0.20"))
SAME_COS = float(os.environ.get("DVI_FACE_SAME_COS", "0.55"))
SCORE_FLOOR = float(os.environ.get("DVI_FACE_SCORE_FLOOR", "30"))
BASE_WEIGHT = float(os.environ.get("DVI_FACE_WEIGHT", "0.20"))

MIN_DET_SCORE = 0.50     # detector confidence below this => "low_quality"
MIN_FACE_PX = 48         # shorter side of the face box, in pixels
REF_FACE_PX = 112        # face size at which resolution stops limiting quality
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

STATUS_HELP = {
    "ok": "Face detected and embedded.",
    "low_quality": "Face found but small/blurry -- it will carry very little weight.",
    "no_face": "No face detected in this photo -- try a clearer, front-facing image.",
    "unreadable": "The image file could not be decoded.",
    "not_processed": "Saved, but the ArcFace face-recognition backend is unavailable; this photo is not used for facial matching.",
}


class FaceBackendUnavailable(RuntimeError):
    pass


# --- Data classes -----------------------------------------------------------

@dataclass
class FaceRecord:
    owner_type: str          # "ante_mortem" | "post_mortem"
    owner_id: str
    photo_path: str
    status: str
    vector: Optional[list] = None
    det_score: float = 0.0
    face_px: float = 0.0
    face_count: int = 0
    quality: float = 0.0     # 0-1


@dataclass
class FaceComparison:
    score: float             # 0-100, already calibrated + floored
    weight: float            # 0-BASE_WEIGHT, already scaled by quality
    detail: str
    cosine: float
    quality: float
    ante_photo: str
    post_photo: str
    n_pairs: int


# --- Embedding extraction (lazy, local) --------------------------------------

_APP = None


def _get_app():
    global _APP
    if _APP is None:
        try:
            import cv2  # noqa: F401
            from insightface.app import FaceAnalysis
            app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
            app.prepare(ctx_id=-1, det_size=(640, 640))
            _APP = app
        except Exception as e:
            raise FaceBackendUnavailable(f"InsightFace backend unavailable: {e}") from e
    return _APP


def _quality(det_score: float, face_px: float, face_count: int) -> float:
    q = max(0.0, min(1.0, det_score)) * min(1.0, face_px / REF_FACE_PX)
    if face_count > 1:
        q *= 0.7             # ambiguous photo: largest face used
    return round(q, 3)


def extract_face(image_path: str) -> dict:
    """Return {status, vector, det_score, face_px, face_count, quality}."""
    try:
        app = _get_app()
        import cv2
        img = cv2.imread(image_path)
        if img is None:
            return {"status": "unreadable"}
        faces = app.get(img)
        if not faces:
            return {"status": "no_face"}
        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        x1, y1, x2, y2 = (float(v) for v in face.bbox)
        face_px = min(x2 - x1, y2 - y1)
        det = float(face.det_score)
        vec = _normalize([float(v) for v in face.normed_embedding])
        ok = det >= MIN_DET_SCORE and face_px >= MIN_FACE_PX
        return {
            "status": "ok" if ok else "low_quality",
            "vector": vec, "det_score": det, "face_px": face_px,
            "face_count": len(faces), "quality": _quality(det, face_px, len(faces)),
        }
    except FaceBackendUnavailable:
        return {"status": "not_processed"}
    except Exception as e:
        print(f"Error during face extraction: {e}")
        return {"status": "unreadable"}


def _fallback_extract_face(image_path: str) -> dict:
    """Deprecated compatibility hook: never fabricate a face embedding.

    OpenCV Haar detection is not a face-recognition model. Returning a
    pixel-derived vector here would create a similarity score that looks like
    biometric evidence but has no identity-recognition meaning. Keep the photo
    available for human review and report the biometric backend as unavailable.
    """
    return {"status": "not_processed"}


# --- Pure math (no dependencies; unit-tested) --------------------------------

def _normalize(v: list) -> list:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))    # vectors are stored L2-normalised


def cosine_to_score(cos: float) -> float:
    """Map cosine similarity to 0-100, then floor it."""
    span = SAME_COS - DIFFERENT_COS
    raw = max(0.0, min(1.0, (cos - DIFFERENT_COS) / span)) * 100.0
    return max(SCORE_FLOOR, raw)


def compare(ante_records: list, post_records: list) -> Optional[FaceComparison]:
    """Best-pair comparison across all usable photos on each side."""
    a_recs = [r for r in ante_records if getattr(r, 'vector', None)]
    p_recs = [r for r in post_records if getattr(r, 'vector', None)]
    if not a_recs or not p_recs:
        return None

    best = None
    for a in a_recs:
        for p in p_recs:
            c = cosine(a.vector, p.vector)
            if best is None or c > best[0]:
                best = (c, a, p)
                
    if best is None:
        return None

    c, a, p = best
    quality = min(getattr(a, 'quality', 0.5), getattr(p, 'quality', 0.5))
    score = round(cosine_to_score(c), 1)
    weight = round(BASE_WEIGHT * quality, 4)
    notes = [f"best photo pair cosine {c:.2f} ({len(a_recs) * len(p_recs)} pair(s) compared)"]
    if quality < 0.5:
        notes.append(f"photo quality {quality:.2f} -- weight reduced")
    if getattr(a, 'face_count', 0) > 1 or getattr(p, 'face_count', 0) > 1:
        notes.append("a photo contained several faces; largest used")
    notes.append("supplementary lead only")
    
    return FaceComparison(
        score=score, weight=weight, detail="; ".join(notes), cosine=round(c, 3),
        quality=quality, ante_photo=getattr(a, 'photo_path', ''), post_photo=getattr(p, 'photo_path', ''),
        n_pairs=len(a_recs) * len(p_recs),
    )


# --- Ingestion + lookup (touch the database) ---------------------------------

def _to_record(row: dict) -> FaceRecord:
    return FaceRecord(
        owner_type=row["owner_type"], owner_id=row["owner_id"], photo_path=row["photo_path"],
        status=row["status"], vector=row.get("vector"), det_score=row.get("det_score") or 0.0,
        face_px=row.get("face_px") or 0.0, face_count=row.get("face_count") or 0,
        quality=row.get("quality") or 0.0,
    )


def ingest_bytes(owner_type: str, owner_id: str, data: bytes, filename: str) -> dict:
    """Save a photo, embed its face, and store the result."""
    if owner_type not in ("ante_mortem", "post_mortem"):
        raise ValueError("owner_type must be 'ante_mortem' or 'post_mortem'")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Unsupported image type '{ext}'. Allowed: {sorted(ALLOWED_EXT)}")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Image is larger than 15 MB")

    os.makedirs(PHOTO_DIR, exist_ok=True)
    dest = os.path.join(PHOTO_DIR, f"{owner_id}_{uuid.uuid4().hex[:8]}{ext}")
    with open(dest, "wb") as f:
        f.write(data)

    res = extract_face(dest)

    try:
        import database as db
        db.add_photo({
            "owner_type": owner_type, "owner_id": owner_id, "photo_path": dest,
            "status": res["status"], "model": MODEL_TAG if res.get("vector") else None,
            "vector": res.get("vector"), "det_score": res.get("det_score"),
            "face_px": res.get("face_px"), "face_count": res.get("face_count"),
            "quality": res.get("quality"),
        })
    except ImportError:
        pass

    return {"photo_path": dest, "status": res["status"], "message": STATUS_HELP.get(res["status"], "")}


def ingest_photo(owner_type: str, owner_id: str, image_path: str) -> dict:
    """Same as ingest_bytes but from a file on disk."""
    if not os.path.isfile(image_path):
        raise ValueError(f"No such file: {image_path}")
    with open(image_path, "rb") as f:
        return ingest_bytes(owner_type, owner_id, f.read(), os.path.basename(image_path))


def photos_for(owner_type: str, owner_id: str) -> list:
    try:
        import database as db
        return [_to_record(r) for r in db.list_photos(owner_type, owner_id)]
    except ImportError:
        return []


def build_lookup() -> Callable:
    """Return `lookup(ante, post) -> FaceComparison | None`."""
    try:
        import database as db
        by_owner: dict = {}
        for row in db.list_photos():
            by_owner.setdefault((row["owner_type"], row["owner_id"]), []).append(_to_record(row))

        def lookup(ante, post):
            return compare(by_owner.get(("ante_mortem", ante.id), []),
                           by_owner.get(("post_mortem", post.id), []))

        return lookup
    except ImportError:
        def empty_lookup(ante, post):
            return None
        return empty_lookup