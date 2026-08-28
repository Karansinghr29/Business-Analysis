"""Fail-loud validation for the Decision Execution -> KPI -> Outcome layer. Read-only + determinism."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
E=o("phase3_decision_execution_analytics.csv"); DEC=o("phase3_business_decisions.csv")
bb=E[E["is_backbone"]==True]; opp=E[E["is_backbone"]==False]
fails=[]; blob=" ".join(map(str,E.values.ravel())).lower()
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] all 14 decision IDs preserved; no duplicate; existing decisions unmodified")
chk(set(bb["decision_id"])==set(DEC["decision_id"]),"backbone ids == the 14 existing decision ids")
chk(len(bb)==14 and bb["decision_id"].is_unique,"exactly 14 backbone rows, unique")
chk(E["decision_id"].is_unique,"no duplicated decision/opportunity id")
chk(len(DEC)==14,"phase3_business_decisions.csv still 14 (unmodified)")

print("\n[2] no fabricated ROI/uplift/savings/conversion; ₹ values are measured baselines only")
# flag FABRICATED figures only — bare 'roi' is fine (DEC-MKT-ROI-GAP says ROI is UNAVAILABLE)
BAD=["uplift","savings of","% increase","increased revenue by","projected revenue","expected uplift","revenue gain"]
chk(not any(b in blob for b in BAD),"no fabricated uplift/savings/revenue-gain language")
chk(re.search(r"roi\s*[:=]?\s*\d|conversion\s*(rate)?\s*[:=]?\s*\d+\s*%|uplift\s*\d",blob) is None,
    "no fabricated ROI/conversion figure")
# outcome column must be 'Outcome unavailable' everywhere (no computed outcome)
chk(bool((E["outcome"]=="Outcome unavailable").all()),"every outcome = 'Outcome unavailable' (none fabricated)")
chk(bool((E["outcome_availability"]=="pending_post_action_data").all()),"outcome_availability = pending_post_action_data")

print("\n[3] Unknown/Unavailable preserved")
unav=bb[bb["baseline_value"]=="UNAVAILABLE"]
chk(bool((unav["status"]=="not_measurable_pending_data").all()) if len(unav) else True,"UNAVAILABLE baselines -> not_measurable_pending_data")
chk(bool((E["target_value"]=="UNKNOWN").all()),"target_value = UNKNOWN everywhere (no invented target)")
# owner-verify opportunities keep UNAVAILABLE baseline (unknown not converted to available/absent)
ov=opp[opp["status"]=="owner_verify_first"]
chk(bool((ov["baseline_value"]=="UNAVAILABLE").all()) if len(ov) else True,"owner-verify opportunities baseline UNAVAILABLE (unknown preserved)")
chk(not ov["measurement_method"].str.contains("available|present|absent",case=False).any() if len(ov) else True,
    "owner-verify opportunities never assert available/absent")

print("\n[4] baseline periods valid + KPI traceable")
def valid_period(p):
    p=str(p)
    return (p in ("current snapshot","cumulative (all recorded)","UNAVAILABLE","UNKNOWN")
            or re.match(r"^\d{4}-\d{2}\.\.\d{4}-\d{2}$",p) is not None)
chk(bool(E["baseline_period"].apply(valid_period).all()),"baseline_period values valid (period range / snapshot / cumulative / unavailable)")
meas=bb[bb["status"]=="baseline_established_pending_action"]
chk(bool(meas["data_source"].astype(str).str.len().gt(0).all()),"every measurable KPI cites a data_source (traceable)")
chk("data_confidence" in E.columns,"data_confidence field present (limitations surfaced)")

print("\n[5] opportunities separate from backbone")
chk(bool((opp["is_backbone"]==False).all()) and len(opp)==6,"6 review opportunities kept separate (is_backbone=False)")
chk(not set(opp["decision_id"]) & set(DEC["decision_id"]),"opportunity ids do not collide with backbone decision ids")

print("\n[6] no competitor comparison")
BADC=["cheaper","best pg","worst pg","competitor rank","benchmark against","vs competitor","better than competitor"]
chk(not any(b in blob for b in BADC),"no competitor comparison/ranking")

print("\n[7] deterministic + isolation")
p=os.path.join(OUT,"phase3_decision_execution_analytics.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_decision_execution_analytics.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")
chk(re.search(r"gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}",blob) is None,"no API key leak")
chk(len(o("phase3_competitor_master.csv"))==115,"competitor master unchanged (115)")
chk(len(o("phase3_review_decision_candidates.csv"))==16,"review decision layer unchanged (16)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
# dashboard MAY read this layer (approved ⑩ integration) but must do so read-only (no writes)
chk(not re.search(r"\.to_csv\(|\.to_parquet\(|open\([^)]*,\s*['\"][wa]\+?b?['\"]",dash),
    "dashboard performs no file writes (⑩ KPI display is read-only)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
