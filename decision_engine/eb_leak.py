"""
Phase-2 EB leak-INVESTIGATION enhancement (deterministic, no ML).
Does NOT replace eb_anomaly.py or its outputs — writes NEW files only.
Reuses the validated apartment robust-baseline methodology + temporally-valid occupancy.
Never labels 'confirmed leak' — only 'possible abnormal consumption — inspect'.
Read-only source CSVs.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np, pandas as pd
from loader import load_all, num, to_dt

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)
D,_=load_all()
er=D["electricity_readings"].copy()
for c in ["reading_start","reading_end","units_consumed","unit_cost"]: er[c]=num(er[c])
er["month"]=pd.to_datetime(er["billing_month"].astype(str),format="%b-%y",errors="coerce")
er=er.dropna(subset=["month","apartment_id"]).copy()

# temporally-valid occupancy per apartment x billing_month
al=D["tenant_allotments"].copy()
for c in ["onboarding_date","booking_date","actual_exit_date"]: al[c]=to_dt(al[c])
al["start"]=al["onboarding_date"].fillna(al["booking_date"])
er["occ_beds"]=er.apply(lambda r: int(len(al[(al["apartment_id"]==r["apartment_id"])&(al["start"]<=r["month"])&
                        ((al["actual_exit_date"].isna())|(al["actual_exit_date"]>r["month"]))])), axis=1)

er["valid"]=(er["units_consumed"]>0)&(er["reading_end"]>=er["reading_start"])
er["invalid_reason"]=np.where(er["reading_end"]<er["reading_start"],"reading_end<reading_start",
                     np.where(er["units_consumed"]<=0,"units<=0",""))
v=er[er["valid"]].copy()
v["med"]=v.groupby("apartment_id")["units_consumed"].transform("median")
v["mad"]=v.groupby("apartment_id")["units_consumed"].transform(lambda u:(u-u.median()).abs().median())
v["baseline_p75"]=v.groupby("apartment_id")["units_consumed"].transform(lambda u:u.quantile(.75))
v["z"]=np.where(v["mad"]>0,(v["units_consumed"]-v["med"])/(1.4826*v["mad"]),0.0)
v=v.sort_values(["apartment_id","month"])
v["previous_units"]=v.groupby("apartment_id")["units_consumed"].shift(1)
# consecutive months above apartment p75
def consec(g):
    out=[]; run=0
    for above in (g["units_consumed"]>g["baseline_p75"]).astype(int):
        run=run+1 if above else 0; out.append(run)
    return pd.Series(out,index=g.index)
v["consecutive_high_months"]=v.groupby("apartment_id",group_keys=False).apply(consec)
er=er.merge(v[["z","med","mad","baseline_p75","previous_units","consecutive_high_months"]],left_index=True,right_index=True,how="left")

def classify(r):
    if not r["valid"]:
        return ("invalid_meter_reading","High","none",np.nan,"high",
                f"invalid: {r['invalid_reason']}","Verify meter / reset / data entry",False)
    z=r["z"]; occ=r["occ_beds"]; prev=r["previous_units"]; ch=r["consecutive_high_months"]
    base=f"z={z:.2f} vs apartment robust baseline (med={r['med']:.0f})"
    # priority
    if occ<=1 and z>2:
        note=" occ<=1 bed" + (" (occ=0: may be common-area load / appliances left on / occupancy-data limits)" if occ==0 else "")
        return ("low_occupancy_high_consumption","High","apartment",round(z,2),"high",
                base+note,"Possible abnormal consumption — inspect meter/plumbing/usage",True)
    if pd.notna(prev) and prev>0 and r["units_consumed"]>2*prev and z>2:
        return ("sudden_increase","Medium","apartment",round(z,2),"medium",
                base+f"; >2x prev month ({prev:.0f})","Possible abnormal consumption — inspect meter/plumbing/usage",True)
    if pd.notna(ch) and ch>=3:
        return ("sustained_high_consumption","Medium","apartment",round(z,2),"medium",
                base+f"; {int(ch)} consecutive months > p75","Possible abnormal consumption — inspect usage pattern",False)
    if z>3.5:
        return ("abnormal_high_consumption","High" if z>6 else "Medium","apartment",round(z,2),"high",
                base,"Possible abnormal consumption — inspect meter/plumbing/usage",True)
    return ("normal","None","apartment",round(z,2) if pd.notna(z) else np.nan,"n/a","within baseline","Monitor",False)

res=er.apply(classify,axis=1,result_type="expand")
res.columns=["anomaly_type","severity","baseline_method","deviation_score","confidence","reason","recommended_action","leak_signal"]
out=pd.concat([er.reset_index(drop=True),res.reset_index(drop=True)],axis=1)

cols=["apartment_id","property_id","billing_month","month","units_consumed","occ_beds","previous_units",
      "baseline_p75","consecutive_high_months","anomaly_type","severity","baseline_method","deviation_score",
      "confidence","leak_signal","reason","recommended_action"]
out[cols].sort_values(["leak_signal","deviation_score"],ascending=[False,False]).to_csv(os.path.join(OUT,"phase2_eb_leak_signals.csv"),index=False)

# summary
def cnt(t): return int((out["anomaly_type"]==t).sum())
def apts(t): return int(out.loc[out["anomaly_type"]==t,"apartment_id"].nunique())
summ=pd.DataFrame([
 ("invalid_meter_reading",cnt("invalid_meter_reading"),apts("invalid_meter_reading")),
 ("abnormal_high_consumption",cnt("abnormal_high_consumption"),apts("abnormal_high_consumption")),
 ("sustained_high_consumption",cnt("sustained_high_consumption"),apts("sustained_high_consumption")),
 ("low_occupancy_high_consumption",cnt("low_occupancy_high_consumption"),apts("low_occupancy_high_consumption")),
 ("sudden_increase",cnt("sudden_increase"),apts("sudden_increase")),
 ("possible_leak_investigation(total leak_signal)",int(out["leak_signal"].sum()),int(out.loc[out["leak_signal"],"apartment_id"].nunique())),
],columns=["signal","readings","distinct_apartments"])
summ.to_csv(os.path.join(OUT,"phase2_eb_leak_summary.csv"),index=False)
print("EB LEAK signals written. Summary:"); print(summ.to_string(index=False))
print("NOTE: 'possible' only — NOT confirmed leak. Missing for confirmation: water/sub-meter/appliance data; occ counts allotments not presence; common-area load may be on apartment meter.")
