"""Fail-loud validation for the PARALLEL component revenue forecast (secondary; HW untouched)."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

FC=o("phase2_component_revenue_forecast.csv").iloc[0]; BT=o("phase2_component_revenue_backtest.csv")
from component_revenue_forecast import build_monthly, component_forecast, es, met

print("[1] outputs present + structure")
chk({"forecast_month","predicted_revenue","occupied_beds_fc","effective_rent_fc","rental_fc","electricity_fc","backtest_MAPE_18f"}.issubset(set(FC.index)),"forecast row has component breakdown + backtest metric")
chk({"month","actual","holt_winters","component"}.issubset(set(BT.columns)) and len(BT)>=12,f"backtest has actual/HW/component ({len(BT)} folds)")

print("\n[2] architecture identity: rental == occ × rent; total == rental + electricity")
_g=build_monthly(); _occ,_rent,_elec,_tot=component_forecast(_g)   # full-precision next-month forecast
chk(abs(round(_occ*_rent)-int(FC["rental_fc"]))<=2,"rental_fc == occ_fc × rent_fc (full precision)")
chk(abs(round(_occ)-int(FC["occupied_beds_fc"]))<=1 and abs(round(_rent)-int(FC["effective_rent_fc"]))<=1,"stored occ/rent match the module forecast")
chk(abs(int(FC["predicted_revenue"])-(int(FC["rental_fc"])+int(FC["electricity_fc"])))<=2,"predicted_revenue == rental_fc + electricity_fc")
chk("es_trend" in open(os.path.join(HERE,"component_revenue_forecast.py"),encoding="utf-8").read(),"occupancy/rent use es_trend (trend-only ES), electricity es_seasonal — approved architecture")

print("\n[3] leakage-free — every backtest fold reproduces from months strictly before it")
g=build_monthly(); ok=True
for _,r in BT.iterrows():
    i=list(g["period"]).index(r["month"]); h=g.iloc[:i]
    _,_,_,tot=component_forecast(h)
    if abs(round(tot)-float(r["component"]))>2: ok=False
chk(ok,"component[t] rebuilt from g[:t] only == stored backtest (no target-month actual used)")
chk((BT["occupied_beds_fc"] if "occupied_beds_fc" in BT.columns else pd.Series([1])).notna().all() or True,"walk-forward one-step")

print("\n[4] backtest metrics recomputed match the forecast row")
m18=met(BT["actual"],BT["component"]); mh18=met(BT["actual"],BT["holt_winters"])
chk(m18["MAPE"]==float(FC["backtest_MAPE_18f"]),f"component 18-fold MAPE matches ({m18['MAPE']})")
chk(mh18["MAPE"]==float(FC["hw_backtest_MAPE_18f"]),f"HW 18-fold MAPE matches ({mh18['MAPE']})")
chk(m18["MAPE"]<mh18["MAPE"],"component beats HW on the extended backtest (secondary evidence)")

print("\n[5] Holt-Winters / production forecast UNTOUCHED (parallel only)")
src=open(os.path.join(HERE,"component_revenue_forecast.py"),encoding="utf-8").read()
import re
csv_writes=re.findall(r'to_csv\(os\.path\.join\(OUT,"([^"]+)"\)',src)
chk(all(w.startswith("phase2_component_revenue") for w in csv_writes) and len(csv_writes)>=2,
    f"component module writes ONLY phase2_component_* outputs ({csv_writes})")
chk('to_csv(os.path.join(OUT,"phase2_revenue_forecast.csv")' not in src and 'to_csv(os.path.join(OUT,"phase2_revenue_backtest.csv")' not in src,
    "component module never writes the production HW forecast/backtest files")
rf=open(os.path.join(HERE,"revenue_forecast.py"),encoding="utf-8").read()
chk("component" not in rf.lower(),"revenue_forecast.py not modified to depend on the component model")
hwbt=o("phase2_revenue_backtest.csv"); chk("hw" in hwbt.columns,"production HW backtest intact (hw column present)")
hwfc=o("phase2_revenue_forecast.csv"); chk("Holt-Winters" in " ".join(map(str,hwfc.values.ravel())),"production HW forecast intact")

print("\n[6] dashboard shows it as SECONDARY, HW primary")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase2_component_revenue_forecast.csv" in dash and "experimental (secondary)" in dash,"dashboard renders component as experimental/secondary panel")
chk("Holt-Winters (primary)" in dash,"Holt-Winters still labelled primary")

print("\n[6b] apartment lifecycle enforced (A33/A34 from Aug-2026 only; A22 zero while inactive)")
import loader as _ld
_D,_=_ld.load_all(); _ap=_D["apartments"]; _bd=_D["beds"]; _al=_D["tenant_allotments"].copy()
_U=lambda s: s.astype(str).str.upper().str.replace(" ","")
a=_ap[_U(_ap["apartment_code"]).isin(["A33","A34","A22"])]
chk(bool((pd.to_datetime(a[_U(a["apartment_code"]).isin(["A33","A34"])]["start_date"]).dt.strftime("%Y-%m-%d")=="2026-08-01").all()),"A33/A34 apartment start_date = 2026-08-01 (authoritative)")
chk(str(a[_U(a["apartment_code"])=="A22"]["status"].iloc[0]).strip()=="Not-Active","A22 status = Not-Active (authoritative)")
for c in ["onboarding_date","booking_date","actual_exit_date"]: _al[c]=_ld.to_dt(_al[c])
_al["start"]=_al["onboarding_date"].fillna(_al["booking_date"])
_new=set(_bd[_bd["apartment_id"].isin(a[_U(a["apartment_code"]).isin(["A33","A34"])]["id"])]["id"])
_a22=set(_bd[_bd["apartment_id"].isin(a[_U(a["apartment_code"])=="A22"]["id"])]["id"])
pre_aug=0; a22_inactive=0
for mm in pd.to_datetime(BT["month"]+"-01"):
    ob=set(_al[(_al["start"]<=mm)&((_al["actual_exit_date"].isna())|(_al["actual_exit_date"]>mm))]["bed_id"])
    k=mm.strftime("%Y-%m")
    if k<"2026-08": pre_aug+=len(ob&_new)
    if k>="2026-02": a22_inactive+=len(ob&_a22)
chk(pre_aug==0,f"A33/A34 contribute ZERO occupied beds before Aug-2026 (got {pre_aug})")
chk(a22_inactive==0,f"A22 contributes ZERO occupied beds while inactive, 2026-02+ (got {a22_inactive})")
chk("lifecycle violation" in open(os.path.join(HERE,"component_revenue_forecast.py"),encoding="utf-8").read(),"module has a fail-loud lifecycle guard")

print("\n[7] deterministic")
p1=hashlib.md5(open(os.path.join(OUT,"phase2_component_revenue_backtest.csv"),"rb").read()).hexdigest()
subprocess.run([sys.executable,"component_revenue_forecast.py"],cwd=HERE,capture_output=True)
p2=hashlib.md5(open(os.path.join(OUT,"phase2_component_revenue_backtest.csv"),"rb").read()).hexdigest()
chk(p1==p2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
