# Vishful Business Analysis — Decision Dashboard

Streamlit dashboard (15 pages) over the Vishful decision-engine outputs.

## Run

```bash
pip install -r requirements.txt
streamlit run decision_engine/dashboard.py
```

## Structure

- `decision_engine/dashboard.py` — the 15-page Streamlit dashboard
- `decision_engine/*.py` — analytics modules, decision engines, validators
- `decision_engine/outputs/` — generated analysis outputs read by the dashboard
- `decision_engine/operational/` — append-only operational stores (owner events, confirmations)
- `Supabase Snippet*.csv` — source data exports read by `decision_engine/loader.py`

## Regenerate and verify

```bash
python decision_engine/run_all.py --verify
```

## Notes

API keys (`GROQ_API_KEY`, `APIFY_API_TOKEN`) are read from environment variables only and are
never stored in this repository. Network-dependent collectors are excluded from `run_all.py`.
