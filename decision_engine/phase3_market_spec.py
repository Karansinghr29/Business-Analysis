"""
Phase-3 read-only Market AI SPECIFICATION generator (isolated, NOT wired to dashboard).
Transforms phase3_competitor_master.csv (+ phase3_pg_price_evidence.csv) into a structured
view-spec (JSON) for a future read-only Market page. Pure projection — NO impute, NO estimate,
NO market average, NO room->bed / day->month / starts-from conversion, NO aggregator price.
unknown stays unknown. Single-source pricing shown as raw evidence with a sample-size warning.

Writes ONLY outputs/phase3_market_spec.json (+ phase3_market_directory.csv). Reads master +
price-evidence read-only. Does not touch dashboard / locked outputs / existing phase3 modules.
"""
from __future__ import annotations
import os, sys, json, math
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
M=pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv"))
PE=pd.read_csv(os.path.join(OUT,"phase3_pg_price_evidence.csv"))
def clean(v): return None if (v is None or (isinstance(v,float) and math.isnan(v))) else v

# ---------------- Section 1: Nearby Market Overview ----------------
def tc(t): return int((M["property_type"]==t).sum())
overview={
 "total_competitors":len(M),
 "mens_pg":tc("mens_pg"),"womens_pg":tc("womens_pg"),"coed_or_unclear_pg":tc("pg_unknown_gender"),
 "co_living":tc("co_living"),"serviced_apartments":tc("serviced_apartment"),
 "hotels":tc("hotel"),"residential_apartments":tc("residential_apartment"),
 "within_1km":int(M["within_1km"].sum()),"within_2km":int(M["within_2km"].sum()),
 "within_3km":int(M["within_3km"].sum()),
 "distance_note":"coarse suburb/pincode centroid (no street-level geocoding); far/downtown banded >5km",
}

# ---------------- Section 2: Competitor Directory (NO price numbers) ----------------
directory=[]
for _,r in M.sort_values(["within_5km","competitor_name"],ascending=[False,True]).iterrows():
    ps=r["price_confidence"]
    price_status=("first_party_published" if ps=="first_party_published"
                  else "first_party_room_class_excluded" if ps=="first_party_room_class"
                  else "unknown")
    directory.append({
        "canonical_name":r["competitor_name"],"property_type":r["property_type"],
        "gender":clean(r["gender"]),"locality":clean(r["locality"]),
        "distance_km":clean(r["distance_km"]),"distance_precision":clean(r["distance_precision"]),
        "verification_status":clean(r["verification_status"]),
        "first_party_website":(clean(r["official_url"]) if bool(r["official_site_verified"]) else None),
        "price_status":price_status,"provenance":clean(r["provenance"])})

# ---------------- Section 3: Comparable Pricing (first-party per-bed x sharing x AC ONLY) ----------------
dia=PE[(PE["property_name"].astype(str).str.contains("Diyaa")) & (PE["price_status"]=="published")]
grid=[]
for _,r in dia.iterrows():
    grid.append({"property":"Diyaa Paying Guest","sharing_type":r["sharing_type"],
        "ac":("ac" if r["ac"]=="ac" else "non_ac"),"monthly_rent_per_bed_inr":int(r["monthly_rent_inr"]),
        "source_url":r["source_url"],"grain":"full_by_sharing"})
# Sumathi = room-class -> EXCLUDED from comparable (listed separately, never in grid)
sumathi=PE[(PE["property_name"].astype(str).str.contains("Sumathi")) & (PE["monthly_rent_inr"].notna())]
excluded=[{"property":"Sumathi Illam","room_class":r["room_class"],
           "monthly_rent_inr":int(r["monthly_rent_inr"]),
           "reason":"room-class price, NOT per-bed; excluded from comparable (no conversion)"}
          for _,r in sumathi.iterrows()]
comparable={
 "independent_properties":int(dia["property_name"].nunique()),
 "sample_size_warning":("SAMPLE SIZE = 1. Single property (Diyaa Paying Guest), Adyar 600020 "
   "(NOT Vishful's 600041), men-only, all-inclusive. This is raw first-party evidence, NOT a "
   "market benchmark. No average/min/max is computed."),
 "market_average":None,   # intentionally null — never computed from n=1
 "grid":grid,
 "excluded_room_class":excluded,
 "grain":"per_bed_x_sharing_x_ac",
}

spec={"section_1_overview":overview,"section_2_directory":directory,"section_3_comparable_pricing":comparable,
      "rules":{"impute":False,"estimate":False,"market_average_from_single":False,
               "aggregator_prices":False,"room_to_bed_conversion":False,"day_to_month_conversion":False,
               "starts_from_as_exact":False,"unknown_preserved":True},
      "read_only":True,"wired_to_dashboard":False}

with open(os.path.join(OUT,"phase3_market_spec.json"),"w",encoding="utf-8") as f:
    json.dump(spec,f,indent=2,ensure_ascii=False)
pd.DataFrame(directory).to_csv(os.path.join(OUT,"phase3_market_directory.csv"),index=False)

print("PHASE-3 MARKET SPEC generated (read-only, not wired):")
print("  overview:",json.dumps(overview))
print(f"  directory rows: {len(directory)}")
print(f"  comparable: n_properties={comparable['independent_properties']} grid_points={len(grid)} excluded_room_class={len(excluded)} market_average={comparable['market_average']}")

if __name__=="__main__": pass
