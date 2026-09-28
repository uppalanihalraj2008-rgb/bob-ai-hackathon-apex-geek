"""Fingerprint comparison layer for the DVI coordination tool.

What it does
------------
1. Takes a fingerprint image (ante-mortem reference print, or a print taken
   from the recovered body), enhances it, extracts *minutiae* (ridge endings
   and bifurcations) and stores that compact template in SQLite (`fingerprint`
   table). Everything runs locally; no print leaves the machine.
2. Compares an ante-mortem profile's prints with a post-mortem case's prints
   using a minutiae matcher (Hough-transform alignment + tolerance-box
   pairing) and returns a `FingerprintComparison`.
   `matching_engine.score_pair` folds that in as one more component,
   "Fingerprint".

Where do ante-mortem prints come from?
--------------------------------------
Any *lawfully obtained* reference print: ten-print cards / thumb impressions
held by an authorised agency (police / fingerprint bureau / passport or
licence records), or latent prints lifted from the missing person's
belongings. The `source` label is stored with every print for the audit
trail. NOTE: UIDAI does not release Aadhaar fingerprints (Aadhaar Act s.29),
so there is deliberately no Aadhaar download code here, and Aadhaar numbers
are never stored by this module.

Design rules
------------
* Fingerprints are a PRIMARY identifier in DVI, so this component carries the
  largest weight (default 0.40) -- but it is scaled by print quality.
* NEVER an exclusion rule.
* Deterministic after ingestion.
"""
from __future__ import annotations

import math
import os
import uuid
from dataclasses import dataclass
from typing import Callable, Optional, List, Dict, Any

import numpy as np

HERE = os.path.dirname(__file__)
FP_DIR = os.environ.get("DVI_FINGERPRINT_DIR", os.path.join(HERE, "photos", "fingerprints"))

ALGO_TAG = "minutiae-hough-v1"

# --- Tunable knobs -----------------------------------------------------------
BASE_WEIGHT = float(os.environ.get("DVI_FP_WEIGHT", "0.40"))
SCORE_FLOOR = float(os.environ.get("DVI_FP_SCORE_FLOOR", "20"))
MIN_MATCHED = int(os.environ.get("DVI_FP_MIN_MATCHED", "6"))     # <= this many pairs => score 0
HIGH_MATCHED = int(os.environ.get("DVI_FP_HIGH_MATCHED", "14"))  # >= this many pairs => full count credit
RATIO_LOW = float(os.environ.get("DVI_FP_RATIO_LOW", "0.20"))    # matched / overlapping minutiae at/below this => 0 credit
RATIO_OK = float(os.environ.get("DVI_FP_RATIO_OK", "0.40"))      # ... at/above this => full credit
DIST_TOL = float(os.environ.get("DVI_FP_DIST_TOL", "12"))        # pixels (at normalised ridge spacing)
ANG_TOL = math.radians(float(os.environ.get("DVI_FP_ANG_TOL_DEG", "20")))

TARGET_PERIOD = 9.0        # ridge period (px) images are rescaled to (~500 dpi)
MIN_MINUTIAE_OK = 15       # fewer than this => status "low_quality"
MIN_MINUTIAE_KEEP = 6      # fewer than this => no usable template
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
FINGERS = ["right_thumb", "right_index", "right_middle", "right_ring", "right_little",
           "left_thumb", "left_index", "left_middle", "left_ring", "left_little", "unknown"]
SOURCES = ["authorised_record", "latent_from_belongings", "post_mortem_capture", "other"]

STATUS_HELP = {
    "ok": "Print processed; minutiae extracted.",
    "low_quality": "Print processed but few/poor minutiae -- it will carry little weight.",
    "too_few_minutiae": "Too few minutiae found (partial, smudged or wrong scale). Try a clearer image.",
    "unreadable": "The image file could not be decoded.",
    "not_processed": "Saved, but the fingerprint processing backend is unavailable; this print is not used for fingerprint matching.",
}


class FingerprintBackendUnavailable(RuntimeError):
    pass


# --- Data classes -----------------------------------------------------------

@dataclass
class FingerprintRecord:
    owner_type: str
    owner_id: str
    image_path: str
    finger: str
    source: str
    status: str
    template: Optional[dict] = None     # {"minutiae": [[x, y, theta, type], ...], "bbox": [x0, y0, x1, y1]}
    quality: float = 0.0
    n_minutiae: int = 0


@dataclass
class FingerprintComparison:
    score: float          # 0-100, floored
    weight: float         # 0-BASE_WEIGHT, scaled by quality
    detail: str
    matched: int
    quality: float
    ante_image: str
    post_image: str
    ante_finger: str
    post_finger: str
    n_pairs: int
    strong: bool


# =============================================================================
# 1. IMAGE -> MINUTIAE TEMPLATE
# =============================================================================

def _imports():
    try:
        import cv2
        from skimage.morphology import skeletonize
        return cv2, skeletonize
    except ImportError as e:
        raise FingerprintBackendUnavailable(str(e)) from e


def _estimate_period(gray: np.ndarray) -> float:
    """Dominant ridge period in pixels, from the radial FFT spectrum of the centre crop."""
    h, w = gray.shape
    n = min(h, w, 256)
    y0, x0 = (h - n) // 2, (w - n) // 2
    crop = gray[y0:y0 + n, x0:x0 + n].astype(np.float32)
    crop = crop - crop.mean()
    win = np.outer(np.hanning(n), np.hanning(n)).astype(np.float32)
    mag = np.abs(np.fft.fftshift(np.fft.fft2(crop * win)))
    yy, xx = np.indices(mag.shape)
    r = np.hypot(yy - n // 2, xx - n // 2).astype(int)
    radial = np.bincount(r.ravel(), mag.ravel()) / np.maximum(np.bincount(r.ravel()), 1)
    lo, hi = max(2, int(n / 30)), max(3, int(n / 3))
    if hi <= lo:
        return TARGET_PERIOD
    k = lo + int(np.argmax(radial[lo:hi]))
    return float(n) / max(k, 1)


def extract_template(image_path: str, invert: bool = False) -> dict:
    """Return {status, template, quality, n_minutiae}."""
    try:
        cv2, skeletonize = _imports()
        gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if gray is None or gray.size == 0:
            return {"status": "unreadable"}
        if invert:
            gray = 255 - gray

        period = _estimate_period(gray)
        scale = float(np.clip(TARGET_PERIOD / max(period, 1.0), 0.25, 4.0))
        if abs(scale - 1.0) > 0.05:
            gray = cv2.resize(gray, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        img = gray.astype(np.float32)
        img = (img - img.mean()) / (img.std() + 1e-6)
        h, w = img.shape

        blk = 16
        bh, bw = h // blk, w // blk
        if bh < 4 or bw < 4:
            return {"status": "too_few_minutiae"}
        sd = img[:bh * blk, :bw * blk].reshape(bh, blk, bw, blk).std(axis=(1, 3))
        sd8 = np.clip(sd / (sd.max() + 1e-6) * 255, 0, 255).astype(np.uint8)
        thr, _ = cv2.threshold(sd8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        bmask = (sd8 > max(thr * 0.8, 1)).astype(np.uint8)
        bmask = cv2.morphologyEx(bmask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        bmask = cv2.morphologyEx(bmask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = np.zeros((h, w), np.uint8)
        mask[:bh * blk, :bw * blk] = cv2.resize(bmask, (bw * blk, bh * blk), interpolation=cv2.INTER_NEAREST)
        if mask.sum() < 0.05 * h * w:
            return {"status": "too_few_minutiae"}

        sm = cv2.GaussianBlur(img, (0, 0), 1.0)
        gx, gy = cv2.Sobel(sm, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(sm, cv2.CV_32F, 0, 1, ksize=3)
        gxx = cv2.GaussianBlur(gx * gx, (0, 0), 7)
        gyy = cv2.GaussianBlur(gy * gy, (0, 0), 7)
        gxy = cv2.GaussianBlur(gx * gy, (0, 0), 7)
        theta = 0.5 * np.arctan2(2 * gxy, gxx - gyy) + math.pi / 2
        coh = np.sqrt((gxx - gyy) ** 2 + 4 * gxy ** 2) / (gxx + gyy + 1e-6)

        n_or = 16
        bank = []
        for k in range(n_or):
            t = k * math.pi / n_or + math.pi / 2
            kern = cv2.getGaborKernel((21, 21), 4.0, t, TARGET_PERIOD, 1.0, 0, ktype=cv2.CV_32F)
            bank.append(cv2.filter2D(img, cv2.CV_32F, kern))
        bank = np.stack(bank)
        idx = np.round((np.mod(theta, math.pi) / math.pi) * n_or).astype(int) % n_or
        enh = np.take_along_axis(bank, idx[None], axis=0)[0]

        ridges = ((enh < 0) & (mask > 0)).astype(np.uint8)
        ridges = cv2.morphologyEx(ridges, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        skel = skeletonize(ridges > 0).astype(np.uint8)
        skel = _prune_spurs(skel, 6)

        margin = 14
        inner = cv2.erode(mask, np.ones((2 * margin + 1, 2 * margin + 1), np.uint8)) > 0
        pts = _crossing_number_points(skel, inner)
        pts = _drop_clusters(pts, 8.0)
        minutiae = [[float(x), float(y), float(np.mod(theta[y, x], math.pi)), int(t)] for x, y, t in pts]

        ys, xs = np.nonzero(mask)
        bbox = [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())]
        fg_frac = float(mask.mean())
        coh_mean = float(coh[mask > 0].mean())
        n = len(minutiae)
        quality = round(0.4 * min(1.0, coh_mean / 0.6) + 0.4 * min(1.0, n / 35.0)
                        + 0.2 * min(1.0, fg_frac / 0.5), 3)

        if n < MIN_MINUTIAE_KEEP:
            return {"status": "too_few_minutiae", "quality": quality, "n_minutiae": n}
        status = "ok" if n >= MIN_MINUTIAE_OK and quality >= 0.35 else "low_quality"
        return {"status": status, "template": {"minutiae": minutiae, "bbox": bbox},
                "quality": quality, "n_minutiae": n}
    except FingerprintBackendUnavailable:
        return _fallback_extract_template(image_path)
    except Exception as e:
        print(f"Error during fingerprint extraction: {e}")
        return {"status": "unreadable"}


def _fallback_extract_template(image_path: str) -> dict:
    """Deprecated compatibility hook: never fabricate fingerprint minutiae.

    OpenCV corner detection is not fingerprint minutiae extraction. Treating
    generic image corners as ridge endings/bifurcations can create misleading
    biometric matches, so an unavailable minutiae backend now fails safely.
    """
    return {"status": "not_processed"}


def _neighbours(skel: np.ndarray) -> list:
    p = np.pad(skel, 1)
    h, w = skel.shape
    offs = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
    return [p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy, dx in offs]


def _prune_spurs(skel: np.ndarray, iterations: int) -> np.ndarray:
    s = skel.copy()
    for _ in range(iterations):
        nb = _neighbours(s)
        count = sum(n.astype(np.int16) for n in nb)
        s[(s == 1) & (count <= 1)] = 0
    return s


def _crossing_number_points(skel: np.ndarray, valid: np.ndarray) -> list:
    nb = [n.astype(np.int16) for n in _neighbours(skel)]
    cn = sum(np.abs(nb[i] - nb[(i + 1) % 8]) for i in range(8)) // 2
    ends = (skel == 1) & (cn == 1) & valid
    bifs = (skel == 1) & (cn == 3) & valid
    out = [(int(x), int(y), 1) for y, x in zip(*np.nonzero(ends))]
    out += [(int(x), int(y), 2) for y, x in zip(*np.nonzero(bifs))]
    return out


def _drop_clusters(pts: list, min_dist: float) -> list:
    if len(pts) < 2:
        return pts
    arr = np.array([[p[0], p[1]] for p in pts], dtype=np.float32)
    d = np.hypot(arr[:, None, 0] - arr[None, :, 0], arr[:, None, 1] - arr[None, :, 1])
    np.fill_diagonal(d, 1e9)
    keep = d.min(axis=1) >= min_dist
    return [p for p, k in zip(pts, keep) if k]


# =============================================================================
# 2. TEMPLATE MATCHING
# =============================================================================

def _rot(phi: float) -> np.ndarray:
    c, s = math.cos(phi), math.sin(phi)
    return np.array([[c, -s], [s, c]])


def _angdiff_pi(a, b):
    d = np.abs(np.mod(a - b, math.pi))
    return np.minimum(d, math.pi - d)


def _pair_up(A: np.ndarray, B: np.ndarray, R: np.ndarray, t: np.ndarray) -> list:
    pa = A[:, :2] @ R.T + t
    ta = np.mod(A[:, 2] + math.atan2(R[1, 0], R[0, 0]), math.pi)
    d = np.hypot(pa[:, None, 0] - B[None, :, 0], pa[:, None, 1] - B[None, :, 1])
    da = _angdiff_pi(ta[:, None], B[None, :, 2])
    ok = (d < DIST_TOL) & (da < ANG_TOL)
    cand = sorted(zip(*np.nonzero(ok)), key=lambda ij: d[ij])
    used_a, used_b, pairs = set(), set(), []
    for i, j in cand:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append((i, j))
    return pairs


def _refine(A: np.ndarray, B: np.ndarray, R: np.ndarray, t: np.ndarray, pairs: list):
    if len(pairs) < 3:
        return R, t
    pa = np.array([A[i, :2] @ R.T + t for i, _ in pairs])
    pb = np.array([B[j, :2] for _, j in pairs])
    ca, cb = pa.mean(axis=0), pb.mean(axis=0)
    qa, qb = pa - ca, pb - cb
    dphi = math.atan2(np.sum(qa[:, 0] * qb[:, 1] - qa[:, 1] * qb[:, 0]),
                      np.sum(qa[:, 0] * qb[:, 0] + qa[:, 1] * qb[:, 1]))
    R2 = _rot(dphi)
    return R2 @ R, R2 @ (t - ca) + cb


def _inside(pts: np.ndarray, bbox: list) -> int:
    x0, y0, x1, y1 = bbox
    return int(np.sum((pts[:, 0] >= x0) & (pts[:, 0] <= x1) & (pts[:, 1] >= y0) & (pts[:, 1] <= y1)))


def match_templates(ta: dict, tb: dict) -> dict:
    A = np.array(ta["minutiae"], dtype=np.float64).reshape(-1, 4)
    B = np.array(tb["minutiae"], dtype=np.float64).reshape(-1, 4)
    if len(A) < 3 or len(B) < 3:
        return {"matched": 0, "n_overlap_a": len(A), "n_overlap_b": len(B), "ratio": 0.0, "score": 0.0}

    dth = np.mod(B[None, :, 2] - A[:, None, 2], math.pi)
    votes = {}
    for extra in (0.0, math.pi):
        phi = dth + extra
        c, s = np.cos(phi), np.sin(phi)
        tx = B[None, :, 0] - (c * A[:, None, 0] - s * A[:, None, 1])
        ty = B[None, :, 1] - (s * A[:, None, 0] + c * A[:, None, 1])
        key = np.stack([np.round(phi / math.radians(10)).astype(int) % 36,
                        np.round(tx / 14).astype(int), np.round(ty / 14).astype(int)], axis=-1).reshape(-1, 3)
        for k, ph, x, y in zip(map(tuple, key), phi.ravel(), tx.ravel(), ty.ravel()):
            v = votes.setdefault(k, [0, 0.0, 0.0, 0.0, 0.0])
            v[0] += 1
            v[1] += math.cos(ph)
            v[2] += math.sin(ph)
            v[3] += x
            v[4] += y

    best = None
    for k, v in sorted(votes.items(), key=lambda kv: -kv[1][0])[:8]:
        n = v[0]
        R = _rot(math.atan2(v[2], v[1]))
        t = np.array([v[3] / n, v[4] / n])
        pairs = _pair_up(A, B, R, t)
        for _ in range(2):
            R, t = _refine(A, B, R, t, pairs)
            pairs = _pair_up(A, B, R, t)
        if best is None or len(pairs) > len(best[0]):
            best = (pairs, R, t)

    if not best:
        return {"matched": 0, "n_overlap_a": len(A), "n_overlap_b": len(B), "ratio": 0.0, "score": 0.0}

    pairs, R, t = best
    m = len(pairs)
    a_in_b = _inside(A[:, :2] @ R.T + t, tb.get("bbox", [0, 0, 100, 100]))
    b_in_a = _inside((B[:, :2] - t) @ R, ta.get("bbox", [0, 0, 100, 100]))
    min_ov = max(1, min(a_in_b, b_in_a))
    ratio = m / min_ov
    count_score = float(np.clip((m - MIN_MATCHED) / max(HIGH_MATCHED - MIN_MATCHED, 1), 0, 1))
    ratio_score = float(np.clip((ratio - RATIO_LOW) / max(RATIO_OK - RATIO_LOW, 1e-6), 0, 1))
    score = 100.0 * count_score * ratio_score
    return {"matched": m, "n_overlap_a": a_in_b, "n_overlap_b": b_in_a,
            "ratio": round(ratio, 3), "score": round(score, 1)}


def compare(ante_records: list, post_records: list) -> Optional[FingerprintComparison]:
    a_recs = [r for r in ante_records if getattr(r, 'template', None)]
    p_recs = [r for r in post_records if getattr(r, 'template', None)]
    best, n_pairs = None, 0
    for a in a_recs:
        for p in p_recs:
            if getattr(a, 'finger', 'unknown') != "unknown" and getattr(p, 'finger', 'unknown') != "unknown" and a.finger != p.finger:
                continue
            n_pairs += 1
            r = match_templates(a.template, p.template)
            key = (r["score"], r["matched"])
            if best is None or key > best[0]:
                best = (key, r, a, p)
    if best is None:
        return None
    _, r, a, p = best
    quality = round(min(getattr(a, 'quality', 0.5), getattr(p, 'quality', 0.5)), 3)
    score = round(max(SCORE_FLOOR, r["score"]), 1)
    weight = round(BASE_WEIGHT * quality, 4)
    strong = r["matched"] >= HIGH_MATCHED and r["score"] >= 80
    notes = [f"{r['matched']} minutiae paired (of {min(r['n_overlap_a'], r['n_overlap_b'])} overlapping), "
             f"finger {getattr(a, 'finger', 'unknown')}/{getattr(p, 'finger', 'unknown')}, {n_pairs} print pair(s) compared"]
    if quality < 0.5:
        notes.append(f"print quality {quality:.2f} -- weight reduced")
    if strong:
        notes.append("STRONG lead -- send both prints for examiner confirmation")
    else:
        notes.append("supplementary lead; never exclusionary")
    return FingerprintComparison(
        score=score, weight=weight, detail="; ".join(notes), matched=r["matched"], quality=quality,
        ante_image=getattr(a, 'image_path', ''), post_image=getattr(p, 'image_path', ''), 
        ante_finger=getattr(a, 'finger', 'unknown'), post_finger=getattr(p, 'finger', 'unknown'),
        n_pairs=n_pairs, strong=strong)


# =============================================================================
# 3. INGESTION + LOOKUP
# =============================================================================

def _to_record(row: dict) -> FingerprintRecord:
    return FingerprintRecord(
        owner_type=row["owner_type"], owner_id=row["owner_id"], image_path=row["image_path"],
        finger=row.get("finger") or "unknown", source=row.get("source") or "other",
        status=row["status"], template=row.get("template"),
        quality=row.get("quality") or 0.0, n_minutiae=row.get("n_minutiae") or 0)


def ingest_bytes(owner_type: str, owner_id: str, data: bytes, filename: str,
                 finger: str = "unknown", source: str = "other", invert: bool = False) -> dict:
    if owner_type not in ("ante_mortem", "post_mortem"):
        raise ValueError("owner_type must be 'ante_mortem' or 'post_mortem'")
    if finger not in FINGERS:
        raise ValueError(f"finger must be one of {FINGERS}")
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Unsupported image type '{ext}'. Allowed: {sorted(ALLOWED_EXT)}")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Image is larger than 15 MB")

    os.makedirs(FP_DIR, exist_ok=True)
    dest = os.path.join(FP_DIR, f"{owner_id}_{uuid.uuid4().hex[:8]}{ext}")
    with open(dest, "wb") as f:
        f.write(data)
    
    res = extract_template(dest, invert=invert)

    try:
        import database as db
        db.add_fingerprint({
            "owner_type": owner_type, "owner_id": owner_id, "image_path": dest, "finger": finger,
            "source": source, "status": res["status"], "algo": ALGO_TAG if res.get("template") else None,
            "template": res.get("template"), "quality": res.get("quality"),
            "n_minutiae": res.get("n_minutiae"),
        })
    except ImportError:
        pass

    return {"image_path": dest, "status": res["status"], "message": STATUS_HELP.get(res["status"], ""),
            "n_minutiae": res.get("n_minutiae", 0), "quality": res.get("quality", 0.0)}


def ingest_file(owner_type: str, owner_id: str, image_path: str,
                finger: str = "unknown", source: str = "other", invert: bool = False) -> dict:
    if not os.path.isfile(image_path):
        raise ValueError(f"No such file: {image_path}")
    with open(image_path, "rb") as f:
        return ingest_bytes(owner_type, owner_id, f.read(), os.path.basename(image_path),
                            finger=finger, source=source, invert=invert)


def prints_for(owner_type: str, owner_id: str) -> list:
    try:
        import database as db
        return [_to_record(r) for r in db.list_fingerprints(owner_type, owner_id)]
    except ImportError:
        return []


def build_lookup() -> Callable:
    try:
        import database as db
        by_owner: dict = {}
        for row in db.list_fingerprints():
            by_owner.setdefault((row["owner_type"], row["owner_id"]), []).append(_to_record(row))

        def lookup(ante, post):
            return compare(by_owner.get(("ante_mortem", ante.id), []),
                           by_owner.get(("post_mortem", post.id), []))

        return lookup
    except ImportError:
        def empty_lookup(ante, post):
            return None
        return empty_lookup