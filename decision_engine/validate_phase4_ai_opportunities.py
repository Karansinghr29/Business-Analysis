"""Fail-loud validation of Phase-4 AI opportunities: evidence-grounded, guard-compliant, no competitor comparison,
no fabricated metrics, owner-verify preserved, execution-tracker-compatible ids, deterministic."""
from __future__ import annotations
import os, sys, subprocess, hashlib, re, glob
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import phase4_guard as guard
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
A=o("phase4_ai_opportunities.csv"); RJ=o("phase4_ai_opportunities_rejected.csv"); P=o("phase4_evidence_pack.csv")
packval={r["evidence_id"]:(int(float(r["metric_value"])) if str(r["metric_value"]).replace('.','',1).lstrip('-').isdigit() else None) for _,r in P.iterrows()}
ids=set(P["evidence_id"]); fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] structure")
need={"recommendation_id","opportunity","evidence_ids","why_it_matters","suggested_action","expected_kpi","confidence","data_limitation","owner_verify_required","provenance","guard_status"}
chk(need.issubset(A.columns),"opportunity schema complete")
chk(len(A)>0,f"opportunities generated ({len(A)})")
chk((A["guard_status"]=="passed").all(),"every displayed opportunity is guard-passed")

print("\n[2] every recommendation is evidence-grounded")
for _,r in A.iterrows():
    eids=str(r["evidence_ids"]).split("|")
    chk(all(e in ids for e in eids),f"{r['recommendation_id']}: all evidence_ids exist in pack")

print("\n[3] confidence + limitation mandatory; owner-verify preserved")
chk(A["confidence"].isin(["High","Medium","Low"]).all(),"confidence present on every rec")
chk(A["data_limitation"].astype(str).str.len().gt(0).all(),"data_limitation present on every rec")
ov=A[A["owner_verify_required"]==True]
chk(bool(ov["suggested_action"].str.contains("verify",case=False).all()) if len(ov) else True,"owner-verify recs instruct internal verification (never assert)")
chk(len(ov)>=1,"owner-verify items exist (Food/Parking/Security/Power own-status unknown)")

print("\n[4] NO competitor comparison / fabricated metrics anywhere in phase4 opportunity text")
for _,r in A.iterrows():
    blob=" ".join(str(r[c]) for c in ["opportunity","why_it_matters","suggested_action","expected_kpi"]).lower()
    bad=[b for b in guard.BLOCK_PHRASES if b in blob]
    fab=[p for p in guard.FAB_PATTERNS if re.search(p,blob)]
    chk(not bad,f"{r['recommendation_id']}: no competitor-comparison phrase ({bad})")
    chk(not fab,f"{r['recommendation_id']}: no fabricated-metric pattern ({fab})")

print("\n[5] numeric traceability — every number in text is a referenced evidence value")
for _,r in A.iterrows():
    eids=str(r["evidence_ids"]).split("|")
    allowed={packval[e] for e in eids if packval.get(e) is not None}
    text=" ".join(str(r[c]) for c in ["opportunity","why_it_matters","suggested_action","expected_kpi"])
    stray=guard._nums(text)-allowed
    chk(not stray,f"{r['recommendation_id']}: numbers {sorted(guard._nums(text))} all trace to evidence (stray={sorted(stray)})")

print("\n[6] unavailable handling + no 'unavailable->0'")
for _,r in A.iterrows():
    lim=str(r["data_limitation"]); kpi=str(r["expected_kpi"])
    chk(("Unavailable" in kpi) or (kpi.strip()!="" and kpi.strip()!="0"),f"{r['recommendation_id']}: KPI not blank/zero (uses Unavailable literal if absent)")

print("\n[7] rejected file disjoint; ids execution-tracker-compatible")
chk(set(A["recommendation_id"]).isdisjoint(set(RJ["recommendation_id"])) if len(RJ) else True,"passed and rejected ids disjoint")
chk(A["recommendation_id"].astype(str).str.match(r"^AIREC-").all(),"recommendation_id uses AIREC- key format (execution-tracker compatible)")
et=o("phase3_execution_tracker.csv")
chk("decision_id" in et.columns,"execution_tracker has decision_id key to receive future outcomes")

print("\n[8] compliance grep across ALL phase4 outputs")
blob=""
for f in glob.glob(os.path.join(OUT,"phase4_*.csv")):
    blob+=open(f,encoding="utf-8").read().lower()
chk(not any(b in blob for b in ["cheaper","more expensive","better than vishful","worse than vishful","market average","rank competitor","vishful should charge"]),"no competitor-comparison string in any phase4_*.csv")

print("\n[9] deterministic")
h1=hashlib.md5(open(os.path.join(OUT,"phase4_ai_opportunities.csv"),"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase4_opportunity_rules.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(os.path.join(OUT,"phase4_ai_opportunities.csv"),"rb").read()).hexdigest()
chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
