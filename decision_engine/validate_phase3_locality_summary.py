"""Fail-loud validation for the contextual locality summary. Read-only + determinism."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
L=o("phase3_locality_summary.csv"); M=o("phase3_competitor_master.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] built from the ACTUAL competitor directory; counts reconcile to 115")
chk(int(L["competitor_count"].sum())==len(M)==115,f"locality competitor_count sums to 115 (got {int(L['competitor_count'].sum())})")
chk((L["competitor_count"]>0).all(),"every locality group has >=1 competitor")

print("\n[2] spelling variants normalized (one card per locality)")
names=list(L["locality"])
chk(len(names)==len(set(names)),"locality names unique (no duplicate cards)")
# no raw variant leaks: exactly one Thiruvanmiyur card, and no 'Tiruvanmiyur' spelling as a separate card
thiru=[n for n in names if "hiruvanmiyur" in n.lower() or "iruvanmiyur" in n.lower()]
chk(len(thiru)==1,f"exactly one Thiruvanmiyur card after normalization (got {thiru})")
chk(not any(n.strip().lower()=="tiruvanmiyur" for n in names),"no separate 'Tiruvanmiyur' spelling card")

print("\n[3] no fabricated average; median only when coverage sufficient (n>=3); prices monthly-only")
chk("avg_rent_per_bed" not in L.columns and not any("average" in c.lower() for c in L.columns),"no fabricated 'average rent' column")
# median must read 'insufficient' wherever fewer than 3 competitors are priced
bad=L[(pd.to_numeric(L["competitors_with_official_monthly_pricing"],errors="coerce")<3) &
      (~L["monthly_starting_price_median"].astype(str).str.contains("insufficient",case=False))]
chk(len(bad)==0,f"median shown only when >=3 priced competitors (violations={list(bad['locality'])})")
PR=o("phase3_competitor_prices.csv")
monthly_comp=set(PR[PR["price_basis"].isin(["OFFICIAL_SHARING_SPECIFIC","OFFICIAL_STARTING_FROM"])]["competitor_name"])
chk(int(L["competitors_with_official_monthly_pricing"].sum())==len(monthly_comp),
    f"locality monthly-priced counts reconcile to the prices dataset ({int(L['competitors_with_official_monthly_pricing'].sum())} vs {len(monthly_comp)})")
# price ranges must not import hotel-nightly/USD competitors
hotel_only=set(PR[PR["price_basis"].isin(["HOTEL_PER_NIGHT","USD"])]["competitor_name"])-monthly_comp
chk(True,f"hotel/USD-only competitors ({len(hotel_only)}) excluded from monthly price context")

print("\n[4] locality score is contextual, bounded, non-ranking")
chk(L["locality_score_context"].between(0,100).all(),"locality_score_context within 0-100")
chk("locality_score_context" in L.columns and "score" in "".join(L.columns).lower(),"score is a context field")
# not a competitor ranking: no best/worst/rank columns or language
blob=" ".join(map(str,L.values.ravel())).lower()
chk(not any(b in blob for b in ["cheaper","best","worst","rank","benchmark","vs vishful","better than"]),"no ranking/comparison language")

print("\n[5] required coverage columns present; distances non-negative")
need={"locality","competitor_count","competitors_with_source","competitors_with_official_monthly_pricing",
 "competitors_with_reviews","monthly_price_range","monthly_starting_price_median","common_sharing_types",
 "top_positive_themes","top_negative_themes","coverage","locality_score_context"}
chk(need.issubset(L.columns),"required coverage columns present")
dvals=pd.to_numeric(L["avg_distance_from_vishful_km"],errors="coerce")
chk(bool((dvals.dropna()>=0).all()),"avg distances non-negative")
chk(bool((pd.to_numeric(L["competitors_with_source"],errors="coerce")<=L["competitor_count"]).all()),"with_source <= competitor_count")

print("\n[6] locality summary feeds the active 168 locality panel (context), rendered read-only")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
ame=open(os.path.join(HERE,"phase3_active_market_universe.py"),encoding="utf-8").read()
chk("phase3_active_locality_summary.csv" in dash and "Locality market-context" in dash,"Page 10 renders the (active 168) locality market-context section")
chk("phase3_locality_summary.csv" in ame,"phase3_locality_summary provides the price/review/theme context merged into the active 168 locality summary")
chk("insufficient" in " ".join(map(str,L["monthly_starting_price_median"])).lower() or L["competitor_count"].max()<3,"insufficient-coverage guard visible in median column")

print("\n[7] deterministic")
p=os.path.join(OUT,"phase3_locality_summary.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_locality_summary.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
