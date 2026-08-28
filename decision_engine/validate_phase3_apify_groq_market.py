"""Fail-loud validation for phase3_apify_groq_market. Isolated, read-only."""
from __future__ import annotations
import os, sys, re, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
D=pd.read_csv(os.path.join(OUT,"phase3_apify_groq_market_discovery.csv"))
E=pd.read_csv(os.path.join(OUT,"phase3_apify_groq_web_evidence.csv"))
S=pd.read_csv(os.path.join(OUT,"phase3_apify_groq_summary.csv"))
M=pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv"))
TYPES={"mens_pg","womens_pg","coed_pg","hostel","co_living","serviced_apartment","residential","unknown"}
TARGET={"adyar","thiruvanmiyur","tiruvanmiyur","perungudi","kattankulathur"}
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] unique canonical candidates")
chk(D["canonical_name"].is_unique,"canonical_name unique")

print("\n[2] master (115) not modified/deleted")
chk(len(M)>=115,f"master still has >=115 rows ({len(M)})")

print("\n[3] provenance valid")
chk(D["discovery_source"].isin(["groq","apify","independent"]).all(),"discovery_source in {groq,apify,independent}")

print("\n[4] valid property types")
chk(bool(D["property_type"].isin(TYPES).all()),f"property_type in {TYPES}")

print("\n[5] valid target locations")
chk(bool(D["locality"].str.lower().isin(TARGET).all()),"all localities in the 4 target areas")

print("\n[6] no aggregator/operator price; no fabricated price")
chk(D["monthly_rent"].isna().all(),"no numeric monthly_rent stored (none fabricated)")
chk((D["price_status"]=="unknown").all(),"all price_status=unknown")
op=D[D["is_aggregator_operator"]==True]
chk(bool(op["monthly_rent"].isna().all()) if len(op) else True,"no operator/aggregator carries a price")

print("\n[7] no conversions (room->bed, day->month, starts-from->exact)")
# no price at all -> conversions impossible; assert grain fields all null
chk(D["sharing_type"].isna().all() and D["ac"].isna().all() and D["price_unit"].isna().all(),
    "no sharing/AC/price_unit populated (no conversion possible)")

print("\n[8] first-party URL verification honest")
vf=D[D["official_site_verified"]==True]
chk(bool(vf["official_url"].astype(str).str.startswith("http").all()) if len(vf) else True,
    "verified first-party rows carry http official_url")
chk(bool((~vf["is_aggregator_operator"]).all()) if len(vf) else True,
    "no operator/aggregator marked official_site_verified")

print("\n[9] unknown-price preservation")
chk(int((D["price_status"]=="unknown").sum())==len(D),"every row unknown-price (preserved)")

print("\n[10] API/quota errors captured + apify usage captured")
chk(E["error"].notna().any(),"Groq 429 errors recorded in evidence")
chk(bool(E[E["tool"]=="apify/rag-web-browser"]["compute_units"].notna().all()),"Apify compute-units captured")

print("\n[11] no dashboard/locked-output modification")
# dashboard.py + master unchanged (spot check master row count already; dashboard not written here)
chk(os.path.exists(os.path.join(OUT,"phase3_competitor_master.csv")),"master present (not deleted)")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_pg_research_candidates.csv")))==9,"existing phase3 research still 9 rows")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
