"""
ISOLATED ML experiment — chronological OCCUPANCY forecaster.
Predicts a target month's occupancy WITHOUT using that month's actual occupancy: trained only on rows strictly
before it, on prior-only occupancy lags + known-ahead usable inventory + calendar. Predicts the occupancy RATE,
then × known-ahead usable_beds[t], clamped [0, usable]. This forecast is the forward occupancy fed into
Experiment B. No I/O; imported by the experiment runner.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from features import FEATS_OCC

def _model(name):
    if name=="rf": return RandomForestRegressor(n_estimators=200,max_depth=4,min_samples_leaf=2,random_state=0,n_jobs=1)
    return LinearRegression()

def forecast_occupancy_at(df, i, model_name="rf"):
    """Forecast (occ_pred:int, rate_pred:float) for row i using ONLY rows [0:i]. No row-i actual used."""
    train=df.iloc[:i].dropna(subset=FEATS_OCC+["occupancy_rate"])
    usable_i=float(df.iloc[i]["usable_beds"])
    if len(train)<6 or df.iloc[i][FEATS_OCC].isna().any():
        prior=df["occupancy_rate"].iloc[max(0,i-3):i].dropna()
        rate=float(np.median(prior)) if len(prior) else float(df["occupancy_rate"].iloc[:i].mean())
    else:
        mdl=_model(model_name); mdl.fit(train[FEATS_OCC], train["occupancy_rate"])
        rate=float(mdl.predict(df.iloc[[i]][FEATS_OCC])[0])
    rate=float(min(max(rate,0.0),1.0))
    occ=int(min(max(round(rate*usable_i),0),usable_i))
    return occ, rate
