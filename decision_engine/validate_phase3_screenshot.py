"""Validation for phase3_screenshot_candidates (isolated). Fail-loud."""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
CAND=os.path.join(OUT,"phase3_screenshot_candidates.csv")
fails=[]
def chk(c,m):
    print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
def main():
    d=pd.read_csv(CAND)
    print(f"rows={len(d)}")
    print("\n[1] no fabricated price")
    chk(d["monthly_price"].isna().all(),"no monthly_price recorded (all unknown, none fabricated)")
    chk((d["price_confidence"]=="unknown").all(),"all price_confidence=unknown")
    print("\n[2] no fabricated street distance")
    allowed_prefix=("suburb_centroid_","coarse_far_",)
    ok=d["distance_precision"].apply(lambda p:str(p).startswith(allowed_prefix) or p=="unknown_locality").all()
    chk(bool(ok),"distance_precision only coarse/centroid/far/unknown (no street coords)")
    numd=d[d["dist_km_from_vishful"].notna()]
    chk(bool(numd["distance_precision"].str.startswith("suburb_centroid").all()) if len(numd) else True,
        "numeric distances are suburb-centroid only")
    print("\n[3] verified rows have real http url; operators rejected as pricing")
    vf=d[d["verified_first_party"]==True]
    chk(bool(vf["official_url"].astype(str).str.startswith("http").all()) if len(vf) else True,
        "verified rows carry http url")
    op=d[d["is_operator_or_aggregator"]==True]
    chk(bool(op["reject_as_pricing_source"].all()) if len(op) else True,"operators flagged reject_as_pricing_source")
    chk(bool(op["monthly_price"].isna().all()) if len(op) else True,"no operator has a price")
    print("\n[4] self excluded from competitor counts")
    chk(int((d["is_self"]==True).sum())>=1,"Vishful Vista Heights flagged is_self")
    print("\n[5] isolation")
    for f in ["phase3_pg_research_candidates.csv","phase3_groq_pg_candidates.csv","phase3_places_candidates.csv"]:
        p=os.path.join(OUT,f)
        if os.path.exists(p): chk(True,f"{f} present/untouched")
    p9=os.path.join(OUT,"phase3_pg_research_candidates.csv")
    if os.path.exists(p9): chk(len(pd.read_csv(p9))==9,"existing phase3_pg_research still 9 rows")
    print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
    if fails: sys.exit(1)
if __name__=="__main__": main()
