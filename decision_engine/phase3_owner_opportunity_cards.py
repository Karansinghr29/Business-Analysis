"""
Phase-3 OWNER OPPORTUNITY CARDS (isolated, deterministic, DISPLAY-AGGREGATION ONLY).

Consolidates the 11 engine-produced business opportunities (phase3_business_opportunities.csv) into 5
owner-facing cards for readability. Does NOT change the engine, scores, or the underlying CSV — it only groups
existing rows and re-labels them for display; the original 11 rows remain the source of truth / traceability.
Guardrails preserved: no competitor ranking, no Vishful-vs-competitor, no market-average, no recommended price.

Writes ONLY phase3_owner_opportunity_cards.csv.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
OPP=pd.read_csv(os.path.join(OUT,"phase3_business_opportunities.csv"))
VAC=pd.read_csv(os.path.join(OUT,"step4_vacancy_at_risk.csv"))      # DERIVE vacancy metrics from corrected source
PRICE=pd.read_csv(os.path.join(OUT,"step5_pricing_analysis.csv"))

def _vm(bt):
    """Vacancy metrics for a bed_type derived from corrected step4/step5 (no hard-coded numbers)."""
    v=VAC[VAC["bed_type"]==bt]; n=int(len(v)); rev=float(v["rev_at_risk_monthly"].sum())
    med=v["days_vacant"].median()
    p=PRICE[PRICE["bed_type"]==bt]; tot=float(p["total_beds"].sum()); occd=float(p["occupied_beds"].sum())
    occ=(100.0*occd/tot) if tot else float("nan")
    return dict(n=n,rev=rev,med=med,occ=occ)

def _row(nm):
    r=OPP[OPP["opportunity"].str.contains(nm,case=False,na=False)]
    return r.iloc[0] if len(r) else None
def _ev(*names):
    parts=[]
    for n in names:
        r=_row(n)
        if r is None: continue
        for col in ("vishful_evidence","market_context_evidence"):
            v=str(r.get(col) or "")
            if v and v.lower()!="nan": parts.append(v)
    return parts

# groups: card -> the engine opportunity names it consolidates (for traceability + provenance rollup)
GROUPS={
 "fill_2_sharing":["Highlight 2-sharing availability","Promote available 2-sharing inventory"],
 "fill_3_sharing":["Promote available 3-sharing inventory"],
 "investigate_single":["Highlight single availability","Promote available single inventory"],
 "locality_campaign":["Locality-targeted campaign"],
 "verify_amenities":["Food","AC","Wi-Fi","Parking","Security/CCTV"],
}
def prov_label(names):
    srcs={str(_row(n)["evidence_source"]) for n in names if _row(n) is not None}
    if "COMBINED" in srcs or ("VISHFUL_INTERNAL" in srcs and "MARKET_CONTEXT" in srcs): return "COMBINED"
    return srcs.pop() if len(srcs)==1 else "COMBINED"

def main():
    cards=[]
    def add(cid,order,title,evidence,action,names):
        cards.append(dict(card_id=cid,display_order=order,title=title,evidence=" | ".join(evidence),
            suggested_action=action,provenance_label=prov_label(names),
            consolidates=" + ".join(names),source_count=len(names)))

    # 1 Fill 2-sharing vacancies (derived from corrected step4/step5) — shown only if current vacancy > 0
    d2=_vm("Double")
    if d2["n"]>0:
        ev2=[f"{d2['n']} vacant 2-sharing beds",f"{d2['occ']:.1f}% occupancy"]
        if pd.notna(d2["med"]): ev2.append(f"median vacancy {int(d2['med'])} days")
        ev2+=[f"₹{d2['rev']:,.0f}/month revenue-at-risk","2-sharing is a first-party market-published configuration"]
        add("fill_2_sharing",1,"Fill 2-sharing vacancies",ev2,
            "Prioritize targeted marketing for available 2-sharing beds. (No specific price is recommended.)",
            GROUPS["fill_2_sharing"])
    # 2 Promote/fill 3-sharing vacancies (derived) — shown only if current vacancy > 0
    d3=_vm("Triple")
    if d3["n"]>0:
        ev3=[f"{d3['n']} vacant 3-sharing beds",f"{d3['occ']:.1f}% occupancy"]
        ev3.append(f"median vacancy {int(d3['med'])} days" if pd.notna(d3["med"]) else "fill-time unknown")
        ev3.append(f"₹{d3['rev']:,.0f}/month revenue-at-risk")
        add("fill_3_sharing",2,"Promote / fill 3-sharing vacancies",ev3,
            "Prioritize targeted marketing for available 3-sharing beds. (No specific price is recommended.)",
            GROUPS["fill_3_sharing"])
    # 3 Single card — shown ONLY when there is a current rentable single vacancy (A22's old 272-day single is
    #   excluded/closed inventory, so with 0 current single vacancy this actionable card correctly disappears).
    d1=_vm("Single")
    if d1["n"]>0 and all(_row(n) is not None for n in GROUPS["investigate_single"]):
        ev1=[f"{d1['n']} vacant single bed(s)",f"{d1['occ']:.1f}% occupancy"]
        if pd.notna(d1["med"]): ev1.append(f"median vacancy {int(d1['med'])} days")
        ev1.append(f"₹{d1['rev']:,.0f}/month revenue-at-risk")
        add("investigate_single",3,"Investigate single-bed slow fill",ev1,
            ("Before simply increasing marketing, review the specific bed/room condition, pricing setup, availability "
             "status, and booking visibility. (Do NOT automatically reduce or set a specific price.)"),
            GROUPS["investigate_single"])
    # 4 Run locality-targeted campaign
    add("locality_campaign",4,"Run locality-targeted campaign",
        ["Vishful has available inventory","PG/co-living/serviced-apartment supply is densely present in the "
         "Thiruvanmiyur / Adyar / Perungudi cluster (first-party market context)"],
        "Run locality-targeted marketing for available inventory in the Thiruvanmiyur / Adyar / Perungudi cluster.",
        GROUPS["locality_campaign"])
    # 5 Verify marketable amenities (consolidates the 5 amenity cards)
    add("verify_amenities",5,"Verify marketable amenities",
        ["AC appears in 3/6 first-party market sources","Food appears in 4/6","Parking appears in 3/6",
         "Security/CCTV appears in 2/6","Wi-Fi appears in 5/6",
         "Vishful's current availability for these amenities is not validated in the internal outputs"],
        ("Verify internally which amenities Vishful currently provides, then highlight only confirmed amenities in "
         "marketing. (Market prevalence is not proof of customer demand; do NOT claim Vishful should add any amenity.)"),
        GROUPS["verify_amenities"])

    D=pd.DataFrame(cards).sort_values("display_order").reset_index(drop=True)
    # guardrails
    blob=" ".join(map(str,D.values.ravel())).lower()
    for bad in ["better than","worse than","cheaper than","market average","vishful should charge","charge ₹","charge rs ","rank"]:
        assert bad not in blob, f"forbidden phrase: {bad}"
    # every consolidated opportunity name must exist in the engine output (no invented opportunity)
    for _,c in D.iterrows():
        for n in c["consolidates"].split(" + "):
            assert OPP["opportunity"].str.contains(n,case=False,na=False).any(), f"missing source opportunity: {n}"
    D.to_csv(os.path.join(OUT,"phase3_owner_opportunity_cards.csv"),index=False)
    consolidated=sum(len(v) for v in GROUPS.values())
    print("PHASE-3 OWNER OPPORTUNITY CARDS (display consolidation):")
    print(f"  engine opportunities: {len(OPP)} -> owner cards: {len(D)} (consolidating {consolidated} rows)")
    for _,c in D.iterrows(): print(f"  {c['display_order']}. {c['title']}  [{c['provenance_label']}]  <- {c['consolidates']}")

if __name__=="__main__": main()
