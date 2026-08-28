# STEP 1 — Audit (read-only). No existing file modified.

## Revenue
- **Authoritative source:** `v_pnl_by_category` (accounting P&L view). Loaded read-only via `loader.load_all()`.
- **Amount column:** `revenue`. **Period column:** `month` (already month-bucketed in the view).
- **Aggregation:** `groupby("month")["revenue"].sum()` → monthly series; dense-tail trim (`s > 0.2*max`) then `asfreq("MS")`. Matches `revenue_forecast.py` exactly.
- **Target basis:** **ACCRUAL** revenue (booked P&L), NOT cash collected (`receipts` is a separate cash table, not used — same choice as production HW).
- **Coverage:** 31 monthly observations, **2024-02 … 2026-08** (2026-08 partial).

## Occupancy
- **Authoritative source:** `tenant_allotments` (+ `beds`, `apartments`) — read-only.
- **Occupied beds (month m):** active allotments where `start ≤ m AND (actual_exit_date is null OR > m)`, `start = onboarding_date.fillna(booking_date)`; count `nunique(bed_id)`. Same definition as `revenue_forecast.py`.
- **Usable/total beds (month m):** apartment-lifecycle reconstruction — beds whose apartment is operational (`apartments.start_date < month_end` AND not closed). Closure recognised only when apartment `status==Not-Active` with an `end_date` (raw `end_date` is a lease term; many Live apts have past end_dates). Current/forward months additionally require bed `status==Live`. `beds.created_at` never used (migration timestamp).
- **Occupancy %:** `occupied_beds / usable_beds`, capped ≤ 1.0; flagged unreliable where occupied>usable (early start_date under-reporting).
- **Availability at prediction time:** actual occupancy of month t is **retrospective** (known only during/after t). No future bookings exist for Sep-2026+ (all onboarding ≤ 2026-08-23). ⇒ occupancy for a future month must be **forecast from history**, and only LAGGED occupancy is usable directly.

## Existing Holt-Winters (production — NOT modified)
- **Source dataset / target:** monthly accrual revenue series above (univariate).
- **Implementation:** `revenue_forecast.py` → `hw_fit()` = `statsmodels ExponentialSmoothing(trend="add", seasonal="add", seasonal_periods=12, optimized)`.
- **Frequency:** monthly (MS).
- **Methodology:** walk-forward **one-step**, expanding window, `START=max(24,13)=24`.
- **Test period:** **2026-02 … 2026-08 (7 folds)**. Forecast horizon = 1 month.
- **Metrics (from `outputs/phase2_revenue_backtest.csv`, read-only):** MAE=149,667 · RMSE=183,721 · MAPE=4.86%. (naive1 4.59%, xgb-challenger 5.86%.)
- **Existing predictions reused, not recomputed:** the `hw` column of `phase2_revenue_backtest.csv`.

## Isolation proof
- Experiment lives entirely under `ml_revenue_experiment/`; outputs under `ml_revenue_experiment/outputs/` (NOT `decision_engine/outputs/`), so the `run_all.py --verify` locked-snapshot system never sees them.
- Data access is read-only via `import loader` (loader writes nothing; globs source CSVs). Revenue/occupancy/inventory logic is **reproduced locally** in the experiment files, not imported from production modules.
- No existing `.py`, CSV, output, dashboard, validator, or `run_all.py` is read-for-write, renamed, deleted, or overwritten.
