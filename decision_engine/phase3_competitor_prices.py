"""
Phase-3 COMPETITOR PRICES (isolated, deterministic, read-only).

Every real, on-page price observed during the approved web-research pricing audit, kept STRICTLY separated by
basis so nothing misleading blends. NO fabrication, NO conversion, NO averaging here. Google Maps is never a
pricing source. Reads a frozen committed input (phase3_price_observations.json — fixed captured_at, never now()).

price_basis (mutually exclusive, never mixed):
  OFFICIAL_SHARING_SPECIFIC - monthly ₹ tied to a sharing tier on an official/operator page
  OFFICIAL_STARTING_FROM    - monthly ₹ "from/onwards" (NOT an actual rent)
  HOTEL_PER_NIGHT           - hotel / serviced-apartment / OTA nightly ₹ (NOT monthly PG rent)
  USD                       - non-INR figure, preserved as-shown (never converted)
  REVIEW_MENTIONED          - customer-reported ₹ from a review (schema kept; currently 0 — 0/114 reviews quote rent)

Writes ONLY phase3_competitor_prices.csv (+ _summary.csv). Master/distance/source-link/pricing-master untouched.
"""
from __future__ import annotations
import os, sys, json
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
M=pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv"))
OBS=json.load(open(os.path.join(HERE,"phase3_price_observations.json"),encoding="utf-8"))

COLS=["competitor_name","source_platform","source_url","price_basis","sharing_type","price","currency",
      "ac","gender","food_included","evidence_text","captured_at","provenance"]
BASES=["OFFICIAL_SHARING_SPECIFIC","OFFICIAL_STARTING_FROM","HOTEL_PER_NIGHT","USD","REVIEW_MENTIONED"]

def main():
    D=pd.DataFrame(OBS)
    for c in COLS:
        if c not in D.columns: D[c]=None
    D=D[COLS].drop_duplicates(subset=["competitor_name","price_basis","sharing_type","price","source_url"]).sort_values(
        ["competitor_name","price_basis","price"]).reset_index(drop=True)
    # guardrails
    assert D["price_basis"].isin(BASES).all(), "unknown price_basis"
    assert not D["source_url"].astype(str).str.contains("google.com/maps",case=False).any(), "google maps as price source"
    assert bool(D["source_url"].astype(str).str.startswith("http").all()), "non-http source"
    # every competitor must be in the existing 115 universe (no new competitors)
    assert set(D["competitor_name"]).issubset(set(M["competitor_name"])), "price row for non-existent competitor"
    D.to_csv(os.path.join(OUT,"phase3_competitor_prices.csv"),index=False)

    monthly=D[D["price_basis"].isin(["OFFICIAL_SHARING_SPECIFIC","OFFICIAL_STARTING_FROM"])]
    summary=[("total_price_observations",len(D)),
     ("competitors_with_any_price",int(D["competitor_name"].nunique())),
     ("OFFICIAL_SHARING_SPECIFIC_obs",int((D["price_basis"]=="OFFICIAL_SHARING_SPECIFIC").sum())),
     ("OFFICIAL_SHARING_SPECIFIC_competitors",int(monthly[monthly["price_basis"]=="OFFICIAL_SHARING_SPECIFIC"]["competitor_name"].nunique())),
     ("OFFICIAL_STARTING_FROM_obs",int((D["price_basis"]=="OFFICIAL_STARTING_FROM").sum())),
     ("HOTEL_PER_NIGHT_obs",int((D["price_basis"]=="HOTEL_PER_NIGHT").sum())),
     ("USD_obs",int((D["price_basis"]=="USD").sum())),
     ("REVIEW_MENTIONED_obs",int((D["price_basis"]=="REVIEW_MENTIONED").sum())),
     ("monthly_PG_priced_competitors",int(monthly["competitor_name"].nunique())),
     ("note","bases never mixed; hotel-nightly/USD are NOT monthly PG rent; review-mentioned=0 (0/114 reviews quote rent); no fabrication/conversion")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_competitor_prices_summary.csv"),index=False)
    print("PHASE-3 COMPETITOR PRICES (bases separated):")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nby basis:"); print(D["price_basis"].value_counts().to_string())

if __name__=="__main__": main()
