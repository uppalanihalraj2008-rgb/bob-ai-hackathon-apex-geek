"""
ui_theme.py
-----------
Visual layer for the Streamlit dashboard: the "Forensic Precision & Human
Empathy" design system (dark slate tiers, cobalt / emerald / amber / crimson
semantics, Space Grotesk + Inter + JetBrains Mono).

Nothing in here touches the matching engine or the database. It only turns
data the app already has into styled HTML. Every piece of user-entered text
is passed through `html.escape` before being placed in markup.
"""
from __future__ import annotations

from html import escape as _e

import streamlit as st

# ---------------------------------------------------------------------------
# Design tokens (from DESIGN.md)
# ---------------------------------------------------------------------------
C = {
    "ground": "#0f131a", "base": "#131720", "l1": "#181d28", "l2": "#1e2433", "l3": "#252c3d",
    "border": "#2d3548", "border_hi": "#333d52",
    "text": "#f1f5f9", "text2": "#94a3b8", "text3": "#64748b",
    "blue": "#3b82f6", "blue_hi": "#60a5fa",
    "green": "#10b981", "green_hi": "#34d399",
    "amber": "#f59e0b", "amber_hi": "#fbbf24",
    "red": "#f43f5e", "red_hi": "#fb7185",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap');

:root{
  --ground:#0f131a; --base:#131720; --l1:#181d28; --l2:#1e2433; --l3:#252c3d;
  --border:#2d3548; --border-hi:#333d52;
  --t1:#f1f5f9; --t2:#94a3b8; --t3:#64748b;
  --blue:#3b82f6; --blue-hi:#60a5fa; --green:#10b981; --green-hi:#34d399;
  --amber:#f59e0b; --amber-hi:#fbbf24; --red:#f43f5e; --red-hi:#fb7185;
  --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
  --head:'Space Grotesk','Inter',system-ui,sans-serif;
  --body:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;
}

/* ---- app frame ---- */
.stApp{background:var(--ground);color:var(--t1);font-family:var(--body);}
[data-testid="stHeader"]{background:transparent;}
.block-container{padding-top:1.5rem;padding-bottom:4rem;max-width:1280px;}
h1,h2,h3,h4{font-family:var(--head)!important;color:var(--t1)!important;letter-spacing:-0.01em;}
h3{font-size:1.05rem!important;font-weight:500!important;}
p,li,label,span{font-family:var(--body);}
code{font-family:var(--mono)!important;color:var(--blue-hi)!important;background:var(--l2)!important;
  border:1px solid var(--border);border-radius:4px;padding:1px 5px;font-size:.8em;}
hr{border-color:var(--border)!important;}
[data-testid="stCaptionContainer"],.stCaption{color:var(--t2)!important;}

/* ---- sidebar ---- */
[data-testid="stSidebar"]{background:var(--base);border-right:1px solid var(--border);}
[data-testid="stSidebar"] .block-container{padding-top:1rem;}
[data-testid="stSidebar"] [role="radiogroup"]{gap:2px;}
[data-testid="stSidebar"] [role="radiogroup"] label{
  width:100%;padding:.55rem .75rem;border-radius:4px;border:1px solid transparent;
  cursor:pointer;transition:background .15s,border-color .15s;}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{background:var(--l2);}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){
  background:var(--l2);border-color:var(--border-hi);box-shadow:inset 2px 0 0 var(--blue);}
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child{display:none;} /* hide radio dot */
[data-testid="stSidebar"] [role="radiogroup"] label p{font-size:.9rem;color:var(--t2);}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p{color:var(--t1);font-weight:500;}

.rc-brand{display:flex;gap:.7rem;align-items:center;padding:.25rem .25rem 1rem;}
.rc-logo{width:34px;height:34px;border:1px solid var(--blue);border-radius:6px;display:grid;place-items:center;
  color:var(--blue-hi);font-family:var(--mono);font-weight:600;background:rgba(59,130,246,.1);}
.rc-brand-t{font-family:var(--head);font-weight:700;font-size:1.05rem;letter-spacing:.04em;line-height:1.1;}
.rc-brand-s{font-family:var(--mono);font-size:10px;color:var(--t3);letter-spacing:.04em;}
.rc-proto{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--amber-hi);
  border:1px solid rgba(245,158,11,.25);background:rgba(245,158,11,.08);border-radius:4px;padding:.35rem .5rem;margin-bottom:1rem;}
.rc-sys{font-family:var(--mono);font-size:11px;color:var(--t2);display:grid;gap:.3rem;margin-top:.5rem;}
.rc-sys div{display:flex;justify-content:space-between;}
.rc-dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px;background:var(--green);}
.rc-dot.off{background:var(--amber);}

/* ---- cards ---- */
.rc-card{background:var(--l1);border:1px solid var(--border);border-radius:8px;margin-bottom:1rem;overflow:hidden;}
.rc-card-h{padding:.8rem 1rem;border-bottom:1px solid var(--l3);display:flex;justify-content:space-between;
  align-items:center;gap:1rem;flex-wrap:wrap;}
.rc-card-t{font-family:var(--head);font-weight:500;font-size:1.02rem;}
.rc-card-s{font-family:var(--mono);font-size:11px;color:var(--t3);}
.rc-card-b{padding:1rem;}
.rc-eyebrow{font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--t3);}
.rc-hero{background:linear-gradient(180deg,var(--l1),var(--base));border:1px solid var(--border);border-radius:8px;
  padding:1.25rem 1.5rem;margin-bottom:1rem;}
.rc-hero h1{font-size:1.75rem!important;margin:.35rem 0 .3rem!important;padding:0!important;}
.rc-hero p{color:var(--t2);margin:0;font-size:.9rem;}

/* ---- notices ---- */
.rc-notice{display:flex;gap:.75rem;align-items:flex-start;border-radius:8px;padding:.8rem 1rem;margin-bottom:1rem;
  border:1px solid rgba(245,158,11,.3);background:rgba(245,158,11,.07);font-size:.86rem;color:var(--t1);}
.rc-notice b{color:var(--amber-hi);font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;display:block;margin-bottom:2px;}
.rc-notice.blue{border-color:rgba(59,130,246,.3);background:rgba(59,130,246,.07);}
.rc-notice.blue b{color:var(--blue-hi);}

/* ---- stat cards ---- */
.rc-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;margin-bottom:1rem;}
.rc-stat{background:var(--l1);border:1px solid var(--border);border-radius:8px;padding:.9rem 1rem;}
.rc-stat-v{font-family:var(--head);font-size:2rem;font-weight:600;line-height:1.1;margin:.25rem 0 .1rem;}
.rc-stat-f{font-family:var(--mono);font-size:11px;color:var(--t2);}
.rc-bar{height:4px;border-radius:2px;background:var(--l3);overflow:hidden;margin-top:.5rem;}
.rc-bar > i{display:block;height:100%;border-radius:2px;}

/* ---- chips ---- */
.rc-chip{display:inline-block;font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;
  padding:2px 8px;border-radius:4px;border:1px solid;white-space:nowrap;margin:0 4px 4px 0;}
.rc-chip.green{background:rgba(16,185,129,.12);color:var(--green-hi);border-color:rgba(16,185,129,.25);}
.rc-chip.amber{background:rgba(245,158,11,.12);color:var(--amber-hi);border-color:rgba(245,158,11,.25);}
.rc-chip.red{background:rgba(244,63,94,.12);color:var(--red-hi);border-color:rgba(244,63,94,.25);}
.rc-chip.blue{background:rgba(59,130,246,.12);color:var(--blue-hi);border-color:rgba(59,130,246,.25);}
.rc-chip.grey{background:var(--l2);color:var(--t2);border-color:var(--border);}

/* ---- table ---- */
.rc-table{width:100%;border-collapse:collapse;font-size:.86rem;}
.rc-table th{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--t3);
  text-align:left;padding:.6rem 1rem;background:var(--base);border-bottom:1px solid var(--border);font-weight:600;}
.rc-table td{padding:.7rem 1rem;border-bottom:1px solid var(--l3);vertical-align:middle;}
.rc-table tr:nth-child(even) td{background:#1c2230;}
.rc-mono{font-family:var(--mono);font-size:12.5px;}
.rc-muted{color:var(--t3);}

/* ---- candidate cards ---- */
.rc-cand{background:var(--l1);border:1px solid var(--border);border-radius:8px;padding:1rem 1.1rem;margin-bottom:1rem;}
.rc-cand.top{border-color:var(--blue);box-shadow:0 8px 32px -4px rgba(0,0,0,.65);background:var(--l2);}
.rc-cand-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;}
.rc-cand-name{font-family:var(--head);font-size:1.35rem;font-weight:600;line-height:1.2;margin:.3rem 0;}
.rc-cand.small .rc-cand-name{font-size:1.05rem;}
.rc-score{font-family:var(--head);font-weight:600;font-size:2.4rem;line-height:1;text-align:right;}
.rc-cand.small .rc-score{font-size:1.6rem;}
.rc-score small{font-family:var(--mono);font-size:11px;color:var(--t3);font-weight:400;}
.rc-rationale{margin-top:.8rem;padding:.7rem .9rem;background:var(--base);border:1px solid var(--border);
  border-radius:6px;font-size:.84rem;color:var(--t2);}
.rc-rationale li{margin:.2rem 0;}
.rc-comp{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:.8rem 1.4rem;margin-top:.9rem;}
.rc-comp-row .top{display:flex;justify-content:space-between;font-family:var(--mono);font-size:11px;color:var(--t2);}
.rc-comp-row .d{font-size:11.5px;color:var(--t3);margin-top:3px;}

/* ---- concordance rows ---- */
.rc-conc{display:grid;grid-template-columns:1fr 130px 1fr;gap:1rem;align-items:center;padding:.65rem 1rem;
  border-bottom:1px solid var(--l3);}
.rc-conc:nth-child(even){background:#1c2230;}
.rc-conc.hd{background:var(--base)!important;font-family:var(--mono);font-size:10px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--t3);font-weight:600;}
.rc-conc .lab{font-family:var(--mono);font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--t3);}
.rc-conc .val{font-size:.9rem;}
.rc-conc .mid{text-align:center;}
.rc-conc .r{text-align:right;}

/* ---- exclusions ---- */
.rc-excl{display:flex;justify-content:space-between;gap:1rem;align-items:center;padding:.7rem 1rem;
  border:1px solid rgba(244,63,94,.25);background:rgba(244,63,94,.06);border-radius:6px;margin-bottom:.5rem;}

/* ---- buttons ---- */
.stButton>button,.stFormSubmitButton>button,.stDownloadButton>button{
  border-radius:4px;border:1px solid var(--border-hi);background:var(--l2);color:var(--t1);
  font-family:var(--body);font-weight:500;transition:all .15s;}
.stButton>button:hover,.stFormSubmitButton>button:hover,.stDownloadButton>button:hover{
  background:var(--l3);border-color:var(--blue);color:var(--t1);}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"],.stButton>button[data-testid="stBaseButton-primary"],
.stFormSubmitButton>button[data-testid="stBaseButton-primaryFormSubmit"]{
  background:var(--blue);border-color:var(--blue);color:#fff;}
.stButton>button[kind="primary"]:hover,.stFormSubmitButton>button[kind="primary"]:hover,
.stButton>button[data-testid="stBaseButton-primary"]:hover,
.stFormSubmitButton>button[data-testid="stBaseButton-primaryFormSubmit"]:hover{background:var(--blue-hi);border-color:var(--blue-hi);}
.stButton>button:active{transform:scale(.98);}

/* ---- inputs ---- */
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div,[data-testid="stNumberInput"] input{
  background:var(--base)!important;border-color:var(--border)!important;border-radius:4px!important;}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within,[data-baseweb="select"]>div:focus-within{
  border-color:var(--blue)!important;box-shadow:0 0 0 1px var(--blue)!important;}
input,textarea{color:var(--t1)!important;font-family:var(--body)!important;}
input::placeholder,textarea::placeholder{color:var(--t3)!important;}
label[data-testid="stWidgetLabel"] p,[data-testid="stWidgetLabel"] p{
  font-family:var(--mono);font-size:11px;letter-spacing:.04em;color:var(--t2);}

/* ---- forms / expanders / uploaders / alerts ---- */
[data-testid="stForm"]{background:var(--l1);border:1px solid var(--border);border-radius:8px;padding:1.25rem;}
[data-testid="stExpander"]{background:var(--l1);border:1px solid var(--border)!important;border-radius:8px;}
[data-testid="stExpander"] summary{font-family:var(--head);}
[data-testid="stFileUploaderDropzone"]{background:var(--base);border:1px dashed var(--border-hi);border-radius:8px;}
[data-testid="stAlert"]{border-radius:6px;border:1px solid var(--border);background:var(--l2);}
[data-testid="stMarkdownContainer"] table{border-collapse:collapse;}
[data-testid="stMarkdownContainer"] th,[data-testid="stMarkdownContainer"] td{border:1px solid var(--border);padding:.4rem .7rem;}
[data-testid="stImage"] img{border-radius:6px;border:1px solid var(--border);}
[data-testid="stImageCaption"]{font-family:var(--mono);font-size:11px;color:var(--t3);}
.rc-report{background:var(--l1);border:1px solid var(--border);border-radius:8px;padding:1.25rem 1.5rem;}

::-webkit-scrollbar{width:8px;height:8px;}
::-webkit-scrollbar-thumb{background:var(--border-hi);border-radius:4px;}
</style>
"""


def inject_theme() -> None:
    """Call once, right after st.set_page_config()."""
    st.markdown(CSS, unsafe_allow_html=True)


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def tone_for_score(score: float) -> str:
    """Same thresholds as report_generator._confidence_label (75 / 50 / 25)."""
    if score >= 75:
        return "green"
    if score >= 50:
        return "blue"
    if score >= 25:
        return "amber"
    return "red"


def band_for_score(score: float) -> str:
    if score >= 75:
        return "High lead"
    if score >= 50:
        return "Moderate"
    if score >= 25:
        return "Low"
    return "Very low"


def chip(text: str, tone: str = "grey") -> str:
    return f'<span class="rc-chip {tone}">{_e(str(text))}</span>'


def bar(pct: float, tone: str = "blue") -> str:
    pct = max(0.0, min(100.0, float(pct)))
    return f'<div class="rc-bar"><i style="width:{pct:.0f}%;background:var(--{tone})"></i></div>'


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
def sidebar_brand() -> None:
    html(
        '<div class="rc-brand"><div class="rc-logo">R</div><div>'
        '<div class="rc-brand-t">RECONCILE</div>'
        '<div class="rc-brand-s">Bob-Powered DVI Coordination</div></div></div>'
        '<div class="rc-proto">Investigative lead tool &middot; not an identification</div>'
    )


def sidebar_status(items: list) -> None:
    """items: [(label, value, ok_bool)]"""
    rows = "".join(
        f'<div><span><span class="rc-dot {"" if ok else "off"}"></span>{_e(l)}</span><span>{_e(v)}</span></div>'
        for l, v, ok in items
    )
    html(f'<div class="rc-sys">{rows}</div>')


def page_header(eyebrow: str, title: str, subtitle: str = "") -> None:
    sub = f"<p>{_e(subtitle)}</p>" if subtitle else ""
    html(
        f'<div class="rc-hero"><div class="rc-eyebrow">{_e(eyebrow)}</div>'
        f"<h1>{_e(title)}</h1>{sub}</div>"
    )


def notice(title: str, body: str, tone: str = "amber") -> None:
    cls = "blue" if tone == "blue" else ""
    html(f'<div class="rc-notice {cls}"><div><b>{_e(title)}</b>{_e(body)}</div></div>')


def legal_notice() -> None:
    notice(
        "Legal & ethical notice: AI-assisted investigative lead, not a confirmed identification",
        "Candidate ranking is prioritization only. Formal identification requires confirmation by a "
        "qualified forensic examiner using DNA, dental, or fingerprint evidence.",
    )


def stat_cards(cards: list) -> None:
    """cards: [(label, value, footnote, pct_or_None, tone)]"""
    out = []
    for label, value, foot, pct, tone in cards:
        b = bar(pct, tone) if pct is not None else ""
        out.append(
            f'<div class="rc-stat"><div class="rc-eyebrow">{_e(label)}</div>'
            f'<div class="rc-stat-v">{_e(str(value))}</div>'
            f'<div class="rc-stat-f">{_e(foot)}</div>{b}</div>'
        )
    html(f'<div class="rc-stats">{"".join(out)}</div>')


def card(title: str, sub: str = "", body_html: str = "") -> None:
    """Self-contained card (Streamlit renders each st.markdown call separately, so
    a card can't be opened in one call and closed in another)."""
    s_ = f'<span class="rc-card-s">{_e(sub)}</span>' if sub else ""
    html(f'<div class="rc-card"><div class="rc-card-h"><span class="rc-card-t">{_e(title)}</span>{s_}</div>'
         f'<div class="rc-card-b">{body_html}</div></div>')


def worklist_table(rows: list) -> None:
    """rows: dicts with case, site, found, modalities(list[str]), lead, lead_id, score(float|None), state"""
    body = []
    for r in rows:
        mods = "".join(chip(m, "grey") for m in r["modalities"]) or '<span class="rc-muted">none recorded</span>'
        if r["score"] is None:
            lead = '<span class="rc-muted"><i>No viable candidate</i></span>'
            score = '<span class="rc-muted rc-mono">&mdash;</span>'
            state = chip("No lead", "red")
        else:
            tone = tone_for_score(r["score"])
            lead = f'<span class="rc-mono">{_e(r["lead_id"])}</span> <span class="rc-muted">{_e(r["lead"])}</span>'
            score = f'<span class="rc-mono">{r["score"]:.1f}%</span>{bar(r["score"], tone)}'
            state = chip(band_for_score(r["score"]), tone)
        body.append(
            f'<tr><td class="rc-mono">{_e(r["case"])}</td><td>{_e(r["site"] or "unknown")}</td>'
            f'<td class="rc-mono">{_e(r["found"] or "n/a")}</td><td>{mods}</td><td>{lead}</td>'
            f'<td style="min-width:110px">{score}</td><td>{state}</td></tr>'
        )
    html(
        '<div class="rc-card"><div class="rc-card-h"><span class="rc-card-t">Active forensic worklist</span>'
        '<span class="rc-card-s">top candidate per case &middot; deterministic engine</span></div>'
        '<table class="rc-table"><thead><tr><th>Case</th><th>Recovery site</th><th>Date found</th>'
        "<th>Biometrics / evidence</th><th>Top candidate lead</th><th>Score</th><th>Triage</th></tr></thead>"
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def candidate_card(rank: int, name: str, ante_id: str, score: float, subtitle: str,
                   rationale: list, components: list, primary: bool) -> None:
    tone = tone_for_score(score)
    cls = "top" if primary else "small"
    comps = ""
    if primary:
        cells = "".join(
            f'<div class="rc-comp-row"><div class="top"><span>{_e(c.name)} (wt. {c.weight*100:.0f}%)</span>'
            f'<span>{c.score:.0f}/100</span></div>{bar(c.score, tone_for_score(c.score))}'
            f'<div class="d">{_e(c.detail)}</div></div>'
            for c in components
        )
        comps = (
            '<div class="rc-eyebrow" style="margin-top:1rem">Weighted modality breakdown</div>'
            f'<div class="rc-comp">{cells}</div>'
        )
    rat = "".join(f"<li>{_e(r)}</li>" for r in rationale)
    rat_html = (
        f'<div class="rc-rationale"><div class="rc-eyebrow" style="margin-bottom:4px">Explainable engine rationale</div>'
        f"<ul style='margin:0;padding-left:1.1rem'>{rat}</ul></div>"
        if primary else ""
    )
    html(
        f'<div class="rc-cand {cls}"><div class="rc-cand-head"><div>'
        f'{chip("Rank #" + str(rank), "blue")}{chip(ante_id, "grey")}{chip(band_for_score(score), tone)}'
        f'<div class="rc-cand-name">{_e(name)}</div><div class="rc-stat-f">{_e(subtitle)}</div></div>'
        f'<div class="rc-score" style="color:var(--{tone}-hi)">{score:.1f}<small>/100</small></div></div>'
        f"{rat_html}{comps}</div>"
    )


def concordance_table(am_label: str, pm_label: str, rows: list) -> None:
    """rows: (field, am_value, pm_value, status) with status in concordant|unconfirmed|discordant"""
    tone = {"concordant": "green", "unconfirmed": "amber", "discordant": "red"}
    head = (
        f'<div class="rc-conc hd"><div>Ante-mortem &middot; {_e(am_label)}</div><div class="mid">Concordance</div>'
        f'<div class="r">Post-mortem &middot; {_e(pm_label)}</div></div>'
    )
    body = "".join(
        f'<div class="rc-conc"><div><div class="lab">{_e(f)}</div><div class="val">{_e(a) or "&mdash;"}</div></div>'
        f'<div class="mid">{chip(s, tone[s])}</div>'
        f'<div class="r"><div class="lab">{_e(f)}</div><div class="val">{_e(p) or "&mdash;"}</div></div></div>'
        for f, a, p, s in rows
    )
    html(f'<div class="rc-card">{head}{body}</div>')


def exclusion_row(name: str, ante_id: str, reason: str) -> None:
    html(
        f'<div class="rc-excl"><div><span class="rc-mono">{_e(ante_id)}</span> &nbsp;{_e(name)}'
        f'<div class="rc-stat-f">Deterministic rule violation: {_e(reason)}</div></div>'
        f'{chip("Excluded", "red")}</div>'
    )


# ---------------------------------------------------------------------------
# Field-by-field concordance (presentation only -- the ENGINE score is unchanged)
# ---------------------------------------------------------------------------
from difflib import SequenceMatcher as _SM


def _blank(v) -> bool:
    return v is None or str(v).strip().lower() in ("", "unknown", "none", "n/a")


def _text_status(a, b) -> str:
    if _blank(a) or _blank(b):
        return "unconfirmed"
    ratio = _SM(None, str(a).strip().lower(), str(b).strip().lower()).ratio()
    return "concordant" if ratio >= 0.8 else "discordant"


def _range_status(a_lo, a_hi, b_lo, b_hi, buffer: float = 0) -> str:
    if None in (a_lo, a_hi, b_lo, b_hi):
        return "unconfirmed"
    return "concordant" if (a_lo - buffer) <= b_hi and (b_lo - buffer) <= a_hi else "discordant"


def _range_txt(lo, hi, unit="") -> str:
    if lo is None and hi is None:
        return ""
    return f"{lo:g}\u2013{hi:g}{unit}" if lo != hi else f"{lo:g}{unit}"


def _marks_txt(marks) -> str:
    return "; ".join(f"{m.type} ({m.location}): {m.description}".strip() for m in marks)


def _component_status(components, name: str, both_sides: bool) -> str:
    comp = next((c for c in components if c.name == name), None)
    if comp is None:
        return "unconfirmed"
    if comp.score >= 60:
        return "concordant"
    if both_sides and comp.score < 40:
        return "discordant"
    return "unconfirmed"


def build_concordance(ante, post, result) -> list:
    """Return [(field, am_value, pm_value, status)] for the dual-dossier inspection table."""
    comps = result.components if result else []
    am_dental = getattr(ante, "dental_notes", "")
    pm_dental = getattr(post, "dental_findings", "")
    return [
        ("Biological sex", ante.sex, post.sex,
         "unconfirmed" if _blank(ante.sex) or _blank(post.sex) else ("concordant" if ante.sex == post.sex else "discordant")),
        ("Age (years)", _range_txt(ante.age_min, ante.age_max), _range_txt(post.age_min, post.age_max),
         _range_status(ante.age_min, ante.age_max, post.age_min, post.age_max, buffer=3)),
        ("Height (cm)", _range_txt(ante.height_cm_min, ante.height_cm_max), _range_txt(post.height_cm_min, post.height_cm_max),
         _range_status(ante.height_cm_min, ante.height_cm_max, post.height_cm_min, post.height_cm_max, buffer=3)),
        ("Build", ante.build, post.build, _text_status(ante.build, post.build)),
        ("Hair", f"{ante.hair_color} {ante.hair_length}".strip(), f"{post.hair_color} {post.hair_length}".strip(),
         _text_status(f"{ante.hair_color} {ante.hair_length}", f"{post.hair_color} {post.hair_length}")),
        ("Eye colour", ante.eye_color, post.eye_color, _text_status(ante.eye_color, post.eye_color)),
        ("Blood type", ante.blood_type, post.blood_type, _text_status(ante.blood_type, post.blood_type)),
        ("Distinguishing marks", _marks_txt(ante.marks), _marks_txt(post.marks),
         _component_status(comps, "Distinguishing marks", bool(ante.marks and post.marks))),
        ("Dental", am_dental, pm_dental,
         _component_status(comps, "Dental", bool(not _blank(am_dental) and not _blank(pm_dental)))),
        ("Clothing / effects", "; ".join(ante.clothing), "; ".join(post.clothing),
         _component_status(comps, "Clothing / personal effects", bool(ante.clothing and post.clothing))),
    ]