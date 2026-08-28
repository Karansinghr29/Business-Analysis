"""
Phase-3 Decision Execution -> KPI -> Outcome analytics (isolated, deterministic, read-only).
Closes the chain: Decision -> Owner Action -> KPI -> Baseline (real data) -> Measurement -> Actual
Outcome. Does NOT modify the 14 decisions, engines, review layer, or Market AI. NO fabricated
ROI/revenue/conversion uplift. Baselines computed from ACTUAL Vishful data with traceable period +
method + source; where not derivable -> UNKNOWN/UNAVAILABLE. Outcomes stay 'Outcome unavailable'
until real post-action data exists (execution tracker = all Pending). 6 review opportunities kept
SEPARATE from the 14 backbone (is_backbone=False). Writes only new files.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
def src(nn): return pd.read_csv(os.path.join(ROOT,f"Supabase Snippet Untitled query ({nn}).csv"),low_memory=False)
UNK="UNKNOWN"; UNAV="UNAVAILABLE"; OUT_UNAV="Outcome unavailable"

DEC=o("phase3_business_decisions.csv"); ET=o("phase3_execution_tracker.csv")
VAC=o("step4_vacancy_at_risk.csv"); PRICE=o("step5_pricing_analysis.csv")
AR=src(89); LEADS=src(84); TK=src(71); IT=src(76); EX=src(48)
try: EB=o("phase2_eb_anomalies.csv")
except Exception: EB=pd.DataFrame()

# ---- helpers: deterministic time-series baseline = last 3 COMPLETE months before the latest month in the data ----
def monthly(df,datecol):
    m=pd.to_datetime(df[datecol],errors="coerce",utc=True).dt.tz_localize(None).dt.to_period("M")
    g=df.assign(_m=m).dropna(subset=["_m"]).groupby("_m").size()
    if len(g)<2: return None
    months=sorted(g.index); complete=months[:-1]  # drop latest (partial) month
    base=complete[-3:] if len(complete)>=3 else complete
    return dict(period=f"{base[0]}..{base[-1]}", value=round(float(g.loc[base].mean()),1),
                unit="events/month (mean)", n_months=len(base))

TK["issue"]=TK["issue_type_id"].map(dict(zip(IT["id"],IT["name"])))
maint=monthly(TK,"created_at")
exits=monthly(EX,"exit_date")
ac_total=int((TK["issue"]=="AC Issues").sum()); tk_total=len(TK)
ac_pct=round(100*ac_total/max(tk_total,1),1)
ac_created_null=round(100*pd.to_datetime(TK[TK["issue"]=="AC Issues"]["created_at"],errors="coerce",utc=True).isna().mean(),0)
occ_by={r["bed_type"]:round(100*float(r["occupied_beds"])/max(float(r["total_beds"]),1),1)
        for _,r in PRICE.groupby("bed_type").agg(occupied_beds=("occupied_beds","sum"),total_beds=("total_beds","sum")).reset_index().iterrows()}
vac_by=VAC.groupby("bed_type").agg(vac=("bed_code","size"),rev=("rev_at_risk_monthly","sum")).reindex(["Double","Triple","Single"]).fillna(0.0)  # zero-vacancy bed_type (e.g. Single after A22 excl) -> 0, not KeyError
ar90_amt=round(float(AR.loc[AR["bucket_90_plus"]>0,"bucket_90_plus"].sum()),0); ar90_n=int((AR["bucket_90_plus"]>0).sum())
open_leads=int((LEADS["status"]=="in_progress").sum()); dbl_leads=int((LEADS["bed_type"]=="Double").sum())
eb_hi=int(EB[EB.get("anomaly_type","")=="high_consumption"]["apartment_id"].nunique()) if len(EB) and "anomaly_type" in EB.columns else 0
LM="2026-08 (data export snapshot)"

# per decision_id -> (kpi_name, method, data_source, baseline_period, baseline_value)
def K(name,method,source,period,value,conf):
    return dict(kpi_name=name,measurement_method=method,data_source=source,baseline_period=period,baseline_value=value,data_confidence=conf)
KPI={
 "DEC-MAINT-PRIORITISE":K("maintenance tickets / month","mean monthly ticket count, last 3 complete months","maintenance_tickets #71",maint["period"] if maint else UNK,maint["value"] if maint else UNK,"low-medium (created_at ~31% null; window = populated coverage, undercounts true volume)"),
 "DEC-AMEN-AC":K("AC-Issue tickets (cumulative) & share of maintenance","cumulative AC-Issue ticket count + % of all tickets","maintenance_tickets #71 (AC Issues)","cumulative (all recorded)",f"{ac_total} tickets ({ac_pct}% of maintenance)",f"medium — cumulative reliable; monthly TREND unreliable (created_at {ac_created_null:.0f}% null, coverage ends 2026-03)"),
 "DEC-RETENTION-REVIEW":K("tenant exits / month","mean monthly exits, last 3 complete months","tenant_exits #48",exits["period"] if exits else UNK,exits["value"] if exits else UNK,"medium (exit_date well-populated)"),
 "DEC-REVPROTECT-AR90":K("AR 90+ outstanding (₹) & tenant count","sum of positive 90+ day AR bucket (snapshot)","ar_aging #89","current snapshot",f"₹{ar90_amt:,.0f} across {ar90_n} tenants","high (ledger-derived receivable, measured not estimated)"),
 "DEC-VAC-Double":K("vacant 2-sharing beds & ₹/mo at risk","count vacant + rev_at_risk (snapshot)","step4_vacancy_at_risk.csv","current snapshot",f"{int(vac_by.loc['Double','vac'])} beds / ₹{float(vac_by.loc['Double','rev']):,.0f}","high"),
 "DEC-VAC-Triple":K("vacant 3-sharing beds & ₹/mo at risk","count vacant + rev_at_risk (snapshot)","step4_vacancy_at_risk.csv","current snapshot",f"{int(vac_by.loc['Triple','vac'])} beds / ₹{float(vac_by.loc['Triple','rev']):,.0f}","high"),
 "DEC-VAC-Single":K("vacant single beds & ₹/mo at risk","count vacant + rev_at_risk (snapshot)","step4_vacancy_at_risk.csv","current snapshot",f"{int(vac_by.loc['Single','vac'])} beds / ₹{float(vac_by.loc['Single','rev']):,.0f}","high"),
 "DEC-PRICEREV-Triple":K("Triple occupancy %","occupied/total for Triple (snapshot)","step5_pricing_analysis.csv","current snapshot",f"{occ_by.get('Triple',UNK)}%","high"),
 "DEC-PRICEREV-Single":K("Single occupancy %","occupied/total for Single (snapshot)","step5_pricing_analysis.csv","current snapshot",f"{occ_by.get('Single',UNK)}%","high"),
 "DEC-LEAD-FOLLOWUP":K("open leads (in_progress)","count leads status=in_progress (snapshot)","leads #84","current snapshot",str(open_leads),"high (small n=18; whatsapp_bot only)"),
 "DEC-LEAD-DEMAND-2SH":K("Double-requested leads","count leads bed_type=Double (snapshot)","leads #84","current snapshot",str(dbl_leads),"low (n=2; bed_type mostly null)"),
 "DEC-EB-INVESTIGATE":K("high-consumption apartments flagged","distinct apartments flagged high_consumption","phase2_eb_anomalies.csv","current snapshot",str(eb_hi),"medium (validated anomaly engine; snapshot)"),
 "DEC-LOC-MKT":K("leads by locality",UNAV+" — leads table has no populated locality field","leads #84",UNAV,UNAV,UNAV),
 "DEC-MKT-ROI-GAP":K("cost per lead / cost per fill",UNAV+" — no spend<->lead attribution","financials #85 / leads #84",UNAV,UNAV,UNAV),
}
et_status=dict(zip(ET["decision_id"],ET["status"])); et_action=dict(zip(ET["decision_id"],ET["action_taken"]))

def main():
    rows=[]
    for _,d in DEC.iterrows():
        did=d["decision_id"]; k=KPI.get(did)
        measurable = k is not None and k["baseline_value"] not in (UNK,UNAV)
        act=et_action.get(did); act="none yet" if (act is None or str(act) in ("nan","None","")) else act
        rows.append(dict(decision_id=did, is_backbone=True, decision_topic=d["decision"],
            decision_source=d["evidence_source"], evidence_summary=str(d["data_signal"])[:160],
            owner_action=act, business_impact_metric=d["expected_impact"],
            kpi_name=(k["kpi_name"] if k else UNK), baseline_period=(k["baseline_period"] if k else UNK),
            baseline_value=(k["baseline_value"] if k else UNK),
            current_period=("current snapshot" if measurable else UNAV),
            current_value=(k["baseline_value"] if measurable else UNAV),  # = baseline (no action executed yet)
            target_value=UNK,  # no legitimate pre-existing target -> not invented
            data_confidence=(k["data_confidence"] if k else UNAV),
            status=("baseline_established_pending_action" if measurable else "not_measurable_pending_data"),
            outcome=OUT_UNAV, outcome_availability="pending_post_action_data",
            measurement_method=(k["measurement_method"] if k else UNAV),
            data_source=(k["data_source"] if k else UNAV), last_measured_at=LM))
    # 6 review-derived opportunities (SEPARATE from backbone)
    OPP=[("OPP-laundry","Laundry marketing","actionable_now","laundry-related engagement (marketing)","own washing-machine assets VERIFIED","no"),
         ("OPP-common_area","Common-area marketing","actionable_now","common-area marketing engagement","common area VERIFIED (issue-data)","no"),
         ("OPP-food","Food owner verification","owner_verify_first","food-service availability","Vishful food status UNKNOWN","yes"),
         ("OPP-security","Security/CCTV owner verification","owner_verify_first","CCTV/security availability","Vishful security status UNKNOWN","yes"),
         ("OPP-safety","Safety owner verification","owner_verify_first","safety availability","Vishful safety status UNKNOWN","yes"),
         ("OPP-parking","Parking owner verification","owner_verify_first","parking availability","Vishful parking status UNKNOWN","yes")]
    for oid,topic,status,kpi,vf,owner in OPP:
        rows.append(dict(decision_id=oid, is_backbone=False, decision_topic=topic,
            decision_source="review_derived", evidence_summary="market review signal (context) + Vishful fact",
            owner_action="none yet", business_impact_metric="see review layer (no ₹ computed)",
            kpi_name=kpi, baseline_period=UNAV, baseline_value=(UNAV if owner=="yes" else "verified capability present"),
            current_period=UNAV, current_value=UNAV, target_value=UNK,
            data_confidence=(UNAV if owner=="yes" else "medium (own asset/issue evidence)"), status=status,
            outcome=OUT_UNAV, outcome_availability="pending_post_action_data",
            measurement_method=("owner verification required — do not infer presence/absence" if owner=="yes" else "engagement/complaint measure once actioned"),
            data_source="phase3_review_decision_candidates.csv", last_measured_at=LM))
    df=pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT,"phase3_decision_execution_analytics.csv"),index=False)

    bb=df[df["is_backbone"]]
    meas=int((bb["status"]=="baseline_established_pending_action").sum())
    summary=[("backbone_decisions",len(bb)),("with_measurable_baseline",meas),
     ("baseline_unavailable",int((bb["status"]=="not_measurable_pending_data").sum())),
     ("outcomes_available",0),("all_outcomes",OUT_UNAV+" (no action executed yet)"),
     ("review_opportunities",int((~df["is_backbone"]).sum())),
     ("opportunities_owner_verify",int(((~df["is_backbone"])&(df["status"]=="owner_verify_first")).sum())),
     ("time_series_kpis","maintenance tickets/mo, AC tickets/mo, exits/mo"),
     ("snapshot_kpis","AR90 ₹, vacancy beds/₹, occupancy %, open leads, 2-share leads, EB high-consumption"),
     ("unavailable_kpis","DEC-LOC-MKT (no locality on leads), DEC-MKT-ROI-GAP (no spend<->lead attribution)"),
     ("rule","baselines from real data; outcomes unavailable until post-action; no fabricated ROI; unknown preserved")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_decision_kpi_summary.csv"),index=False)
    print("PHASE-3 DECISION EXECUTION ANALYTICS:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nbackbone KPI baselines:")
    for _,r in bb.iterrows(): print(f"  {r['decision_id']:22} | {r['kpi_name']:34} | baseline={r['baseline_value']} ({r['baseline_period']}) | {r['status']}")

if __name__=="__main__": main()
