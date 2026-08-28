"""
ISOLATED ML experiment — feature sets + documentation (no I/O; imported by experiment/validate).

Every feature is available BEFORE the target month:
  - lag/rolling features use shift(1)+ (strictly prior periods)
  - usable_beds is a deterministic, known-ahead inventory plan
  - avg_rent_card is an exogenous published rate card
  - calendar terms are known for any month
  - occ_pred / rate_pred are FORECASTS produced chronologically (no actual future occupancy)
The target month's own revenue / occupied_beds / occupancy_rate are NEVER features.
"""
# Experiment A: revenue history + calendar only
FEATS_A=["revenue_lag1","revenue_lag2","revenue_lag3","revenue_lag6","revenue_lag12",
         "revenue_roll3","revenue_roll6","month_num","quarter","sin_m","cos_m"]

# Experiment B: A + lagged occupancy/tenants + known-ahead usable + exogenous rent + FORECAST occupancy
FEATS_B_BASE=FEATS_A+["occupied_beds_lag1","occupied_beds_lag2","occupied_beds_lag3","occupied_roll3",
                      "occupancy_rate_lag1","occupancy_rate_lag2","occupancy_rate_lag3",
                      "tenants_lag1","usable_lag1","usable_beds","avg_rent_card"]
FEATS_B_OCC=["occ_pred","rate_pred"]   # injected at fit/predict time by the runner (forecast, not actual)

# occupancy forecaster inputs (prior-only + known-ahead usable)
FEATS_OCC=["occupied_beds_lag1","occupied_beds_lag2","occupied_beds_lag3","occupied_roll3",
           "occupancy_rate_lag1","occupancy_rate_lag2","tenants_lag1","usable_beds","month_num","sin_m","cos_m"]

# documentation table (feature, source, availability, why valid)
FEATURE_DOC=[
 ("revenue_lag1..12","monthly accrual revenue, shifted","prior months","past revenue known before t"),
 ("revenue_roll3/6","mean of revenue[t-1..t-3/6]","prior months","rolling on strictly prior periods"),
 ("occupied_beds_lag1..3","occupied beds, shifted","prior months","past occupancy known before t"),
 ("occupancy_rate_lag1..3","occupied/usable, shifted","prior months","past rate known before t"),
 ("occupied_roll3","mean occupied[t-1..t-3]","prior months","rolling on prior periods"),
 ("tenants_lag1","active tenants, shifted","prior month","past headcount known"),
 ("usable_lag1","usable beds prior month","prior month","past inventory known"),
 ("usable_beds","apartment-lifecycle inventory for month t","known ahead","inventory plan is deterministic/known before t"),
 ("avg_rent_card","published rate-card mean in effect","known ahead","exogenous published price, not derived from target revenue"),
 ("month_num/quarter/sin_m/cos_m","calendar of month t","known ahead","deterministic calendar"),
 ("occ_pred/rate_pred","chronological occupancy FORECAST for t","known ahead (forecast)","generated from prior data only; actual future occupancy never used"),
]
