# Occupancy sub-forecast experiment (isolated)

Revenue architecture fixed: `occupied_beds_fc × effective_rent_fc + electricity_fc`. Only the occupancy forecaster
is varied; rent + electricity stay the current ES. Decision is on DOWNSTREAM revenue, not occupancy MAPE.
Windows: 7-fold (2026-02..2026-08, production HW read-only) and 18-fold (2025-03..2026-08, HW reproduced).
Leakage-safe (occupancy uses only months before t), no synthetic occupancy, no shuffle, deterministic.
Production untouched (244-file hash NONE changed).

## Occupancy accuracy (MAPE)
| method | 7-fold | 18-fold |
|---|--:|--:|
| es_seasonal (current) | **2.94** | **4.71** |
| es_trend | 3.49 | 4.93 |
| naive1 | 3.93 | 4.62 |
| es_damped | 4.94 | 5.32 |
| median3 | 5.04 | 5.75 |
| snaive | 6.46 | 8.52 |

## Downstream REVENUE accuracy (occ × rent + electricity)
| occupancy method | 7-fold MAPE | 18-fold MAPE |
|---|--:|--:|
| **es_trend** | **2.64** | **3.71** |
| es_seasonal (current) | 3.31 | 3.97 |
| naive1 | 3.03 | 4.18 |
| median3 | 3.99 | 4.54 |
| es_damped | 5.48 | 4.96 |
| snaive | 6.62 | 8.25 |
| Holt-Winters (benchmark) | 4.86 | 5.55 |

**Lesson:** es_seasonal has the best occupancy MAPE, but **es_trend gives the best revenue** in both windows — occupancy
accuracy ≠ revenue accuracy. es_trend beats HW in 15/18 folds; vs current it wins on aggregate (tail-error), only
3/18 per-fold. Recommendation: adopt es_trend occupancy inside the experiment. No production integration.
