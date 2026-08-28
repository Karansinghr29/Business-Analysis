"""
Phase-3 EXPERIMENTAL — URL-resolution + first-party verification pass for the 3 NEW
men's-PG names Groq discovered (Star Mens PG, SVH Gents PG, Triples Men's PG).

Method: Groq compound-mini proposed an official URL per name; that URL was NOT trusted —
it was independently checked with a real WebSearch (aggregators blocked). A price is
recorded ONLY from a verified first-party own-domain page. No first-party site was found
for any of the 3, so all prices stay unknown. A 'starts from Rs.5500' figure for Triples
appeared ONLY in a third-party YouTube vlog -> NOT first-party, NOT exact -> NOT recorded.

Writes ONLY outputs/phase3_groq_urlresolve.csv (+ prints). Does not touch dashboard,
locked outputs, phase3_pg_research outputs, or the phase3_groq_pg_* files. Read-only else.
Every row below is grounded in the actual Groq + WebSearch evidence gathered this session.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from phase3_pg_research import AGGREGATOR_HOSTS, host_of

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
CSV = os.path.join(OUT,"phase3_groq_urlresolve.csv")

# Verified evidence (Groq compound-mini web search + independent WebSearch, aggregators blocked).
ROWS = [
 dict(pg_name="Star Mens PG",
      groq_suggested_url=None, groq_is_aggregator=True,
      independent_search_finding="No own domain; only listing/microsite pages (e.g. lyzoo.co.in). No first-party site.",
      verified_first_party_url=None,
      monthly_rent_per_bed=None, price_confidence="unknown",
      source_url=None, first_party=False,
      evidence="Groq: official_url=null,is_aggregator=true. WebSearch (aggregators blocked): no own-domain result."),
 dict(pg_name="SVH Gents PG",
      groq_suggested_url=None, groq_is_aggregator=True,
      independent_search_finding="No own website; property is in Tharamani (25 Peeliamman Kovil St, MG Nagar), NOT Thiruvanmiyur.",
      verified_first_party_url=None,
      monthly_rent_per_bed=None, price_confidence="unknown",
      source_url=None, first_party=False,
      evidence="Groq: official_url=null,is_aggregator=true. WebSearch: only directory pages; located Tharamani (out of 600041 area)."),
 dict(pg_name="Triples Men's PG",
      groq_suggested_url=None, groq_is_aggregator=True,
      independent_search_finding="No own website; only a Google Maps page + third-party YouTube vlog. 'Starts from Rs.5500' is from the vlog, not first-party.",
      verified_first_party_url=None,
      monthly_rent_per_bed=None, price_confidence="unknown",   # NOT 5500: non-first-party + 'starts from'
      source_url=None, first_party=False,
      evidence="Groq: official_url=null,is_aggregator=true. WebSearch: g.page maps + YouTube 'Starts from Rs.5500' (3rd-party vlog) -> rejected per rules (not first-party, not exact)."),
]

def main():
    df = pd.DataFrame(ROWS)
    # guards: any recorded price must be first-party + published_exact; none here -> all null
    bad = df[(df["monthly_rent_per_bed"].notna()) & (~df["first_party"])]
    assert bad.empty, "GUARD FAILED: a non-first-party price was recorded"
    assert (df["price_confidence"]!="published_exact").all() or df["monthly_rent_per_bed"].notna().all(), "confidence/price mismatch"
    df.to_csv(CSV, index=False)
    verified = int(df["verified_first_party_url"].notna().sum())
    priced   = int(df["monthly_rent_per_bed"].notna().sum())
    print("PHASE-3 GROQ URL-RESOLUTION PASS:")
    print(f"  candidates_checked: {len(df)}")
    print(f"  verified_first_party_urls: {verified}")
    print(f"  first_party_prices_found: {priced}")
    print(f"  all_unknown_preserved: {bool((df['price_confidence']=='unknown').all())}")
    for _,r in df.iterrows():
        print(f"  - {r['pg_name']}: first_party_url={r['verified_first_party_url'] or 'NONE'} | "
              f"price={r['price_confidence']} | {r['independent_search_finding']}")
    print("\nNOTE: Triples 'Rs.5500' seen ONLY in a 3rd-party YouTube vlog ('starts from') -> NOT recorded.")
    print("Wrote outputs/phase3_groq_urlresolve.csv")

if __name__=="__main__": main()
