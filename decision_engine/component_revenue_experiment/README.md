# Component-based revenue forecast (isolated experiment)

Forecasts revenue by its real P&L drivers instead of as one aggregate series:
```
occupied_beds forecast (ES)  ×  effective_rent/bed forecast (ES trend)  =  rental forecast
total = rental + electricity forecast (ES) + minor components (trailing-3 median) + reconciling 'other'
```
Identity `rental_income = occupied_beds × effective_rent_per_bed` verified for every month. Compared to the
EXISTING revenue-only production Holt-Winters (read from `phase2_revenue_backtest.csv`, never retrained) on the
same unseen window (2026-02..2026-08, 7 folds, START=24).

**Isolation:** every file new; no existing `.py`/CSV/output/dashboard/validator/`run_all.py` modified (proven by
before/after MD5 of 244 production files). Outputs under `component_revenue_experiment/outputs/` only. No synthetic
data; every sub-forecast uses only months strictly before the target. Deterministic.

## Result (unseen 2026-02..2026-08, 7 folds)
| Model | MAE | RMSE | MAPE |
|---|--:|--:|--:|
| A. Revenue-only Holt-Winters (production) | 149,667 | 183,721 | 4.86% |
| **B. Component-based (occ × rent + components)** | **110,605** | **127,242** | **3.79%** |

Sub-forecast accuracy (MAPE): occupied_beds 2.94%, effective_rent 3.26%, rental_income 3.38%,
electricity_income 10.55%, total 3.79%.

**The component-based model beats Holt-Winters on all three metrics.** Occupancy and effective rent are each
smoother and more predictable than aggregate revenue, so forecasting them separately (occupancy ES + rent trend)
and multiplying captures both the volume and the rent escalation more cleanly than a univariate view of the noisier
total. Isolated experiment only — NOT integrated into production.
