# Applying the new Reconcile UI

Copy these into your project's `src/` folder (overwrite when asked):

| File | What it is |
|---|---|
| `src/demo_app.py` | REPLACES your existing file. New layout: sidebar nav + 5 pages. Same backend calls and widget keys. |
| `src/ui_theme.py` | NEW. All CSS + HTML components from the design system. |
| `src/.streamlit/config.toml` | NEW. Dark theme base colors (folder must be named `.streamlit`). |
| `src/database.py` | REPLACES your existing file. Adds the missing `fingerprint` table + `add_fingerprint` / `list_fingerprints` (fingerprint matching was silently disabled without these) and `list_match_audit`. |

Run:  `cd src && streamlit run demo_app.py`
No new pip dependencies.
