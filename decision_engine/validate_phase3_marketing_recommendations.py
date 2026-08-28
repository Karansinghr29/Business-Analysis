"""Fail-loud validation for phase3_marketing_recommendations + closed-loop. Isolated."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
CSV=os.path.join(OUT,"phase3_marketing_recommendations.csv")
D=pd.read_csv(CSV); CL=pd.read_csv(os.path.join(OUT,"phase3_closed_loop_tracking.csv"))
CATS={"Inventory marketing","Vacancy/slow-fill marketing","Sharing-positioning","Amenity marketing","Locality marketing"}
SRC={"VISHFUL_INTERNAL","MARKET_CONTEXT","COMBINED"}
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
def cell(i,col): return str(D.at[i,col]).lower()
alltext=" ".join(map(str,D.values.ravel())).lower()

print("[competitor comparison / ranking / price benchmark]")
BAD=["cheaper","more expensive","competitor price","vs competitor","versus competitor","beat competitor",
     "better than competitor","worse than competitor","competitor ranking","competitor benchmark",
     "outperform","market average price","cheaper than","who beats"]
hit=[b for b in BAD if b in alltext]; chk(not hit,f"no forbidden comparison/ranking phrases {hit}")
comp_price=[(i,col) for i in D.index for col in D.columns if "competitor" in cell(i,col) and re.search(r"₹\s*\d",cell(i,col))]
chk(not comp_price,f"no competitor price figure in any cell {comp_price[:2]}")

print("\n[evidence + provenance]")
chk(bool(D["business_reason"].astype(str).str.len().gt(0).all()),"every rec has business_reason")
chk(bool(D["provenance"].astype(str).str.len().gt(0).all()),"every rec has provenance")
inr=D[D["evidence_source"].isin(["VISHFUL_INTERNAL","COMBINED"])]
chk(bool(inr["vishful_evidence"].notna().all()) if len(inr) else True,"internal/combined recs carry vishful_evidence")
mc=D[D["evidence_source"].isin(["MARKET_CONTEXT","COMBINED"])]
chk(bool(mc["market_evidence"].notna().all()) if len(mc) else True,"market/combined recs carry market_evidence")
chk(bool(mc["provenance"].astype(str).str.contains("playwright|competitor_master").all()) if len(mc) else True,
    "market claims cite first-party market provenance")

print("\n[unknown / invented Vishful amenities]")
am=D[D["category"]=="Amenity marketing"]
chk(bool((am["evidence_source"]=="MARKET_CONTEXT").all()) if len(am) else True,"amenity recs MARKET_CONTEXT")
chk(bool(am["vishful_evidence"].isna().all()) if len(am) else True,"amenity recs assert NO Vishful amenity (unknown kept)")
chk(bool(am["recommended_action"].astype(str).str.contains("Confirm internally",case=False).all()) if len(am) else True,
    "amenity action = confirm internally before marketing")

print("\n[no conversions]")
chk(not re.search(r"per bed.*per room|room price.*per bed|/day|per day|per night|starting from|starts from",alltext),
    "no room->bed / day->month / starts-from language")

print("\n[invented campaign outcomes]")
chk(bool((CL.drop(columns=['recommendation_id']).astype(str)=="unavailable").any(axis=1).all()) or
    bool((CL["outcome_status"]=="unavailable_no_data").all()),"closed-loop outcomes all unavailable (not fabricated)")
chk(set(CL["recommendation_id"])==set(D["recommendation_id"]),"closed-loop ids match recommendations")

print("\n[determinism / reproducibility]")
h1=hashlib.md5(open(CSV,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_marketing_recommendations.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(CSV,"rb").read()).hexdigest()
chk(h1==h2,"re-run byte-identical (deterministic)")

print("\n[schema / dedup / categories]")
chk(D["recommendation_id"].is_unique,"recommendation_id unique (no duplicate)")
chk(bool(D["category"].isin(CATS).all()),f"category in {CATS}")
chk(bool(D["evidence_source"].isin(SRC).all()),"evidence_source valid")
chk(bool(pd.to_numeric(D["score"],errors="coerce").notna().all()),"score numeric")
chk(bool(D["priority"].isin(["High","Medium","Low"]).all()),"priority valid")
chk(bool((D["validation_status"]=="validated").all()),"validation_status set")

print("\n[key leak / existing files]")
blob=open(CSV,encoding="utf-8").read()
chk(re.search(r"(gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}|api[_-]?key\s*[:=]\s*\S{16,})",blob,re.I) is None,"no key leak")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv")))==115,"master still 115 rows")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_business_opportunities.csv")))==9,"business opportunities reflect corrected vacancy (9; Single opps dropped at 0 single vacancy)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
