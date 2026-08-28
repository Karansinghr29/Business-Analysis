"""Fail-loud validator for the isolated XGBoost revenue experiment.
Proves: NO existing file changed (before/after hash of every production .py + output CSV), leakage-free lags,
period alignment (not row-join), same unseen test window as HW, HW read-only (not retrained), determinism."""
from __future__ import annotations
import os, sys, glob, hashlib, subprocess
HERE=os.path.dirname(os.path.abspath(__file__)); ENGINE=os.path.dirname(HERE)
sys.path.insert(0, ENGINE); sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np, pandas as pd
OUTX=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUTX,f))
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
def _hash(p):
    with open(p,"rb") as f: return hashlib.md5(f.read()).hexdigest()
def _snap():
    h={}
    for p in glob.glob(os.path.join(ENGINE,"*.py")): h[p]=_hash(p)
    for p in glob.glob(os.path.join(ENGINE,"outputs","*.csv")): h[p]=_hash(p)
    return h

print("[1] NO existing file modified by the experiment (before/after hash)")
before=_snap()
subprocess.run([sys.executable,"xgb_experiment.py"],cwd=HERE,capture_output=True)
after=_snap()
chk([os.path.basename(k) for k in before if before.get(k)!=after.get(k)]==[],"no production .py/CSV changed")
chk([k for k in before if k not in after]==[],"no production file deleted")
chk(len(before)>50,f"snapshot covered production files ({len(before)})")
prod=set(os.path.basename(p) for p in glob.glob(os.path.join(ENGINE,"outputs","*")))
chk(not any(n.startswith("xgb_revenue_experiment") for n in prod),"no experiment output leaked into decision_engine/outputs/")

DS=o("xgb_revenue_experiment_dataset.csv").sort_values("period").reset_index(drop=True)
P=o("xgb_revenue_experiment_predictions.csv"); C=o("xgb_revenue_experiment_comparison.csv")
from xgb_experiment import XFEAT

print("\n[2] leakage — strictly-prior lags; no target-month value in any feature")
chk(all(abs(DS["rev_lag1"].iloc[i]-DS["revenue"].iloc[i-1])<1 for i in range(1,len(DS))),"rev_lag1[t]==revenue[t-1]")
chk(all(abs(DS["rev_lag12"].iloc[i]-DS["revenue"].iloc[i-12])<1 for i in range(12,len(DS))),"rev_lag12[t]==revenue[t-12]")
chk(all(abs(DS["coll_lag1"].iloc[i]-DS["collections"].iloc[i-1])<1 for i in range(1,len(DS))),"coll_lag1[t]==collections[t-1]")
chk(all(abs(DS["occ_lag1"].iloc[i]-DS["occupied_beds"].iloc[i-1])<1 for i in range(1,len(DS))),"occ_lag1[t]==occupied_beds[t-1]")
chk(all(abs(DS["rev_roll3"].iloc[i]-DS["revenue"].iloc[i-3:i].mean())<1 for i in range(3,len(DS))),"rev_roll3 uses only prior months")
raw=["revenue","active_tenants","occupied_beds","usable_beds","occupancy_rate","collections","eb_billed","collection_rate"]
chk(not [f for f in XFEAT if f in raw],"XFEAT contains no current-month raw business value (only lags/calendar)")
chk(all(f.endswith(("lag1","lag2","lag3","lag6","lag12","roll3")) or f in ("month_num","quarter","sin_m","cos_m") for f in XFEAT),
    "every XFEAT is a lag/rolling(prior) or calendar term")

print("\n[3] period alignment (revenue joined by month, not row number)")
D2,_=__import__("loader").load_all()
pp=D2["v_pnl_by_category"].copy(); pp["revenue"]=pd.to_numeric(pp["revenue"],errors="coerce")
truth=pp.groupby("month")["revenue"].sum(); truth.index=pd.to_datetime(truth.index).strftime("%Y-%m")
chk(all(abs(truth.get(r["period"],np.nan)-r["revenue"])<1.0 for _,r in DS.iterrows()),"dataset revenue[period]==v_pnl monthly sum")

print("\n[4] same unseen test window; chronological; identical observations for both models")
chk(list(P["period"])==sorted(P["period"]),"test periods strictly increasing (no shuffle)")
chk(list(P["period"])[0]=="2026-02" and list(P["period"])[-1]=="2026-08" and len(P)==7,"same window as production HW (2026-02..2026-08, 7 folds)")
chk(P["hw"].notna().all() and P["xgboost"].notna().all(),"HW and XGBoost both predict all 7 identical test months")

print("\n[5] Holt-Winters READ from production (not retrained)")
src=open(os.path.join(HERE,"xgb_experiment.py"),encoding="utf-8").read()
chk("phase2_revenue_backtest.csv" in src and "ExponentialSmoothing" not in src,"HW read from backtest; no HW re-implementation")
def mape(a,p):
    a=np.array(a,float);p=np.array(p,float); return round(float(np.mean(np.abs((a-p)/a))*100),2)
hw_mape=float(C[C["model"].str.contains("Holt")]["MAPE"].iloc[0])
chk(abs(mape(P["actual"],P["hw"])-hw_mape)<0.01,"HW MAPE in comparison matches production backtest predictions")

print("\n[6] determinism")
h1=[_hash(os.path.join(OUTX,f)) for f in ["xgb_revenue_experiment_predictions.csv","xgb_revenue_experiment_comparison.csv"]]
subprocess.run([sys.executable,"xgb_experiment.py"],cwd=HERE,capture_output=True)
h2=[_hash(os.path.join(OUTX,f)) for f in ["xgb_revenue_experiment_predictions.csv","xgb_revenue_experiment_comparison.csv"]]
chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
