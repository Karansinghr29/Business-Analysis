"""Fail-loud validation for phase3_data_readiness layer. Isolated, read-only + determinism."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def rd(f): return pd.read_csv(os.path.join(OUT,f))
AM=rd("phase3_vishful_amenity_master.csv"); AL=rd("phase3_marketing_action_log.csv")
LF=rd("phase3_lead_funnel.csv"); OT=rd("phase3_outcome_tracking.csv")
AUD=rd("phase3_triple_fill_time_audit.csv"); REC=rd("phase3_marketing_recommendations.csv")
VALID_IDS=set(REC["recommendation_id"])
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] no inferred Vishful amenities (all UNKNOWN, no market inference)")
amen=["ac","non_ac","wifi","food","laundry","parking","cctv_security","power_backup"]
chk(all((AM[c].astype(str)=="unknown").all() for c in amen),"every amenity value = 'unknown' (nothing inferred)")
chk(bool((AM["status"]=="pending_owner_input").all()),"amenity status = pending_owner_input")
chk(AM["source_evidence"].isna().all() and AM["verified_by"].isna().all(),"no source/verified_by fabricated")
# no market file referenced as an amenity source
blob_am=open(os.path.join(OUT,"phase3_vishful_amenity_master.csv"),encoding="utf-8").read().lower()
chk("playwright" not in blob_am and "competitor_master" not in blob_am,"amenity master does NOT source from market data")

print("\n[2] no fabricated outcomes / funnel metrics (all null/unknown)")
for c in ["leads","enquiries","visits","applications","conversions","beds_filled"]:
    chk(LF[c].isna().all(),f"lead funnel {c} is null (not fabricated)")
for c in ["occupancy_before","occupancy_after","beds_filled","revenue_impact","campaign_cost"]:
    chk(OT[c].isna().all(),f"outcome {c} is null (not fabricated)")
chk(bool((OT["outcome_status"]=="unavailable_no_data").all()),"outcome_status all unavailable_no_data")
chk(bool((AL["status"]=="not_started").all()),"action_log status all not_started")
chk(AL["action_taken"].isna().all() and AL["action_date"].isna().all(),"no action taken/date fabricated")

print("\n[3] valid recommendation IDs")
for name,df in [("action_log",AL),("lead_funnel",LF),("outcome",OT)]:
    chk(set(df["recommendation_id"]).issubset(VALID_IDS),f"{name} ids ⊆ marketing recommendation ids")
    chk(df["recommendation_id"].is_unique,f"{name} recommendation_id unique")

print("\n[4] valid dates (any populated date must be ISO YYYY-MM-DD)")
dates=pd.concat([AL["action_date"].dropna()])
chk(all(re.match(r"^\d{4}-\d{2}-\d{2}$",str(d)) for d in dates),"all populated dates are ISO (none now)")

print("\n[5] no negative/impossible business metrics")
nums=pd.concat([LF[["leads","enquiries","visits","applications","conversions","beds_filled"]],
                OT[["occupancy_before","occupancy_after","beds_filled","revenue_impact","campaign_cost"]]],axis=0)
bad=nums.apply(pd.to_numeric,errors="coerce")
chk(bool((bad.dropna(how="all")<0).sum().sum()==0),"no negative business metric values")

print("\n[6] Triple vacancy-duration honest: new-inventory KNOWN from operational start; fill-time never manufactured")
known=AUD["duration_known"]==True; unk=~known
# new-inventory Triple beds: duration KNOWN -> days_vacant populated (measured from 2026-08-01, not fabricated)
chk((not known.any()) or bool(AUD.loc[known,"days_vacant"].notna().all()),
    "known-duration Triple beds have days_vacant populated (from operational start, not manufactured)")
# any genuinely UNKNOWN-duration Triple bed: days_vacant MUST stay null (fill-time never fabricated)
chk((not unk.any()) or bool(AUD.loc[unk,"days_vacant"].isna().all()),
    "unknown-duration Triple beds keep days_vacant null (fill-time never manufactured)")
chk(bool(AUD["reason_missing"].astype(str).str.len().gt(0).all()),"duration basis documented per bed")
chk((not known.any()) or bool(AUD.loc[known,"resolution"].astype(str).str.contains("known",case=False).all()),
    "known-duration Triple beds resolved as 'duration known from operational start'")

print("\n[7] no competitor comparison / pricing / market->Vishful inference")
allblob=" ".join(open(os.path.join(OUT,f),encoding="utf-8").read().lower() for f in
    ["phase3_vishful_amenity_master.csv","phase3_marketing_action_log.csv","phase3_lead_funnel.csv",
     "phase3_outcome_tracking.csv","phase3_triple_fill_time_audit.csv"])
BAD=["cheaper","more expensive","competitor price","vs competitor","competitor ranking","market average",
     "beats","outperform","better than competitor"]
chk(not any(b in allblob for b in BAD),"no competitor comparison/pricing language")
chk(re.search(r"₹\s*\d+.*competitor|competitor.*₹\s*\d+",allblob) is None,"no competitor price figure")

print("\n[8] determinism / reproducibility")
def h(f): return hashlib.md5(open(os.path.join(OUT,f),"rb").read()).hexdigest()
files=["phase3_vishful_amenity_master.csv","phase3_marketing_action_log.csv","phase3_lead_funnel.csv",
       "phase3_outcome_tracking.csv","phase3_triple_fill_time_audit.csv"]
h1=[h(f) for f in files]
subprocess.run([sys.executable,"phase3_data_readiness.py"],cwd=HERE,capture_output=True)
h2=[h(f) for f in files]
chk(h1==h2,"re-run byte-identical (deterministic)")

print("\n[9] key leak / existing files unchanged")
chk(re.search(r"gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}",allblob) is None,"no API key leak")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv")))==115,"master still 115 rows")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_marketing_recommendations.csv")))==10,"marketing recs reflect corrected vacancy (10; Single INV/VAC/SHR dropped at 0 single vacancy)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
