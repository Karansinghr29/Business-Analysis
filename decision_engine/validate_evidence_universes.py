"""
Evidence-universe invariant (regression guard, read-only).

Locks the audit finding that the two market-evidence universes are DISTINCT and must not be conflated, and that
Zolo (operator/aggregator) is not first-party per-property amenity/price/sharing evidence:

  - AMENITY universe        = 6 eligible first-party sources (phase3_playwright_market_research); the 'X/6' counts.
  - PRICING/SHARING universe = 23 competitors / 66 observations (phase3_competitor_prices), a different, broader set.
  - Both are subsets of the 115-property universe (phase3_competitor_master).
  - Zolo = operator/aggregator: 0 price rows, 0 sharing rows, price_status unknown, not in the comparable grid.
"""
from __future__ import annotations
import os, sys, json
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
M=o("phase3_competitor_master.csv"); PR=o("phase3_competitor_prices.csv")
PW=o("phase3_playwright_market_research.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] universes are distinct and correctly sized")
chk(len(M)==115,"115-property research universe (competitor master)")
chk(len(PW)==6,"AMENITY universe = 6 eligible first-party sources")
chk(PR["competitor_name"].nunique()==23,f"PRICING/SHARING universe = 23 competitors (got {PR['competitor_name'].nunique()})")
ss=PR[PR["price_basis"]=="OFFICIAL_SHARING_SPECIFIC"]
chk(len(ss)==49 and ss["competitor_name"].nunique()==14,"sharing-specific = 49 obs across 14 competitors")
# the 6 amenity sources are NOT the same set as the priced competitors (different universes)
amen_set=set(PW["property_name"]); priced_set=set(PR["competitor_name"])
chk(amen_set!=priced_set,"amenity-source set != pricing-source set (distinct universes)")

print("\n[2] Zolo correctly classified; no per-property price/sharing evidence")
z=M[M["competitor_name"].str.lower()=="zolo"]
chk(len(z)==1 and str(z.iloc[0]["evidence_class"])=="operator_aggregator","Zolo = 1 row, evidence_class operator_aggregator")
chk(int((PR["competitor_name"].str.lower()=="zolo").sum())==0,"Zolo has 0 extracted price observations")
chk(int((PW["property_name"].str.lower()=="zolo").sum())==0,"Zolo is NOT one of the 6 first-party amenity sources")
spec=json.load(open(os.path.join(OUT,"phase3_market_spec.json"),encoding="utf-8"))
zdir=[r for r in spec["section_2_directory"] if str(r.get("canonical_name","")).lower()=="zolo"]
chk(len(zdir)==1 and str(zdir[0].get("price_status"))=="unknown","Zolo directory row shows price_status=unknown (no fabricated price)")
chk(not any("zolo" in str(g).lower() for g in spec["section_3_comparable_pricing"].get("grid",[])),"Zolo NOT in the comparable-pricing grid")

print("\n[3] dashboard makes both universes explicit (display labels)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("EVIDENCE UNIVERSE" in dash,"dashboard labels the evidence universes")
chk("6 eligible first-party amenity-evidence sources" in dash or "6 ELIGIBLE first-party amenity-evidence sources" in dash,"amenity /6 denominator explained")
chk("23 competitors" in dash and "66 observations" in dash,"pricing/sharing universe (23 competitors / 66 obs) shown")
chk("Zolo" in dash and "operator/aggregator" in dash,"Zolo flagged as operator/aggregator, not first-party per-property evidence")

print("\n[4] engine/scores/outputs unchanged")
chk(len(o("phase3_marketing_recommendations.csv"))==10,"marketing recs reflect corrected vacancy (10; Single INV/VAC/SHR dropped at 0 single vacancy)")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
chk(len(PR)==66,"prices dataset unchanged (66 obs)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
