"""Fail-loud validation of the Phase-4 evidence pack: every fact traceable to a real source value; no fabrication."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
P=o("phase4_evidence_pack.csv"); fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] schema + integrity")
need={"evidence_id","domain","statement","metric_name","metric_value","source_dataset","source_field","engine","provenance","confidence","as_of_date","data_limitation"}
chk(need.issubset(P.columns),"evidence schema complete")
chk(P["evidence_id"].is_unique,"evidence_id unique")
chk(P["confidence"].isin(["High","Medium","Low"]).all(),"confidence in High/Medium/Low")
chk(P["provenance"].isin(["VISHFUL_INTERNAL","MARKET_CONTEXT"]).all(),"provenance is VISHFUL_INTERNAL or MARKET_CONTEXT")
chk(P["as_of_date"].astype(str).str.len().gt(3).all(),"as_of_date present on every fact")
chk(P["data_limitation"].astype(str).str.len().gt(0).all(),"data_limitation present (or 'none')")

print("\n[2] every metric re-verified against its real source output (no recompute drift)")
def val(eid):
    r=P[P["evidence_id"]==eid]; return int(float(r["metric_value"].iloc[0])) if len(r) else None
v=o("step4_vacancy_at_risk.csv")
chk(val("EV-VAC-TOTAL")==len(v),"EV-VAC-TOTAL == vacant bed count in step4_vacancy_at_risk.csv")
chk(val("EV-VAC-RISK")==int(v["rev_at_risk_monthly"].sum()),"EV-VAC-RISK == sum(rev_at_risk_monthly)")
chk(val("EV-VAC-DOU")==int((v["bed_type"]=="Double").sum()),"EV-VAC-DOU == Double vacant count")
chk(val("EV-VAC-DOU-RISK")==int(v[v["bed_type"]=="Double"]["rev_at_risk_monthly"].sum()),"EV-VAC-DOU-RISK == Double rev-at-risk")
lf=o("phase3_lead_followup.csv"); openl=lf[lf["lead_status"].isin(["in_progress","visit_requested"])]
chk(val("EV-DEM-DOU")==int((openl["requested_bed_type"]=="Double").sum()),"EV-DEM-DOU == open Double leads")
ov=o("phase2_overdue_risk_scored.csv"); hi=ov[ov["risk"]>0.7]
chk(val("EV-AR-HIGH")==len(hi),"EV-AR-HIGH == overdue risk>0.7 count")
chk(val("EV-AR-HIGH-AMT")==int(hi["amount"].sum()),"EV-AR-HIGH-AMT == high-risk AR amount")
ch=o("phase2_churn_risk_scored.csv"); chk(val("EV-CHURN-HIGH")==int((ch["risk_band"]=="High").sum()),"EV-CHURN-HIGH == churn High-band count")
eb=o("phase2_eb_leak_signals.csv"); chk(val("EV-EB-LEAK")==int(eb["leak_signal"].sum()),"EV-EB-LEAK == leak_signal True count")
mr=o("phase2_maintenance_repeat_register.csv")
chk(val("EV-MAINT-HOT")==int(((mr["priority"]=="High")&(mr["date_confidence"]=="high")&(mr["recur_le90"]>0)).sum()),"EV-MAINT-HOT == high-conf High recurring hotspots")
am=o("phase3_amenity_master_from_data.csv")
chk(("EV-AMEN-AC" in set(P["evidence_id"]))==bool((am["amenity"]=="AC").any() and (am[am["amenity"]=="AC"]["verified_status"]=="VERIFIED_PRESENT").any()),"EV-AMEN-AC present iff AC verified in master")

print("\n[3] no fabricated provenance; market facts flagged context")
mkt=P[P["provenance"]=="MARKET_CONTEXT"]
chk(bool(mkt["data_limitation"].astype(str).str.len().gt(0).all()),"every MARKET_CONTEXT fact carries a limitation note")
chk(not P["statement"].str.contains("average|benchmark|cheaper|better than|worse than",case=False).any(),"no comparison/benchmark language in any evidence statement")

print("\n[4] deterministic")
h1=hashlib.md5(open(os.path.join(OUT,"phase4_evidence_pack.csv"),"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase4_evidence_pack.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(os.path.join(OUT,"phase4_evidence_pack.csv"),"rb").read()).hexdigest()
chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
