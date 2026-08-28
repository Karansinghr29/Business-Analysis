# Business-aware Holt-Winters experiment (regression + HW-on-residuals)

Isolated experiment. Keeps Holt-Winters as the time-series core while letting real business drivers explain the
revenue level:
```
lagged business drivers -> Ridge regression (revenue level)
residual = actual - regression   (training months only)
Holt-Winters fit on the residual series -> next-month residual
final = regression_forecast + HW_residual_forecast
```
Compared to the EXISTING revenue-only production Holt-Winters (read from phase2_revenue_backtest.csv, never
retrained) on the same unseen walk-forward window (2026-02..2026-08, 7 folds, START=24).

**Isolation:** every file is NEW; no existing `.py`/CSV/output/dashboard/validator/`run_all.py` modified (proven by
before/after MD5 of 244 production files). Outputs under `hw_business_aware_experiment/outputs/` only. No synthetic
data; all features are lags/rolling(prior)/calendar. Deterministic (Ridge alpha=10, HW optimized).

## Result (unseen 2026-02..2026-08)
| Model | MAE | RMSE | MAPE |
|---|--:|--:|--:|
| A. Revenue-only Holt-Winters (production) | 149,667 | 183,721 | 4.86% |
| B. Business-aware HW (regression + HW residual) | 250,689 | 325,417 | 7.99% |
| (diagnostic) regression component only | 187,285 | 224,304 | 6.00% |

Revenue-only Holt-Winters wins on all three metrics. The HW-on-residuals step made it worse than the regression
alone (7.99% vs 6.00%) — the residual series is too short/noisy on 7 folds for HW to add value. Business drivers
did not improve the forecast. Not integrated into production; experiment only.
