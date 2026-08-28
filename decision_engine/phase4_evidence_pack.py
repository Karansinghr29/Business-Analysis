"""
Phase-4 EVIDENCE PACK (deterministic, read-only). Assembles ID'd, source-traceable facts from EXISTING validated
engine outputs. Does NOT recompute business metrics — every metric_value is copied from a source output and the
validator re-verifies it against that source. No LLM, no now()/random. VISHFUL_INTERNAL vs MARKET_CONTEXT tagged.
Writes ONLY phase4_evidence_pack.csv + _summary.csv. Existing outputs untouched.
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))

def _asof():
    try: return str(pd.read_csv(os.path.join(OUT,"phase2_revenue_backtest.csv"))["month"].max())
    except Exception: return "2026-08"

def build():
    ASOF=_asof(); rows=[]
    def ev(eid,domain,statement,name,value,unit,ds,field,ref,engine,prov,conf,limit="none"):
        rows.append(dict(evidence_id=eid,domain=domain,statement=statement,metric_name=name,metric_value=value,
            unit=unit,source_dataset=ds,source_field=field,source_row_ref=ref,engine=engine,provenance=prov,
            confidence=conf,as_of_date=ASOF,data_limitation=limit))

    # ---- Vacancy (VISHFUL_INTERNAL) ----
    v=o("step4_vacancy_at_risk.csv")
    ev("EV-VAC-TOTAL","vacancy",f"{len(v)} vacant beds; monthly revenue at risk Rs{int(v['rev_at_risk_monthly'].sum()):,}",
       "vacant_beds",int(len(v)),"beds","step4_vacancy_at_risk.csv","bed_code","aggregate","step4_vacancy","VISHFUL_INTERNAL","High",
       "vacancy duration approximate (bed_status_history missing)")
    ev("EV-VAC-RISK","vacancy",f"Total monthly revenue at risk Rs{int(v['rev_at_risk_monthly'].sum()):,} across {len(v)} vacant beds",
       "rev_at_risk_monthly",int(v['rev_at_risk_monthly'].sum()),"INR/month","step4_vacancy_at_risk.csv","rev_at_risk_monthly","aggregate","step4_vacancy","VISHFUL_INTERNAL","High")
    for bt in ["Double","Triple","Single"]:
        sub=v[v["bed_type"]==bt]
        if len(sub):
            ev(f"EV-VAC-{bt[:3].upper()}","vacancy",f"{len(sub)} vacant {bt} beds; Rs{int(sub['rev_at_risk_monthly'].sum()):,}/month at risk",
               "vacant_beds",int(len(sub)),"beds","step4_vacancy_at_risk.csv","bed_type",bt,"step4_vacancy","VISHFUL_INTERNAL","High")
            ev(f"EV-VAC-{bt[:3].upper()}-RISK","vacancy",f"{bt} vacant beds monthly revenue at risk Rs{int(sub['rev_at_risk_monthly'].sum()):,}",
               "rev_at_risk_monthly",int(sub['rev_at_risk_monthly'].sum()),"INR/month","step4_vacancy_at_risk.csv","rev_at_risk_monthly",bt,"step4_vacancy","VISHFUL_INTERNAL","High")

    # ---- Demand / leads (VISHFUL_INTERNAL) ----
    lf=o("phase3_lead_followup.csv"); openl=lf[lf["lead_status"].isin(["in_progress","visit_requested"])]
    ev("EV-DEM-OPEN","demand",f"{len(openl)} open leads (in_progress/visit_requested)","open_leads",int(len(openl)),"leads",
       "phase3_lead_followup.csv","lead_status","aggregate","phase3_lead_followup","VISHFUL_INTERNAL","High")
    for bt in ["Double","Triple","Single"]:
        n=int((openl["requested_bed_type"]==bt).sum())
        if n>0: ev(f"EV-DEM-{bt[:3].upper()}","demand",f"{n} open {bt}-sharing leads","open_leads",n,"leads",
                   "phase3_lead_followup.csv","requested_bed_type",bt,"phase3_lead_followup","VISHFUL_INTERNAL","High")

    # ---- Collections / AR (VISHFUL_INTERNAL) ----
    ov=o("phase2_overdue_risk_scored.csv"); hi=ov[ov["risk"]>0.7]
    ev("EV-AR-HIGH","collections",f"{len(hi)} tenants at high overdue risk (>0.7); AR Rs{int(hi['amount'].sum()):,}",
       "high_risk_tenants",int(len(hi)),"tenants","phase2_overdue_risk_scored.csv","risk","aggregate","overdue_model","VISHFUL_INTERNAL","High",
       "settlement UNRECONCILED (receipt_allocations missing)")
    ev("EV-AR-HIGH-AMT","collections",f"AR exposure of high-risk tenants Rs{int(hi['amount'].sum()):,}",
       "ar_amount",int(hi['amount'].sum()),"INR","phase2_overdue_risk_scored.csv","amount","aggregate","overdue_model","VISHFUL_INTERNAL","High",
       "settlement UNRECONCILED (receipt_allocations missing)")

    # ---- Churn (VISHFUL_INTERNAL) ----
    ch=o("phase2_churn_risk_scored.csv"); nH=int((ch["risk_band"]=="High").sum())
    ev("EV-CHURN-HIGH","churn",f"{nH} tenants in High churn-risk band","high_band_tenants",nH,"tenants",
       "phase2_churn_risk_scored.csv","risk_band","High","churn_model","VISHFUL_INTERNAL","Medium",
       "ranking-only (ROC-AUC ~0.72); not a yes/no classifier")

    # ---- EB (VISHFUL_INTERNAL) ----
    eb=o("phase2_eb_leak_signals.csv"); nleak=int(eb["leak_signal"].sum())
    ev("EV-EB-LEAK","eb",f"{nleak} possible-leak EB candidates (occupancy-aware)","leak_candidates",nleak,"meters",
       "phase2_eb_leak_signals.csv","leak_signal","aggregate","eb_leak","VISHFUL_INTERNAL","Medium",
       "abnormal consumption is NOT a confirmed leak (inspect)")

    # ---- Maintenance (VISHFUL_INTERNAL) ----
    mr=o("phase2_maintenance_repeat_register.csv")
    nhot=int(((mr["priority"]=="High")&(mr["date_confidence"]=="high")&(mr["recur_le90"]>0)).sum())
    ev("EV-MAINT-HOT","maintenance",f"{nhot} high-confidence High-priority recurring maintenance hotspots (<=90d)",
       "hotspots",nhot,"apartment_issue_groups","phase2_maintenance_repeat_register.csv","priority","aggregate","maintenance_repeat","VISHFUL_INTERNAL","High",
       "act on date_confidence=high only")

    # ---- Amenity verified (VISHFUL_INTERNAL) ----
    am=o("phase3_amenity_master_from_data.csv"); ver=am[am["verified_status"]=="VERIFIED_PRESENT"]
    for _,r in ver.iterrows():
        key=re.sub(r"[^A-Za-z0-9]","",str(r["amenity"])).upper()[:8]
        ev(f"EV-AMEN-{key}","amenity",f"Vishful amenity '{r['amenity']}' is verified present ({r['mapping_confidence']})",
           "verified",1,"flag","phase3_amenity_master_from_data.csv","verified_status",str(r["amenity"]),"amenity_master","VISHFUL_INTERNAL","High")

    # ---- Market context (MARKET_CONTEXT — never a comparison) ----
    md=o("phase3_market_decision_signals.csv")
    for _,r in md.iterrows():
        st=str(r["signal_type"]); sv=str(r["signal_value"]); act=str(r.get("candidate_action",""))
        m=re.search(r"on (\d+) first-party", sv)
        if st=="published_amenity" and m:
            amn=sv.split(" published")[0].split(" availability")[0].strip()
            key=re.sub(r"[^A-Za-z0-9]","",amn).upper()[:8]
            gate = "Do NOT advertise" in act
            ev(f"EV-MKT-AMEN-{key}","market",f"'{amn}' is publicly published on {int(m.group(1))} first-party market sources",
               "published_sources",int(m.group(1)),"sources","phase3_market_decision_signals.csv","signal_value",amn,"market_decision_signals","MARKET_CONTEXT","Medium",
               ("Vishful own status unknown -> owner verification required" if gate else "market context only; no causal conversion evidence"))
        if st=="sharing_configuration":
            sh=sv.split(" is a")[0].strip(); key=re.sub(r"[^A-Za-z0-9]","",sh).upper()[:8]
            ev(f"EV-MKT-SHARE-{key}","market",f"'{sh}' sharing configuration appears in public market listings",
               "published",1,"flag","phase3_market_decision_signals.csv","signal_value",sh,"market_decision_signals","MARKET_CONTEXT","Low",
               "market context only")

    P=pd.DataFrame(rows)
    assert P["evidence_id"].is_unique, "duplicate evidence_id"
    P.to_csv(os.path.join(OUT,"phase4_evidence_pack.csv"),index=False)
    (P.groupby(["domain","provenance"]).size().reset_index(name="facts")).to_csv(os.path.join(OUT,"phase4_evidence_pack_summary.csv"),index=False)
    return P

if __name__=="__main__":
    P=build(); print(f"EVIDENCE PACK: {len(P)} facts, {P['provenance'].value_counts().to_dict()}")
    print(P[["evidence_id","domain","statement","confidence"]].to_string(index=False))
