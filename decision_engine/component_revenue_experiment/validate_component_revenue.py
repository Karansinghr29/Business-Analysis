"""Fail-loud validator — isolated component-based revenue forecast.
Proves: NO existing file changed; identity rental==occ×rent; components reconcile to revenue; leakage-free
(each fold uses only prior months; no test-month actual); same unseen window; HW read-only; determinism."""
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
before=_snap(); subprocess.run([sys.executable,"component_revenue_experiment.py"],cwd=HERE,capture_output=True); after=_snap()
chk([os.path.basename(k) for k in before if before.get(k)!=after.get(k)]==[],"no production .py/CSV changed")
chk([k for k in before if k not in after]==[],"no production file deleted")
chk(len(before)>50,f"snapshot covered production files ({len(before)})")
prod=set(os.path.basename(p) for p in glob.glob(os.path.join(ENGINE,"outputs","*")))
chk(not any(n.startswith("component_revenue") for n in prod),"no experiment output leaked into decision_engine/outputs/")

DS=o("component_revenue_dataset.csv"); P=o("component_revenue_predictions.csv"); C=o("component_revenue_comparison.csv")
from component_revenue_experiment import build_monthly, es_fit, trailing_median, MINOR, START

print("\n[2] P&L identity + component reconciliation (verified every month)")
chk(bool((DS["occupied_beds"]>0).all()),"occupied_beds > 0 every month (rent identity well-defined)")
id_ok=all(abs(r["rental_income"]-r["occupied_beds"]*r["effective_rent"])<2 for _,r in DS.iterrows())
chk(id_ok,"rental_income == occupied_beds × effective_rent_per_bed for every month")
comps=["rental_income","electricity_income","guest_stay_income","onboarding_income","late_fees_income","exit_charges_income","other"]
recon=all(abs(r["revenue"]-sum(r[c] for c in comps))<2 for _,r in DS.iterrows())
chk(recon,"revenue == sum(components incl reconciling 'other') every month")

print("\n[3] leakage-free — every fold uses ONLY prior months; no test-month actual")
g=build_monthly(); n=len(g); ok=True
for k in range(len(P)):
    i=START+k; h=g.iloc[:i]
    occ_fc=es_fit(h["occupied_beds"],seasonal=True); rent_fc=es_fit(h["effective_rent"],seasonal=False)
    elec_fc=es_fit(h["electricity_income"],seasonal=True); minor=sum(trailing_median(h[c]) for c in MINOR)
    total=occ_fc*rent_fc+elec_fc+minor
    if abs(round(total)-float(P["component_total"].iloc[k]))>2: ok=False
chk(ok,"component_total reproduces from forecasts on rows[:i] (occ×rent + elec + minor); test month never used")
# forecast != actual (they are genuine forecasts, not copies of month t)
chk((P["occ_fc"]!=P["occ_actual"]).any(),"occupancy forecast differs from actual (forecast, not copied)")
chk((P["rent_fc"]!=P["rent_actual"]).any(),"effective-rent forecast differs from actual")

print("\n[4] alignment + same unseen window")
D2,_=__import__("loader").load_all()
pp=D2["v_pnl_by_category"].copy(); pp["revenue"]=pd.to_numeric(pp["revenue"],errors="coerce")
truth=pp.groupby("month")["revenue"].sum(); truth.index=pd.to_datetime(truth.index).strftime("%Y-%m")
chk(all(abs(truth.get(r["period"],np.nan)-r["revenue"])<1.0 for _,r in DS.iterrows()),"dataset revenue[period]==v_pnl monthly sum (aligned by period)")
chk(list(P["period"])==sorted(P["period"]) and list(P["period"])[0]=="2026-02" and list(P["period"])[-1]=="2026-08" and len(P)==7,"same window as production HW (2026-02..2026-08, 7 folds); no shuffle")
chk(P["hw"].notna().all() and P["component_total"].notna().all(),"both models predict all 7 identical test months")

print("\n[5] baseline HW read-only; comparison recomputed")
src=open(os.path.join(HERE,"component_revenue_experiment.py"),encoding="utf-8").read()
chk("phase2_revenue_backtest.csv" in src,"HW read from production backtest (not retrained)")
def mape(a,p):
    a=np.array(a,float);p=np.array(p,float); return round(float(np.mean(np.abs((a-p)/a))*100),2)
chk(abs(mape(P["actual"],P["hw"])-float(C[C["model"].str.contains("Existing")]["MAPE"].iloc[0]))<0.01,"HW MAPE matches production backtest")
chk(abs(mape(P["actual"],P["component_total"])-float(C[C["model"].str.contains("Component")]["MAPE"].iloc[0]))<0.01,"component MAPE recomputed matches table")

print("\n[6] determinism")
h1=[_hash(os.path.join(OUTX,f)) for f in ["component_revenue_predictions.csv","component_revenue_comparison.csv"]]
subprocess.run([sys.executable,"component_revenue_experiment.py"],cwd=HERE,capture_output=True)
h2=[_hash(os.path.join(OUTX,f)) for f in ["component_revenue_predictions.csv","component_revenue_comparison.csv"]]
chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
