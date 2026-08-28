"""Regression validation for the promoted ACTIVE market universe (168). Read-only + determinism."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
A=o("phase3_active_market_universe.csv"); L=o("phase3_active_locality_summary.csv")
M=o("phase3_competitor_master.csv"); V2=o("phase3_market_universe_v2.csv"); HOLD=o("phase3_market_universe_v2_holdout.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] active universe = 168; baseline v1 = 115 unchanged")
chk(len(A)==168,f"active universe = 168 (got {len(A)})")
chk(len(M)==115,"phase3_competitor_master still 115 rows (frozen)")
v1=A[A["universe_version"]=="v1"]
chk(len(v1)==115 and set(v1["property_name"])==set(M["competitor_name"]),"all 115 baseline names present as v1")

print("[2] verified additions = 44 independent + 9 Zolo")
v2=A[A["universe_version"]=="v2"]
chk(len(v2)==53,"53 v2 additions in active universe")
chk(int((v2["operator_source_type"]=="independent").sum())==44,"44 independents")
chk(int(v2["operator_source_type"].str.startswith("operator:Zolo").sum())==9,"9 operator:Zolo")
chk(A["property_name"].is_unique,"no duplicate property in active universe")

print("[3] holdout excluded (no leakage)")
chk(len(HOLD)==85,"holdout still 85")
chk(not set(A["property_name"]) & set(HOLD["property_name"]),"no holdout property leaked into the active universe")

print("[4] locality counts recomputed on 168 (targets)")
lc=dict(zip(L["locality"],L["competitor_count"]))
for loc,exp in [("Thiruvanmiyur, Chennai",56),("Perungudi, Chennai",47),("Adyar, Chennai",13),("Kattankulathur, Chennai",24)]:
    chk(lc.get(loc)==exp,f"{loc} = {exp} (got {lc.get(loc)})")
chk(int(L["competitor_count"].sum())==168,"locality counts sum to 168")

print("[5] no fabricated distances/prices/reviews for the 53")
num=v2[pd.to_numeric(v2["distance_km"],errors="coerce").notna()]
chk(bool(num["distance_precision"].str.contains("coarse",case=False).all()),"every v2 numeric distance is COARSE-labelled (no fake exact coord)")
chk(int(pd.to_numeric(v2["distance_km"],errors="coerce").isna().sum())==3,"exactly 3 v2 (Kattankulathur) distances remain Unknown")
chk(set(v2["price_status"]).issubset({"SHARING_SPECIFIC","STARTING_FROM","RANGE","FLAT_DISPLAYED","UNKNOWN"}),"v2 price_status uses valid basis (no fabricated rent)")

print("[6] third-party evidence never labelled first-party")
chk(bool(v2["source_evidence_type"].str.contains("third_party|Zolo",case=False).all()),"all v2 rows tagged third-party/operator (never first_party)")
chk(not v2["source_evidence_type"].str.contains("first_party",case=False).any(),"no v2 row claims first_party evidence")

print("[7] special denominators preserved (pricing/sharing + amenity own universes)")
chk(len(o("phase3_competitor_prices.csv"))==66,"pricing/sharing evidence bucket unchanged (66 obs)")
chk(len(o("phase3_vishful_amenity_provenance.csv"))==5,"amenity provenance unchanged (5 amenities, /6 denominator)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("amenity denominator stays /6" in dash,"dashboard keeps /6 amenity denominator explicitly")
chk("pricing/sharing keeps its OWN denominator" in dash,"dashboard keeps pricing/sharing own denominator explicitly")
chk("phase3_active_market_universe.csv" in dash,"Page 10 directory reads the 168 active universe")

print("[8] Vishful internal + frozen layers unchanged")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
chk(len(o("phase3_competitor_distances.csv"))==115,"distance layer (v1 evidence) unchanged (115)")
chk(o("phase3_competitor_source_links.csv")["competitor_name"].nunique()==90,"source-links (v1 evidence) unchanged (90)")

print("[9] deterministic")
for f in ["phase3_active_market_universe.csv","phase3_active_locality_summary.csv"]:
    p=os.path.join(OUT,f); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
    subprocess.run([sys.executable,"phase3_active_market_universe.py"],cwd=HERE,capture_output=True)
    h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,f"{f} re-run byte-identical")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
