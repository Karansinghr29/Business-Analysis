"""Fail-loud validation for phase3_playwright_market. Isolated, read-only."""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
R=pd.read_csv(os.path.join(OUT,"phase3_playwright_market_research.csv"))
E=pd.read_csv(os.path.join(OUT,"phase3_playwright_web_evidence.csv"))
FIRST_PARTY={"tsppgaccommodation.com","kripahomes.com","mahalakshmipgaccommodation.com",
             "season4.in","kolamapartments.com","oliveservicedapartments.com"}
TYPES={"mens_pg","womens_pg","coed_pg","hostel","co_living","serviced_apartment","residential","unknown"}
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] no fabricated price / all unknown")
chk(R["monthly_rent"].isna().all(),"no numeric monthly_rent (none fabricated)")
chk((R["price_status"]=="unknown").all(),"all price_status=unknown")
chk(R["sharing_type_priced"].isna().all() and R["ac_priced"].isna().all() and R["price_unit"].isna().all(),
    "no priced grain populated (no room->bed / day->month / starts-from conversion possible)")

print("\n[2] first-party only + provenance")
chk(bool(R["domain"].isin(FIRST_PARTY).all()),"every domain is an identified first-party site")
chk(bool(R["provenance"].notna().all()) and (R["provenance"]=="playwright_first_party_render").all(),"provenance present")
chk(bool(R["official_site_verified"].all()),"all rows first-party verified")

print("\n[3] no duplicate property / valid types / supported URLs")
chk(R["domain"].is_unique and R["canonical"].is_unique,"unique property per domain/canonical")
chk(bool(R["property_type"].isin(TYPES).all()),f"property_type in {TYPES}")
chk(bool(E["url"].astype(str).str.startswith("https://").all()),"all evidence URLs are https first-party")
chk(bool(E["domain"].isin(FIRST_PARTY).all()),"all evidence domains first-party")

print("\n[4] amenity flags: True or null only (no False-assertion / fabrication)")
amen=["wifi","food","laundry","housekeeping","cctv_security","parking","power_backup","ac_available","non_ac"]
ok=all(R[c].dropna().isin([True]).all() for c in amen)  # only True or NaN
chk(ok,"amenity columns hold only True or null (absence => unknown, never False)")

print("\n[5] no API keys / credentials in outputs")
blob=" ".join(open(os.path.join(OUT,f),encoding="utf-8").read() for f in
    ["phase3_playwright_market_research.csv","phase3_playwright_web_evidence.csv","phase3_playwright_summary.csv"])
leak=re.search(r"(gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}|api[_-]?key\s*[:=]\s*\S{16,})",blob,re.I)
chk(leak is None,"no API key / credential string in any output")

print("\n[6] isolation — master/locked/existing unchanged")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv")))==115,"master still 115 rows")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_pg_research_candidates.csv")))==9,"existing phase3 research still 9 rows")
chk(os.path.exists(os.path.join(OUT,"phase3_market_spec.json")),"Market AI spec present (untouched)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
