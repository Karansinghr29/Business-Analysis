"""ISOLATED ML experiment — metrics + rank helper (no I/O)."""
from __future__ import annotations
import numpy as np, pandas as pd

def metrics(actual, pred):
    a=np.array(actual,float); p=np.array(pred,float); e=a-p
    return dict(MAE=int(round(np.abs(e).mean())),
                RMSE=int(round(np.sqrt((e**2).mean()))),
                MAPE=round(float(np.mean(np.abs(e/a))*100),2))

def add_ranks(comp_df):
    d=comp_df.copy()
    d["Rank"]=d["MAPE"].rank(method="min").astype(int)   # primary rank by MAPE
    return d.sort_values(["MAPE","RMSE","MAE"]).reset_index(drop=True)
