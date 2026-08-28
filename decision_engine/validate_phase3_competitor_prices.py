"""Fail-loud validation for the isolated competitor-prices layer. Read-only + determinism."""
from __future__ import annotations
import os, sys, re, json, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase3_competitor_prices.csv"); M=o("phase3_competitor_master.csv")
OBS=json.load(open(os.path.join(HERE,"phase3_price_observations.json"),encoding="utf-8"))
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
BASES={"OFFICIAL_SHARING_SPECIFIC","OFFICIAL_STARTING_FROM","HOTEL_PER_NIGHT","USD","REVIEW_MENTIONED"}

print("[1] bases valid + strictly separated; no mixing")
chk(set(D["price_basis"]).issubset(BASES),"every price_basis is one of the 5 defined bases")
chk(int((D["price_basis"]=="REVIEW_MENTIONED").sum())==0,"REVIEW_MENTIONED = 0 (0/114 reviews quote rent) — schema kept, no fabrication")
# hotel/USD must never be labelled a monthly official basis
ota={"OYO","Booking.com","MakeMyTrip","Goibibo","Agoda","EaseMyTrip","Trip.com","Tripadvisor"}
mix=D[(D["price_basis"].isin(["OFFICIAL_SHARING_SPECIFIC","OFFICIAL_STARTING_FROM"])) & (D["source_platform"].isin(ota))]
chk(len(mix)==0,f"no OTA hotel platform is labelled monthly-official (found={list(mix['competitor_name'])[:2]})")
chk(bool((D[D["price_basis"]=="USD"]["currency"]!="INR").all()) if (D["price_basis"]=="USD").any() else True,"USD basis rows are non-INR")

print("\n[2] no fabrication; every row == a frozen observation; only existing competitors")
frozen={(r["competitor_name"],r["price_basis"],str(r.get("sharing_type")),r["price"],r["source_url"]) for r in OBS}
csv={(r["competitor_name"],r["price_basis"],str(r["sharing_type"]) if pd.notna(r["sharing_type"]) else "None",r["price"],r["source_url"]) for _,r in D.iterrows()}
chk(csv.issubset(frozen),"no CSV price row outside the frozen verified observation set")
chk(set(D["competitor_name"]).issubset(set(M["competitor_name"])),"no price row for a non-existent competitor (115 universe intact)")
chk(bool(D["source_url"].astype(str).str.startswith("http").all()),"every price source_url is http")
chk(int(D["source_url"].str.contains("google.com/maps",case=False,na=False).sum())==0,"no Google Maps as a price source")

print("\n[3] captured_at fixed (deterministic, never now())")
chk(D["captured_at"].nunique()==1,"captured_at is a single frozen date (not per-run now())")

print("\n[4] required schema + no ranking")
need={"competitor_name","source_platform","source_url","price_basis","sharing_type","price","currency","ac","gender","food_included","evidence_text","captured_at","provenance"}
chk(need.issubset(D.columns),"required columns present")
blob=" ".join(map(str,D.values.ravel())).lower()
chk(not any(b in blob for b in ["cheaper","best pg","worst pg"," rank","benchmark","better than","vs competitor"]),"no ranking/comparison language")

print("\n[5] master/distance/source-link untouched; deterministic")
chk(len(M)==115,"competitor master unchanged (115)")
chk(len(o("phase3_competitor_distances.csv"))==115,"distance layer unchanged (115)")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
p=os.path.join(OUT,"phase3_competitor_prices.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_competitor_prices.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_competitor_prices.csv" in dash and "by basis" in dash,"Page 10 renders prices by basis")

print("\n[6] ③ sharing-price context: OFFICIAL_SHARING_SPECIFIC monthly only; consistent with existing comparable grid")
ss=D[D["price_basis"]=="OFFICIAL_SHARING_SPECIFIC"]
chk(bool(ss["sharing_type"].notna().all()),"every sharing-specific row has a real sharing tier")
chk(set(ss["sharing_type"].dropna()).issubset({"Single","Double","Triple","4-sharing","5-sharing"}),"tiers limited to Single/Double/Triple/4/5")
# hotel/USD/starting-from must never enter the sharing-price context
chk(not ss["price_basis"].isin(["HOTEL_PER_NIGHT","USD","OFFICIAL_STARTING_FROM"]).any(),"no hotel/USD/starting-from in the sharing grid")
# Sumathi Illam room-class stays excluded (never a per-bed sharing observation)
chk(not ss["competitor_name"].str.contains("Sumathi",case=False,na=False).any(),"Sumathi Illam room-class NOT in per-bed sharing context (exclusion preserved)")
chk(not ss["evidence_text"].str.contains("dorm|room-class",case=False,na=False).any(),"no room-class/dormitory price in the per-bed sharing context")
# existing ③ comparable grid unchanged (spec still 1 property, 8 rows, Sumathi excluded)
import json as _j
_cp=_j.load(open(os.path.join(OUT,"phase3_market_spec.json"),encoding="utf-8"))["section_3_comparable_pricing"]
chk(_cp.get("independent_properties")==1 and len(_cp.get("grid",[]))==8,"existing comparable grid unchanged (1 property, 8 per-bed rows)")
chk(len(_cp.get("excluded_room_class",[]))==3,"Sumathi Illam 3-row room-class exclusion unchanged")
# Diyaa new obs consistent with the existing spec grid values (no conflicting data)
dy={(r["sharing_type"].lower().replace("double","two").replace("triple","three").replace("4-sharing","four"),str(r["ac"]).lower(),int(r["price"]))
    for _,r in ss[ss["competitor_name"].str.contains("Diyaa",case=False)].iterrows()}
spec_dy={(g["sharing_type"],g["ac"],int(g["monthly_rent_per_bed_inr"])) for g in _cp["grid"]}
chk(dy==spec_dy,"Diyaa sharing prices byte-consistent between new dataset and existing ③ grid")
chk("Verified published sharing-price context" in dash,"Page 10 renders the additive sharing-price context block")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
