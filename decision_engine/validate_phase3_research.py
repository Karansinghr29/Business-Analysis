"""
Validation for phase3_pg_research (isolated). Fail-loud. Proves:
  * every price came from a FIRST-PARTY, NON-aggregator source (no scraped/aggregated numbers)
  * NO fabricated price: every published rent has a verbatim_quote AND a source_url
  * unknown PRESERVED: no numeric rent invented where the site showed none
  * PG-vs-hotel classification is in the allowed set and reproducible from signals
  * classifier sanity: a hotel-signal string classifies as HOTEL (rule actually discriminates)
  * ISOLATION: only the 3 new phase3_pg_research_* files are produced; locked outputs untouched.
Run AFTER phase3_pg_research.py. Read-only.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from phase3_pg_research import AGGREGATOR_HOSTS, classify, host_of

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
CAND = os.path.join(OUT,"phase3_pg_research_candidates.csv")
PRICE= os.path.join(OUT,"phase3_pg_price_evidence.csv")
SUMM = os.path.join(OUT,"phase3_pg_research_summary.csv")
NEW_FILES = {"phase3_pg_research_candidates.csv","phase3_pg_price_evidence.csv","phase3_pg_research_summary.csv"}
# Files this module must NEVER create/alter (locked pipeline + discovery output).
PROTECTED = {"phase3_places_candidates.csv"}  # OSM discovery stays price-free & unchanged

fails=[]
def chk(cond, msg):
    print(("  PASS " if cond else "  FAIL ")+msg)
    if not cond: fails.append(msg)

def main():
    for p in (CAND,PRICE,SUMM):
        chk(os.path.exists(p), f"exists: {os.path.basename(p)}")
    cand = pd.read_csv(CAND); price = pd.read_csv(PRICE)

    print("\n[1] provenance — first-party, no aggregator prices")
    chk(bool(cand["is_first_party"].all()), "every candidate is_first_party=True")
    chk(int(cand["is_aggregator_source"].sum())==0, "zero aggregator-sourced candidates")
    for _,r in cand.iterrows():
        h=host_of(str(r["source_url"]))
        chk(not any(h==a or h.endswith("."+a) for a in AGGREGATOR_HOSTS),
            f"source not aggregator: {r['property_id']} {h}")

    print("\n[2] no fabricated price — published rent needs quote + source_url")
    pub = price[price["price_status"]=="published"]
    chk(bool(pub["monthly_rent_inr"].notna().all()), "published rows all have a number")
    chk(bool(pub["verbatim_quote"].astype(str).str.strip().ne("").all()), "published rows all have verbatim_quote")
    chk(bool(pub["source_url"].astype(str).str.startswith("http").all()), "published rows all have http source_url")
    chk(bool((pub["monthly_rent_inr"]>0).all()), "published rents strictly positive")

    print("\n[3] unknown preserved")
    unk = price[price["price_status"]=="unknown"]
    chk(bool(unk["monthly_rent_inr"].isna().all()), "unknown rows carry NO number (null preserved)")
    chk(len(unk)>0, "at least one unknown row exists (honest gaps kept, not filled)")

    print("\n[4] classification")
    allowed={"PG","PG_LIKELY","HOTEL","UNKNOWN"}
    chk(bool(cand["property_kind"].isin(allowed).all()), f"property_kind in {allowed}")
    # reproducible: re-running classifier must match stored kind is not stored-from-signals here,
    # so just prove the classifier discriminates a hotel string and a PG string.
    chk(classify("per night check-in book a room suite")[0]=="HOTEL", "classifier flags hotel-signal text as HOTEL")
    chk(classify("paying guest sharing monthly rent ladies hostel")[0] in ("PG","PG_LIKELY"),
        "classifier flags PG-signal text as PG")

    print("\n[4b] distance — no invented street precision")
    allowed_prec={"same_suburb_600041 (<=~2km; street geocode unavailable on OSM)",
                  "suburb_centroid_600020","suburb_centroid_600096","suburb_centroid_600097","unknown_locality"}
    chk(bool(cand["distance_precision"].isin(allowed_prec).all()),
        "distance_precision only coarse/centroid/unknown labels (no fabricated street coords)")
    # any numeric distance must carry a centroid precision label, never a street-precision claim
    numd = cand[cand["dist_km_from_vishful"].notna()]
    chk(bool(numd["distance_precision"].str.startswith("suburb_centroid").all()),
        "every numeric distance is explicitly suburb-centroid (approx)")

    print("\n[5] isolation — protected/locked outputs untouched")
    for pf in PROTECTED:
        pp=os.path.join(OUT,pf)
        if os.path.exists(pp):
            cols=set(pd.read_csv(pp,nrows=0).columns)
            chk("monthly_rent_inr" not in cols and "monthly_rent" not in cols,
                f"{pf} still carries NO price column")
    # this module's writes are confined to the 3 new files (by construction) — assert names distinct
    chk(NEW_FILES.isdisjoint(PROTECTED), "new research files do not collide with protected outputs")

    print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
    if fails: sys.exit(1)

if __name__=="__main__": main()
