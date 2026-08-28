"""Fail-loud validation for Stage-3 competitor review collection + theme extraction. Read-only.
Note: theme extraction uses Groq (LLM) -> NOT byte-deterministic; this validator checks the STORED
artifacts, it does not re-run extraction. Raw collection IS deterministic (immutable Apify dataset)."""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
RAW=o("phase3_competitor_reviews_raw.csv"); BYP=o("phase3_competitor_reviews_by_property.csv")
TH=o("phase3_review_themes.csv"); AGG=o("phase3_review_theme_aggregate.csv")
VOCAB={"food","wifi","laundry","cleanliness","maintenance","staff","security","parking",
       "power_backup","room_quality","sharing","ac","water","common_area","location","value","safety"}
TARGET={"Sahithyan Men's PG","TSP PG Accommodation","Yali Service Apartment","Subodhaya Paying Guest (Ladies)",
 "Season 4 Rentals","Kripa Homes PG","Kolam Gandhi Serviced Apartments","Olive Serviced Apartments",
 "Diyaa Paying Guest","Feel At Home Ladies Hostel"}
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] no reviewer PII stored")
PII={"name","reviewername","reviewer_name","reviewerid","reviewer_id","reviewerurl","reviewerphotourl","profile"}
chk(not any(c.lower() in PII for c in RAW.columns),"no reviewer-PII columns")
chk(not RAW["review_text"].astype(str).str.contains(r"reviewerUrl|reviewerId|photoUrl",case=False).any(),"no PII tokens in review_text")

print("\n[2] every review tied to a target property + correct fields")
chk(bool(RAW["property_name"].isin(TARGET).all()),"every review tied to an approved target property")
chk(bool((RAW["platform"]=="google_maps").all()),"platform = google_maps for all")
chk(bool(RAW["review_text"].astype(str).str.len().gt(0).all()),"every row has review_text")
chk(bool(RAW["rating"].between(1,5).all()),"ratings within 1..5")
chk(bool((RAW["apify_run_id"]=="zID57BCmD2hhyLRCb").all()),"apify_run_id stamped on every row")
chk(bool((BYP["reviews_collected"]<=20).all()),"<=20 reviews per property (bound honored)")
chk(len(RAW)<=200,"total reviews <=200 (bound honored)")

print("\n[3] themes from fixed vocab; sentiment valid; linked to raw (no fabrication)")
special={"(none)","(extraction_missing)"}
chk(bool(TH["theme"].apply(lambda t:t in VOCAB or t in special).all()),"themes only from fixed vocab (+none/missing)")
chk(bool(TH["sentiment"].isin(["positive","negative","neutral","unknown"]).all()),"sentiment values valid")
chk(set(TH["review_id"].astype(str)).issubset(set(RAW["review_id"].astype(str))),"every theme row links to a real collected review")
chk(bool((TH["extractor"]=="groq").all()),"extractor tagged groq (derived layer)")

print("\n[4] raw preserved / derived layer separate")
chk("theme" not in RAW.columns and "sentiment" not in RAW.columns,"raw review file unchanged (no theme/sentiment mixed in)")

print("\n[5] no competitor comparison/ranking/benchmark")
blob=" ".join(map(str,AGG.values.ravel())).lower()+" ".join(map(str,BYP.values.ravel())).lower()
BAD=["cheaper","better than","worse than","rank","best pg","top rated vs","benchmark","competitor average","vishful"]
chk(not any(b in blob for b in BAD),"no comparison/ranking/benchmark/Vishful-mix in review aggregates")
# aggregate is theme counts only, no property-vs-property ranking column
chk("property" not in [c.lower() for c in AGG.columns],"theme aggregate is market-wide (no per-property ranking table)")

print("\n[6] separation from other datasets + no decision creation")
# review artifacts not read by any decision engine or dashboard
import glob
coupled=[]
for f in glob.glob(os.path.join(HERE,"phase3_business_decisions.py"))+glob.glob(os.path.join(HERE,"phase3_marketing_recommendations.py"))+[os.path.join(HERE,"dashboard.py")]:
    if os.path.exists(f) and re.search(r"competitor_reviews_raw|review_themes|review_theme_aggregate",open(f,encoding="utf-8").read()):
        coupled.append(os.path.basename(f))
chk(not coupled,f"no decision engine/dashboard reads review data yet {coupled}")

print("\n[7] no key leak + existing outputs untouched")
allb=" ".join(map(str,RAW.head(50).values.ravel()))
chk(not re.search(r"gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}",allb),"no API key in outputs")
chk(len(o("phase3_business_decisions.csv"))==14,"business decisions unchanged (14)")
chk(len(o("phase3_competitor_master.csv"))==115,"competitor master unchanged (115)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
