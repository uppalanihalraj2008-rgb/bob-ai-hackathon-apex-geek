"""
Streamlit UI for the DVI coordination tool  --  "Forensic Precision & Human Empathy" redesign.

Same backend as before: every call goes to the same `matching_engine.py` /
`database.py` / `report_generator.py` / `face_matching.py` / `fingerprint_matching.py`
modules the MCP server uses. Only the presentation changed (see `ui_theme.py`).

Run with:
    streamlit run demo_app.py
"""
try:
    import streamlit as st  # type: ignore[import-not-found]
except ImportError as exc:
    raise RuntimeError(
        "Streamlit is required to run this demo. Install it with 'pip install streamlit'."
    ) from exc

import database as db
import document_parser as dp
import face_matching as fm
import fingerprint_matching as fpm
import matching_engine as me
import report_generator as rg
import ui_theme as ui
from models import AnteMortemProfile, PostMortemObservation

st.set_page_config(page_title="Reconcile — DVI Coordination", page_icon="🔎", layout="wide")
db.init_db()
ui.inject_theme()

PHOTO_TYPES = ["jpg", "jpeg", "png", "webp", "bmp"]
FINGERPRINT_TYPES = ["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"]
DOC_TYPES = ["pdf", "docx", "txt"]

PAGES = ["Overview", "Ante-Mortem Intake", "Post-Mortem Intake", "Match Center", "Reports"]
if "nav" not in st.session_state:
    st.session_state["nav"] = PAGES[0]


def _go(page: str):
    st.session_state["nav"] = page


# =============================================================================
# Shared helpers (unchanged behaviour)
# =============================================================================
def _ingest_uploads(owner_type, owner_id, photos, fingerprints, fp_finger="unknown", fp_source="other"):
    """Save uploaded photos and fingerprints, extracting biometric features locally."""
    for f in photos or []:
        try:
            res = fm.ingest_bytes(owner_type, owner_id, f.getvalue(), f.name)
            (st.success if res["status"] == "ok" else st.warning)(f"Photo {f.name}: {res['message']}")
        except ValueError as e:
            st.warning(f"Photo {f.name}: {e}")

    for f in fingerprints or []:
        try:
            res = fpm.ingest_bytes(
                owner_type, owner_id, f.getvalue(), f.name, finger=fp_finger, source=fp_source
            )
            (st.success if res["status"] == "ok" else st.warning)(
                f"Fingerprint {f.name}: {res['message']} ({res.get('n_minutiae', 0)} minutiae)"
            )
        except ValueError as e:
            st.warning(f"Fingerprint {f.name}: {e}")


def _marks_editor(key_prefix: str):
    n = st.number_input("Number of distinguishing marks", 0, 10, 0, key=f"{key_prefix}_n")
    marks = []
    for i in range(int(n)):
        c1, c2, c3 = st.columns(3)
        t = c1.selectbox(
            "Type", ["scar", "tattoo", "birthmark", "deformity", "piercing", "fracture", "other"],
            key=f"{key_prefix}_t{i}",
        )
        loc = c2.text_input("Location", key=f"{key_prefix}_l{i}", placeholder="e.g. left forearm")
        desc = c3.text_input("Description", key=f"{key_prefix}_d{i}", placeholder="e.g. 3cm curved scar")
        marks.append({"type": t, "location": loc, "description": desc})
    return marks


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _modalities(post) -> list:
    """Evidence types actually recorded for a post-mortem case (no invented data)."""
    mods = []
    if (post.dental_findings or "").strip():
        mods.append("Dental")
    for t in sorted({m.type.title() for m in post.marks}):
        mods.append(t)
    if post.clothing:
        mods.append("Effects")
    if any(p["status"] == "ok" for p in _safe(lambda: db.list_photos("post_mortem", post.id), [])):
        mods.append("Face")
    if any(p["status"] == "ok" for p in _safe(lambda: db.list_fingerprints("post_mortem", post.id), [])):
        mods.append("Fingerprint")
    return mods


def _case_leads(posts, antes):
    """Top-1 candidate per case using the real engine + stored biometrics."""
    face_lookup, fp_lookup = fm.build_lookup(), fpm.build_lookup()
    out = []
    for p in posts:
        top = me.top_matches(p, antes, top_n=1, face_lookup=face_lookup, fingerprint_lookup=fp_lookup)
        lead = top[0] if top else None
        a = db.get_ante(lead.ante_id) if lead else None
        out.append({
            "case": p.case_number or p.id, "site": p.location_found, "found": p.date_found,
            "modalities": _modalities(p),
            "lead": (a.missing_person_name or "(name unknown)") if a else "",
            "lead_id": a.id if a else "", "score": lead.score if lead else None,
        })
    return out


# =============================================================================
# Sidebar
# =============================================================================
with st.sidebar:
    ui.sidebar_brand()
    st.radio("Navigate", PAGES, key="nav", label_visibility="collapsed")
    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    import importlib.util as _iu
    _face_ok = _iu.find_spec("insightface") is not None
    _fp_ok = _iu.find_spec("cv2") is not None
    ui.sidebar_status([
        ("SQLite DB", "connected", True),
        ("Match engine", "deterministic", True),
        ("Face matching", "insightface" if _face_ok else "not installed", _face_ok),
        ("Fingerprint", "opencv" if _fp_ok else "fallback", _fp_ok),
    ])

page = st.session_state["nav"]


# =============================================================================
# PAGE: Overview
# =============================================================================
def page_overview():
    posts, antes = db.list_post_mortem(), db.list_ante_mortem()
    ui.page_header(
        "Active incident · DVI coordination",
        "Reconcile — Overview",
        "Ante-mortem family reports and post-mortem recoveries, reconciled into ranked, explainable investigative leads.",
    )
    ui.legal_notice()

    c1, c2, c3, _ = st.columns([1, 1, 1, 3])
    c1.button("New AM intake", on_click=_go, args=("Ante-Mortem Intake",), use_container_width=True)
    c2.button("New PM case", on_click=_go, args=("Post-Mortem Intake",), use_container_width=True)
    c3.button("Open Match Center", on_click=_go, args=("Match Center",), type="primary", use_container_width=True)

    leads = _case_leads(posts, antes) if posts and antes else []
    with_lead = sum(1 for l in leads if l["score"] is not None)
    strong = sum(1 for l in leads if l["score"] is not None and l["score"] >= 75)
    n_photos = len([p for p in _safe(db.list_photos, []) if p["status"] == "ok"])
    n_prints = len([p for p in _safe(db.list_fingerprints, []) if p["status"] == "ok"])

    ui.stat_cards([
        ("Post-mortem cases", len(posts), f"{with_lead} with a viable lead", (with_lead / len(posts) * 100) if posts else 0, "blue"),
        ("Ante-mortem profiles", len(antes), "family-reported", 100 if antes else 0, "green"),
        ("Biometrics on file", n_photos + n_prints, f"{n_photos} face · {n_prints} fingerprint", None, "blue"),
        ("High-priority leads", strong, "score ≥ 75 · needs forensic confirmation", (strong / len(posts) * 100) if posts else 0, "amber"),
    ])

    if not posts:
        st.info("No post-mortem cases yet. Log one, or run `python seed_demo_data.py` for sample data.")
    elif not antes:
        st.info("No ante-mortem profiles yet.")
    else:
        ui.worklist_table(leads)

    # ---- Demographics charts ------------------------------------------------
    if antes or posts:
        import pandas as _pd
        from collections import Counter as _Ctr

        st.markdown("### Population demographics")
        col1, col2, col3 = st.columns(3)

        # --- Sex distribution ---
        with col1:
            with st.container(border=True):
                st.markdown("**Sex distribution**")
                am_sex = _Ctr(a.sex or "unknown" for a in antes)
                pm_sex = _Ctr(p.sex or "unknown" for p in posts)
                all_sex = sorted(set(am_sex) | set(pm_sex))
                sex_df = _pd.DataFrame(
                    {"Ante-mortem": [am_sex.get(s, 0) for s in all_sex],
                     "Post-mortem": [pm_sex.get(s, 0) for s in all_sex]},
                    index=all_sex,
                )
                st.bar_chart(sex_df, stack=False)

        # --- Age bracket distribution ---
        with col2:
            with st.container(border=True):
                st.markdown("**Age brackets (mid-point estimate)**")

                def _age_bracket(lo, hi):
                    mid = ((lo or 0) + (hi or 0)) / 2
                    if mid < 18: return "<18"
                    if mid < 30: return "18-29"
                    if mid < 45: return "30-44"
                    if mid < 60: return "45-59"
                    return "60+"

                brackets = ["<18", "18-29", "30-44", "45-59", "60+"]
                am_age = _Ctr(_age_bracket(a.age_min, a.age_max) for a in antes)
                pm_age = _Ctr(_age_bracket(p.age_min, p.age_max) for p in posts)
                age_df = _pd.DataFrame(
                    {"Ante-mortem": [am_age.get(b, 0) for b in brackets],
                     "Post-mortem": [pm_age.get(b, 0) for b in brackets]},
                    index=brackets,
                )
                st.bar_chart(age_df, stack=False)

        # --- Blood type distribution ---
        with col3:
            with st.container(border=True):
                st.markdown("**Blood type distribution**")
                am_bt = _Ctr((a.blood_type or "unknown").strip() for a in antes)
                pm_bt = _Ctr((p.blood_type or "unknown").strip() for p in posts)
                all_bt = sorted(set(am_bt) | set(pm_bt))
                bt_df = _pd.DataFrame(
                    {"Ante-mortem": [am_bt.get(b, 0) for b in all_bt],
                     "Post-mortem": [pm_bt.get(b, 0) for b in all_bt]},
                    index=all_bt,
                )
                st.bar_chart(bt_df, stack=False)
    # -------------------------------------------------------------------------

    import datetime as _dt
    audit = _safe(lambda: db.list_match_audit(8), [])
    if audit:
        rows = ""
        for a in audit:
            ts = _dt.datetime.fromtimestamp(a["generated_at"] or 0).strftime("%Y-%m-%d %H:%M")
            tag = ui.chip("Excluded", "red") if a["excluded"] else ui.chip(f'{a["score"]:.1f}', ui.tone_for_score(a["score"]))
            rows += (f'<div class="rc-mono" style="padding:.25rem 0">{ui._e(ts)} &nbsp;'
                     f'{ui._e(a["post_id"])} &rarr; {ui._e(a["ante_id"])} &nbsp;{tag}</div>')
    else:
        rows = ('<div class="rc-muted" style="font-size:.85rem">No audit entries yet. Entries are written when '
                'matches are run through Bob (MCP <code>compute_top_matches</code>).</div>')
    ui.card("Match audit log", "every score computed, including exclusions", rows)


# =============================================================================
# PAGE: Ante-Mortem Intake
# =============================================================================
def page_am():
    ui.page_header("Intake · family-reported", "Ante-Mortem Profile",
                   "Log a missing person's description, dental notes, marks, and biometrics.")

    with st.expander("📄 AI autofill — upload profile document (PDF / Word / TXT)", expanded=True):
        doc_file_am = st.file_uploader(
            "Upload official report, missing person flyer, or family statement",
            type=DOC_TYPES, key="am_doc_upload",
        )
        if doc_file_am:
            raw_text_am = dp.extract_text_from_file(doc_file_am.getvalue(), doc_file_am.name)
            st.text_area("Extracted document text preview", raw_text_am, height=120, key="am_doc_preview")
            st.info("💡 Ask Bob AI in your chat/editor: *'Extract all fields from the uploaded text and fill the ante-mortem profile.'*")

    with st.form("am_form"):
        c1, c2 = st.columns(2)
        reporter_name = c1.text_input("Reporter name *")
        reporter_relationship = c2.text_input("Relationship to missing person *")
        reporter_contact = st.text_input("Reporter contact")
        missing_person_name = st.text_input("Missing person's name (if known)")

        c1, c2, c3 = st.columns(3)
        sex = c1.selectbox("Sex", ["unknown", "male", "female"])
        age_min = c2.number_input("Age — min estimate", 0, 120, 20)
        age_max = c3.number_input("Age — max estimate", 0, 120, 30)

        c1, c2 = st.columns(2)
        height_min = c1.number_input("Height cm — min", 0.0, 250.0, 160.0)
        height_max = c2.number_input("Height cm — max", 0.0, 250.0, 170.0)

        c1, c2, c3, c4 = st.columns(4)
        build = c1.text_input("Build", placeholder="e.g. slim")
        hair_color = c2.text_input("Hair color")
        hair_length = c3.text_input("Hair length")
        eye_color = c4.text_input("Eye color")

        blood_type = st.selectbox("Blood type", ["unknown", "O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"])
        physical_description = st.text_area("Physical description (scars, birthmarks, general observations)")
        clothing_raw = st.text_area("Clothing / personal effects last seen (one per line)")
        dental_notes = st.text_area("Dental notes (from family / dentist records)")

        marks = _marks_editor("am")

        c1, c2 = st.columns(2)
        last_seen_location = c1.text_input("Last seen location")
        last_seen_date = c2.text_input("Last seen date")
        other_notes = st.text_area("Other notes")

        st.markdown("### Biometric attachments")
        c1, c2 = st.columns(2)
        am_photos = c1.file_uploader("Face photo(s)", type=PHOTO_TYPES, accept_multiple_files=True, key="am_photos")
        am_fingerprints = c2.file_uploader("Fingerprint image(s)", type=FINGERPRINT_TYPES, accept_multiple_files=True, key="am_fps")
        c3, c4 = st.columns(2)
        fp_finger = c3.selectbox("Finger designation", fpm.FINGERS, key="am_fp_finger")
        fp_source = c4.selectbox("Fingerprint source", fpm.SOURCES, key="am_fp_source")

        if st.form_submit_button("Log profile", type="primary"):
            if not reporter_name:
                st.error("Reporter name is required.")
            else:
                profile = AnteMortemProfile.new(
                    reporter_name=reporter_name, reporter_relationship=reporter_relationship,
                    reporter_contact=reporter_contact, missing_person_name=missing_person_name,
                    sex=sex, age_min=int(age_min), age_max=int(age_max),
                    height_cm_min=float(height_min), height_cm_max=float(height_max),
                    build=build, hair_color=hair_color, hair_length=hair_length, eye_color=eye_color,
                    marks=marks, clothing=[c.strip() for c in clothing_raw.splitlines() if c.strip()],
                    dental_notes=dental_notes, blood_type=blood_type,
                    last_seen_location=last_seen_location, last_seen_date=last_seen_date,
                    physical_description=physical_description, other_notes=other_notes,
                )
                db.add_ante_mortem(profile)
                for alert in dp.validate_extracted_fields(profile.to_dict(), record_type="ante_mortem"):
                    st.info(alert)
                st.success(f"Logged ante-mortem profile {profile.id}")
                _ingest_uploads("ante_mortem", profile.id, am_photos, am_fingerprints, fp_finger, fp_source)

    items = "".join(
        f'<div style="padding:.3rem 0"><span class="rc-mono" style="color:var(--blue-hi)">{ui._e(a.id)}</span> &nbsp;'
        f'{ui._e(a.missing_person_name or "(name unknown)")} '
        f'<span class="rc-muted">— reported by {ui._e(a.reporter_name)}</span></div>'
        for a in db.list_ante_mortem()
    ) or '<span class="rc-muted">No profiles yet.</span>'
    ui.card("Profiles on file", f"{len(db.list_ante_mortem())} records", items)


# =============================================================================
# PAGE: Post-Mortem Intake
# =============================================================================
def page_pm():
    ui.page_header("Intake · forensic recovery", "Post-Mortem Case",
                   "Log observations recorded for an unidentified body or remains.")

    with st.expander("📄 AI autofill — upload case file / autopsy report (PDF / Word / TXT)", expanded=True):
        doc_file_pm = st.file_uploader(
            "Upload forensic report or scene recovery notes", type=DOC_TYPES, key="pm_doc_upload",
        )
        if doc_file_pm:
            raw_text_pm = dp.extract_text_from_file(doc_file_pm.getvalue(), doc_file_pm.name)
            st.text_area("Extracted document text preview", raw_text_pm, height=120, key="pm_doc_preview")
            st.info("💡 Ask Bob AI in your chat/editor: *'Extract all fields from the uploaded forensic report and fill the post-mortem case.'*")

    with st.form("pm_form"):
        case_number = st.text_input("Case number *")
        c1, c2 = st.columns(2)
        location_found = c1.text_input("Location found")
        date_found = c2.text_input("Date found")

        c1, c2, c3 = st.columns(3)
        sex = c1.selectbox("Sex", ["unknown", "male", "female"], key="pm_sex")
        age_min = c2.number_input("Estimated age — min", 0, 120, 20, key="pm_amin")
        age_max = c3.number_input("Estimated age — max", 0, 120, 30, key="pm_amax")

        c1, c2 = st.columns(2)
        height_min = c1.number_input("Height cm — min", 0.0, 250.0, 160.0, key="pm_hmin")
        height_max = c2.number_input("Height cm — max", 0.0, 250.0, 170.0, key="pm_hmax")

        c1, c2, c3, c4 = st.columns(4)
        build = c1.text_input("Build", key="pm_build")
        hair_color = c2.text_input("Hair color", key="pm_hair")
        hair_length = c3.text_input("Hair length", key="pm_hairlen")
        eye_color = c4.text_input("Eye color", key="pm_eye")

        blood_type = st.selectbox(
            "Blood type", ["unknown", "O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"], key="pm_bt"
        )
        physical_description = st.text_area("Physical description (scars, birthmarks, general observations)", key="pm_phys")
        clothing_raw = st.text_area("Clothing / personal effects found (one per line)", key="pm_cloth")
        dental_findings = st.text_area("Dental findings", key="pm_dental")

        marks = _marks_editor("pm")
        other_findings = st.text_area("Other findings", key="pm_other")

        st.markdown("### Biometric attachments")
        c1, c2 = st.columns(2)
        pm_photos = c1.file_uploader("Post-mortem face photo(s)", type=PHOTO_TYPES, accept_multiple_files=True, key="pm_photos")
        pm_fingerprints = c2.file_uploader("Post-mortem fingerprint image(s)", type=FINGERPRINT_TYPES, accept_multiple_files=True, key="pm_fps")
        c3, c4 = st.columns(2)
        fp_finger_pm = c3.selectbox("Finger designation", fpm.FINGERS, key="pm_fp_finger")
        fp_source_pm = c4.selectbox("Fingerprint source", fpm.SOURCES, key="pm_fp_source")

        if st.form_submit_button("Log case", type="primary"):
            if not case_number:
                st.error("Case number is required.")
            else:
                obs = PostMortemObservation.new(
                    case_number=case_number, location_found=location_found, date_found=date_found,
                    sex=sex, age_min=int(age_min), age_max=int(age_max),
                    height_cm_min=float(height_min), height_cm_max=float(height_max),
                    build=build, hair_color=hair_color, hair_length=hair_length, eye_color=eye_color,
                    marks=marks, clothing=[c.strip() for c in clothing_raw.splitlines() if c.strip()],
                    dental_findings=dental_findings, blood_type=blood_type,
                    physical_description=physical_description, other_findings=other_findings,
                )
                db.add_post_mortem(obs)
                for alert in dp.validate_extracted_fields(obs.to_dict(), record_type="post_mortem"):
                    st.info(alert)
                st.success(f"Logged case {obs.id}")
                _ingest_uploads("post_mortem", obs.id, pm_photos, pm_fingerprints, fp_finger_pm, fp_source_pm)

    items = "".join(
        f'<div style="padding:.3rem 0"><span class="rc-mono" style="color:var(--blue-hi)">{ui._e(p.id)}</span> &nbsp;'
        f'case {ui._e(p.case_number)} <span class="rc-muted">— found {ui._e(p.location_found)}</span></div>'
        for p in db.list_post_mortem()
    ) or '<span class="rc-muted">No cases yet.</span>'
    ui.card("Cases on file", f"{len(db.list_post_mortem())} records", items)


# =============================================================================
# PAGE: Match Center
# =============================================================================
def page_match():
    ui.page_header("Analysis · prioritization & review", "Match Center",
                   "Ranked investigative leads with explainable, component-by-component rationale.")
    ui.legal_notice()

    posts, antes = db.list_post_mortem(), db.list_ante_mortem()
    if not posts:
        st.info("No post-mortem cases logged yet. Use 'Post-Mortem Intake', or run `python seed_demo_data.py` for sample data.")
        return
    if not antes:
        st.info("No ante-mortem profiles logged yet.")
        return

    options = {f"{p.case_number} ({p.id})": p.id for p in posts}
    choice = st.selectbox("Active reference post-mortem case", list(options.keys()))
    post = db.get_post(options[choice])

    face_lookup, fingerprint_lookup = fm.build_lookup(), fpm.build_lookup()
    matches = me.top_matches(post, antes, top_n=3, face_lookup=face_lookup, fingerprint_lookup=fingerprint_lookup)

    ui.html(
        f'<div class="rc-stat-f" style="margin:.25rem 0 1rem">Recovered: {ui._e(post.location_found or "unknown")}, '
        f'{ui._e(post.date_found or "date unknown")} &nbsp;·&nbsp; Sex: {ui._e(post.sex)} &nbsp;·&nbsp; '
        f'Est. age {ui._e(str(post.age_min))}–{ui._e(str(post.age_max))} &nbsp;·&nbsp; '
        f'Evidence: {ui._e(", ".join(_modalities(post)) or "none recorded")}</div>'
    )

    if not matches:
        st.warning("No viable candidates — every profile on file was excluded on biological grounds.")
    else:
        st.markdown("### Investigative prioritization matrix")
        for rank, m in enumerate(matches, start=1):
            ante = db.get_ante(m.ante_id)
            sub = (f"Reported by {ante.reporter_name} ({ante.reporter_relationship}) · last seen "
                   f"{ante.last_seen_date or 'unknown'} at {ante.last_seen_location or 'unknown'}")
            ui.candidate_card(rank, ante.missing_person_name or "(name unknown)", ante.id, m.score, sub,
                              m.rationale, m.components, primary=(rank == 1))
            if rank > 1:
                with st.expander(f"Scoring breakdown — #{rank} {ante.missing_person_name or ante.id}"):
                    for r in m.rationale:
                        st.write(f"- {r}")

        # ---------------- Dual-dossier concordance ----------------
        st.markdown("### Dual-dossier concordance inspection")
        labels = {f"#{i} — {db.get_ante(m.ante_id).missing_person_name or m.ante_id} ({m.score})": i - 1
                  for i, m in enumerate(matches, start=1)}
        pick = st.selectbox("Inspect candidate", list(labels.keys()))
        m = matches[labels[pick]]
        ante = db.get_ante(m.ante_id)
        ui.concordance_table(ante.id, post.case_number or post.id, ui.build_concordance(ante, post, m))
        st.caption("Field status is a presentation aid derived from the recorded values; "
                   "the score itself comes only from the deterministic engine.")

        # ---------------- Biometric evidence ----------------
        st.markdown("### Corroborative imagery & friction-ridge bay")
        show_pm_photo = st.checkbox("Show post-mortem photos/prints (may be distressing)", value=False)
        face = face_lookup(ante, post)
        fp = fingerprint_lookup(ante, post)
        if not face and not fp:
            st.info("No usable face photos or fingerprints on both sides for this candidate.")
        if face:
            with st.container(border=True):
                st.markdown("#### Facial biometric match")
                c1, c2 = st.columns(2)
                c1.image(face.ante_photo, caption="Family-provided photo", use_container_width=True)
                if show_pm_photo:
                    c2.image(face.post_photo, caption="Post-mortem photo", use_container_width=True)
                else:
                    c2.info("Post-mortem photo hidden (victim-privacy protocol).")
                st.caption(f"Face similarity {face.score:.0f}/100 (cosine {face.cosine}, quality {face.quality:.2f})")
        if fp:
            with st.container(border=True):
                st.markdown("#### Fingerprint biometric match")
                c1, c2 = st.columns(2)
                c1.image(fp.ante_image, caption=f"Ante-mortem print ({fp.ante_finger})", use_container_width=True)
                if show_pm_photo:
                    c2.image(fp.post_image, caption=f"Post-mortem print ({fp.post_finger})", use_container_width=True)
                else:
                    c2.info("Post-mortem fingerprint hidden (victim-privacy protocol).")
                st.caption(f"Fingerprint match {fp.score:.0f}/100 ({fp.matched} minutiae paired, quality {fp.quality:.2f})")

    # ---------------- Biological exclusions registry ----------------
    excluded = [(a, r) for a in antes for r in [me.score_pair(a, post)] if r.excluded]
    with st.expander(f"Biological exclusions registry ({len(excluded)} excluded)", expanded=False):
        if not excluded:
            st.caption("No candidates were excluded for this case.")
        for a, r in excluded:
            ui.exclusion_row(a.missing_person_name or "(name unknown)", a.id, r.exclusion_reason or "excluded")


# =============================================================================
# PAGE: Reports
# =============================================================================
def page_reports():
    ui.page_header("Output · for the forensic examiner", "Reconciliation Report",
                   "A single report across every open case, ready to hand to a forensic examiner.")
    ui.legal_notice()
    if st.button("Generate report", type="primary"):
        st.session_state["report_md"] = rg.generate_reconciliation_report(
            db.list_ante_mortem(), db.list_post_mortem(),
            face_lookup=fm.build_lookup(), fingerprint_lookup=fpm.build_lookup(),
        )
    if "report_md" in st.session_state:
        with st.container(border=True):
            st.markdown(st.session_state["report_md"])
        st.download_button("Download as Markdown", st.session_state["report_md"],
                           file_name="reconciliation_report.md")


{
    "Overview": page_overview,
    "Ante-Mortem Intake": page_am,
    "Post-Mortem Intake": page_pm,
    "Match Center": page_match,
    "Reports": page_reports,
}[page]()