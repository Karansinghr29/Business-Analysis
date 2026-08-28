"""Fail-loud validation for the read-only Market AI spec. Isolated, read-only."""
from __future__ import annotations
import os, sys, json
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
spec=json.load(open(os.path.join(OUT,"phase3_market_spec.json"),encoding="utf-8"))
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

ov=spec["section_1_overview"]; dr=spec["section_2_directory"]; cp=spec["section_3_comparable_pricing"]

print("[1] no market average from single property")
chk(cp["market_average"] is None,"market_average is null (never computed)")
chk(cp["independent_properties"]==1,"comparable sample size explicitly = 1")
chk("SAMPLE SIZE = 1" in cp["sample_size_warning"],"sample-size warning present")

print("\n[2] comparable = first-party per-bed only")
chk(all(g["grain"]=="full_by_sharing" for g in cp["grid"]),"every grid point is full_by_sharing per-bed")
chk(all(str(g["source_url"]).startswith("https://menspg.in") for g in cp["grid"]),"every grid point first-party (menspg.in)")
chk(all(g["sharing_type"] and g["ac"] in ("ac","non_ac") for g in cp["grid"]),"sharing + AC preserved on every point")

print("\n[3] Sumathi room-class excluded, not converted")
gridprops={g["property"] for g in cp["grid"]}
chk("Sumathi Illam" not in gridprops,"Sumathi NOT in comparable grid")
chk(len(cp["excluded_room_class"])>=1 and all(e["property"]=="Sumathi Illam" for e in cp["excluded_room_class"]),
    "Sumathi room-class listed under excluded")
chk(all("room_class" in e for e in cp["excluded_room_class"]),"excluded rows keep room_class grain (no bed conversion)")

print("\n[4] directory: unknown preserved, no inline prices")
chk(all(d["price_status"] in ("first_party_published","first_party_room_class_excluded","unknown") for d in dr),
    "price_status uses only allowed labels")
chk(all("monthly_rent" not in k for d in dr for k in d.keys()),"directory rows carry NO price number")
chk(any(d["price_status"]=="unknown" for d in dr),"unknown price_status preserved in directory")

print("\n[5] rules flags all safe")
r=spec["rules"]
chk(r["impute"] is False and r["estimate"] is False and r["market_average_from_single"] is False
    and r["aggregator_prices"] is False and r["room_to_bed_conversion"] is False
    and r["day_to_month_conversion"] is False and r["starts_from_as_exact"] is False
    and r["unknown_preserved"] is True,"all rule flags safe")
chk(spec["wired_to_dashboard"] is False,"spec marked NOT wired to dashboard")

print("\n[6] isolation")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv")))>=100,"master intact")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_pg_research_candidates.csv")))==9,"existing phase3_pg_research still 9 rows")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
