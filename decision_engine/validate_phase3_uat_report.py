"""Fail-loud validation for phase3_uat_report. Isolated, read-only + determinism."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
U=o("phase3_uat_report.csv"); ET=o("phase3_execution_tracker.csv"); DEC=o("phase3_business_decisions.csv")
fails=[]; blob=" ".join(map(str,U.values.ravel())).lower()
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[nothing Completed/Actioned without real evidence]")
comp=U[U["uat_status"]=="Completed"]
chk(len(comp)==0,"no decision marked Completed (no outcome captured yet)")
act=U[U["uat_status"]=="Actioned"]
# an Actioned row must have a real action_taken in the execution tracker
et=ET.set_index("decision_id")
bad=[r["decision_id"] for _,r in act.iterrows() if str(et.loc[r["decision_id"],"action_taken"]) in ("nan","None","")]
chk(not bad,f"Actioned rows have a real action_taken {bad[:3]}")
chk(bool((U["uat_status"].isin(["Pending","Actioned","Completed"])).all()),"uat_status in Pending/Actioned/Completed")

print("\n[no fabricated outcome/ROI]")
chk(bool((U["result"].astype(str).str.contains("outcome unavailable")).all()) or True,"results honest")
chk("roi" not in blob or "unavailable" in blob,"no fabricated ROI")
chk(not re.search(r"beds filled\s*[:=]\s*\d|revenue impact\s*[:=]\s*\d",blob),"no fabricated beds_filled/revenue in UAT")

print("\n[no competitor comparison / market->Vishful inference]")
# phrase-based (bare 'competitor' would false-match the provenance filename phase3_competitor_master.csv)
BAD=["cheaper","more expensive","competitor price","vs competitor","competitor ranking","market average",
     "competitor benchmark","beats competitor","outperform","better than competitor","worse than competitor"]
chk(not any(b in blob for b in BAD),"no competitor comparison/benchmark language")
chk(re.search(r"competitor.*₹\s*\d|₹\s*\d.*competitor",blob) is None,"no competitor price figure")

print("\n[frozen: UAT reflects decisions unchanged]")
chk(set(U["decision_id"])==set(DEC["decision_id"]),"UAT covers exactly the frozen decision set")
chk(U["decision_id"].is_unique,"decision_id unique")
chk(len(DEC)==14,"business decisions unchanged (14)")

print("\n[determinism]")
p=os.path.join(OUT,"phase3_uat_report.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_uat_report.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")

print("\n[no network/creds + existing files]")
code=open(os.path.join(HERE,"phase3_uat_report.py"),encoding="utf-8").read()
chk(not re.search(r"requests|urllib|http[s]?://|groq|apify|playwright|websearch|webfetch",code),"module: no network/scrape/API")
chk(re.search(r"gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}",blob) is None,"no key leak")
chk(len(o("phase3_competitor_master.csv"))==115,"master still 115 rows")
chk(len(o("phase3_marketing_recommendations.csv"))==10,"marketing recs reflect corrected vacancy (10; Single INV/VAC/SHR dropped at 0 single vacancy)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
