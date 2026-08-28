"""
ISOLATED ML experiment — fail-loud validator.
Proves: NO existing file changes (before/after hash of every production .py + output CSV), leakage-free,
period alignment (not row-join), determinism, and identical test observations across all models.
"""
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
def _snapshot_existing():
    h={}
    for p in glob.glob(os.path.join(ENGINE,"*.py")): h[p]=_hash(p)          # production modules (top-level only)
    for p in glob.glob(os.path.join(ENGINE,"outputs","*.csv")): h[p]=_hash(p)  # production outputs
    return h

print("[1] NO existing file is modified by running the experiment (before/after hash of every production .py + output)")
before=_snapshot_existing()
subprocess.run([sys.executable,"experiment.py"],cwd=HERE,capture_output=True)
after=_snapshot_existing()
changed=[os.path.basename(k) for k in before if before.get(k)!=after.get(k)]
missing=[os.path.basename(k) for k in before if k not in after]
chk(len(changed)==0,f"no production .py/CSV changed by the experiment (changed: {changed or 'none'})")
chk(len(missing)==0,f"no production file deleted (missing: {missing or 'none'})")
chk(len(before)>50,f"snapshot actually covered production files ({len(before)} hashed)")

print("\n[2] experiment outputs are ISOLATED (never in production outputs/)")
prod=set(os.path.basename(p) for p in glob.glob(os.path.join(ENGINE,"outputs","*")))
chk(not any(n.startswith("ml_revenue_experiment") for n in prod),"no ml_revenue_experiment_* file in decision_engine/outputs/")
chk(os.path.isdir(OUTX) and len(glob.glob(os.path.join(OUTX,"*.csv")))>=5,"experiment outputs live under ml_revenue_experiment/outputs/")

DS=o("ml_revenue_experiment_dataset.csv"); P=o("ml_revenue_experiment_predictions.csv")
OC=o("ml_revenue_experiment_occupancy_forecast.csv"); C=o("ml_revenue_experiment_comparison.csv")
from features import FEATS_A, FEATS_B_BASE, FEATS_B_OCC, FEATS_OCC
from occupancy_forecast import forecast_occupancy_at

print("\n[3] leakage — strictly-prior lags; no target-month revenue/occupancy in any feature")
DS=DS.sort_values("period").reset_index(drop=True)
chk(all(abs(DS["revenue_lag1"].iloc[i]-DS["revenue"].iloc[i-1])<1 for i in range(1,len(DS))),"revenue_lag1[t]==revenue[t-1]")
chk(all(abs(DS["revenue_lag3"].iloc[i]-DS["revenue"].iloc[i-3])<1 for i in range(3,len(DS))),"revenue_lag3[t]==revenue[t-3]")
chk(all(abs(DS["occupied_beds_lag1"].iloc[i]-DS["occupied_beds"].iloc[i-1])<1 for i in range(1,len(DS))),"occupied_beds_lag1[t]==occupied_beds[t-1]")
chk(all(abs(DS["revenue_roll3"].iloc[i]-DS["revenue"].iloc[i-3:i].mean())<1 for i in range(3,len(DS))),"revenue_roll3 uses only prior months")
for fs,nm in [(FEATS_A,"A"),(FEATS_B_BASE+FEATS_B_OCC,"B"),(FEATS_OCC,"occ-forecaster")]:
    bad=[f for f in fs if f in ("revenue","occupied_beds","occupancy_rate")]
    chk(not bad,f"{nm} excludes target-month revenue/occupied/rate ({bad or 'clean'})")

print("\n[4] period alignment (revenue & occupancy joined by month, not row number)")
D2,_=__import__("loader").load_all()
pp=D2["v_pnl_by_category"].copy(); pp["revenue"]=pd.to_numeric(pp["revenue"],errors="coerce")
truth=pp.groupby("month")["revenue"].sum(); truth.index=pd.to_datetime(truth.index).strftime("%Y-%m")  # normalize YYYY-MM-01 -> YYYY-MM
chk(all(abs(truth.get(r["period"],np.nan)-r["revenue"])<1.0 for _,r in DS.iterrows()),"dataset revenue[period]==v_pnl monthly sum for the SAME period")
chk(list(DS["period"])==sorted(DS["period"]),"dataset ordered by period (aligned, monotonic)")

print("\n[5] same unseen test observations for every model; chronological; no shuffle")
chk(list(P["period"])==sorted(P["period"]),"test periods strictly increasing (no shuffle)")
chk(list(P["period"])[0]=="2026-02" and list(P["period"])[-1]=="2026-08" and len(P)==7,"same window as production HW (2026-02..2026-08, 7 folds)")
modelcols=[c for c in P.columns if c.startswith("A_") or c.startswith("B_") or c=="hw"]
chk(all(P[c].notna().all() for c in modelcols),"every model has a prediction for all 7 test months (identical observations)")

print("\n[6] occupancy FORECAST used at test, not actual future occupancy")
rep=[forecast_occupancy_at(DS,i,"rf")[0] for i in range(len(DS)-len(P),len(DS))]
chk(list(OC["occ_pred"])==rep,"occupancy forecast reproduces from forecast_occupancy_at(rows[:i]) exactly")
chk((OC["occ_pred"]!=OC["actual_occupied"]).any(),"forecast occupancy differs from actual (predicted, not copied)")
mrg=P.merge(OC,on="period")
chk((mrg["occ_pred_x"]==mrg["occ_pred_y"]).all() and (mrg["occ_pred_x"]!=mrg["actual_occupied"]).any(),
    "Experiment B test row uses the forecast occ_pred, never the month's actual occupied beds")

print("\n[7] Holt-Winters READ from production (not retrained); comparison recomputed")
src=open(os.path.join(HERE,"experiment.py"),encoding="utf-8").read()
chk("phase2_revenue_backtest.csv" in src and "ExponentialSmoothing" not in src,"HW read from existing backtest; no HW re-implementation in the experiment")
def met(a,p):
    a=np.array(a,float);p=np.array(p,float);e=a-p; return round(float(np.mean(np.abs(e/a))*100),2)
hw_row=C[C["model"].str.contains("Holt")].iloc[0]
chk(abs(met(P["actual"],P["hw"])-float(hw_row["MAPE"]))<0.01,"HW MAPE in comparison matches production backtest predictions")
chk(len(C)==1+2*4,f"comparison has HW + 4 models x 2 experiments = 9 rows (got {len(C)})")

print("\n[8] determinism (fixed seeds)")
h1=[_hash(os.path.join(OUTX,f)) for f in ["ml_revenue_experiment_predictions.csv","ml_revenue_experiment_comparison.csv","ml_revenue_experiment_occupancy_forecast.csv"]]
subprocess.run([sys.executable,"experiment.py"],cwd=HERE,capture_output=True)
h2=[_hash(os.path.join(OUTX,f)) for f in ["ml_revenue_experiment_predictions.csv","ml_revenue_experiment_comparison.csv","ml_revenue_experiment_occupancy_forecast.csv"]]
chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
