# Isolated XGBoost revenue experiment (Vishful real monthly business features)

Compares an XGBoost model built on **real monthly Vishful business features + valid lags** against the existing
production **Holt-Winters** over the same unseen walk-forward window (2026-02…2026-08, 7 folds).

**Isolation:** every file is NEW; no existing `.py`/CSV/output/dashboard/validator/`run_all.py` is modified,
renamed, deleted, or overwritten (`validate_xgb_experiment.py` proves it via before/after MD5 of 244 production
files). All outputs go to `xgb_revenue_experiment/outputs/` — outside `decision_engine/outputs/`, so the locked
snapshot never sees them. Holt-Winters is READ from `phase2_revenue_backtest.csv`, never retrained. No synthetic
data; every feature is a real lag/rolling(prior) or a calendar term. Deterministic (seed 42).

## Run
```
python xgb_experiment.py
python validate_xgb_experiment.py
```

## Result (unseen 2026-02…2026-08)
Holt-Winters is best on MAE, RMSE and MAPE (4.86%). The 17-feature XGBoost (real revenue/tenant/occupancy/usable-
bed/collection/electricity lags + calendar) scores 6.95%, and the existing 9-feature challenger 5.86% — both trail
HW. On 31 months / 7 folds, extra features overfit; usable-bed and occupancy-rate lags carry ~0 importance.
Not integrated into production; comparison experiment only.
