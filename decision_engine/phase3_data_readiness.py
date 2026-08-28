"""
Phase-3 DATA-READINESS / capture layer (ISOLATED). Builds validated EMPTY schemas so Vishful can
start recording the real business data the UAT flagged as missing. NO fabricated values, NO market
inference. Every unknown stays unknown. Turns the recommendation system into a future closed loop.

Outputs (schemas seeded ONLY with facts that already exist — recommendation_id, target, Vishful
inventory grain; all outcome/amenity/funnel values UNKNOWN pending owner/staff input):
  * phase3_vishful_amenity_master.csv     (Part 1) — Vishful's OWN amenities, all UNKNOWN
  * phase3_marketing_action_log.csv       (Part 2) — actions taken per recommendation_id
  * phase3_lead_funnel.csv                (Part 3) — leads->conversions per recommendation_id
  * phase3_outcome_tracking.csv           (Part 4) — occupancy/revenue outcome per recommendation_id
  * phase3_triple_fill_time_audit.csv     (Part 5) — why Triple days_vacant is missing (documented)
  * phase3_data_readiness_summary.csv
Reads validated CSVs read-only. Does not modify dashboard / locked outputs / existing phase3 / master.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
def rd(f): return pd.read_csv(os.path.join(OUT,f))
REC=rd("phase3_marketing_recommendations.csv")
PRICE=rd("step5_pricing_analysis.csv")
VAC=rd("step4_vacancy_at_risk.csv")
U="unknown"; PEND="pending_owner_input"; NA="unavailable_no_data"

def main():
    # ---- Part 1: Vishful Amenity Master (grain = property x bed_type x toilet; ALL amenities UNKNOWN) ----
    grain=PRICE[["bed_type","toilet_type"]].drop_duplicates().reset_index(drop=True)
    am=[]
    for _,g in grain.iterrows():
        am.append(dict(property="Vishful Vista Heights", locality="Thiruvanmiyur 600041",
            bed_type=g["bed_type"], sharing_type={"Single":"single","Double":"2-sharing","Triple":"3-sharing",
                "Executive":"executive"}.get(g["bed_type"],U), toilet_type=g["toilet_type"],
            ac=U, non_ac=U, wifi=U, food=U, laundry=U, parking=U, cctv_security=U, power_backup=U,
            source_evidence=None, verified_by=None, verified_at=None, status=PEND))
    amdf=pd.DataFrame(am)
    amdf.to_csv(os.path.join(OUT,"phase3_vishful_amenity_master.csv"),index=False)

    # ---- Part 2: Marketing / Campaign Action Log (one row per recommendation_id; nothing done yet) ----
    tgt=dict(zip(REC["recommendation_id"],REC["target_inventory_locality"]))
    al=pd.DataFrame({"recommendation_id":REC["recommendation_id"]})
    al["action_taken"]=None; al["action_date"]=None; al["campaign_channel"]=None
    al["target_inventory"]=al["recommendation_id"].map(tgt)   # known fact from the recommendation
    al["campaign_cost"]=pd.NA; al["owner_feedback"]=None; al["status"]="not_started"
    al.to_csv(os.path.join(OUT,"phase3_marketing_action_log.csv"),index=False)

    # ---- Part 3: Lead Funnel (per recommendation_id; ALL metrics UNKNOWN, no fabrication) ----
    lf=pd.DataFrame({"recommendation_id":REC["recommendation_id"]})
    for c in ["lead_source","leads","enquiries","visits","applications","conversions","beds_filled"]:
        lf[c]=pd.NA
    lf["status"]=PEND
    lf.to_csv(os.path.join(OUT,"phase3_lead_funnel.csv"),index=False)

    # ---- Part 4: Outcome Tracking (extends closed-loop; outcomes UNAVAILABLE until real data) ----
    ot=pd.DataFrame({"recommendation_id":REC["recommendation_id"]})
    for c in ["occupancy_before","occupancy_after","beds_filled","revenue_impact","campaign_cost"]:
        ot[c]=pd.NA
    ot["owner_feedback"]=None; ot["outcome_status"]=NA
    ot.to_csv(os.path.join(OUT,"phase3_outcome_tracking.csv"),index=False)

    # ---- Part 5: Triple vacancy-duration audit (honest; NO manufactured fill-time) ----
    # Owner-approved lifecycle correction: A33/A34 Triple beds are NEW INVENTORY -> vacancy duration is KNOWN and
    # measured from the operational start (apartments.start_date 2026-08-01), i.e. availability-since-launch, NOT a
    # manufactured historical fill-time. Any older never-occupied Triple bed (no allotment/exit history) keeps an
    # UNKNOWN duration and stays documented; fill-time is never fabricated for it.
    t=VAC[VAC["bed_type"]=="Triple"]
    def _audit_row(r):
        known=bool(r["duration_known"])
        if known:
            reason=("new inventory — vacancy counted from operational start (apartments.start_date 2026-08-01); "
                    "this is availability-since-launch, not a manufactured historical fill-time")
            rec="n/a — duration known from operational start"; res="duration KNOWN (from operational start)"
        else:
            reason=("no prior allotment/exit record -> no vacancy-start timestamp (vacancy duration derives from "
                    "allotment exit gaps; bed_status_history missing)")
            rec="none identified in current exports"; res="leave UNKNOWN (documented limitation)"
        return dict(bed_code=r["bed_code"],apartment_id=r["apartment_id"],duration_known=known,
            days_vacant=(r["days_vacant"] if pd.notna(r["days_vacant"]) else None),
            monthly_rate=r["monthly_rate"],reason_missing=reason,recoverable_source=rec,resolution=res)
    audit=[_audit_row(r) for _,r in t.iterrows()]
    aud=pd.DataFrame(audit); aud.to_csv(os.path.join(OUT,"phase3_triple_fill_time_audit.csv"),index=False)

    summary=[("amenity_master_rows",len(amdf)),("amenity_fields_unknown","100% (no market inference)"),
     ("action_log_rows",len(al)),("lead_funnel_rows",len(lf)),("outcome_rows",len(ot)),
     ("triple_beds_audited",len(aud)),
     ("triple_duration_known",int(aud["duration_known"].sum()) if len(aud) else 0),
     ("triple_fill_time_recoverable","N/A for new-inventory beds (duration known from operational start 2026-08-01); any legacy never-occupied Triple: none recoverable"),
     ("triple_resolution","new-inventory duration KNOWN (from operational start); any legacy never-occupied Triple UNKNOWN preserved (bed_status_history missing)"),
     ("outcomes_status",NA),("action_status","not_started"),
     ("recommendation_ids_linked",int(REC["recommendation_id"].nunique())),
     ("governing_rule","Vishful data = decision driver; market = context; never compare competitors")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_data_readiness_summary.csv"),index=False)
    print("PHASE-3 DATA READINESS:")
    for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": main()
