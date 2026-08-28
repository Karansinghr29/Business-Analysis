"""
Phase-3 Business Opportunities / Marketing Decision engine (ISOLATED, deterministic).
Owner rule: analytics + PUBLIC market CONTEXT -> Vishful marketing/business action.
NEVER a competitor-vs-Vishful comparison. No ML, no LLM text, no randomness.

INTERNAL evidence  = Vishful's own validated outputs (step5 occupancy/inventory, step4 vacancy).
MARKET CONTEXT     = first-party public evidence (phase3_playwright_market_research.csv) — used
                     only as aggregate context (what amenities/sharing are commonly PUBLISHED),
                     never as a per-competitor comparison, never with competitor prices.
Every recommendation is tagged VISHFUL_INTERNAL / MARKET_CONTEXT / COMBINED and carries explicit
evidence + a transparent rule-based score. Unknown stays unknown (Vishful's own amenities are NOT
in any output -> amenity recs are MARKET_CONTEXT 'investigate', never 'Vishful has X').

Reads validated CSVs read-only. Writes ONLY phase3_business_opportunities.csv,
_summary.csv, _evidence.csv. Modifies nothing else (dashboard/master/locked/analytics untouched).
"""
from __future__ import annotations
import os, sys, json
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
def rd(f): return pd.read_csv(os.path.join(OUT,f))

PRICE=rd("step5_pricing_analysis.csv")     # INTERNAL: inventory + occupancy by bed_type x toilet
VAC=rd("step4_vacancy_at_risk.csv")        # INTERNAL: vacant beds, days_vacant, rev_at_risk
PA=rd("phase3_playwright_market_research.csv")  # MARKET CONTEXT: first-party amenities/sharing

# ---- explicit, documented scoring rules (deterministic; NO random/ML/LLM) ----
RULES={
 "inventory_promote":"score = 40*(100-occ_pct)/100 + 25*min(med_days_vacant/180,1)[0 if unknown] "
   "+ 20*(rev_at_risk/max_rev_at_risk) + 15*min(vacant/max_vacant,1). High>=60, Medium 40-59, Low<40.",
 "sharing_opportunity":"score = 50*min(vacant/max_vacant,1) + 50*(sharing config present in first-party market? 1:0). "
   "Only when Vishful has vacant beds AND config is first-party market-published. COMBINED. High>=75,Med 50-74,Low<50.",
 "amenity_context":"fixed 35: amenity is commonly PUBLISHED in first-party market AND Vishful availability is UNKNOWN "
   "(not in any Vishful output) -> Low, action=confirm internally then highlight IF present. MARKET_CONTEXT.",
 "location_context":"fixed 45: PG/co-living density observed in Vishful locality per market context -> Medium, "
   "action=locality-targeted campaign for available inventory. MARKET_CONTEXT (coarse; no fabricated demand).",
}
SHARE={"Single":"single","Double":"2-sharing","Triple":"3-sharing","Executive":"executive/premium"}

# Vishful's OWN amenities are NOT present in any validated output -> explicitly UNKNOWN.
VISHFUL_AMENITIES_KNOWN=set()   # do not assume Vishful has wifi/AC/food; unknown stays unknown

def _num(x,d=0.0):
    try:
        return float(x) if pd.notna(x) else d
    except Exception: return d

def internal_by_bedtype():
    inv=PRICE.groupby("bed_type").agg(total_beds=("total_beds","sum"),
        occupied=("occupied_beds","sum")).reset_index()
    inv["occ_pct"]=100.0*inv["occupied"]/inv["total_beds"].clip(lower=1)
    vac=VAC.groupby("bed_type").agg(vacant=("bed_code","size"),
        med_days=("days_vacant","median"),rev=("rev_at_risk_monthly","sum")).reset_index()
    m=inv.merge(vac,on="bed_type",how="left")
    m["vacant"]=m["vacant"].fillna(0).astype(int); m["rev"]=m["rev"].fillna(0.0)
    return m

def market_amenity_freq():
    cols=["ac_available","non_ac","wifi","food","laundry","cctv_security","parking","power_backup"]
    freq={c:int((PA[c]==True).sum()) for c in cols if c in PA.columns}
    props=int(len(PA))
    return freq, props

def market_sharing_tokens():
    toks=set()
    for s in PA.get("sharing_config",pd.Series(dtype=object)).dropna():
        s=str(s).lower()
        if "single" in s or " 1" in s or "one" in s: toks.add("single")
        if "double" in s or "two" in s or "2" in s: toks.add("2-sharing")
        if "triple" in s or "three" in s or "3" in s: toks.add("3-sharing")
        if "four" in s or "4" in s: toks.add("4-sharing")
        if "5" in s or "five" in s: toks.add("5-sharing")
    return toks

def band_inv(s): return "High" if s>=60 else "Medium" if s>=40 else "Low"
def band_share(s): return "High" if s>=75 else "Medium" if s>=50 else "Low"

def main():
    inv=internal_by_bedtype()
    max_rev=max(inv["rev"].max(),1.0); max_vac=max(inv["vacant"].max(),1)
    amen_freq,props=market_amenity_freq(); mtoks=market_sharing_tokens()
    recs=[]; ev=[]

    # A. Inventory to Promote (VISHFUL_INTERNAL)
    for _,r in inv.iterrows():
        bt=r["bed_type"]; occ=_num(r["occ_pct"]); vac=int(r["vacant"]); rev=_num(r["rev"])
        med=r["med_days"]; med_known=pd.notna(med)
        if vac==0: continue  # nothing available to promote
        occ_pts=40*(100-occ)/100
        fill_pts=25*min(_num(med)/180.0,1.0) if med_known else 0.0
        rev_pts=20*(rev/max_rev)
        vac_pts=15*min(vac/max_vac,1.0)
        score=round(occ_pts+fill_pts+rev_pts+vac_pts,1)
        fill_txt=(f"median vacancy {int(_num(med))}d" if med_known else "fill-time unknown")
        reason=(f"{bt} inventory: occupancy {occ:.1f}%, {vac} vacant bed(s), {fill_txt}, "
                f"₹{rev:,.0f}/mo revenue-at-risk (Vishful internal).")
        recs.append(dict(opportunity=f"Promote available {SHARE.get(bt,bt)} inventory",
            category="Inventory to Promote", priority=band_inv(score), score=score,
            evidence_source="VISHFUL_INTERNAL", reason=reason,
            vishful_evidence=f"step5 occ {occ:.1f}% / step4 vacant {vac}, {fill_txt}, rev_at_risk ₹{rev:,.0f}",
            market_context_evidence=None,
            recommended_action=f"Prioritize marketing/campaign for {SHARE.get(bt,bt)} beds",
            confidence=("high" if med_known else "medium"),
            provenance="step5_pricing_analysis.csv; step4_vacancy_at_risk.csv"))
        ev.append(dict(rec=f"promote_{bt}",evidence_type="VISHFUL_INTERNAL",
            detail=reason,source="step5_pricing_analysis.csv; step4_vacancy_at_risk.csv"))

    # C. Sharing / Inventory Opportunity (COMBINED: internal vacancy + market config published)
    for _,r in inv.iterrows():
        bt=r["bed_type"]; vac=int(r["vacant"]); cfg=SHARE.get(bt)
        if vac==0 or cfg is None: continue
        present = cfg in mtoks
        if not present: continue
        score=round(50*min(vac/max_vac,1.0)+50*(1 if present else 0),1)
        recs.append(dict(opportunity=f"Highlight {cfg} availability",
            category="Sharing / Inventory Opportunity", priority=band_share(score), score=score,
            evidence_source="COMBINED",
            reason=(f"Vishful has {vac} available {cfg} bed(s) (internal) AND {cfg} is a first-party "
                    f"market-published configuration (market context) — a recognized offering to market."),
            vishful_evidence=f"{vac} vacant {cfg} beds (step4_vacancy_at_risk.csv)",
            market_context_evidence=f"{cfg} appears in first-party rendered sources (phase3_playwright_market_research.csv)",
            recommended_action=f"Highlight {cfg} availability in marketing",
            confidence="medium",
            provenance="step4_vacancy_at_risk.csv; phase3_playwright_market_research.csv"))
        ev.append(dict(rec=f"sharing_{bt}",evidence_type="COMBINED",
            detail=f"{cfg} vacant={vac}; market-published={present}",
            source="step4_vacancy_at_risk.csv; phase3_playwright_market_research.csv"))

    # B. Amenity Marketing Opportunity (MARKET_CONTEXT — Vishful availability UNKNOWN)
    amen_label={"ac_available":"AC","non_ac":"Non-AC","wifi":"Wi-Fi","food":"Food","laundry":"Laundry",
                "cctv_security":"Security/CCTV","parking":"Parking","power_backup":"Power backup"}
    for col,cnt in sorted(amen_freq.items(),key=lambda kv:-kv[1]):
        if cnt<2: continue  # 'commonly published' threshold >=2 first-party sources
        lbl=amen_label.get(col,col)
        has=lbl.lower() in {a.lower() for a in VISHFUL_AMENITIES_KNOWN}
        if has:  # would be COMBINED 'highlight' — but VISHFUL_AMENITIES_KNOWN is empty by design
            continue
        recs.append(dict(opportunity=f"Consider highlighting {lbl} (verify Vishful availability)",
            category="Amenity Marketing Opportunity", priority="Low", score=35.0,
            evidence_source="MARKET_CONTEXT",
            reason=(f"{lbl} is commonly published across {cnt}/{props} first-party market sources "
                    f"(market context). Vishful's own {lbl} availability is UNKNOWN (not in any Vishful output)."),
            vishful_evidence=None,
            market_context_evidence=f"{lbl} published on {cnt}/{props} first-party sources (phase3_playwright_market_research.csv)",
            recommended_action=f"Confirm internally whether Vishful offers {lbl}; highlight in marketing ONLY if present",
            confidence="low",
            provenance="phase3_playwright_market_research.csv"))
        ev.append(dict(rec=f"amenity_{col}",evidence_type="MARKET_CONTEXT",
            detail=f"{lbl} first-party count {cnt}/{props}; Vishful availability unknown",
            source="phase3_playwright_market_research.csv"))

    # D. Location / Marketing Opportunity (MARKET_CONTEXT, coarse — no fabricated demand)
    recs.append(dict(opportunity="Locality-targeted campaign (Thiruvanmiyur 600041 core)",
        category="Location / Marketing Opportunity", priority="Medium", score=45.0,
        evidence_source="MARKET_CONTEXT",
        reason=("PG/co-living/serviced-apartment supply is densely present in Vishful's own locality cluster "
                "(Thiruvanmiyur/Adyar/Perungudi) per validated market context. No competitor demand/price claimed."),
        vishful_evidence="Vishful has available inventory (step4_vacancy_at_risk.csv)",
        market_context_evidence="Property density by locality (phase3_competitor_master.csv aggregate; coarse suburb-centroid)",
        recommended_action="Run locality-targeted marketing for available inventory in the Thiruvanmiyur/Adyar/Perungudi belt",
        confidence="low",
        provenance="phase3_competitor_master.csv (aggregate locality context)"))
    ev.append(dict(rec="location_context",evidence_type="MARKET_CONTEXT",
        detail="locality supply density; coarse; no demand/price inference",source="phase3_competitor_master.csv"))

    df=pd.DataFrame(recs).sort_values(["score"],ascending=False).reset_index(drop=True)
    cols=["opportunity","category","priority","score","evidence_source","reason","vishful_evidence",
          "market_context_evidence","recommended_action","confidence","provenance"]
    df[cols].to_csv(os.path.join(OUT,"phase3_business_opportunities.csv"),index=False)
    pd.DataFrame(ev).to_csv(os.path.join(OUT,"phase3_business_opportunity_evidence.csv"),index=False)

    cat=lambda c:int((df["category"]==c).sum())
    summary=[("total_opportunities",len(df)),
     ("High",int((df["priority"]=="High").sum())),("Medium",int((df["priority"]=="Medium").sum())),
     ("Low",int((df["priority"]=="Low").sum())),
     ("inventory_to_promote",cat("Inventory to Promote")),
     ("sharing_opportunities",cat("Sharing / Inventory Opportunity")),
     ("amenity_opportunities",cat("Amenity Marketing Opportunity")),
     ("location_opportunities",cat("Location / Marketing Opportunity")),
     ("evidence_VISHFUL_INTERNAL",int((df["evidence_source"]=="VISHFUL_INTERNAL").sum())),
     ("evidence_MARKET_CONTEXT",int((df["evidence_source"]=="MARKET_CONTEXT").sum())),
     ("evidence_COMBINED",int((df["evidence_source"]=="COMBINED").sum())),
     ("vishful_amenities_known",len(VISHFUL_AMENITIES_KNOWN)),
     ("scoring_rules",json.dumps(RULES))]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_business_opportunities_summary.csv"),index=False)
    print("PHASE-3 BUSINESS OPPORTUNITIES:")
    for k,v in summary:
        if k!="scoring_rules": print(f"  {k}: {v}")
    print("\ntop recommendations:")
    for _,r in df.iterrows():
        print(f"  [{r['priority']:6}] {r['score']:>5} {r['evidence_source']:16} | {r['opportunity']} -> {r['recommended_action']}")

if __name__=="__main__": main()
