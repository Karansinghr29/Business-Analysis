"""
Phase-3 Market Research consolidation + Market Signals (ISOLATED, deterministic). Parts 3/4/6.
Assembles a single market-research DATASET + aggregate MARKET SIGNALS from ALREADY-VALIDATED
evidence — it does NOT launch new blind scraping (public pricing is exhausted: 1 comparable).

Reusable pipeline stages (documented; live discovery only on explicit opt-in, default OFF):
  DISCOVERY -> OFFICIAL-URL RESOLUTION -> FIRST-PARTY VERIFICATION -> FETCH -> JS RENDER ->
  STRUCTURED EXTRACTION -> EVIDENCE CAPTURE -> VALIDATION -> MARKET DATA OUTPUT
Tool roles (when run live): Groq=discovery, Apify=bounded fetch, Playwright=JS first-party,
WebSearch/WebFetch=independent verification. LLM URLs never trusted; aggregator/operator/social/
map/directory pages NEVER become first-party evidence.

Default mode = CONSOLIDATE: merge first-party-verified market evidence (playwright research =
verified first-party attrs) into the Part-4 field schema; price stays unknown unless a first-party
per-bed x sharing x AC price exists (none newly). Market signals are MARKET CONTEXT only — never
competitor rankings.

Writes ONLY phase3_market_research_dataset.csv, phase3_market_signals.csv, phase3_market_research_summary.csv.
Reads validated CSVs read-only. Modifies nothing else.
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
def rd(f): return pd.read_csv(os.path.join(OUT,f))
PA=rd("phase3_playwright_market_research.csv")   # first-party VERIFIED attrs (JS-rendered)
M=rd("phase3_competitor_master.csv")             # aggregate market context (115 canonical)
LOC_NORM={"tiruvanmiyur":"thiruvanmiyur"}
def nloc(s):
    s=str(s).strip().lower(); return LOC_NORM.get(s,s)

FIELD=["property_name","property_type","gender","locality","pincode","official_url","official_site_verified",
       "sharing_type","ac_availability","monthly_price","price_unit","deposit","food","wifi","laundry","parking",
       "security_cctv","power_backup","source_url","evidence_text","verification_status","verified_at"]

def yn(v): return True if v is True else None  # True or unknown(null); never False-assert

def main():
    # ---- Part 4: market-research DATASET (first-party verified rows only; fields only where evidence) ----
    rows=[]
    for _,r in PA.iterrows():
        dom=r["domain"]; url=f"https://{dom}"
        ac = True if r.get("ac_available")==True else None
        rows.append(dict(
            property_name=r["property_name"], property_type=r["property_type"], gender=r.get("gender"),
            locality=None, pincode=None,           # street/pincode not asserted from render (unknown)
            official_url=url, official_site_verified=bool(r.get("official_site_verified")),
            sharing_type=(r.get("sharing_config") if pd.notna(r.get("sharing_config")) else None),
            ac_availability=ac,
            monthly_price=None, price_unit=None, deposit=None,   # NO first-party price published -> unknown
            food=yn(r.get("food")), wifi=yn(r.get("wifi")), laundry=yn(r.get("laundry")),
            parking=yn(r.get("parking")), security_cctv=yn(r.get("cctv_security")), power_backup=yn(r.get("power_backup")),
            source_url=url, evidence_text=r.get("evidence"),
            verification_status="first_party_verified", verified_at="2026-08-17"))
    ds=pd.DataFrame(rows).reindex(columns=FIELD)
    ds.to_csv(os.path.join(OUT,"phase3_market_research_dataset.csv"),index=False)

    # ---- Part 6: MARKET SIGNALS (aggregate context only; never rankings) ----
    amen_cols=[("ac_available","AC availability"),("non_ac","Non-AC availability"),("wifi","Wi-Fi"),
               ("food","Food"),("laundry","Laundry"),("cctv_security","Security/CCTV"),
               ("parking","Parking"),("power_backup","Power backup")]
    sig=[]
    for c,lbl in amen_cols:
        if c in PA.columns:
            sig.append(dict(signal_type="published_amenity",signal=lbl,
                value=int((PA[c]==True).sum()),basis=f"first-party sites publishing {lbl}",
                evidence_source="MARKET_CONTEXT",provenance="phase3_playwright_market_research.csv"))
    # sharing configurations commonly observed (first-party)
    toks={}
    for s in PA.get("sharing_config",pd.Series(dtype=object)).dropna():
        for t in ["single","double","triple","2-5","1-4"]:
            if t in str(s).lower(): toks[t]=toks.get(t,0)+1
    for t,c in toks.items():
        sig.append(dict(signal_type="sharing_configuration",signal=t,value=c,
            basis="first-party rendered sharing configs",evidence_source="MARKET_CONTEXT",
            provenance="phase3_playwright_market_research.csv"))
    # locality + property-type concentration (from master aggregate) — context, not ranking
    M["_loc"]=M["locality"].map(nloc)
    for loc,cnt in M.groupby("_loc").size().sort_values(ascending=False).head(8).items():
        if loc in ("nan","none",""): continue
        sig.append(dict(signal_type="locality_concentration",signal=loc,value=int(cnt),
            basis="canonical competitors in locality (coarse)",evidence_source="MARKET_CONTEXT",
            provenance="phase3_competitor_master.csv"))
    for pt,cnt in M.groupby("property_type").size().sort_values(ascending=False).items():
        sig.append(dict(signal_type="property_type_concentration",signal=pt,value=int(cnt),
            basis="canonical competitors by type",evidence_source="MARKET_CONTEXT",
            provenance="phase3_competitor_master.csv"))
    # first-party website availability + new-property discovery signals
    sig.append(dict(signal_type="first_party_website_availability",signal="verified first-party sites",
        value=int(M["official_site_verified"].sum()),basis="master canonical with verified own site",
        evidence_source="MARKET_CONTEXT",provenance="phase3_competitor_master.csv"))
    sig.append(dict(signal_type="new_property_discovery",signal="new first-party properties (last discovery run)",
        value=0,basis="Apify+Groq run added 0 new first-party properties",
        evidence_source="MARKET_CONTEXT",provenance="phase3_apify_groq_summary.csv"))
    sig.append(dict(signal_type="comparable_price_sources",signal="first-party per-bed x sharing x AC",
        value=1,basis="only Diyaa; public pricing otherwise unavailable",
        evidence_source="MARKET_CONTEXT",provenance="phase3_pg_price_evidence.csv"))
    sg=pd.DataFrame(sig)
    sg.to_csv(os.path.join(OUT,"phase3_market_signals.csv"),index=False)

    summary=[("dataset_properties",len(ds)),
     ("first_party_verified",int(ds["official_site_verified"].sum())),
     ("with_monthly_price",int(ds["monthly_price"].notna().sum())),
     ("unknown_price",int(ds["monthly_price"].isna().sum())),
     ("signals_total",len(sg)),
     ("signal_types",", ".join(sorted(sg["signal_type"].unique()))),
     ("comparable_perbed_sources",1),
     ("new_first_party_discovered",0),
     ("mode","CONSOLIDATE existing validated evidence (no new blind scraping)"),
     ("locations_normalized","adyar, kattankulathur, perungudi, thiruvanmiyur(=tiruvanmiyur)")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_market_research_summary.csv"),index=False)
    print("PHASE-3 MARKET RESEARCH (consolidated):")
    for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": main()
