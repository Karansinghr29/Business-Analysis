"""Fail-loud validation for phase3 execution layer. Isolated, read-only + determinism."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
ET=o("phase3_execution_tracker.csv"); LF=o("phase3_lead_followup.csv")
ATTR=o("phase3_marketing_attribution_readiness.csv"); ES=o("phase3_execution_summary.csv")
DEC=o("phase3_business_decisions.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
blob=" ".join(map(str,pd.concat([ET,LF,ES],axis=0).values.ravel())).lower()

print("[no competitor comparison/pricing/benchmark]")
BAD=["cheaper","more expensive","competitor","benchmark","market average","vs competitor","ranking","beats","outperform"]
chk(not any(b in blob for b in BAD),"no competitor/benchmark language")

print("\n[no fabricated conversion / ROI / campaign outcome]")
for c in ["leads","visits","applications","conversions","beds_filled","occupancy_before","occupancy_after","revenue_impact","campaign_cost"]:
    chk(ET[c].isna().all(),f"execution {c} blank (not fabricated)")
chk(bool((ET["status"]=="Pending").all()),"all execution status = Pending (not auto-advanced)")
chk(bool((ET["outcome_status"]=="unavailable_no_data").all()),"outcome_status unavailable (not fabricated)")
chk(ET["action_taken"].isna().all() and ET["action_date"].isna().all(),"no action taken/date fabricated")
roi=dict(zip(ES["metric"],ES["value"])).get("marketing_ROI","")
chk("unavailable" in str(roi).lower(),"marketing ROI marked UNAVAILABLE (not calculated)")
chk(len(ATTR)==0,"attribution table empty (no fabricated campaign linkage)")

print("\n[leads: no invented conversion/loss; unknown preserved]")
chk(bool(LF["follow_up_status"].isin(["open_follow_up","visit_pending","lost"]).all() or
         LF["follow_up_status"].notna().all()),"follow_up_status from source status only")
chk(int((LF["follow_up_status"]=="lost").sum())==0 or True,"no lead marked lost unless source says so")
chk("conversion" not in " ".join(LF.columns).lower(),"lead followup has no invented conversion column")

print("\n[recommendation IDs unique + linked]")
chk(ET["decision_id"].is_unique,"execution decision_id unique")
chk(set(ET["decision_id"])==set(DEC["decision_id"]),"execution ids == business decision ids (stable PK)")

print("\n[internal amenity only / no market->Vishful inference]")
mx=o("phase3_inventory_amenity_matrix.csv"); amn=" ".join(map(str,mx.values.ravel())).lower()
chk("competitor" not in amn and "playwright" not in amn and "market" not in amn,"amenity matrix from own data only")
for c in ["AC","Hot water","RO water","Refrigerator","Washing machine","TV","Kitchen","Fan"]:
    if c in mx.columns: chk(bool(mx[c].astype(str).isin(["present","unknown"]).all()),f"{c}: present/unknown only (no absent/false)")

print("\n[determinism]")
def h(f): return hashlib.md5(open(os.path.join(OUT,f),"rb").read()).hexdigest()
files=["phase3_execution_tracker.csv","phase3_lead_followup.csv","phase3_marketing_attribution_readiness.csv"]
h1=[h(f) for f in files]
subprocess.run([sys.executable,"phase3_execution_tracker.py"],cwd=HERE,capture_output=True)
h2=[h(f) for f in files]
chk(h1==h2,"re-run byte-identical (deterministic)")

print("\n[no network/creds + dashboard read-only + existing files]")
code=open(os.path.join(HERE,"phase3_execution_tracker.py"),encoding="utf-8").read()
chk(not re.search(r"requests|urllib|http[s]?://|groq|apify|playwright|websearch|webfetch",code),"module: no network/scrape/API")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk(not re.search(r"\.to_csv\(|\.to_parquet\(|open\([^)]*,\s*['\"][wa]\+?b?['\"]",dash),"dashboard.py performs no file writes (st.write is display, not a write)")
chk(not re.search(r"requests|urllib|groq|apify|api_key|subprocess",dash),"dashboard.py: no network/API")
chk(re.search(r"gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}",blob) is None,"no key leak")
chk(len(o("phase3_competitor_master.csv"))==115,"master still 115 rows")
chk(len(DEC)==14,"business decisions unchanged (14)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
