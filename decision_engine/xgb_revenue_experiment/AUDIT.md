# STEP 1 — Audit of existing revenue forecasting (read-only; nothing modified)

- **Module:** `revenue_forecast.py` (production). Orchestrated by `run_all.py` (ORDER).
- **Target:** monthly **accrual revenue** — `v_pnl_by_category.revenue` grouped by `month`, summed; dense-tail trim (`>0.2·max`) then `asfreq("MS")`. 31 months, **2024-02 … 2026-08** (2026-08 partial).
- **Frequency:** monthly.
- **Production model:** **Holt-Winters** `ExponentialSmoothing(trend="add", seasonal="add", seasonal_periods=12, optimized)`; forecast month 2026-09 = ₹3,199,727. Baselines: naive1, snaive.
- **Existing XGBoost challenger (already in `revenue_forecast.py`, backtest-only, NOT production):** `XFEAT = rev_lag1, rev_lag2, rev_lag3, rev_lag12, rev_roll3, active_lag1, occ_lag1, coll_lag1, month_num`; params `n_estimators=200, max_depth=3, lr=0.05, subsample=0.9, colsample=0.9, reg_lambda=1.0, seed=42`.
- **Validation:** walk-forward one-step, `START=max(24,13)=24` → **test 2026-02 … 2026-08 (7 folds)**, horizon 1 month.
- **Metrics (from `outputs/phase2_revenue_backtest.csv`, read-only):** HW MAE 149,667 / RMSE 183,721 / MAPE 4.86%; naive1 4.59%; existing xgb-challenger 5.86%.
- **Outputs / consumers:** `phase2_revenue_forecast.csv` (dashboard Forecast page KPI), `phase2_revenue_backtest.csv` (dashboard line chart). Governed by `run_all.py --verify` locked snapshot.

**This experiment does NOT modify any of the above.** It reproduces the monthly aggregation locally, reads HW predictions from the existing backtest, and evaluates an extended-feature XGBoost on the same 7 folds.
