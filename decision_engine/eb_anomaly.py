"""
Phase 2 - Deterministic EB anomaly engine (NO ML, NO forecasting).
- Read-only source CSVs.
- Parse billing_month %b-%y; split valid vs invalid readings (flag invalids, never drop silently).
- Per-apartment robust z (median/MAD, 3.5) + apartment x month-season adjustment where supported (else fallback).
- Explainable anomaly_type / severity / recommended_action. Cost/recovery = secondary only.
Outputs: phase2_eb_anomalies.csv (per reading), phase2_eb_anomaly_by_apartment.csv (profile).
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

# 2. parse billing_month %b-%y -> chronological month
er["month"]=pd.to_datetime(er["billing_month"].astype(str), format="%b-%y", errors="coerce")
er["season"]=er["month"].dt.month
bad_month=int(er["month"].isna().sum())

# 3/4. valid vs invalid
er["valid"]=(er["units_consumed"]>0) & (er["reading_end"]>=er["reading_start"])
er["invalid_reason"]=np.where(er["reading_end"]<er["reading_start"],"reading_end<reading_start",
                     np.where(er["units_consumed"]<=0,"units<=0",""))

MAD_K=1.4826; THR=3.5; MIN_APT=4; MIN_SEASON=3

# 6. per-apartment robust-z on VALID readings only
valid=er[er["valid"]].copy()
def apt_stats(g):
    u=g["units_consumed"]; med=u.median(); mad=(u-med).abs().median()
    return pd.Series({"apt_med":med,"apt_mad":mad,"apt_n":len(u)})
aps=valid.groupby("apartment_id").apply(apt_stats)
er=er.merge(aps,left_on="apartment_id",right_index=True,how="left")
# 7. seasonal (apartment x season) stats where enough history
def sea_stats(g):
    u=g["units_consumed"]; return pd.Series({"sea_med":u.median(),"sea_mad":(u-u.median()).abs().median(),"sea_n":len(u)})
sea=valid.groupby(["apartment_id","season"]).apply(sea_stats)
er=er.merge(sea,left_on=["apartment_id","season"],right_index=True,how="left")

def robust_z(x,med,mad):
    if pd.isna(med) or pd.isna(mad) or mad==0: return np.nan
    return (x-med)/(MAD_K*mad)

rows=[]
for _,r in er.iterrows():
    u=r["units_consumed"]
    if not r["valid"]:
        rows.append(dict(anomaly_type="invalid", severity="High", baseline_method="none",
            expected_range="", deviation_score=np.nan,
            recommended_action="Verify meter / reset / data entry",
            reason=f"invalid_reading: {r['invalid_reason']}")); continue
    # choose baseline: seasonal if supported, else apartment, else insufficient
    if pd.notna(r["sea_n"]) and r["sea_n"]>=MIN_SEASON and pd.notna(r["sea_mad"]) and r["sea_mad"]>0:
        method="seasonal"; med,mad,n=r["sea_med"],r["sea_mad"],r["sea_n"]
    elif pd.notna(r["apt_n"]) and r["apt_n"]>=MIN_APT and pd.notna(r["apt_mad"]) and r["apt_mad"]>0:
        method="apartment_fallback"; med,mad,n=r["apt_med"],r["apt_mad"],r["apt_n"]
    else:
        rows.append(dict(anomaly_type="normal", severity="None", baseline_method="insufficient_history",
            expected_range="", deviation_score=np.nan, recommended_action="Monitor (no baseline)",
            reason="insufficient history for a robust baseline")); continue
    z=robust_z(u,med,mad)
    lo=med-THR*MAD_K*mad; hi=med+THR*MAD_K*mad
    if z>THR:  atype,sev,act="high_consumption","High" if z>6 else "Medium","Possible abnormal consumption — inspect for leak or usage change"
    elif z<-THR: atype,sev,act="low_consumption","Medium","Unusually low — verify meter/occupancy/vacancy"
    else: atype,sev,act="normal","None","Monitoring"
    rows.append(dict(anomaly_type=atype, severity=sev, baseline_method=method,
        expected_range=f"{lo:.0f}-{hi:.0f}", deviation_score=round(z,2),
        recommended_action=act, reason=f"z={z:.2f} vs {method} baseline (n={int(n)}, med={med:.0f})"))
out=pd.concat([er.reset_index(drop=True), pd.DataFrame(rows)],axis=1)

# 13. per-reading output
cols=["apartment_id","property_id","billing_month","month","units_consumed","anomaly_type","severity",
      "baseline_method","expected_range","deviation_score","recommended_action","reason"]
res=out[cols].sort_values(["anomaly_type","deviation_score"],ascending=[True,False])
res.to_csv(os.path.join(OUT,"phase2_eb_anomalies.csv"),index=False)

# 14. per-apartment profile
prof=out.groupby("apartment_id").agg(
    readings=("units_consumed","size"),
    invalid=("anomaly_type",lambda s:(s=="invalid").sum()),
    high=("anomaly_type",lambda s:(s=="high_consumption").sum()),
    low=("anomaly_type",lambda s:(s=="low_consumption").sum()),
    avg_units=("units_consumed",lambda s:s[s>0].mean())).reset_index()
prof["anomalies"]=prof["invalid"]+prof["high"]+prof["low"]
prof["anomaly_rate"]=(prof["anomalies"]/prof["readings"]).round(3)
prof=prof.sort_values(["high","invalid","low"],ascending=False)
prof.to_csv(os.path.join(OUT,"phase2_eb_anomaly_by_apartment.csv"),index=False)

# ---- signal overlap: robust-z-only vs seasonal-only vs both (on valid, statistical) ----
v=out[out["valid"]].copy()
zap=v.apply(lambda r: robust_z(r["units_consumed"],r["apt_med"],r["apt_mad"]),axis=1)
zse=v.apply(lambda r: robust_z(r["units_consumed"],r["sea_med"],r["sea_mad"]) if (pd.notna(r["sea_n"]) and r["sea_n"]>=MIN_SEASON) else np.nan,axis=1)
fa=(zap.abs()>THR); fs=(zse.abs()>THR)
both=int((fa&fs).sum()); apt_only=int((fa&~fs.fillna(False)).sum()); sea_only=int((fs.fillna(False)&~fa).sum())
fallback=int((out["baseline_method"]=="apartment_fallback").sum())
insuff=int((out["baseline_method"]=="insufficient_history").sum())

# ---- 11. quantify ----
tot=len(out); nvalid=int(out["valid"].sum()); ninv=tot-nvalid
stat_anom=int(out["anomaly_type"].isin(["high_consumption","low_consumption"]).sum())
nhigh=int((out["anomaly_type"]=="high_consumption").sum()); nlow=int((out["anomaly_type"]=="low_consumption").sum())
print("="*70); print("DETERMINISTIC EB ANOMALY ENGINE — RESULTS"); print("="*70)
print(f"total readings={tot} | valid={nvalid} | invalid(flagged)={ninv} | bad billing_month parse={bad_month}")
print(f"apartments covered={out['apartment_id'].nunique()}")
print(f"statistical anomalies={stat_anom}  (high={nhigh}, low={nlow})  invalid_anomalies={ninv}")
print(f"overall anomaly rate={ (stat_anom+ninv)/tot:.1%}")
print(f"signal overlap (valid, |z|>3.5): apartment-only={apt_only}  seasonal-only={sea_only}  both={both}")
print(f"seasonal baseline used vs apartment fallback: fallback(n<{MIN_SEASON} season)={fallback}  insufficient_history={insuff}")
print("\nTop abnormal apartments:")
print(prof.head(8)[["apartment_id","readings","invalid","high","low","anomaly_rate","avg_units"]].to_string(index=False))
print("\nOutputs: phase2_eb_anomalies.csv, phase2_eb_anomaly_by_apartment.csv")
print("NOTE: cost/recovery cross-check intentionally NOT the anomaly target (eb_payments Apr-Jun only; eb_tenant_shares.tenant_id 82% null).")
