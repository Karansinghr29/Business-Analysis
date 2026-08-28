"""
Phase-3 DECISION RECONCILIATION (isolated, deterministic, read-only).
Reconciles existing 14 internal business decisions with the 16 review-derived candidates into ONE
final audit. Classifies each as: EXISTING_STANDALONE / EXISTING_REINFORCED / NEW / SUPPORTING /
REDUNDANT_WEAK. Per row: evidence_chain, business_metric, decision_strength, actionability,
owner_input_required, expected_business_impact_type. Never duplicates a decision; never a competitor
comparison; unknown Vishful status stays unknown. Writes ONLY new files. Modifies nothing.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
DEC=o("phase3_business_decisions.csv")            # existing 14 (unchanged)
RC=o("phase3_review_decision_candidates.csv")     # 16 review candidates
AGG=o("phase3_review_market_aggregate.csv").set_index("theme")

# theme -> (reconciliation_status, links_to_existing_decision_id, impact_type, actionability, owner_input)
MAP={
 # SUPPORTING existing internal decisions (market reviews reinforce them; NOT new)
 "ac":("SUPPORTING","DEC-AMEN-AC","occupancy + complaint_reduction","operational_then_marketing","no"),
 "staff":("SUPPORTING","DEC-RETENTION-REVIEW","retention","actionable_now","no"),
 "value":("SUPPORTING","DEC-PRICEREV-Triple","occupancy/revenue","review_only","no"),
 "location":("SUPPORTING","DEC-LOC-MKT","occupancy(marketing)","actionable_now","no"),
 "maintenance":("SUPPORTING","DEC-MAINT-PRIORITISE","maintenance_cost/complaint_reduction","operational_first","no"),
 "cleanliness":("SUPPORTING","DEC-MAINT-PRIORITISE","complaint_reduction/retention","operational_first","no"),
 "room_quality":("SUPPORTING","DEC-MAINT-PRIORITISE","complaint_reduction/occupancy","operational_first","no"),
 "water":("SUPPORTING","DEC-MAINT-PRIORITISE","complaint_reduction","operational_first","no"),
 # GENUINELY NEW (distinct from all 14)
 "food":("NEW","","lead_conversion (if added)","owner_verify_first","yes — confirm food-service status"),
 "security":("NEW","","lead_conversion/occupancy (if added)","owner_verify_first","yes — confirm CCTV/security"),
 "safety":("NEW","","lead_conversion/occupancy (if added)","owner_verify_first","yes — confirm safety/security"),
 "parking":("NEW","","lead_conversion/occupancy (if added)","owner_verify_first","yes — confirm parking"),
 "laundry":("NEW","","complaint_reduction/marketing","actionable_now","no"),
 "common_area":("NEW","","marketing","actionable_now","no"),
 # REDUNDANT / WEAK (thin signal and/or already covered internally)
 "wifi":("REDUNDANT_WEAK","","(internally handled: 65 tickets)","informational","no"),
 "sharing":("REDUNDANT_WEAK","DEC-VAC-Double","(already covered by vacancy decisions)","informational","no"),
}
def strength(t):
    if t not in AGG.index: return "informational"
    r=AGG.loc[t]; npg=int(r["n_independent_pgs"]); nrev=int(r["n_reviews"])
    if npg<2 or nrev<3: return "informational"
    return "High" if (npg>=5 and nrev>=10) else "Medium" if npg>=3 else "Low-Medium"

def chain(t):
    if t not in AGG.index: return f"{t}: insufficient review evidence"
    r=AGG.loc[t]
    return (f"reviews[{r['example_review_ids']}] -> {int(r['n_reviews'])} reviews / {int(r['n_independent_pgs'])} PGs "
            f"(+{int(r['positive'])}/-{int(r['negative'])}, pain={int(r['pain_points'])}) -> market aggregate")

def main():
    rows=[]
    # 1) existing 14 — annotate reinforced vs standalone (NEVER modified)
    reinforced={v[1] for v in MAP.values() if v[0]=="SUPPORTING" and v[1]}
    for _,d in DEC.iterrows():
        did=d["decision_id"]
        rein=did in reinforced
        themes=[t for t,v in MAP.items() if v[0]=="SUPPORTING" and v[1]==did]
        rows.append(dict(decision_ref=did, origin="internal_engine",
            reconciliation_status=("EXISTING_REINFORCED" if rein else "EXISTING_STANDALONE"),
            topic=d["decision"],
            evidence_chain=(f"Vishful internal ({d['provenance']})" + (f" + review support: {themes}" if rein else "")),
            business_metric=d["tracking_field"], decision_strength=(d["priority"]+"+review" if rein else d["priority"]),
            actionability=("actionable_now" if d["priority"]=="High" else "review/plan"),
            owner_input_required=(str(d["missing_data_flag"]) if pd.notna(d["missing_data_flag"]) else "no"),
            expected_business_impact_type=d["expected_impact"]))
    # 2) review-derived — new / supporting / redundant
    for t,(status,link,impact,action,owner) in MAP.items():
        if status=="SUPPORTING":
            rows.append(dict(decision_ref=f"RV-{t}", origin="review_derived",
                reconciliation_status="SUPPORTING", topic=f"{t} (reinforces {link})",
                evidence_chain=chain(t)+f" -> Vishful evidence -> supports {link}",
                business_metric=impact, decision_strength=strength(t), actionability=action,
                owner_input_required=owner, expected_business_impact_type=impact))
        elif status=="NEW":
            rows.append(dict(decision_ref=f"RV-{t}", origin="review_derived",
                reconciliation_status="NEW", topic=f"{t} (genuinely new)",
                evidence_chain=chain(t)+" -> Vishful fact -> new candidate",
                business_metric=impact, decision_strength=strength(t), actionability=action,
                owner_input_required=owner, expected_business_impact_type=impact))
        else:
            rows.append(dict(decision_ref=f"RV-{t}", origin="review_derived",
                reconciliation_status="REDUNDANT_WEAK", topic=f"{t}",
                evidence_chain=chain(t), business_metric=impact, decision_strength=strength(t),
                actionability="informational", owner_input_required="no",
                expected_business_impact_type="none — no incremental action"))
    R=pd.DataFrame(rows)
    R.to_csv(os.path.join(OUT,"phase3_decision_reconciliation.csv"),index=False)

    sc=R["reconciliation_status"].value_counts().to_dict()
    summary=[("total_reconciled_rows",len(R)),
     ("existing_decisions",len(DEC)),("existing_reinforced",int((R["reconciliation_status"]=="EXISTING_REINFORCED").sum())),
     ("existing_standalone",int((R["reconciliation_status"]=="EXISTING_STANDALONE").sum())),
     ("review_new",int((R["reconciliation_status"]=="NEW").sum())),
     ("review_supporting",int((R["reconciliation_status"]=="SUPPORTING").sum())),
     ("review_redundant_weak",int((R["reconciliation_status"]=="REDUNDANT_WEAK").sum())),
     ("new_needing_owner_input",int(((R["reconciliation_status"]=="NEW")&(R["owner_input_required"].str.startswith("yes"))).sum())),
     ("new_actionable_now",int(((R["reconciliation_status"]=="NEW")&(R["actionability"]=="actionable_now")).sum())),
     ("status_counts",str(sc)),
     ("owner_rule","market = context; Vishful = decision driver; never competitor comparison; unknown stays unknown")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_decision_reconciliation_summary.csv"),index=False)
    print("PHASE-3 DECISION RECONCILIATION:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nreconciled decisions:")
    for _,r in R.iterrows():
        print(f"  [{r['reconciliation_status']:19}] {r['decision_ref']:20} | {r['decision_strength']:12} | {r['actionability']:20} | {r['topic'][:40]}")

if __name__=="__main__": main()
