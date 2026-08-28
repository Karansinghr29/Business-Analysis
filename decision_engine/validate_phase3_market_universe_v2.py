"""Fail-loud validation for market universe v2. Read-only + determinism + isolation from existing calcs."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
V2=o("phase3_market_universe_v2.csv"); HOLD=o("phase3_market_universe_v2_holdout.csv"); M=o("phase3_competitor_master.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] 115 baseline preserved + immutable")
chk(len(M)==115,"master still 115 rows")
v1=V2[V2["universe_version"]=="v1"]
chk(len(v1)==115,"v2 carries all 115 as v1")
chk(set(M["competitor_name"])==set(v1["property_name"]),"v1 property names == the original 115 exactly")
chk(bool((v1["status"]=="baseline").all()),"all v1 rows tagged status=baseline")

print("\n[2] v2 = 168 verified (115 + 44 independents + 9 Zolo)")
chk(len(V2)==168,f"v2 total = 168 (got {len(V2)})")
add=V2[V2["universe_version"]=="v2"]
ind=add[add["operator_source_type"]=="independent"]; zolo=add[add["operator"]=="Zolo"]
chk(len(ind)==44,f"44 verified new independents (got {len(ind)})")
chk(len(zolo)==9,f"9 verified Zolo (got {len(zolo)})")
chk(bool((zolo["operator_source_type"]=="operator:Zolo").all()),"Zolo rows tagged operator:Zolo")
chk(bool((add["identity_confidence"]=="high").all()),"all v2 additions are high-confidence")
chk(V2["property_name"].is_unique,"no duplicate property in v2 (fuzzy-dedup applied)")

print("\n[3] required schema present")
need={"property_name","locality","address","pincode","operator","operator_source_type","identity_confidence","universe_version","source_platform","source_url","sharing_type","published_rent","amenities","provenance","status"}
chk(need.issubset(V2.columns),"v2 has the required columns")

print("\n[4] holdout kept OUTSIDE v2 (never in verified universe)")
chk(int((HOLD["status"]=="unverified").sum())==78,"78 medium-confidence unverified in holdout")
chk(int((HOLD["status"]=="possible_duplicate").sum())==2,"2 possible_duplicate in holdout (fuzzy-dedup review)")
chk(int((HOLD["status"]=="low_review").sum())==5,"5 low-review in holdout")
chk(not set(HOLD["property_name"]) & set(add["property_name"]),"no holdout property leaked into v2 verified additions")
chk(not (HOLD["status"]=="verified").any(),"holdout contains zero verified rows")

print("\n[5] existing 115-based outputs UNCHANGED; v2 not wired into denominators")
chk(len(o("phase3_competitor_prices.csv"))==66,"pricing dataset unchanged (66)")
chk(o("phase3_competitor_source_links.csv")["competitor_name"].nunique()==90,"source-links unchanged (90 competitors)")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
chk(len(o("phase3_marketing_recommendations.csv"))==10,"marketing recs reflect corrected vacancy (10; Single INV/VAC/SHR dropped at 0 single vacancy)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_market_universe_v2" not in dash,"dashboard does NOT yet consume v2 (no denominator/score change)")

print("\n[6] deterministic")
for f in ["phase3_market_universe_v2.csv","phase3_market_universe_v2_holdout.csv"]:
    p=os.path.join(OUT,f); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
    subprocess.run([sys.executable,"phase3_market_universe_v2.py"],cwd=HERE,capture_output=True)
    h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,f"{f} re-run byte-identical")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
