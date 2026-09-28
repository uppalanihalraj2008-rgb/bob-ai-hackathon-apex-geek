"""Builds the forensic reconciliation report.

Produces a Markdown report summarising, for every unidentified body
(post-mortem case) on file, the top-N candidate ante-mortem matches with
their scores and rationale. This is the artifact handed to a forensic
examiner as an investigative starting point -- it is explicitly NOT a
final identification. IBM Bob can be asked to re-narrate this report in
plainer language for non-technical stakeholders (family liaisons, incident
commanders), but the scores themselves come from matching_engine.py, not
from Bob.
"""
from __future__ import annotations

import datetime
from typing import List, Optional, Callable, Any

import matching_engine as me

DISCLAIMER = (
    "> **This report contains AI-assisted investigative leads only.**\n"
    "> No entry below constitutes a confirmed identification. Every "
    "candidate match must be confirmed by a qualified forensic examiner "
    "using accepted primary identifiers -- DNA comparison, dental "
    "radiograph comparison, or fingerprint analysis -- before any "
    "identification is finalized or a family is notified, per standard "
    "DVI protocol (e.g. INTERPOL DVI guidelines)."
)


FACE_NOTE = (
    "_Facial similarity (ArcFace embeddings, computed locally) is a low-weight, "
    "supplementary signal. Post-mortem faces are frequently altered by injury, "
    "immersion or decomposition; facial comparison is not an accepted primary "
    "identifier and never excludes a candidate. Review the photos side by side._"
)

FINGERPRINT_NOTE = (
    "_Fingerprint similarity (computed locally via feature/minutiae correlation) "
    "is an investigative lead. Official identification requires direct comparison "
    "by a certified latent print examiner._"
)


def _confidence_label(score: float) -> str:
    if score >= 75:
        return "High — prioritize for forensic confirmation"
    if score >= 50:
        return "Moderate — plausible lead, confirm before acting"
    if score >= 25:
        return "Low — weak lead, review only if no stronger candidates exist"
    return "Very low"


def generate_reconciliation_report(ante_profiles: list, post_observations: list, top_n: int = 3,
                                   face_lookup: Optional[Callable] = None,
                                   fingerprint_lookup: Optional[Callable] = None) -> str:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    lines = [
        "# DVI Reconciliation Report",
        f"_Generated {timestamp} UTC_",
        "",
        DISCLAIMER,
        "",
        f"Cases reviewed: **{len(post_observations)}** unidentified bodies against "
        f"**{len(ante_profiles)}** ante-mortem profiles on file.",
        "",
    ]

    face_used = False
    fp_used = False
    for post in post_observations:
        p_case = getattr(post, 'case_number', None) or getattr(post, 'id', 'Unknown')
        p_loc = getattr(post, 'location_found', 'unknown location')
        p_date = getattr(post, 'date_found', 'date unknown')
        p_sex = getattr(post, 'sex', 'unknown')
        p_age_min = getattr(post, 'age_min', '?')
        p_age_max = getattr(post, 'age_max', '?')

        lines.append(f"## Case {p_case}")
        lines.append(f"- Recovered: {p_loc}, {p_date}")
        lines.append(f"- Recorded sex: {p_sex}; estimated age: {p_age_min}-{p_age_max}")
        lines.append("")

        matches = me.top_matches(
            post, 
            ante_profiles, 
            top_n=top_n, 
            face_lookup=face_lookup, 
            fingerprint_lookup=fingerprint_lookup
        )
        
        for m in matches:
            for c in m.components:
                if c.name == "Facial similarity":
                    face_used = True
                if c.name == "Fingerprint similarity":
                    fp_used = True

        if not matches:
            lines.append(
                "_No viable candidates. Either every ante-mortem profile on file was "
                "excluded on biological grounds, or no profiles are logged yet. "
                "Recommend broadening the ante-mortem search or prioritizing DNA "
                "sampling for this case._"
            )
            lines.append("")
            continue

        for rank, m in enumerate(matches, start=1):
            ante = next((a for a in ante_profiles if a.id == m.ante_id), None)
            if not ante:
                continue
            
            a_name = getattr(ante, 'missing_person_name', None) or getattr(ante, 'id', 'Unknown')
            a_rep = getattr(ante, 'reporter_name', 'Anonymous')
            a_rel = getattr(ante, 'reporter_relationship', 'Relative/Contact')
            a_date = getattr(ante, 'last_seen_date', 'unknown date')
            a_loc = getattr(ante, 'last_seen_location', 'unknown location')

            lines.append(
                f"### #{rank} — {a_name} "
                f"(score: {m.score}/100 — {_confidence_label(m.score)})"
            )
            lines.append(
                f"- Reported missing by: {a_rep} ({a_rel}); "
                f"last seen {a_date} at {a_loc}"
            )
            lines.append("- Rationale:")
            for r in m.rationale:
                lines.append(f"  - {r}")
            lines.append("")

    if face_used:
        lines += [FACE_NOTE, ""]
    if fp_used:
        lines += [FINGERPRINT_NOTE, ""]

    lines += [
        "---",
        "_Report generated by Reconcile's matching engine (`src/matching_engine.py`) — "
        "deterministic, rule-based, and fully auditable. IBM Bob may be asked to narrate "
        "this report in plain language for non-technical readers, but the scores above "
        "are not LLM-generated._",
    ]
    return "\n".join(lines)