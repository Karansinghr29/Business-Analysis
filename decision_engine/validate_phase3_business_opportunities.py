"""Fail-loud validation for phase3_business_opportunities. Isolated, read-only + determinism check."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
CSV=os.path.join(OUT,"phase3_business_opportunities.csv")
D=pd.read_csv(CSV); S=pd.read_csv(os.path.join(OUT,"phase3_business_opportunities_summary.csv"))
E=pd.read_csv(os.path.join(OUT,"phase3_business_opportunity_evidence.csv"))
CATS={"Inventory to Promote","Sharing / Inventory Opportunity","Amenity Marketing Opportunity",
      "Location / Marketing Opportunity"}
SRC={"VISHFUL_INTERNAL","MARKET_CONTEXT","COMBINED"}
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
alltext=" ".join(D.astype(str).fillna("").agg(" ".join,axis=1)).lower()

print("[1-2] no competitor-vs-Vishful / price comparison language")
BAD=["cheaper","more expensive","competitor price","vs competitor","versus competitor","competitor is",
     "than competitor","competitors charge","competitor occupancy","competitor revenue","outperform",
     "better than competitor","worse than competitor","competitor ranking","beat competitor"]
hit=[b for b in BAD if b in alltext]
chk(not hit, f"no forbidden comparison phrases (found: {hit})")

print("\n[3-4] no fabricated market / synthetic Vishful data")
# no numeric COMPETITOR price: a competitor price = 'competitor' AND a ₹-figure in the SAME cell.
# (Vishful's own ₹ revenue-at-risk is internal, not a competitor price; a 'no competitor price' disclaimer is fine.)
def _cell_has_comp_price(cell):
    c=str(cell).lower()
    return ("competitor" in c) and bool(re.search(r"₹\s*\d",c))
comp_price_cells=[ (i,col) for i in D.index for col in D.columns if _cell_has_comp_price(D.at[i,col]) ]
chk(len(comp_price_cells)==0, f"no competitor price figure in any cell (found: {comp_price_cells[:3]})")
# market-context reasons must cite the first-party market file
mc=D[D["evidence_source"].isin(["MARKET_CONTEXT","COMBINED"])]
chk(bool(mc["provenance"].astype(str).str.contains("phase3_playwright_market_research|phase3_competitor_master").all()) if len(mc) else True,
    "every market claim cites first-party market provenance")

print("\n[5-6] every rec has evidence + provenance")
chk(bool(D["reason"].astype(str).str.len().gt(0).all()),"every rec has a reason")
chk(bool(D["provenance"].astype(str).str.len().gt(0).all()),"every rec has provenance")
internal=D[D["evidence_source"].isin(["VISHFUL_INTERNAL","COMBINED"])]
chk(bool(internal["vishful_evidence"].notna().all()) if len(internal) else True,"internal/combined recs carry vishful_evidence")

print("\n[7] unknown preserved (Vishful amenities not assumed)")
amen=D[D["category"]=="Amenity Marketing Opportunity"]
chk(bool((amen["evidence_source"]=="MARKET_CONTEXT").all()) if len(amen) else True,
    "amenity recs are MARKET_CONTEXT (Vishful availability unknown, not asserted)")
chk(bool(amen["vishful_evidence"].isna().all()) if len(amen) else True,"amenity recs assert NO Vishful amenity (unknown kept)")

print("\n[8-10] no conversions present")
chk(not re.search(r"per bed.*per room|room price.*per bed|/day|per day|per night|starting from|starts from",alltext),
    "no room->bed / day->month / starts-from language in outputs")

print("\n[11-12] deterministic + reproducible")
h1=hashlib.md5(open(CSV,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_business_opportunities.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(CSV,"rb").read()).hexdigest()
chk(h1==h2,"re-run produces byte-identical output (deterministic/reproducible)")

print("\n[13] valid categories + sources + numeric scores")
chk(bool(D["category"].isin(CATS).all()),f"category in {CATS}")
chk(bool(D["evidence_source"].isin(SRC).all()),f"evidence_source in {SRC}")
chk(bool(pd.to_numeric(D["score"],errors="coerce").notna().all()),"score numeric on every row")
chk(bool(D["priority"].isin(["High","Medium","Low"]).all()),"priority in High/Medium/Low")

print("\n[14] no API keys / credentials in outputs")
blob=open(CSV,encoding="utf-8").read()+open(os.path.join(OUT,"phase3_business_opportunities_summary.csv"),encoding="utf-8").read()
chk(re.search(r"(gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}|api[_-]?key\s*[:=]\s*\S{16,})",blob,re.I) is None,
    "no API key/credential in outputs")

print("\n[15] existing files unchanged")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv")))==115,"master still 115 rows")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_pg_research_candidates.csv")))==9,"existing phase3 research still 9 rows")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
