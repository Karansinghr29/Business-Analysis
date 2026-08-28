"""Fail-loud validation for the consolidated decision-support layer. Read-only + determinism."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase3_decision_support.csv"); IA=o("phase3_review_intelligence_audit.csv"); RC=o("phase3_review_decision_candidates.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] structure = Observation -> Evidence -> Implication -> Possible action")
need={"source","topic","observation","evidence","business_implication","possible_vishful_action","disclaimer"}
chk(need.issubset(D.columns),"required columns present")
chk(len(D)==len(IA)+len(RC),f"rows == audit topics + review candidates ({len(D)} vs {len(IA)+len(RC)})")
chk(bool(D["disclaimer"].str.contains("not an automatic business decision",case=False).all()),"every row carries the decision-support disclaimer")

print("\n[2] derived only from EXISTING review layers (no new fabricated decisions)")
chk(set(D["source"]).issubset({"review_intelligence_audit","review_decision_candidate"}),"sources limited to the two existing review layers")

print("\n[3] no ranking / no explicit Vishful price recommendation (content cols only; disclaimer may say 'no ranking')")
blob=" ".join(map(str,D[["topic","observation","evidence","business_implication","possible_vishful_action"]].values.ravel())).lower()
for bad in ["better than vishful","worse than vishful","best competitor","rank competitor","vishful should charge","set vishful price","charge rs ","charge ₹"]:
    chk(bad not in blob,f"absent forbidden phrase: '{bad}'")

print("\n[4] existing decision layers unchanged; deterministic")
chk(len(RC)==16 and len(IA)==9,"underlying review candidates(16)+audit(9) intact")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
p=os.path.join(OUT,"phase3_decision_support.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_decision_support.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_decision_support.csv" in dash and "decision-support detail" in dash.lower(),"Page 10 renders the decision-support detail (traceability expander under the owner cards)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
