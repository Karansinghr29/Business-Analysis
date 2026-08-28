"""Fail-loud validator — isolated business-aware Holt-Winters (regression + HW-on-residual) experiment.
Proves: NO existing file changed, leakage-free lags, residual-HW uses train-only residuals, same unseen window,
baseline HW read-only, period alignment, determinism."""
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

print("[1] NO existing file modified (before/after hash)")
before=_snap(); subprocess.run([sys.executable,"hw_business_aware_experiment.py"],cwd=HERE,capture_output=True); after=_snap()
chk([os.path.basename(k) for k in before if before.get(k)!=after.get(k)]==[],"no production .py/CSV changed")
chk([k for k in before if k not in after]==[],"no production file deleted")
chk(len(before)>50,f"snapshot covered production files ({len(before)})")
prod=set(os.path.basename(p) for p in glob.glob(os.path.join(ENGINE,"outputs","*")))
chk(not any(n.startswith("hw_business_aware") for n in prod),"no experiment output leaked into decision_engine/outputs/")

DS=o("hw_business_aware_dataset.csv").sort_values("period").reset_index(drop=True)
P=o("hw_business_aware_predictions.csv"); C=o("hw_business_aware_comparison.csv")
from hw_business_aware_experiment import REGFEAT, build_monthly, hw_resid_fit
from sklearn.linear_model import Ridge

print("\n[2] leakage — regression features are lags/rolling(prior)/calendar only")
raw=["revenue","active_tenants","occupied_beds","usable_beds","occupancy_rate","collections","collection_rate","eb_billed"]
chk(not [f for f in REGFEAT if f in raw],"REGFEAT has no current-month raw business value")
chk(all(f.endswith(("lag1","lag2","lag3","roll3")) or f in ("month_num","sin_m","cos_m","quarter") for f in REGFEAT),"every REGFEAT is lag/rolling(prior) or calendar")
chk(all(abs(DS["rev_lag1"].iloc[i]-DS["revenue"].iloc[i-1])<1 for i in range(1,len(DS))),"rev_lag1[t]==revenue[t-1]")
chk(all(abs(DS["coll_lag1"].iloc[i]-DS["collections"].iloc[i-1])<1 for i in range(1,len(DS))),"coll_lag1[t]==collections[t-1]")
chk(all(abs(DS["rev_roll3"].iloc[i]-DS["revenue"].iloc[i-3:i].mean())<1 for i in range(3,len(DS))),"rev_roll3 uses only prior months")

print("\n[3] residual-HW uses TRAIN-only residuals; final = regression + residual forecast (reproduced)")
df=build_monthly().reset_index(drop=True); START=24; ok=True; okresid=True
for k in range(len(P)):
    i=START+k
    tr=df.iloc[:i].dropna(subset=REGFEAT+["revenue"]).copy()
    reg=Ridge(alpha=10.0); reg.fit(tr[REGFEAT],tr["revenue"])
    reg_test=float(reg.predict(df.iloc[[i]][REGFEAT])[0])
    resid_tr=tr["revenue"].values-reg.predict(tr[REGFEAT])          # residuals from training months only (no month t)
    rf=hw_resid_fit(resid_tr,1)
    if abs(round(reg_test+rf)-float(P["business_aware_hw"].iloc[k]))>2: ok=False
    if abs(round(reg_test)-float(P["regression_only"].iloc[k]))>2: okresid=False
chk(okresid,"regression_only reproduces (Ridge on rows<i)")
chk(ok,"business_aware_hw == regression_forecast + HW_residual_forecast (residuals train-only; month t never used)")

print("\n[4] period alignment; same unseen window; chronological")
D2,_=__import__("loader").load_all()
pp=D2["v_pnl_by_category"].copy(); pp["revenue"]=pd.to_numeric(pp["revenue"],errors="coerce")
truth=pp.groupby("month")["revenue"].sum(); truth.index=pd.to_datetime(truth.index).strftime("%Y-%m")
chk(all(abs(truth.get(r["period"],np.nan)-r["revenue"])<1.0 for _,r in DS.iterrows()),"dataset revenue[period]==v_pnl monthly sum (aligned by period)")
chk(list(P["period"])==sorted(P["period"]) and list(P["period"])[0]=="2026-02" and list(P["period"])[-1]=="2026-08" and len(P)==7,"same window as production HW (2026-02..2026-08, 7 folds); no shuffle")
chk(P["hw_baseline"].notna().all() and P["business_aware_hw"].notna().all(),"both models predict all 7 identical test months")

print("\n[5] baseline HW read-only (not retrained); comparison recomputed")
src=open(os.path.join(HERE,"hw_business_aware_experiment.py"),encoding="utf-8").read()
chk("phase2_revenue_backtest.csv" in src,"baseline HW read from production backtest")
def mape(a,p):
    a=np.array(a,float);p=np.array(p,float); return round(float(np.mean(np.abs((a-p)/a))*100),2)
chk(abs(mape(P["actual"],P["hw_baseline"])-float(C[C["model"].str.contains("Existing")]["MAPE"].iloc[0]))<0.01,"baseline HW MAPE matches production backtest")

print("\n[6] determinism")
h1=[_hash(os.path.join(OUTX,f)) for f in ["hw_business_aware_predictions.csv","hw_business_aware_comparison.csv"]]
subprocess.run([sys.executable,"hw_business_aware_experiment.py"],cwd=HERE,capture_output=True)
h2=[_hash(os.path.join(OUTX,f)) for f in ["hw_business_aware_predictions.csv","hw_business_aware_comparison.csv"]]
chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
