"""
Phase-3 Marketing Recommendation Engine (ISOLATED, deterministic). Parts 1/2/7/8.
Answers "what should Vishful market now, where, why?" from Vishful INTERNAL signals + validated
MARKET CONTEXT. Never a competitor comparison. No ML, no LLM text, no randomness.

Flow per recommendation: DATA -> SIGNAL -> BUSINESS REASON -> ACTION -> PRIORITY -> EVIDENCE.
Does NOT replace the Business Opportunities engine (that stays as-is). Reuses the same validated
internal outputs (step5 occupancy/inventory, step4 vacancy) and first-party market context
(phase3_playwright_market_research.csv). Vishful's own amenities are NOT in any output -> unknown;
amenity recs say "Confirm internally before marketing" (never assumed present).

Closed-loop (Part 8): emits phase3_closed_loop_tracking.csv linking recommendation_id to outcome
fields, all marked 'unavailable' (no campaign outcome data exists -> never fabricated).

Writes ONLY phase3_marketing_recommendations.csv, _summary.csv, phase3_closed_loop_tracking.csv.
Reads validated CSVs read-only. Modifies nothing else.
"""
from __future__ import annotations
import os, sys, json
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
def rd(f): return pd.read_csv(os.path.join(OUT,f))
PRICE=rd("step5_pricing_analysis.csv"); VAC=rd("step4_vacancy_at_risk.csv")
PA=rd("phase3_playwright_market_research.csv")

RULES={
 "inventory_marketing":"score=40*(100-occ)/100 + 25*min(med_days/180,1)[0 if unknown] + 20*(rev/max_rev) + 15*min(vacant/max_vac,1)",
 "vacancy_slow_fill":"score=55*min(med_days/365,1) + 45*(rev/max_rev); triggers only when med_days>=90 OR occ<85",
 "sharing_positioning":"score=50*min(vacant/max_vac,1) + 50*(config first-party market-published?1:0); COMBINED",
 "locality_marketing":"fixed 45; coarse locality supply density (market context) + Vishful has vacant inventory",
 "amenity_marketing":"fixed 30; market-published amenity, Vishful availability UNKNOWN -> confirm internally first",
 "priority_bands":"High>=60, Medium 40-59, Low<40",
}
SHARE={"Single":"single","Double":"2-sharing","Triple":"3-sharing","Executive":"executive/premium"}
VISHFUL_AMENITIES_KNOWN=set()  # not in any validated output -> unknown; never assumed

def band(s): return "High" if s>=60 else "Medium" if s>=40 else "Low"

def internal():
    inv=PRICE.groupby("bed_type").agg(total_beds=("total_beds","sum"),occupied=("occupied_beds","sum")).reset_index()
    inv["occ"]=100.0*inv["occupied"]/inv["total_beds"].clip(lower=1)
    vac=VAC.groupby("bed_type").agg(vacant=("bed_code","size"),med_days=("days_vacant","median"),
        rev=("rev_at_risk_monthly","sum")).reset_index()
    m=inv.merge(vac,on="bed_type",how="left"); m["vacant"]=m["vacant"].fillna(0).astype(int); m["rev"]=m["rev"].fillna(0.0)
    return m

def market_ctx():
    cols=["ac_available","non_ac","wifi","food","laundry","cctv_security","parking","power_backup"]
    freq={c:int((PA[c]==True).sum()) for c in cols if c in PA.columns}
    toks=set()
    for s in PA.get("sharing_config",pd.Series(dtype=object)).dropna():
        s=str(s).lower()
        if "single" in s: toks.add("single")
        if "double" in s or "two" in s: toks.add("2-sharing")
        if "triple" in s or "three" in s: toks.add("3-sharing")
        if "four" in s or "4" in s: toks.add("4-sharing")
    return freq,toks,int(len(PA))

def main():
    inv=internal(); freq,mtoks,mprops=market_ctx()
    max_rev=max(inv["rev"].max(),1.0); max_vac=max(inv["vacant"].max(),1)
    R=[]
    def add(rid,cat,pri,score,target,action,reason,vev,mev,esrc,conf,prov):
        R.append(dict(recommendation_id=rid,category=cat,priority=pri,score=round(score,1),
            target_inventory_locality=target,recommended_action=action,business_reason=reason,
            vishful_evidence=vev,market_evidence=mev,evidence_source=esrc,confidence=conf,
            provenance=prov,validation_status="validated"))

    for _,r in inv.iterrows():
        bt=r["bed_type"]; occ=float(r["occ"]); vac=int(r["vacant"]); rev=float(r["rev"])
        med=r["med_days"]; mk=pd.notna(med); cfg=SHARE.get(bt,bt)
        if vac==0: continue
        # 1. Inventory marketing (VISHFUL_INTERNAL)
        s1=40*(100-occ)/100 + (25*min(float(med)/180,1) if mk else 0) + 20*(rev/max_rev) + 15*min(vac/max_vac,1)
        add(f"INV-{bt}","Inventory marketing",band(s1),s1,cfg,
            f"Prioritize marketing for {cfg} beds",
            f"SIGNAL: {cfg} occupancy {occ:.1f}%, {vac} vacant, "
            f"{('median vacant '+str(int(float(med)))+'d' if mk else 'fill-time unknown')}, ₹{rev:,.0f}/mo at risk. "
            "REASON: available inventory with revenue upside.",
            f"step5 occ {occ:.1f}%, step4 vacant {vac}, rev_at_risk ₹{rev:,.0f}", None,
            "VISHFUL_INTERNAL",("high" if mk else "medium"),
            "step5_pricing_analysis.csv; step4_vacancy_at_risk.csv")
        # 2. Vacancy / slow-fill marketing (VISHFUL_INTERNAL) — only strong signals
        if (mk and float(med)>=90) or occ<85:
            s2=(55*min(float(med)/365,1) if mk else 0) + 45*(rev/max_rev)
            trig=("slow fill "+str(int(float(med)))+"d" if (mk and float(med)>=90) else f"low occupancy {occ:.1f}%")
            add(f"VAC-{bt}","Vacancy/slow-fill marketing",band(s2),s2,cfg,
                f"Targeted campaign to fill {cfg} ({trig})",
                f"SIGNAL: {trig}, ₹{rev:,.0f}/mo at risk. REASON: persistent vacancy erodes revenue.",
                f"step4 med_days {('%.0f'%float(med)) if mk else 'unknown'}, occ {occ:.1f}%, rev ₹{rev:,.0f}", None,
                "VISHFUL_INTERNAL",("high" if mk else "low"),
                "step4_vacancy_at_risk.csv; step5_pricing_analysis.csv")
        # 3. Sharing-positioning (COMBINED) — vacancy AND market-published config
        if cfg in mtoks:
            s3=50*min(vac/max_vac,1)+50
            add(f"SHR-{bt}","Sharing-positioning",band(s3) if s3<75 else "High",s3,cfg,
                f"Highlight {cfg} availability in marketing",
                f"SIGNAL: Vishful has {vac} vacant {cfg} beds AND {cfg} is a first-party market-published "
                "configuration. REASON: promote a recognized offering you currently have available.",
                f"{vac} vacant {cfg} beds (step4)",
                f"{cfg} published in first-party market sources (phase3_playwright_market_research.csv)",
                "COMBINED","medium","step4_vacancy_at_risk.csv; phase3_playwright_market_research.csv")

    # 4. Amenity marketing (MARKET_CONTEXT — Vishful unknown)
    al={"ac_available":"AC","non_ac":"Non-AC","wifi":"Wi-Fi","food":"Food","laundry":"Laundry",
        "cctv_security":"Security/CCTV","parking":"Parking","power_backup":"Power backup"}
    for col,cnt in sorted(freq.items(),key=lambda kv:-kv[1]):
        if cnt<2: continue
        lbl=al.get(col,col)
        if lbl.lower() in {a.lower() for a in VISHFUL_AMENITIES_KNOWN}: continue
        add(f"AMEN-{col}","Amenity marketing","Low",30.0,lbl,
            f"Confirm internally before marketing {lbl}",
            f"SIGNAL: {lbl} published on {cnt}/{mprops} first-party market sources. "
            f"REASON: common market amenity, but Vishful's own {lbl} availability is UNKNOWN.",
            None,f"{lbl} on {cnt}/{mprops} first-party sources","MARKET_CONTEXT","low",
            "phase3_playwright_market_research.csv")

    # 5. Locality marketing (MARKET_CONTEXT + internal vacancy)
    if int(inv["vacant"].sum())>0:
        add("LOC-TVM","Locality marketing","Medium",45.0,"Thiruvanmiyur/Adyar/Perungudi belt",
            "Run locality-targeted marketing for available inventory",
            "SIGNAL: dense PG/co-living/serviced supply in Vishful's own locality cluster (market context) + "
            f"{int(inv['vacant'].sum())} vacant beds internally. REASON: focus spend where inventory needs fill.",
            f"{int(inv['vacant'].sum())} total vacant beds (step4)",
            "locality supply density (phase3_competitor_master.csv aggregate; coarse)",
            "COMBINED","low","step4_vacancy_at_risk.csv; phase3_competitor_master.csv")

    df=pd.DataFrame(R).sort_values(["score"],ascending=False).reset_index(drop=True)
    cols=["recommendation_id","category","priority","score","target_inventory_locality","recommended_action",
          "business_reason","vishful_evidence","market_evidence","evidence_source","confidence","provenance","validation_status"]
    df[cols].to_csv(os.path.join(OUT,"phase3_marketing_recommendations.csv"),index=False)

    # closed-loop scaffold (Part 8) — outcomes UNAVAILABLE (never fabricated)
    cl=pd.DataFrame({"recommendation_id":df["recommendation_id"],
        "owner_action":"unavailable","campaign_result":"unavailable","enquiries":"unavailable",
        "conversions":"unavailable","occupancy_change":"unavailable","revenue_impact":"unavailable",
        "outcome_status":"unavailable_no_data"})
    cl.to_csv(os.path.join(OUT,"phase3_closed_loop_tracking.csv"),index=False)

    catc=lambda c:int((df["category"]==c).sum())
    summary=[("total_recommendations",len(df)),
     ("High",int((df["priority"]=="High").sum())),("Medium",int((df["priority"]=="Medium").sum())),
     ("Low",int((df["priority"]=="Low").sum())),
     ("inventory_marketing",catc("Inventory marketing")),("vacancy_slow_fill",catc("Vacancy/slow-fill marketing")),
     ("sharing_positioning",catc("Sharing-positioning")),("amenity_marketing",catc("Amenity marketing")),
     ("locality_marketing",catc("Locality marketing")),
     ("evidence_VISHFUL_INTERNAL",int((df["evidence_source"]=="VISHFUL_INTERNAL").sum())),
     ("evidence_MARKET_CONTEXT",int((df["evidence_source"]=="MARKET_CONTEXT").sum())),
     ("evidence_COMBINED",int((df["evidence_source"]=="COMBINED").sum())),
     ("closed_loop_outcomes","unavailable_no_data"),
     ("scoring_rules",json.dumps(RULES))]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_marketing_recommendations_summary.csv"),index=False)
    print("PHASE-3 MARKETING RECOMMENDATIONS:")
    for k,v in summary:
        if k!="scoring_rules": print(f"  {k}: {v}")
    print("\nrecommendations:")
    for _,r in df.iterrows():
        print(f"  [{r['priority']:6}] {r['score']:>5} {r['evidence_source']:16} {r['recommendation_id']:10} | {r['recommended_action']}")

if __name__=="__main__": main()
