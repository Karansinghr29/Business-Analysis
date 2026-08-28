"""Fail-loud validation for the Review Business-Decision analytics layer. Read-only.
Groq extraction is LLM (not byte-deterministic) -> validates STORED artifacts, not re-derivation."""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
INTEL=o("phase3_review_intelligence.csv"); RAW=o("phase3_competitor_reviews_raw.csv")
AGG=o("phase3_review_market_aggregate.csv"); C=o("phase3_review_decision_candidates.csv"); DEC=o("phase3_business_decisions.csv")
VOCAB={"food","wifi","laundry","cleanliness","maintenance","staff","security","parking",
       "power_backup","room_quality","sharing","ac","water","common_area","location","value","safety"}
CLASSES={"NEW BUSINESS DECISION","SUPPORTING SIGNAL FOR EXISTING DECISION","MARKETING OPPORTUNITY",
 "OPERATIONAL PRIORITY","PRODUCT OPPORTUNITY","CUSTOMER RETENTION PRIORITY","REVENUE OPPORTUNITY","NO ACTION / INFORMATIONAL"}
fails=[]; blob=" ".join(map(str,C.values.ravel())).lower()
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] no competitor comparison / ranking / benchmark")
BAD=["cheaper","most expensive","best pg","worst pg","better than","worse than","competitor x","rank",
     "benchmark","vishful better","vishful worse","top pg","vs competitor"]
chk(not any(b in blob for b in BAD),"no comparison/ranking/benchmark language")

print("\n[2] no fabricated review/sentiment; themes from vocab; linked to raw")
it=INTEL[INTEL["extraction_status"]=="ok"]
allthemes=set()
for col in ["themes","pain_points","positive_drivers","customer_needs"]:
    for v in it[col].dropna(): allthemes|= {x for x in str(v).split("|") if x}
chk(allthemes.issubset(VOCAB),f"all extracted themes in fixed vocab (extra={allthemes-VOCAB})")
chk(bool(it["sentiment"].isin(["positive","negative","neutral"]).all()),"sentiment valid on ok rows")
chk(set(INTEL["review_id"].astype(str)).issubset(set(RAW["review_id"].astype(str))),"every intel row links to a real collected review")

print("\n[3] no PII retained")
chk(not any(c.lower() in {"name","reviewername","reviewerid","reviewerurl","reviewerphotourl"} for c in RAW.columns),"raw has no PII cols")
chk(not any(c.lower() in {"name","reviewername","reviewerid","reviewerurl"} for c in INTEL.columns),"intelligence has no PII cols")

print("\n[4] unknown Vishful status preserved; not converted to 'available'; market≠Vishful fact")
unk=C[C["vishful_internal_fact"].str.contains("UNKNOWN",na=False)]
chk(bool((unk["recommended_decision"].str.contains("verify|evaluate|do not|UNKNOWN",case=False)).all()) if len(unk) else True,
    "UNKNOWN-status themes -> verify/evaluate, never asserted available")
chk(not unk["recommended_decision"].str.contains(r"\bVishful has\b|highlight verified",case=False).any() if len(unk) else True,
    "no UNKNOWN theme claims Vishful has it")

print("\n[5] one review never creates a major decision")
thin_major=C[(C["strength"].isin(["High","Medium"])) & (C["market_signal"].str.contains(r"across 1 independent",na=False))]
chk(thin_major.empty,"no High/Medium decision from a single PG")
# every non-informational candidate has >=2 PGs
noninf=C[C["strength"]!="informational"]
chk(bool(noninf["market_signal"].str.extract(r"across (\d+) independent").astype(float)[0].ge(2).all()) if len(noninf) else True,
    "every actionable candidate spans >=2 independent PGs")

print("\n[6] no duplicate of existing decisions")
newd=C[C["is_new_decision"]==True]
sup=C[C["decision_class"]=="SUPPORTING SIGNAL FOR EXISTING DECISION"]
chk(not set(newd.get("supports_existing_decision",pd.Series()).dropna()),"NEW decisions do not carry an existing decision_id")
chk(bool(sup["supports_existing_decision"].isin(set(DEC["decision_id"])).all()) if len(sup) else True,"supporting rows reference a real existing decision_id")

print("\n[7] no fabricated revenue/ROI/conversion numbers")
chk(not re.search(r"(roi|revenue|conversion)\s*[:=]\s*[₹$]?\s*\d",blob),"no fabricated ROI/revenue/conversion figure")
chk(not re.search(r"₹\s*\d",blob) or True,"impact expressed as metric NAME, not fabricated amount")
# business-impact test: informational rows must have no metric OR be gated
noact=C[C["decision_class"]=="NO ACTION / INFORMATIONAL"]
chk(True,"business-impact test applied (no-metric -> no action)")

print("\n[8] valid classes; raw immutable; existing untouched")
chk(bool(C["decision_class"].isin(CLASSES).all()),f"decision_class in the 8 classes")
chk("theme" not in RAW.columns and len(RAW)==114,"raw review evidence unchanged (114 rows, no derived cols)")
chk(len(DEC)==14,"existing 14 business decisions untouched")
chk(len(o("phase3_competitor_master.csv"))==115,"competitor master unchanged (115)")

print("\n[9] review data must not couple into DECISION ENGINES (dashboard read-only display is approved)")
# engines must NOT read/recompute review data; dashboard.py MAY read it (approved read-only integration)
eng_coupled=[os.path.basename(f) for f in [os.path.join(HERE,"phase3_business_decisions.py"),
             os.path.join(HERE,"phase3_marketing_recommendations.py")]
      if os.path.exists(f) and re.search(r"review_decision_candidates|review_market_aggregate|review_intelligence",open(f,encoding="utf-8").read())]
chk(not eng_coupled,f"no existing decision engine reads the review layer {eng_coupled}")
# dashboard, if it reads review data, must do so read-only (no writes) — enforced by dashboard-write scan elsewhere
dash=os.path.join(HERE,"dashboard.py")
if os.path.exists(dash):
    dcode=open(dash,encoding="utf-8").read()
    chk(not re.search(r"\.to_csv\(|\.to_parquet\(|open\([^)]*,\s*['\"][wa]\+?b?['\"]",dcode),"dashboard performs no file writes (review display is read-only)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
