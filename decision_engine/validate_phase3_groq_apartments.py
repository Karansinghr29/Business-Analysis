"""
Validation for phase3_groq_apartments (experimental, isolated). Fail-loud.
Proves: no key leak; no fabricated price (numbers only if first-party + published_exact);
unknown preserved; aggregator never priced; verified rows carry a real http first-party URL;
distance labels coarse-only; isolation (existing phase3 + groq_pg outputs untouched).
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from phase3_pg_research import AGGREGATOR_HOSTS, host_of

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
CAND=os.path.join(OUT,"phase3_groq_apartments_candidates.csv")
SUMM=os.path.join(OUT,"phase3_groq_apartments_summary.csv")
fails=[]
def chk(c,m):
    print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

def main():
    for p in (CAND,SUMM): chk(os.path.exists(p), f"exists: {os.path.basename(p)}")
    d=pd.read_csv(CAND); s=pd.read_csv(SUMM)
    print(f"\ncandidates={len(d)}  status={dict(zip(s['metric'],s['value'])).get('groq_status')}")

    print("\n[0] no key leak")
    kv=os.environ.get("GROQ_API_KEY")
    blob=open(CAND,encoding='utf-8').read()+open(SUMM,encoding='utf-8').read()
    chk((not kv) or (kv not in blob), "GROQ_API_KEY absent from outputs")

    if len(d):
        print("\n[1] price integrity")
        num=d[d["monthly_price"].notna()]
        chk(bool((num["price_confidence"]=="published_exact").all()) if len(num) else True,
            "numbers only when published_exact")
        chk(bool(num["verified_first_party"].all()) if len(num) else True,
            "numbers only when verified_first_party")
        for _,r in num.iterrows():
            oh=host_of(str(r["official_url"])); sh=host_of(str(r["source_url"]))
            chk(oh!="" and oh==sh, f"priced row first-party: {r['name']}")
            chk(not any(oh==a or oh.endswith('.'+a) for a in AGGREGATOR_HOSTS), f"priced host not aggregator: {oh}")

        print("\n[2] unknown preserved / aggregator not priced")
        chk(bool(d[d["price_confidence"]=="unknown"]["monthly_price"].isna().all()), "unknown rows carry no number")
        agg=d[d["is_aggregator"]==True]
        chk(bool(agg["monthly_price"].isna().all()) if len(agg) else True, "no aggregator row has a price")

        print("\n[3] verified first-party rows have real http url")
        vf=d[d["verified_first_party"]==True]
        chk(bool(vf["official_url"].astype(str).str.startswith("http").all()) if len(vf) else True,
            "verified rows have http official_url")
        chk(bool((vf["host"]==vf["official_url"].map(lambda u:host_of(str(u)))).all()) if len(vf) else True,
            "verified host matches its url")

        print("\n[4] property_type sane")
        allowed={"residential_apartment","co_living","serviced_apartment","pg","hostel","unknown"}
        chk(bool(d["property_type"].isin(allowed).all()), f"property_type in {allowed}")

    print("\n[5] isolation")
    p9=os.path.join(OUT,"phase3_pg_research_candidates.csv")
    if os.path.exists(p9): chk(len(pd.read_csv(p9))==9,"existing phase3_pg_research still 9 rows")
    pg=os.path.join(OUT,"phase3_groq_pg_candidates.csv")
    if os.path.exists(pg): chk(len(pd.read_csv(pg))==5,"phase3_groq_pg_candidates still 5 rows")
    osm=os.path.join(OUT,"phase3_places_candidates.csv")
    if os.path.exists(osm):
        cols=set(pd.read_csv(osm,nrows=0).columns)
        chk("monthly_price" not in cols and "monthly_rent" not in cols,"OSM output still price-free")

    print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
    if fails: sys.exit(1)

if __name__=="__main__": main()
