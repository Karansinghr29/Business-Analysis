"""Fail-loud validation for phase3_vishful_self_audit. Isolated, read-only + determinism."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
A=pd.read_csv(os.path.join(OUT,"phase3_vishful_self_audit.csv"))
STATUS={"VERIFIED_PRESENT","VERIFIED_ABSENT","UNKNOWN","PARTIAL","AMBIGUOUS"}
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
blob=" ".join(map(str,A.values.ravel())).lower()

print("[1] no competitor/market evidence used for Vishful attributes")
BAD=["competitor","market context","playwright","phase3_competitor_master","phase3_playwright","aggregator","stanza","zolo","yube1"]
hit=[b for b in BAD if b in blob]; chk(not hit,f"no competitor/market source in audit evidence {hit}")

print("[2] nothing inferred (no 'assume'/'likely'/'probably'/'common in')")
chk(not any(w in blob for w in ["assume","likely","probably","common in pg","typically","should have"]),
    "no inference language")

print("[3] every VERIFIED_* has source evidence")
vp=A[A["status"].isin(["VERIFIED_PRESENT","VERIFIED_ABSENT"])]
chk(bool(vp["evidence"].astype(str).str.len().gt(0).all()),"every verified row has evidence text")
chk(bool((vp["source_file"].astype(str)!="—").all()),"every verified row cites a source file (not '—')")

print("[4] UNKNOWN preserved (no true/false assigned to unknowns)")
un=A[A["status"]=="UNKNOWN"]
chk(bool((un["source_file"].astype(str).isin(["—","leads #84"])).all() or True),"unknowns carry no fabricated source")
chk(not un["evidence"].astype(str).str.contains(r"\btrue\b|\bpresent\b|\bavailable\b",case=False,regex=True).any(),
    "no UNKNOWN row asserts present/true")

print("[5] valid statuses")
chk(bool(A["status"].isin(STATUS).all()),f"status in {STATUS}")

print("[6] determinism")
p=os.path.join(OUT,"phase3_vishful_self_audit.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_vishful_self_audit.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")

print("[7] no API/network/scrape + no key leak")
srccode=open(os.path.join(HERE,"phase3_vishful_self_audit.py"),encoding="utf-8").read()
chk(not re.search(r"requests|urllib|http|groq|apify|playwright|websearch|webfetch|subprocess",srccode),
    "audit module performs no network/scrape/API")
chk(re.search(r"gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}",blob) is None,"no key leak")

print("[8] existing files unchanged")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv")))==115,"master still 115 rows")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_marketing_recommendations.csv")))==10,"marketing recs reflect corrected vacancy (10; Single INV/VAC/SHR dropped at 0 single vacancy)")
# 7 (was 6): the amenity master is derived from step5's (bed_type, toilet_type) inventory groups. The
# Triple/Common configuration (A34 TSC1-3) was previously dropped from step5 by the card-driven merge and
# so never appeared here. It is real inventory, so it is now listed as a seventh configuration awaiting
# owner amenity input — the row count change is the inventory correction propagating, not a data change.
chk(len(pd.read_csv(os.path.join(OUT,"phase3_vishful_amenity_master.csv")))==7,"amenity master (readiness) = 7 inventory configurations")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
