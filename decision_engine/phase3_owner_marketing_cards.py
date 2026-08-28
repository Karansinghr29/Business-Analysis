"""
Phase-3 OWNER MARKETING CARDS (isolated, deterministic, DISPLAY-AGGREGATION ONLY).

Consolidates the 13 engine marketing recommendations (phase3_marketing_recommendations.csv) into 5 owner-facing
business decisions for Page 12. Does NOT change the engine, scores, or the underlying CSV — display grouping only;
the 13 rows remain the source of truth / traceability. The amenities card uses the CORRECTED amenity provenance
(phase3_vishful_amenity_provenance.csv), which separates internal-verified from publicly-advertised.

Guardrails preserved: no competitor ranking, no Vishful-vs-competitor, no market-average, no recommended price,
no unsupported demand claim. Writes ONLY phase3_owner_marketing_cards.csv.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
REC=pd.read_csv(os.path.join(OUT,"phase3_marketing_recommendations.csv"))
AP=pd.read_csv(os.path.join(OUT,"phase3_vishful_amenity_provenance.csv"))
VAC=pd.read_csv(os.path.join(OUT,"step4_vacancy_at_risk.csv"))      # DERIVE vacancy metrics from corrected source
PRICE=pd.read_csv(os.path.join(OUT,"step5_pricing_analysis.csv"))
IDCOL="recommendation_id"

def _vm(bt):
    """Vacancy metrics for a bed_type derived from corrected step4/step5 (no hard-coded numbers)."""
    v=VAC[VAC["bed_type"]==bt]; n=int(len(v)); rev=float(v["rev_at_risk_monthly"].sum())
    med=v["days_vacant"].median()
    p=PRICE[PRICE["bed_type"]==bt]; tot=float(p["total_beds"].sum()); occd=float(p["occupied_beds"].sum())
    occ=(100.0*occd/tot) if tot else float("nan")
    return dict(n=n,rev=rev,med=med,occ=occ)

GROUPS={
 "fill_2_sharing":["SHR-Double","INV-Double"],
 "fill_3_sharing":["VAC-Triple","INV-Triple"],
 "investigate_single":["SHR-Single","VAC-Single","INV-Single"],
 "locality_campaign":["LOC-TVM"],
 "verify_amenities":["AMEN-wifi","AMEN-food","AMEN-ac_available","AMEN-parking","AMEN-cctv_security"],
}
def prov_label(ids):
    srcs={str(REC[REC[IDCOL]==i]["evidence_source"].iloc[0]) for i in ids if (REC[IDCOL]==i).any()}
    if "COMBINED" in srcs or {"VISHFUL_INTERNAL","MARKET_CONTEXT"}.issubset(srcs): return "COMBINED"
    return srcs.pop() if len(srcs)==1 else "COMBINED"

def main():
    cards=[]
    def add(cid,order,title,evidence,action,ids):
        cards.append(dict(card_id=cid,display_order=order,title=title,evidence=" | ".join(evidence),
            suggested_action=action,provenance_label=prov_label(ids),
            consolidates=" + ".join(ids),source_count=len(ids)))

    d2=_vm("Double")
    if d2["n"]>0:
        add("fill_2_sharing",1,"Fill 2-sharing vacancies",
            [f"{d2['n']} vacant beds",f"{d2['occ']:.1f}% occupancy",f"₹{d2['rev']:,.0f}/month revenue-at-risk",
             "2-sharing is a first-party market-published configuration"],
            "Prioritize targeted marketing for available 2-sharing beds. (No specific price is recommended.)",
            GROUPS["fill_2_sharing"])
    d3=_vm("Triple")
    if d3["n"]>0:
        add("fill_3_sharing",2,"Fill 3-sharing vacancies",
            [f"{d3['n']} vacant beds",f"{d3['occ']:.1f}% occupancy",f"₹{d3['rev']:,.0f}/month revenue-at-risk"],
            "Prioritize targeted marketing for available 3-sharing beds. (No specific price is recommended.)",
            GROUPS["fill_3_sharing"])
    # Single card shown ONLY when a current rentable single vacancy exists (A22's old 272-day single is excluded).
    d1=_vm("Single")
    if d1["n"]>0 and all((REC[IDCOL]==i).any() for i in GROUPS["investigate_single"]):
        ev1=[f"{d1['n']} vacant single bed(s)"]
        if pd.notna(d1["med"]): ev1.append(f"{int(d1['med'])} days median vacancy")
        ev1.append(f"₹{d1['rev']:,.0f}/month revenue-at-risk")
        add("investigate_single",3,"Investigate single-bed slow fill",ev1,
            ("Review the room/bed condition, pricing setup, availability status and booking visibility before "
             "marketing. Do NOT automatically recommend or apply a price cut."),
            GROUPS["investigate_single"])
    add("locality_campaign",4,"Run locality-targeted campaign",
        ["Vishful has available inventory (internal)","PG/co-living/serviced-apartment supply is densely present "
         "in the Thiruvanmiyur / Adyar / Perungudi belt (first-party market context)"],
        ("Run locality-targeted marketing for available inventory in the Thiruvanmiyur / Adyar / Perungudi belt. "
         "Market-context + Vishful-inventory driven — not a competitor-demand, competitor-performance or ranking claim."),
        GROUPS["locality_campaign"])
    # amenities card — 5-bucket provenance (Vishful-own provision vs competitor market context, kept separate)
    ap={r["amenity"]:r for _,r in AP.iterrows()}
    aev=[]
    for a in ["AC","Wi-Fi","Parking","Security/CCTV","Food"]:
        r=ap[a]; aev.append(f"{a}: {r['vishful_own_bucket']} · market {r['market_context_evidence'].split('[')[0].strip()}")
    add("verify_amenities",5,"Highlight confirmed amenities",
        aev,
        ("AC and Wi-Fi are VISHFUL_INTERNAL_VERIFIED (own assets/services). Parking and Security/CCTV are "
         "VISHFUL_PUBLIC_EXPLICIT — Vishful's own site advertises them as property amenities ('CCTV Security — "
         "round-the-clock surveillance'; 'Parking') — safe to market as advertised, and worth confirming internally "
         "for operational assurance. Food is VISHFUL_PUBLIC_NEARBY_CONTEXT — the site lists 'Food Vendors Nearby' "
         "(location convenience), NOT a Vishful-provided food service, so do NOT market food as a Vishful amenity. "
         "Competitor prevalence stays market context only — never a Vishful claim, never a reason to add an amenity."),
        GROUPS["verify_amenities"])

    D=pd.DataFrame(cards).sort_values("display_order").reset_index(drop=True)
    blob=" ".join(map(str,D.values.ravel())).lower()
    for bad in ["better than","worse than","cheaper than","market average","vishful should charge","charge ₹","charge rs ","rank competitor","proves demand","competitor demand"]:
        assert bad not in blob, f"forbidden phrase: {bad}"
    for _,c in D.iterrows():
        for i in c["consolidates"].split(" + "):
            assert (REC[IDCOL]==i).any(), f"missing engine recommendation: {i}"
    D.to_csv(os.path.join(OUT,"phase3_owner_marketing_cards.csv"),index=False)
    consolidated=sum(len(v) for v in GROUPS.values())
    print("PHASE-3 OWNER MARKETING CARDS (display consolidation):")
    print(f"  engine recommendations: {len(REC)} -> owner cards: {len(D)} (consolidating {consolidated} rows)")
    for _,c in D.iterrows(): print(f"  {c['display_order']}. {c['title']}  [{c['provenance_label']}]  <- {c['consolidates']}")

if __name__=="__main__": main()
