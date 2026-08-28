# Isolated ML revenue-forecasting experiment

**Purpose:** objectively compare occupancy-aware ML revenue forecasting against the existing production
Holt-Winters model on the SAME unseen test period. Experiment only — **not** wired into production/dashboard.

## Isolation guarantees
- Every file here is NEW. No existing `.py`, CSV, output, dashboard, validator, or `run_all.py` is modified,
  renamed, deleted, or overwritten. `validate.py` proves this with a before/after MD5 of every production
  `.py` + output CSV (244 files, all unchanged).
- All experiment outputs are written to `ml_revenue_experiment/outputs/` — **outside** `decision_engine/outputs/`,
  so the `run_all.py --verify` locked-snapshot system never sees them.
- Data access is read-only via `import loader`; Holt-Winters results are READ from
  `decision_engine/outputs/phase2_revenue_backtest.csv` (never retrained).

## Files
| File | Role |
|---|---|
| `AUDIT.md` | Step-1 read-only audit findings |
| `dataset.py` | monthly ML dataset (revenue+occupancy aligned by period; inventory via apartment lifecycle) |
| `features.py` | feature sets A/B + occupancy-forecaster inputs + documentation |
| `occupancy_forecast.py` | chronological occupancy forecaster (no actual future occupancy) |
| `models.py` | LinearRegression / RandomForest / XGBoost / LightGBM (fixed seeds) |
| `evaluation.py` | MAE/RMSE/MAPE + ranking |
| `experiment.py` | walk-forward runner (START=24, 2026-02..2026-08), Experiments A & B, comparison, error analysis |
| `plots.py` | actual-vs-predicted, errors-over-time, error-by-occupancy, scatter |
| `validate.py` | fail-loud validator (no-modification, leakage, alignment, determinism, same test obs) |

## Run
```
python experiment.py      # from this directory
python validate.py
```

## Result (unseen 2026-02..2026-08, 7 folds)
Holt-Winters (existing) is best on all three metrics (MAPE 4.86%). Best ML = LightGBM Experiment B (5.14%).
Adding forecast occupancy improved ML (Experiment B 5.14% < Experiment A 6.24%), but did not overtake
Holt-Winters. Small sample (31 months / 7 folds) — ML complexity kept conservative.
