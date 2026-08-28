"""
Phase-3 BUSINESS DECISION ENGINE (isolated, deterministic, read-only). Parts 2/3/4/7/8/9/10/11/13/14/15/16.
DATA -> SIGNAL -> BUSINESS PROBLEM -> DECISION -> ACTION -> EXPECTED IMPACT -> EVIDENCE -> TRACKING.
Reuses VALIDATED outputs (step4/step5, phase2 eb/maintenance/churn/overdue, amenity-inventory,
market signals) + new lead/marketing/AR signals. Does NOT recompute or alter existing engines.

Rules: Vishful data = decision driver; market = context only; NO competitor comparison/ranking/
benchmark; NO fabricated price/ROI/outcome; expected_impact only where it is a REAL figure from
Vishful data; unknown stays unknown; conversion/ROI linkage flagged UNAVAILABLE when absent.
Writes ONLY new phase3_business_decisions* / owner board / closed-loop classification / gap files.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
def src(nn): return pd.read_csv(os.path.join(ROOT,f"Supabase Snippet Untitled query ({nn}).csv"),low_memory=False)

VAC=o("step4_vacancy_at_risk.csv"); PRICE=o("step5_pricing_analysis.csv")
MX=o("phase3_inventory_amenity_matrix.csv")
LEADS=src(84); FIN=src(85); AR=src(89)
try: EB=o("phase2_eb_anomalies.csv")
except Exception: EB=pd.DataFrame()
try: MREG=o("phase2_maintenance_repeat_register.csv")
except Exception: MREG=pd.DataFrame()
try: CH=o("phase2_churn_risk_scored.csv")
except Exception: CH=pd.DataFrame()

def inv():
    g=PRICE.groupby("bed_type").agg(total=("total_beds","sum"),occ=("occupied_beds","sum")).reset_index()
    g["occ_pct"]=100.0*g["occ"]/g["total"].clip(lower=1)
    v=VAC.groupby("bed_type").agg(vac=("bed_code","size"),med=("days_vacant","median"),rev=("rev_at_risk_monthly","sum")).reset_index()
    return g.merge(v,on="bed_type",how="left")

D=[]
def add(did,cat,pri,score,esrc,signal,problem,decision,action,impact,missing,track,prov):
    D.append(dict(decision_id=did,category=cat,priority=pri,score=round(score,1),evidence_source=esrc,
        data_signal=signal,business_problem=problem,decision=decision,recommended_action=action,
        expected_impact=impact,missing_data_flag=missing,tracking_field=track,provenance=prov))

def main():
    I=inv().set_index("bed_type")
    SH={"Single":"single","Double":"2-sharing","Triple":"3-sharing"}
    maxrev=max(VAC.groupby("bed_type")["rev_at_risk_monthly"].sum().max(),1)

    # --- vacancy reduction / slow-fill / pricing review (per bed_type) ---
    for bt in ["Double","Triple","Single"]:
        if bt not in I.index: continue
        r=I.loc[bt]; occ=float(r["occ_pct"])
        vac=int(r["vac"]) if pd.notna(r["vac"]) else 0            # zero-vacancy category (e.g. Single after A22 excl) is not an error
        rev=float(r["rev"]) if pd.notna(r["rev"]) else 0.0
        med=r["med"]; mk=pd.notna(med)
        cfg=SH[bt]
        sc=40*(100-occ)/100 + (25*min(float(med)/180,1) if mk else 0) + 20*(rev/maxrev) + 15*min(vac/10,1)
        # DEC-VAC-* stays in the protected 14-decision backbone at every vacancy level, but at ZERO vacancy there is
        # no inventory to promote — the decision must say so instead of issuing a promote instruction it cannot
        # support. No fabricated opportunity, no implied lost revenue, no invented future demand.
        if vac==0:
            add(f"DEC-VAC-{bt}","vacancy reduction","Low",sc,
                "VISHFUL_INTERNAL",f"0 vacant {cfg}, occupancy {occ:.1f}% — no current {cfg} vacancy",
                f"No current {cfg} vacancy — zero revenue exposure from vacant {cfg}",
                f"No {cfg} vacancy action required at present",
                f"No current {cfg} vacancy to promote. Monitor inventory availability.",
                "not applicable — no current vacancy, zero exposure",None,
                "beds_filled, occupancy_after, revenue_recovered","step4_vacancy_at_risk.csv; step5_pricing_analysis.csv")
        else:
            add(f"DEC-VAC-{bt}","vacancy reduction",("High" if sc>=60 else "Medium" if sc>=40 else "Low"),sc,
                "VISHFUL_INTERNAL",f"{vac} vacant {cfg}, occupancy {occ:.1f}%, {('median '+str(int(float(med)))+'d vacant' if mk else 'fill-time unknown')}",
                f"₹{rev:,.0f}/mo revenue exposure from vacant {cfg}",
                f"Reduce {cfg} vacancy",f"Promote available {cfg} inventory",
                f"₹{rev:,.0f} / month revenue-at-risk (real, step4)",("Triple fill-time unknown" if (bt=='Triple') else None),
                "beds_filled, occupancy_after, revenue_recovered","step4_vacancy_at_risk.csv; step5_pricing_analysis.csv")
        # pricing review candidate — persistent vacancy despite existing rate (do NOT prescribe ₹)
        if (mk and float(med)>=90) or occ<85:
            add(f"DEC-PRICEREV-{bt}","pricing review",("Medium" if (occ<85 or (mk and float(med)>=180)) else "Low"),
                (50 if occ<85 else 40),"VISHFUL_INTERNAL",
                f"{cfg}: {('vacant '+str(int(float(med)))+'d' if mk else '')} occupancy {occ:.1f}% despite current rate card",
                f"Persistent vacancy on {cfg} despite existing rate","Pricing review candidate",
                f"Review rate card + fill signal for {cfg} (do NOT auto-change price)","not monetarily quantifiable — review only",
                ("fill-time unknown" if not mk else None),"occupancy_after_review, days_to_fill","rate_card #43; step4/step5")

    # --- backbone framework: DEC-PRICEREV-Single is a FIXED member of the 14-decision backbone and must remain
    #     present even when current corrected data shows 0 rentable single vacancy (single occupancy high, no valid
    #     slow-fill signal). Data-honest: NO fabricated vacancy / ₹ / days / slow-fill — the old "1 vacant / ₹19,000 /
    #     272d" evidence came from A22 (now correctly excluded). Non-backbone single opportunities/cards may still drop.
    if not any(d["decision_id"]=="DEC-PRICEREV-Single" for d in D):
        so=I.loc["Single"] if "Single" in I.index else None
        socc=float(so["occ_pct"]) if so is not None else float("nan")
        svac=int(so["vac"]) if (so is not None and pd.notna(so["vac"])) else 0
        add("DEC-PRICEREV-Single","pricing review","Low",30.0,"VISHFUL_INTERNAL",
            f"single: {svac} vacant, occupancy {socc:.1f}% — no current single pricing-review signal",
            "No current single pricing-review signal (single inventory not showing a vacancy/slow-fill issue)",
            "Pricing review candidate (backbone) — no active single signal at present",
            "Monitor single occupancy/fill; no rate action indicated now (do NOT auto-change price)",
            "not applicable — no current single vacancy/slow-fill",None,
            "occupancy_after_review, days_to_fill","rate_card #43; step4/step5")

    # --- AC-associated available inventory (amenity now VERIFIED from own data) ---
    ac_beds=MX[MX["AC"]=="present"] if "AC" in MX.columns else pd.DataFrame()
    if len(ac_beds):
        rev=float(ac_beds["rev_at_risk_monthly"].sum())
        add("DEC-AMEN-AC","amenity marketing","Medium",55.0,"VISHFUL_INTERNAL",
            f"{len(ac_beds)} vacant beds are in AC-equipped apartments (bed/apartment-level allocation)",
            "Available inventory has a confirmed premium amenity not being marketed",
            "Highlight AC-associated available inventory",
            f"Market AC availability on the {len(ac_beds)} vacant AC beds",
            f"₹{rev:,.0f}/mo revenue-at-risk on AC-associated vacant beds (real)",None,
            "beds_filled on AC inventory","phase3_inventory_amenity_matrix.csv (allocations #79)")

    # --- revenue protection: AR 90+ dues ---
    if "bucket_90_plus" in AR.columns:
        n90=int((AR["bucket_90_plus"]>0).sum())
        amt90=float(AR.loc[AR["bucket_90_plus"]>0,"bucket_90_plus"].sum())  # positive dues only (exclude credits/advances)
        add("DEC-REVPROTECT-AR90","revenue protection","High",70.0,"VISHFUL_INTERNAL",
            f"{n90} tenants with dues in the 90+ day bucket",f"₹{amt90:,.0f} aged receivables at risk",
            "Escalate collections on 90+ day AR","Prioritized collections follow-up on 90+ day tenants",
            f"₹{amt90:,.0f} aged AR (real, ar_aging #89)",None,"ar_recovered, dues_cleared","ar_aging #89 / ledger")

    # --- electricity cost control (reuse validated anomalies) ---
    # TIME-FRAMED: the EB series spans multiple years, so a cumulative distinct-apartment count would present old
    # signals as if every one needed inspecting today. Separate the cumulative historical signal from the current
    # period (latest year present in the data) and base the recommendation on the current evidence.
    if len(EB) and "anomaly_type" in EB.columns:
        hi=EB[EB["anomaly_type"]=="high_consumption"]
        n=int(hi["apartment_id"].nunique()) if "apartment_id" in hi.columns else len(hi)
        if n>0:
            _d=pd.to_datetime(EB.get("billing_month"),format="%b-%y",errors="coerce")
            _cy=int(_d.dt.year.max()) if _d.notna().any() else None
            if _cy is not None:
                _hd=pd.to_datetime(hi["billing_month"],format="%b-%y",errors="coerce")
                ncur=int(hi.loc[_hd.dt.year==_cy,"apartment_id"].nunique())
                yr0=int(_d.dt.year.min())
                add("DEC-EB-INVESTIGATE","electricity cost control","Medium",50.0,"VISHFUL_INTERNAL",
                    f"{ncur} apartment(s) flagged high-consumption in the current period ({_cy}); {n} distinct "
                    f"apartment(s) flagged cumulatively across {yr0}-{_cy}",
                    f"High electricity cost signals — {ncur} current in {_cy}, the rest historical; cause unknown",
                    f"Review the {ncur} currently-flagged apartment(s) first",
                    f"Inspect the {ncur} apartment(s) flagged in {_cy} before any broader review; the remaining "
                    f"cumulative {yr0}-{_cy} flags are historical context, not a current inspection list "
                    "(do NOT accuse tenants/claim wastage without evidence)",
                    "not monetarily quantifiable yet — measure EB units/₹ after inspection",
                    f"root cause not in data; cumulative count spans {yr0}-{_cy} and is not a current backlog",
                    "units_consumed_after, eb_cost_change","phase2_eb_anomalies.csv")
            else:
                add("DEC-EB-INVESTIGATE","electricity cost control","Medium",50.0,"VISHFUL_INTERNAL",
                    f"{n} apartment(s) flagged high-consumption by validated EB anomaly engine (period not derivable)",
                    "Recurring high electricity cost — operational cause unknown",
                    "Investigate high-consumption apartments",
                    "Operational inspection of flagged apartments (do NOT accuse tenants/claim wastage without evidence)",
                    "not monetarily quantifiable yet — measure EB units/₹ after inspection",
                    "root cause not in data; reading period not derivable","units_consumed_after, eb_cost_change",
                    "phase2_eb_anomalies.csv")

    # --- maintenance prioritisation (reuse validated register) ---
    if len(MREG):
        hi=MREG[(MREG.get("priority","")=="High")&(MREG.get("date_confidence","")=="high")] if "priority" in MREG.columns else pd.DataFrame()
        if len(hi):
            add("DEC-MAINT-PRIORITISE","maintenance prioritisation","Medium",48.0,"VISHFUL_INTERNAL",
                f"{len(hi)} high-confidence recurring maintenance hotspots (apartment×issue)",
                "Repeat maintenance burden concentrated on specific apartment/issue combos",
                "Prioritise recurring maintenance hotspots + review assets for replacement",
                "Schedule preventive maintenance / asset-replacement review on top hotspots",
                "not monetarily quantifiable — measure repeat-ticket reduction",None,
                "repeat_tickets_after, resolution_time","phase2_maintenance_repeat_register.csv")

    # --- tenant retention review (ranking, not prediction) ---
    if len(CH) and "risk_band" in CH.columns:
        nH=int((CH["risk_band"]=="High").sum())
        if nH>0:
            add("DEC-RETENTION-REVIEW","tenant retention","Medium",45.0,"VISHFUL_INTERNAL",
                f"{nH} tenants in High churn-risk band (ranking, ROC-AUC ~0.72 — NOT a classifier)",
                "Possible avoidable exits concentrated in a ranked watch-list",
                "Retention review signal (not a leave prediction)",
                "Owner/staff review of High-band tenants for retention outreach",
                "not monetarily quantifiable — measure retained vs exited",
                "churn is ranking-only, not a hard prediction","retained_count, exits_avoided","phase2_churn_risk_scored.csv")

    # --- lead follow-up + lead-derived demand (Parts 3/7) ---
    LEADS["created_dt"]=pd.to_datetime(LEADS["created_at"],errors="coerce",utc=True)
    stale=int((LEADS["status"]=="in_progress").sum())
    add("DEC-LEAD-FOLLOWUP","lead follow-up","High",65.0,"VISHFUL_INTERNAL",
        f"{stale} leads in 'in_progress' status (whatsapp_bot), {len(LEADS)} total",
        "Open leads not progressed to visit/conversion",
        "Follow up open leads promptly","Contact all in_progress leads; log outcome per lead id",
        "not monetarily quantifiable — measure lead->visit->fill",
        "lead->conversion linkage UNAVAILABLE (leads #84 not joined to allotments #44)",
        "visits_booked, leads_converted, beds_filled","leads #84")
    req=LEADS["bed_type"].dropna().astype(str).value_counts().to_dict()
    if "Double" in req and "Double" in I.index and int(I.loc["Double","vac"])>0:
        add("DEC-LEAD-DEMAND-2SH","lead-derived demand signal","Medium",50.0,"VISHFUL_INTERNAL",
            f"{req['Double']} lead(s) requested Double (2-sharing) while {int(I.loc['Double','vac'])} 2-sharing beds are vacant",
            "Live demand signal aligns with current 2-sharing vacancy",
            "lead-derived demand signal for 2-sharing (NOT a statistical forecast)",
            "Fast-track 2-sharing leads to the vacant 2-sharing beds",
            "not monetarily quantifiable — measure conversion of these leads",
            "small n (leads bed_type mostly null)","leads_converted_2sharing","leads #84; step4")

    # --- marketing ROI gap (Part 4) ---
    mk=float(FIN["marketing"].sum()); mmonths=int((FIN["marketing"]!=0).sum())
    add("DEC-MKT-ROI-GAP","campaign allocation","Low",30.0,"VISHFUL_INTERNAL",
        f"marketing spend ₹{mk:,.0f} over {mmonths} months; leads exist (source=whatsapp_bot) but not linked to spend",
        "Cannot evaluate marketing effectiveness","Establish spend->lead->conversion linkage",
        "Start tagging spend by channel/campaign + link leads to allotments",
        "ROI UNAVAILABLE — do not estimate","spend<->lead<->conversion linkage missing",
        "cost_per_lead, cost_per_fill (once linked)","financials #85; leads #84")

    # --- locality marketing (market CONTEXT) ---
    add("DEC-LOC-MKT","locality marketing","Medium",45.0,"COMBINED",
        f"{int(VAC.shape[0])} vacant beds internally + dense PG/co-living supply in Vishful's own locality (market context)",
        "Marketing spend should focus where inventory needs fill","Locality-targeted marketing",
        "Run locality-targeted campaign for available inventory (Thiruvanmiyur/Adyar/Perungudi)",
        "not monetarily quantifiable — measure leads by locality",None,
        "leads_by_locality, fills","step4_vacancy_at_risk.csv; phase3_market_signals.csv (context)")

    df=pd.DataFrame(D).sort_values("score",ascending=False).reset_index(drop=True)
    cols=["decision_id","category","priority","score","evidence_source","data_signal","business_problem",
          "decision","recommended_action","expected_impact","missing_data_flag","tracking_field","provenance"]
    df[cols].to_csv(os.path.join(OUT,"phase3_business_decisions.csv"),index=False)

    # ---- Owner Decision Board (Part 15): top decisions, owner-facing ----
    board=df.head(8)[["decision_id","decision","priority","recommended_action","expected_impact","tracking_field","missing_data_flag"]].copy()
    board.columns=["id","decision","priority","action","expected_impact_or_KPI","measure","missing_data"]
    board.to_csv(os.path.join(OUT,"phase3_owner_decision_board.csv"),index=False)

    # ---- Closed-loop field classification (Part 14) ----
    cl=[("recommendation_id","AUTO_SOURCEABLE","decision_id already generated"),
        ("target_inventory","AUTO_SOURCEABLE","bed_type/sharing from step4/step5"),
        ("occupancy_before","AUTO_SOURCEABLE","snapshot from step5 at action time"),
        ("vacant_beds_before","AUTO_SOURCEABLE","step4 count at action time"),
        ("revenue_at_risk","AUTO_SOURCEABLE","step4 rev_at_risk_monthly"),
        ("ar_90_plus_amount","AUTO_SOURCEABLE","ar_aging #89"),
        ("amenity_on_inventory","AUTO_SOURCEABLE","phase3_inventory_amenity_matrix (allocations #79)"),
        ("lead_count/source","AUTO_SOURCEABLE","leads #84"),
        ("marketing_spend","AUTO_SOURCEABLE","financials #85 (aggregate only)"),
        ("action_taken/action_date/campaign_channel","OWNER_INPUT_REQUIRED","not recorded in data"),
        ("leads->conversion linkage","OWNER_INPUT_REQUIRED","leads not joined to allotments"),
        ("beds_filled_after/occupancy_after","OWNER_INPUT_REQUIRED","measured after action"),
        ("revenue_impact","OWNER_INPUT_REQUIRED","measured after action"),
        ("campaign_cost_per_action","OWNER_INPUT_REQUIRED","spend not tagged per campaign"),
        ("owner_feedback","OWNER_INPUT_REQUIRED","qualitative"),
        ("Triple fill-time (days_vacant)","NOT_AVAILABLE","never-occupied beds; no allotment/exit history"),
        ("marketing ROI","NOT_AVAILABLE","no spend<->lead<->conversion linkage")]
    pd.DataFrame(cl,columns=["field","classification","reason"]).to_csv(os.path.join(OUT,"phase3_closed_loop_field_classification.csv"),index=False)

    # ---- Data Gap Report (Part 16), ranked by business value ----
    gap=[("1 available & usable","occupancy, vacancy, rev-at-risk, rate card, AR aging, assets/amenities, maintenance, EB, churn ranking","use now"),
         ("2 available but needs joining","assets->allocations->beds->vacancy (amenity×inventory) — done here; leads->allotments (conversion) — pending","join to enable conversion + per-bed amenity"),
         ("3 partially available","lead attributes (bed_type/budget mostly null), fill-time (10/20 beds), marketing spend (no channel tag)","enrich at capture"),
         ("4 genuinely missing","action log, lead->conversion, campaign channel/cost, occupancy_after, Vishful catered-meals/parking/CCTV/power-backup status","OWNER capture — highest value"),
         ("5 NOT worth collecting","more competitor first-party pricing (exhausted: 1 comparable), competitor benchmarks","do NOT collect")]
    pd.DataFrame(gap,columns=["tier","data","action"]).to_csv(os.path.join(OUT,"phase3_data_gap_report.csv"),index=False)

    catc=df["category"].value_counts().to_dict()
    summary=[("total_decisions",len(df)),("High",int((df["priority"]=="High").sum())),
     ("Medium",int((df["priority"]=="Medium").sum())),("Low",int((df["priority"]=="Low").sum())),
     ("categories",str(catc)),("with_real_₹_impact",int(df["expected_impact"].astype(str).str.contains("₹.*real").sum())),
     ("with_missing_data_flag",int(df["missing_data_flag"].notna().sum())),
     ("roi_status","UNAVAILABLE (no spend<->lead<->conversion linkage)"),
     ("conversion_linkage","UNAVAILABLE (leads #84 not joined to allotments)")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_business_decisions_summary.csv"),index=False)
    print("PHASE-3 BUSINESS DECISIONS:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\ndecisions:")
    for _,r in df.iterrows(): print(f"  [{r['priority']:6}] {r['score']:>5} {r['decision_id']:22} | {r['decision']} | impact={r['expected_impact']}")

if __name__=="__main__": main()
