"""Fail-loud validation for the owner decision cards. Read-only + determinism + traceability."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase3_owner_decision_cards.csv"); M=o("phase3_competitor_master.csv")
PR=o("phase3_competitor_prices.csv"); LOC=o("phase3_locality_summary.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] owner-card structure present")
need={"card_id","business_finding","evidence","business_implication","possible_action","confidence","provenance"}
chk(need.issubset(D.columns),"cards have finding/evidence/implication/action/confidence/provenance")
chk(len(D)==7,f"7 owner decision cards (got {len(D)})")
chk(D["card_id"].is_unique,"card ids unique")

print("\n[2] every card traceable to a real dataset; no empty fields")
for col in ["business_finding","evidence","business_implication","possible_action","confidence","provenance"]:
    chk(bool(D[col].astype(str).str.len().gt(10).all()),f"'{col}' populated on every card")
chk(bool(D["provenance"].str.contains(r"phase3_.*\.csv",regex=True).all()),"every card cites a phase3 dataset in provenance")

print("\n[3] key numbers match the source data (no fabrication)")
n_priced=PR[PR["price_basis"].isin(["OFFICIAL_SHARING_SPECIFIC","OFFICIAL_STARTING_FROM"])]["competitor_name"].nunique()
N_ACTIVE=len(o("phase3_active_market_universe.csv"))
transp=D[D["card_id"]=="price_transparency"]["evidence"].iloc[0]
chk(f"{n_priced} of {N_ACTIVE}" in transp,f"transparency card cites the true {n_priced}/{N_ACTIVE} priced count (168 active universe)")
chk("115 baseline" in transp,"transparency card names the 115 baseline for traceability")
ss=PR[PR["price_basis"]=="OFFICIAL_SHARING_SPECIFIC"]
pos=D[D["card_id"]=="pricing_positioning"]["evidence"].iloc[0]
for t in ["Single","Double","Triple"]:
    s=ss[ss["sharing_type"]==t]
    if len(s):
        chk(f"Rs{int(s['price'].min()):,}-Rs{int(s['price'].max()):,}" in pos,f"pricing card cites true {t} observed range")

print("\n[4] guardrails — decision support only, no ranking / no Vishful price rec")
blob=" ".join(map(str,D.values.ravel())).lower()
for bad in ["better than vishful","worse than vishful","best competitor","rank competitor","vishful should charge","set vishful price","charge rs ","charge ₹"]:
    chk(bad not in blob,f"absent forbidden phrase: '{bad}'")
chk(bool(D["possible_action"].str.contains("consider|evaluate|review|treat",case=False).all()),"actions are framed as options ('consider/evaluate/review'), not directives")
chk(bool(D["confidence"].str.contains("High|Moderate|Explicit|thin|limited|coverage",case=False).any()),"confidence/coverage stated")
# data-confidence card must exist and flag limited evidence
chk("data_confidence" in set(D["card_id"]),"a dedicated data-coverage/confidence card exists")

print("\n[5] underlying data + existing layers unchanged; deterministic")
chk(len(M)==115,"master unchanged (115)")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
chk(len(o("phase3_decision_support.csv"))==25,"underlying decision-support table intact (25)")
p=os.path.join(OUT,"phase3_owner_decision_cards.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_owner_decision_cards.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_owner_decision_cards.csv" in dash and "decision cards" in dash.lower(),"Page 10 renders owner decision cards")
chk("Why it matters to Vishful" in dash and "Possible action" in dash,"cards use owner-readable labels")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
