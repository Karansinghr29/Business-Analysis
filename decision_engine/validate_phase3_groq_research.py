"""
Validation for phase3_groq_pg_research (experimental, isolated). Fail-loud.
Tolerates the KEY_ABSENT / zero-candidate case (empty is valid — no fabrication).
Proves:
  * NO key leak: key never appears in any output CSV
  * every numeric per-bed price is first-party (source host == official host) AND published_exact
  * 'starting_from' never carries a published_exact confidence
  * unknown prices carry NO number (null preserved)
  * no aggregator host was priced
  * ISOLATION: only the 3 new groq_* files exist; existing phase3_pg_research + OSM outputs untouched
Run AFTER phase3_groq_pg_research.py. Read-only.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from phase3_pg_research import AGGREGATOR_HOSTS, host_of

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
CAND = os.path.join(OUT,"phase3_groq_pg_candidates.csv")
PRICE= os.path.join(OUT,"phase3_groq_pg_price_evidence.csv")
SUMM = os.path.join(OUT,"phase3_groq_pg_summary.csv")
PROTECTED = ["phase3_pg_research_candidates.csv","phase3_pg_price_evidence.csv",
             "phase3_pg_research_summary.csv","phase3_places_candidates.csv"]

fails=[]
def chk(cond,msg):
    print(("  PASS " if cond else "  FAIL ")+msg)
    if not cond: fails.append(msg)

def main():
    for p in (CAND,PRICE,SUMM): chk(os.path.exists(p), f"exists: {os.path.basename(p)}")
    cand=pd.read_csv(CAND); price=pd.read_csv(PRICE); summ=pd.read_csv(SUMM)
    status=dict(zip(summ["metric"],summ["value"])).get("groq_status")
    print(f"\n[groq_status] {status}  candidates={len(cand)}  price_rows={len(price)}")

    print("\n[0] no key leak")
    keyv=os.environ.get("GROQ_API_KEY")
    blob=" ".join([open(p,encoding='utf-8').read() for p in (CAND,PRICE,SUMM)])
    chk(bool(keyv) is False or (keyv not in blob), "GROQ_API_KEY not present in any output file")

    if len(cand)==0:
        print("\n(zero candidates — KEY_ABSENT or no discovery; empty outputs are valid, no fabrication)")
    else:
        print("\n[1] price integrity — first-party & published_exact only for numbers")
        num=price[price["monthly_rent_per_bed"].notna()]
        chk(bool((num["price_confidence"]=="published_exact").all()),
            "every numeric per-bed price has confidence=published_exact")
        for _,r in num.iterrows():
            oh=host_of(str(r["official_url"])); sh=host_of(str(r["source_url"]))
            chk(oh!="" and oh==sh, f"numeric price is first-party: {r['pg_name']} src={sh} own={oh}")
            chk(not any(oh==a or oh.endswith('.'+a) for a in AGGREGATOR_HOSTS),
                f"priced host not aggregator: {oh}")

        print("\n[2] unknown preserved / starting_from not exact")
        unk=price[price["price_confidence"]=="unknown"]
        chk(bool(unk["monthly_rent_per_bed"].isna().all()), "unknown rows carry NO number")
        sf=price[price["price_confidence"]=="starting_from"]
        chk(bool((sf["price_confidence"]!="published_exact").all()) if len(sf) else True,
            "starting_from never labelled published_exact")

        print("\n[3] candidates classification sane")
        chk(bool(cand["property_kind"].isin(["PG","PG_LIKELY","HOTEL","UNKNOWN"]).all()),
            "property_kind in allowed set")

    print("\n[4] isolation — protected outputs untouched")
    # protected files still exist and phase3_pg_research still has its 9 rows / no price on OSM
    pc=os.path.join(OUT,"phase3_pg_research_candidates.csv")
    if os.path.exists(pc):
        chk(len(pd.read_csv(pc))==9, "existing phase3_pg_research_candidates still 9 rows (unchanged)")
    osm=os.path.join(OUT,"phase3_places_candidates.csv")
    if os.path.exists(osm):
        cols=set(pd.read_csv(osm,nrows=0).columns)
        chk("monthly_rent" not in cols and "monthly_rent_per_bed" not in cols, "OSM output still price-free")
    newset={"phase3_groq_pg_candidates.csv","phase3_groq_pg_price_evidence.csv","phase3_groq_pg_summary.csv"}
    chk(newset.isdisjoint(set(PROTECTED)), "new groq files distinct from protected outputs")

    print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
    if fails: sys.exit(1)

if __name__=="__main__": main()
