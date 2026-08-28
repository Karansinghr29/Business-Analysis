"""
Phase-3 EXECUTION layer (isolated, deterministic, read-only). Parts 2/3/4/6/7.
Turns validated decisions into an execution/closed-loop scaffold keyed on the stable decision_id.
NO fabrication: action/outcome fields stay blank until real data is captured; status=Pending for all;
marketing ROI = UNAVAILABLE (attribution missing); leads come straight from the real leads table;
amenity claims come only from the validated inventory-amenity matrix (own data). Unknown stays unknown.

Writes ONLY: phase3_execution_tracker.csv, phase3_lead_followup.csv,
phase3_marketing_attribution_readiness.csv, phase3_execution_summary.csv.
Reads validated CSVs + leads/financials read-only. Modifies nothing (no dashboard/locked/existing).
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
def src(nn): return pd.read_csv(os.path.join(ROOT,f"Supabase Snippet Untitled query ({nn}).csv"),low_memory=False)

DEC=o("phase3_business_decisions.csv")
LEADS=src(84); FIN=src(85)

def main():
    # ---- Part 2/6/7: execution tracker keyed on decision_id (all action/outcome BLANK, status Pending) ----
    et=pd.DataFrame({"decision_id":DEC["decision_id"],"decision":DEC["decision"],
        "recommended_action":DEC["recommended_action"]})
    et["action_taken"]=None; et["action_date"]=None
    et["leads"]=pd.NA; et["visits"]=pd.NA; et["applications"]=pd.NA; et["conversions"]=pd.NA
    et["beds_filled"]=pd.NA; et["occupancy_before"]=pd.NA; et["occupancy_after"]=pd.NA
    et["revenue_impact"]=pd.NA; et["campaign_cost"]=pd.NA
    et["status"]="Pending"          # only changes when real action data is captured (never auto)
    et["outcome_status"]="unavailable_no_data"
    et.to_csv(os.path.join(OUT,"phase3_execution_tracker.csv"),index=False)

    # ---- Part 4: lead follow-up from the REAL leads table (no invented conversion/loss) ----
    lf=LEADS.reset_index()[["index","source","bed_type","gender","move_in_date","status","created_at"]].copy()
    lf.columns=["lead_index","source","requested_bed_type","gender","move_in_date","lead_status","created_at"]
    # follow-up status derived only from the source status field (never 'lost' unless source says so)
    lf["follow_up_status"]=lf["lead_status"].map(
        {"in_progress":"open_follow_up","visit_requested":"visit_pending"}).fillna(lf["lead_status"])
    lf.to_csv(os.path.join(OUT,"phase3_lead_followup.csv"),index=False)

    # ---- Part 3: marketing attribution readiness (ROI UNAVAILABLE; empty attribution schema) ----
    spend=float(FIN["marketing"].sum()); months=int((FIN["marketing"]!=0).sum())
    attr_cols=["campaign_id","channel","campaign_date","spend","lead_source","lead_id","conversion","bed_filled","revenue"]
    attr=pd.DataFrame(columns=attr_cols)   # empty template — nothing to populate yet
    attr.to_csv(os.path.join(OUT,"phase3_marketing_attribution_readiness.csv"),index=False)

    summary=[("execution_rows",len(et)),("all_status_pending",bool((et["status"]=="Pending").all())),
     ("outcomes_status","unavailable_no_data (not fabricated)"),
     ("leads_total",len(lf)),("leads_open_follow_up",int((lf["follow_up_status"]=="open_follow_up").sum())),
     ("leads_visit_pending",int((lf["follow_up_status"]=="visit_pending").sum())),
     ("leads_marked_lost",int((lf["follow_up_status"]=="lost").sum())),
     ("lead_sources",str(lf["source"].value_counts().to_dict())),
     ("requested_bed_types",str(lf["requested_bed_type"].dropna().value_counts().to_dict())),
     ("marketing_spend_total",round(spend,0)),("marketing_spend_months",months),
     ("marketing_ROI","UNAVAILABLE — campaign/channel/lead attribution missing"),
     ("attribution_schema","campaign_id->channel->campaign_date->spend->lead_source->lead_id->conversion->bed_filled->revenue (empty until captured)")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_execution_summary.csv"),index=False)
    print("PHASE-3 EXECUTION TRACKER:")
    for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": main()
