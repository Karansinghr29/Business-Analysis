"""Fail-loud validation for phase3_competitor_master. Isolated, read-only."""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
M=pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv"))
SS=pd.read_csv(os.path.join(OUT,"phase3_screenshot_full_verify.csv"))
TYPES={"mens_pg","womens_pg","pg_unknown_gender","co_living","serviced_apartment","hotel",
       "residential_apartment","hostel","unknown"}
def norm(s): return re.sub(r"[^a-z0-9 ]","",re.sub(r"\s+"," ",str(s).strip().lower())).strip()
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] no fabricated numeric prices")
# no numeric per-bed rent stored in master (grid lives in price-evidence file); and any priced row must be first-party
chk(M["monthly_rent_per_bed"].isna().all(),"master carries no inline numeric per-bed price (no fabrication)")
priced=M[M["has_first_party_price"]==True]
chk(bool(priced["price_source_url"].astype(str).str.startswith("http").all()) if len(priced) else True,
    "first-party priced rows have http first-party source_url")
chk(bool((~priced["is_operator_or_aggregator"]).all()) if len(priced) else True,
    "no operator/aggregator flagged as first-party priced")

print("\n[2] provenance present for every row")
chk(M["provenance"].notna().all() and (M["provenance"].str.len()>0).all(),"every row has provenance")
allowed_prov={"dashboard","first_party_web","groq_discovery","independent_web_verification"}
badprov=M[~M["provenance"].apply(lambda p:set(str(p).split(",")).issubset(allowed_prov))]
chk(badprov.empty,"provenance values all in allowed set")

print("\n[3] no duplicate canonical competitors")
chk(int(M["canonical_id"].duplicated().sum())==0,"canonical_id unique")

print("\n[4] valid property types")
chk(bool(M["property_type"].isin(TYPES).all()),f"property_type in {TYPES}")

print("\n[5] valid distance precision")
ok=M["distance_precision"].fillna("unknown_locality").apply(
    lambda p:str(p).startswith(("suburb_centroid","coarse_far","same_suburb")) or p in ("unknown_locality","unknown")).all()
chk(bool(ok),"distance_precision only coarse/centroid/far/unknown labels")
numd=M[M["distance_km"].notna()]
chk(bool(numd["distance_precision"].astype(str).str.startswith(("suburb_centroid","same_suburb")).all()) if len(numd) else True,
    "numeric distances carry centroid/same-suburb precision (no street coords)")

print("\n[6] aggregator not used as first-party pricing")
chk(bool(M[(M["is_operator_or_aggregator"]==True)]["has_first_party_price"].eq(False).all()),
    "no operator/aggregator has_first_party_price=True")

print("\n[7] no room-to-bed conversion")
# room-class priced rows must NOT be flagged comparable per-bed
rc=M[M["price_confidence"]=="first_party_room_class"]
chk(bool((~rc["comparable_perbed_sharing_ac"]).all()) if len(rc) else True,
    "room-class price never counted as per-bed comparable (no conversion)")

print("\n[8] no dashboard candidate silently dropped")
master_norms=set()
for a in M["all_names"]: master_norms.update(norm(x) for x in str(a).split(" || "))
missing=[n for n in SS["candidate_name"] if norm(n) not in master_norms]
chk(len(missing)==0, f"all {len(SS)} dashboard candidates present in master (missing={missing[:5]})")

print("\n[9] isolation")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_pg_research_candidates.csv")))==9,"existing phase3_pg_research still 9 rows")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
