"""
Phase-3 ACTIVE MARKET UNIVERSE (168) — the CURRENT verified competitor universe used by the Page-10 directory
and market-universe/locality counts. Isolated + deterministic + read-only. Does NOT modify the frozen 115
baseline (phase3_competitor_master / phase3_market_spec) or any Vishful-internal calculation.

Composition (168): 115 baseline (universe_version=v1) + 53 verified additions (v2: 44 independents + 9 operator:Zolo).
  - 115 rows: display fields from phase3_market_spec.section_2_directory + Vishful-relative distance from
    phase3_competitor_distances (their existing first-party/operator/OTA evidence).
  - 53 rows: from phase3_universe_v2_additions.json + phase3_universe_v2_enrichment.csv (coarse distance, THIRD-PARTY
    platform / operator:Zolo evidence, price_basis; contact-gated -> UNKNOWN, never fabricated).

Third-party evidence is tagged and NEVER treated as first-party. Pricing/sharing and amenity denominators are NOT
recomputed here (they keep their own evidence universes). Holdout (85) is excluded. Writes ONLY
phase3_active_market_universe.csv + phase3_active_locality_summary.csv (+ _summary).
"""
from __future__ import annotations
import os, sys, json, math, statistics
from collections import Counter
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
spec=json.load(open(os.path.join(OUT,"phase3_market_spec.json"),encoding="utf-8"))
DIRE=pd.DataFrame(spec["section_2_directory"])
DIST=pd.read_csv(os.path.join(OUT,"phase3_competitor_distances.csv"))
SL=pd.read_csv(os.path.join(OUT,"phase3_competitor_source_links.csv"))
ADD=[a for a in json.load(open(os.path.join(HERE,"phase3_universe_v2_additions.json"),encoding="utf-8")) if a["status"]=="verified"]
ENR=pd.read_csv(os.path.join(OUT,"phase3_universe_v2_enrichment.csv")).set_index("property_name")
M=pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv"))

OPERATOR_TOKENS={"yube1":"Yube1","stanza":"Stanza Living","truliv":"Truliv","zolo":"Zolo","bag2bag":"Bag2Bag",
                 "wowlife":"WowLife","olympia":"Olympia","lancor":"Lancor","prohotel":"Prohotel"}
ev_master={r["competitor_name"]:str(r.get("evidence_class")) for _,r in M.iterrows()}
def ost(nm):
    low=str(nm).lower()
    if ev_master.get(nm)=="operator_aggregator" or any(k in low for k in OPERATOR_TOKENS):
        return f"operator:{next((v for k,v in OPERATOR_TOKENS.items() if k in low),'operator')}"
    return "independent"
def norm_loc(s):
    s=str(s).lower()
    if "iruvanmiyur" in s: return "Thiruvanmiyur, Chennai"
    if "perungudi" in s or "thoraipakkam" in s or "kottivakkam" in s or "omr" in s: return "Perungudi, Chennai"
    if "adyar" in s or "indira" in s: return "Adyar, Chennai"
    if "kattankulathur" in s or "potheri" in s or "srm" in s: return "Kattankulathur, Chennai"
    if s=="chennai": return "Chennai (area unspecified)"
    return "Unknown"

def main():
    dmap=dict(zip(DIST["competitor_name"],DIST["distance_km_from_vishful"]))
    pmap=dict(zip(DIST["competitor_name"],DIST["distance_precision"]))
    src_first={c for c in SL["competitor_name"]}
    rows=[]
    # 115 baseline (v1)
    for _,r in DIRE.iterrows():
        nm=r["canonical_name"]
        rows.append(dict(property_name=nm,universe_version="v1",operator_source_type=ost(nm),
            property_type=r.get("property_type"),gender=r.get("gender"),
            locality=r.get("locality"),locality_group=norm_loc(r.get("locality")),
            distance_km=dmap.get(nm),distance_precision=pmap.get(nm),
            source_evidence_type=("first_party_or_verified" if nm in src_first else "unknown"),
            source_platform="",source_url="",
            price_status=r.get("price_status"),verification_status=r.get("verification_status"),
            provenance="phase3_market_spec baseline (v1)"))
    # 53 verified additions (v2)
    for a in ADD:
        nm=a["property_name"]; e=ENR.loc[nm] if nm in ENR.index else None
        dist=e["distance_from_vishful_km"] if e is not None else "Unknown"
        rows.append(dict(property_name=nm,universe_version="v2",operator_source_type=a["operator_source_type"],
            property_type=("co_living" if a["operator"]=="Zolo" else "pg"),
            gender=(a.get("provenance","").split("gender ")[-1].split(";")[0].strip() if "gender " in a.get("provenance","") else "unknown"),
            locality=a["locality"],locality_group=norm_loc(a["locality"]),
            distance_km=(dist if str(dist)!="Unknown" else None),
            distance_precision=(str(e["distance_basis"]) if e is not None else "unknown"),
            source_evidence_type=("operator:Zolo (third-party operator site)" if a["operator"]=="Zolo" else "third_party_platform_listing"),
            source_platform=a.get("source_platform",""),source_url=a.get("source_url",""),
            price_status=(str(e["price_basis"]) if e is not None else "UNKNOWN"),
            verification_status="v2_verified_identity",
            provenance=str(a.get("provenance",""))[:120]))
    D=pd.DataFrame(rows)
    assert len(D)==168, f"active universe must be 168 (got {len(D)})"
    assert D["property_name"].is_unique, "duplicate in active universe"
    D.to_csv(os.path.join(OUT,"phase3_active_market_universe.csv"),index=False)

    # active locality summary (168 counts) + existing price/review/theme CONTEXT (same numerators, denominator now 168)
    prev=pd.read_csv(os.path.join(OUT,"phase3_locality_summary.csv")).set_index("locality")
    def ctx(g,col,default="—"):
        return prev.loc[g,col] if g in prev.index and col in prev.columns else default
    lg=[]
    for g,gr in D.groupby("locality_group"):
        dv=pd.to_numeric(gr["distance_km"],errors="coerce").dropna()
        lg.append(dict(locality=g,competitor_count=len(gr),
            v1_count=int((gr["universe_version"]=="v1").sum()),v2_added=int((gr["universe_version"]=="v2").sum()),
            with_distance=int(dv.shape[0]),distance_unknown=int(len(gr)-dv.shape[0]),
            avg_distance_from_vishful_km=(round(float(dv.mean()),2) if len(dv) else "Unknown"),
            competitors_with_official_monthly_pricing=int(ctx(g,"competitors_with_official_monthly_pricing",0) or 0),
            competitors_with_reviews=int(ctx(g,"competitors_with_reviews",0) or 0),
            monthly_price_range=ctx(g,"monthly_price_range"),monthly_starting_price_median=ctx(g,"monthly_starting_price_median"),
            common_sharing_types=ctx(g,"common_sharing_types"),
            top_positive_themes=ctx(g,"top_positive_themes"),top_negative_themes=ctx(g,"top_negative_themes"),
            operators=", ".join(sorted({o.split(':')[1] for o in gr['operator_source_type'] if o.startswith('operator:')})) or "none"))
    L=pd.DataFrame(lg)
    cnt=L["competitor_count"].astype(float); dens=cnt/cnt.max() if cnt.max()>0 else cnt*0
    dnum=pd.to_numeric(L["avg_distance_from_vishful_km"],errors="coerce"); dmax=dnum.max()
    L["locality_score_context"]=[int(round(100*d)) if pd.isna(p) else int(round(100*(0.6*d+0.4*p)))
        for d,p in zip(dens,(1-(dnum/dmax)) if (dmax and dmax>0) else [float('nan')]*len(L))]
    L=L.sort_values("competitor_count",ascending=False).reset_index(drop=True)
    L.to_csv(os.path.join(OUT,"phase3_active_locality_summary.csv"),index=False)

    summary=[("active_universe",len(D)),("baseline_v1",int((D["universe_version"]=="v1").sum())),
     ("verified_additions_v2",int((D["universe_version"]=="v2").sum())),
     ("independents_added",int((D["operator_source_type"]=="independent")[D["universe_version"]=="v2"].sum())),
     ("zolo_added",int(D["operator_source_type"].str.startswith("operator:Zolo")[D["universe_version"]=="v2"].sum())),
     ("directory_with_distance",int(pd.to_numeric(D["distance_km"],errors="coerce").notna().sum())),
     ("directory_distance_unknown",int(pd.to_numeric(D["distance_km"],errors="coerce").isna().sum())),
     ("note","168 current universe; 115 v1 frozen; 85 holdout excluded; third-party evidence tagged, never first-party; pricing/sharing + amenity keep own denominators")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_active_market_universe_summary.csv"),index=False)
    print("PHASE-3 ACTIVE MARKET UNIVERSE (168):")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nlocality counts (168):")
    print(L[["locality","competitor_count","v1_count","v2_added"]].to_string(index=False))

if __name__=="__main__": main()
