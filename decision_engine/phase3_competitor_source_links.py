"""
Phase-3 Competitor SOURCE-LINK dataset (isolated, deterministic, read-only).

Emits, per competitor, the VERIFIED online-platform / official / operator listing URLs the Page-10 directory
joins for display. Google Maps is NOT a displayed source (it was identity-verification only) and is excluded
here. Only REPUTABLE platforms are kept; questionable niche/metasearch aggregators are excluded. NO fabricated
or search URLs, NO ranking.

Input (frozen, committed): phase3_online_sources.json — the identity-verified reputable listings produced by the
approved web-research audit (10 parallel research agents, each URL opened + confirmed against name+locality+
address; see audit). Sources within it:
  web_research     - listing page found + opened + identity-confirmed on a reputable platform
  existing_project - official/operator/OTA URL already collected in phase3_competitor_master (preserved)
  user_provided    - URL supplied + confirmed by the owner (e.g. Dreams Neelankarai MakeMyTrip)

Competitors absent from the frozen file have no verified online source -> Page 10 shows
"Unknown / No verified online source". Master + first_party_website untouched.

Writes ONLY phase3_competitor_source_links.csv (+ _summary.csv).
"""
from __future__ import annotations
import os, sys, json
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
M=pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv"))
SRC=json.load(open(os.path.join(HERE,"phase3_online_sources.json"),encoding="utf-8"))

VERIF={"web_research":"web_platform_listing_identity_verified",
       "existing_project":"first_party_url_in_project",
       "user_provided":"owner_provided_verified"}
PROV={"web_research":"reputable online-platform listing page found + opened + identity-confirmed (name+locality+address); approved web-research audit",
      "existing_project":"official/operator URL already collected in phase3_competitor_master (preserved)",
      "user_provided":"URL supplied and confirmed by the owner"}

def main():
    rows=[]
    for r in SRC:
        src=str(r.get("source") or "web_research")
        rows.append(dict(
            competitor_name=r["name"],
            source_type=r["platform"],
            source_url=r["url"],
            source_verification=VERIF.get(src,"web_platform_listing_identity_verified"),
            source_provenance=PROV.get(src,PROV["web_research"]),
        ))
    D=pd.DataFrame(rows).drop_duplicates(subset=["competitor_name","source_type","source_url"]).sort_values(
        ["competitor_name","source_type","source_url"]).reset_index(drop=True)
    # guardrails: never a Google Maps / search / fabricated URL in the displayed set
    assert not D["source_url"].str.contains("google.com/maps|maps.google|goo.gl/maps",case=False).any(), "google maps leaked"
    assert not D["source_url"].str.contains(r"/search[/?]|[?&]query=",case=False,regex=True).any(), "search url leaked"
    assert bool(D["source_url"].str.startswith("http").all()), "non-http url"
    D.to_csv(os.path.join(OUT,"phase3_competitor_source_links.csv"),index=False)

    directory=set(M["competitor_name"]); with_src=set(D["competitor_name"])
    OFFICIAL={"Official"}; OPERATOR={"Yube1","Stanza Living","Truliv","Bag2Bag","Zolo","WowLife","Prohotel","The India Hotels","Olympia","Lancor"}
    plat=D[~D["source_type"].isin(OFFICIAL|OPERATOR)]
    summary=[
        ("total_source_rows",len(D)),
        ("competitors_in_directory",len(directory)),
        ("competitors_with_verified_online_source",len(with_src & directory)),
        ("competitors_unknown_no_online_source",len(directory - with_src)),
        ("official_rows",int((D["source_type"]=="Official").sum())),
        ("operator_rows",int(D["source_type"].isin(OPERATOR).sum())),
        ("platform_rows",len(plat)),
        ("google_maps_rows","0 (Google Maps is identity-only, never displayed)"),
        ("note","reputable platforms + official/operator only; questionable niche aggregators excluded; no Google Maps; no fabricated/search URLs"),
    ]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(
        os.path.join(OUT,"phase3_competitor_source_links_summary.csv"),index=False)
    print("PHASE-3 COMPETITOR SOURCE LINKS (reputable online platforms; no Google Maps):")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nsource_type counts:")
    print(D["source_type"].value_counts().to_string())

if __name__=="__main__": main()
