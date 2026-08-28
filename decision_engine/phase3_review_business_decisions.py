"""
Phase-3 Review BUSINESS-DECISION analytics (isolated, deterministic, read-only).
ALL competitor PG reviews -> customer intelligence -> market signals -> Vishful internal data ->
business impact -> classified, traceable decision candidates. NO competitor comparison/ranking/
benchmark. NO fabricated impact. Unknown Vishful status stays unknown. Existing 14 decisions are
NOT duplicated (marked SUPPORTING). Decision strength is NOT review-count alone.

Chain per candidate: market_theme (many review_ids across PGs) -> market aggregate -> Vishful fact
-> business relevance -> business impact metric -> classified decision.
Writes ONLY: phase3_review_market_aggregate.csv, phase3_review_decision_candidates.csv,
phase3_review_decisions_summary.csv. Reads validated CSVs read-only. Modifies nothing.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
INTEL=o("phase3_review_intelligence.csv"); RAW=o("phase3_competitor_reviews_raw.csv")
DEC=o("phase3_business_decisions.csv")  # existing 14 (read-only, for dedup)
_VAC=o("step4_vacancy_at_risk.csv")     # corrected vacancy (lifecycle-aware) -> derive counts, never hard-code
_MX=o("phase3_inventory_amenity_matrix.csv")
_NVAC=int(len(_VAC)); _ACVAC=int((_MX["AC"]=="present").sum()) if "AC" in _MX.columns else 0

# Vishful authoritative facts per theme (grounded in validated data; UNKNOWN stays UNKNOWN)
VF={
 "ac":("VERIFIED",f"110 AC units; {_ACVAC} vacant AC beds; 304 AC maintenance tickets",304,"DEC-AMEN-AC","occupancy/complaint_volume"),
 "wifi":("VERIFIED","Wi-Fi verified (own issue-data); 65 Internet tickets",65,None,"complaint_volume/marketing"),
 "cleanliness":("VERIFIED","housekeeping verified; 118 Cleaning tickets",118,None,"complaint_volume/retention"),
 "maintenance":("VERIFIED","1,540 tickets; validated repeat hotspots",1540,"DEC-MAINT-PRIORITISE","maintenance_cost/complaint_volume"),
 "staff":("PROXY_ONLY","tenant_rating 1020/1026 rated (own satisfaction proxy)",None,"DEC-RETENTION-REVIEW","retention"),
 "food":("UNKNOWN","no food-service evidence (kitchen assets only) — status UNKNOWN",0,None,"lead_conversion(if added)"),
 "water":("VERIFIED","RO verified; 134 RO Water tickets",134,None,"complaint_volume"),
 "laundry":("VERIFIED","washing machines verified; 132 tickets",132,None,"complaint_volume/marketing"),
 "room_quality":("PARTIAL","158 Furniture tickets; room config known",158,None,"complaint_volume/occupancy"),
 "sharing":("VERIFIED","Single/Double/Triple inventory + vacancy",None,"DEC-VAC-Double","occupancy/vacant_bed_days"),
 "value":("INTERNAL","own rate card; pricing-review candidates",None,"DEC-PRICEREV-Triple","occupancy/revenue"),
 "location":("FIXED",f"Vishful Thiruvanmiyur 600041 (fixed); {_NVAC} vacant beds",None,"DEC-LOC-MKT","occupancy(marketing)"),
 "security":("UNKNOWN","CCTV/security status UNKNOWN (not in Vishful data)",None,None,"lead_conversion/occupancy(if added)"),
 "parking":("UNKNOWN","parking status UNKNOWN",None,None,"lead_conversion/occupancy(if added)"),
 "power_backup":("UNKNOWN","power-backup status UNKNOWN",None,None,"lead_conversion/occupancy(if added)"),
 "safety":("UNKNOWN","safety status UNKNOWN (linked to CCTV/security)",None,None,"lead_conversion/occupancy(if added)"),
 "common_area":("VERIFIED","common area verified (issue-data)",None,None,"marketing"),
}
ESW={"high":1.0,"medium":0.5,"low":0.0,"unknown":0.0}

def explode(col):
    ok=INTEL[INTEL["extraction_status"]=="ok"].copy()
    rows=[]
    for _,r in ok.iterrows():
        for t in str(r[col]).split("|"):
            if t and t not in ("nan","none",""): rows.append((r["review_id"],r["property_name"],t,r["sentiment"],r["evidence_strength"],
                               bool(r["purchase_signal"]),bool(r["retention_signal"])))
    return pd.DataFrame(rows,columns=["review_id","property_name","theme","sentiment","evidence_strength","purchase","retention"])

def band(s): return "High" if s>=65 else "Medium" if s>=45 else "Low"

def main():
    th=explode("themes")
    agg=[]
    for t,g in th.groupby("theme"):
        npg=g["property_name"].nunique(); nrev=len(g)
        neg=int((g["sentiment"]=="negative").sum()); pos=int((g["sentiment"]=="positive").sum())
        pain=int(g["review_id"].isin(explode("pain_points").query("theme==@t")["review_id"]).sum())
        need=int(g["review_id"].isin(explode("customer_needs").query("theme==@t")["review_id"]).sum())
        esa=g["evidence_strength"].map(ESW).mean()
        agg.append(dict(theme=t,n_reviews=nrev,n_independent_pgs=npg,positive=pos,negative=neg,
            pain_points=pain,customer_need_mentions=need,purchase_signals=int(g["purchase"].sum()),
            retention_signals=int(g["retention"].sum()),avg_evidence_strength=round(esa,2),
            example_review_ids="|".join(g["review_id"].astype(str).head(3))))
    A=pd.DataFrame(agg).sort_values(["n_independent_pgs","n_reviews"],ascending=False)
    A.to_csv(os.path.join(OUT,"phase3_review_market_aggregate.csv"),index=False)

    existing_ids=set(DEC["decision_id"])
    cands=[]
    for _,r in A.iterrows():
        t=r["theme"]; vf=VF.get(t,("UNKNOWN","status unknown",None,None,None))
        vstatus,vev,vtix,exdec,metric=vf
        npg=int(r["n_independent_pgs"]); nrev=int(r["n_reviews"])
        # decision STRENGTH (not review-count alone): breadth + volume + consistency + vishful evidence + relevance + evidence quality
        total=max(r["positive"]+r["negative"],1); consistency=abs(r["positive"]-r["negative"])/total
        vpresent=1 if vstatus in ("VERIFIED","PARTIAL","PROXY_ONLY","INTERNAL","FIXED") else 0
        relevance=1 if metric else 0
        score=round(25*min(npg/5,1)+15*min(nrev/15,1)+15*consistency+20*vpresent+15*relevance+10*r["avg_evidence_strength"],1)
        # gate: too thin -> informational, never a major decision from 1 PG / <3 reviews
        thin = (npg<2) or (nrev<3)
        # classify
        if thin:
            cat="NO ACTION / INFORMATIONAL"; strength="informational"
        elif exdec in existing_ids:
            cat="SUPPORTING SIGNAL FOR EXISTING DECISION"; strength=band(score)
        elif vstatus=="UNKNOWN":
            cat="PRODUCT OPPORTUNITY"  # unknown Vishful status + strong market -> owner-verify / product gap, never claim
            strength=band(score)
        elif r["pain_points"]>=2 and vtix and vtix>=100:
            cat="OPERATIONAL PRIORITY"; strength=band(score)
        elif r["retention_signals"]>=2 or t=="staff":
            cat="CUSTOMER RETENTION PRIORITY"; strength=band(score)
        elif r["positive"]>r["negative"] and vpresent:
            cat="MARKETING OPPORTUNITY"; strength=band(score)
        else:
            cat="NO ACTION / INFORMATIONAL"; strength="informational"
        # business-impact test: no metric establishable -> force NO ACTION
        if cat!="NO ACTION / INFORMATIONAL" and not metric:
            cat="NO ACTION / INFORMATIONAL"; strength="informational"
        # decision text (traceable; unknown preserved; no comparison)
        if vstatus=="UNKNOWN":
            action=(f"Owner-verify Vishful {t} (recurring market signal across {npg} PGs, +{r['positive']}/-{r['negative']}); "
                    "if genuinely absent, evaluate as an amenity/product gap. Do NOT claim presence/absence.")
        elif cat=="OPERATIONAL PRIORITY":
            action=f"Operational: reduce {t} issues first ({r['negative']} negative mentions; Vishful {vtix} own {t} tickets); then market {t}"
        elif cat=="CUSTOMER RETENTION PRIORITY":
            action=f"Retention: {t} drives stay/return signals in market; review Vishful {t} via tenant_rating + service"
        elif cat=="MARKETING OPPORTUNITY":
            action=f"Marketing: highlight verified Vishful {t} (market values it; Vishful {t} = {vstatus})"
        elif cat=="SUPPORTING SIGNAL FOR EXISTING DECISION":
            action=f"Reinforces existing {exdec} — review-derived supporting evidence (do NOT duplicate the decision)"
        else:
            action=f"Informational only — insufficient breadth/impact ({npg} PGs, {nrev} reviews)"
        cands.append(dict(review_signal_id=f"RS-{t}",theme=t,decision_class=cat,strength=strength,score=score,
            market_signal=f"{t}: {nrev} reviews across {npg} independent PGs (+{r['positive']}/-{r['negative']}, pain={r['pain_points']})",
            evidence_strength=f"pgs={npg}, reviews={nrev}, avg_specificity={r['avg_evidence_strength']}, consistency={round(consistency,2)}",
            vishful_internal_fact=f"{vstatus}: {vev}",business_relevance=(metric or "none"),
            business_impact_metric=(metric or "none — no measurable metric -> no action"),
            recommended_decision=action,supports_existing_decision=(exdec if (exdec in existing_ids) else None),
            is_new_decision=(cat in ("PRODUCT OPPORTUNITY","OPERATIONAL PRIORITY","MARKETING OPPORTUNITY",
                                     "CUSTOMER RETENTION PRIORITY","REVENUE OPPORTUNITY","NEW BUSINESS DECISION")
                             and exdec not in existing_ids and not thin),
            trace=f"themes->{r['example_review_ids']} | market_aggregate | Vishful:{vstatus}",
            provenance="phase3_review_intelligence.csv / phase3_review_market_aggregate.csv / phase3_business_decisions.csv (dedup)"))
    C=pd.DataFrame(cands).sort_values("score",ascending=False)
    C.to_csv(os.path.join(OUT,"phase3_review_decision_candidates.csv"),index=False)

    catc=C["decision_class"].value_counts().to_dict()
    summary=[("themes_analyzed",len(A)),("decision_candidates",len(C)),
     ("classes",str(catc)),
     ("new_decisions",int(C["is_new_decision"].sum())),
     ("supporting_existing",int((C["decision_class"]=="SUPPORTING SIGNAL FOR EXISTING DECISION").sum())),
     ("no_action_informational",int((C["decision_class"]=="NO ACTION / INFORMATIONAL").sum())),
     ("strong_signals(>=2 PGs)",int((C["strength"]!="informational").sum())),
     ("existing_14_untouched",True),
     ("owner_rule","market customer signal -> Vishful opportunity; never competitor comparison; unknown stays unknown")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_review_decisions_summary.csv"),index=False)
    print("PHASE-3 REVIEW BUSINESS DECISIONS:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\ncandidates:")
    for _,r in C.iterrows(): print(f"  [{r['strength']:13}] {r['decision_class']:38} | {r['theme']:12} | {r['business_impact_metric']}")

if __name__=="__main__": main()
