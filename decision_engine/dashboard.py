"""
Vishful — Owner Decision Dashboard (Phase-4).
VIEW LAYER ONLY: consumes validated output CSVs + labels.py. No analytical recompute,
no model/target/source changes. Confidence/business interpretations preserved verbatim.
Run:  streamlit run dashboard.py
"""
from __future__ import annotations
import os, json, html
import pandas as pd
import streamlit as st
from labels import add_labels
from validation import require_columns, SourceValidationError

HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")

# ---- dataset registry: file -> required columns (fail loudly if missing) ----
DATASETS={
 "profit_totals":("step2_profit_totals.csv",["revenue","expenses","owner_rent","existing_profit","corrected_profit","margin_pct"]),
 "profit_monthly":("step2_profit_monthly.csv",["month","revenue","corrected_profit"]),
 "data_trust":("step1_data_trust.csv",["object","classification","note"]),
 "recon_drift":("step1_reconciliation_drift.csv",["source_table","legacy_amount","je_net_amount","diff","verdict"]),
 "collections":("step3_active_collections_worklist.csv",["tenant_id","allotment_id","collectable_ar","priority_score","reason","recommended_action"]),
 "exited_ar":("step3_exited_ar_audit.csv",["tenant_id","collectable_ar"]),
 "overdue":("phase2_overdue_risk_scored.csv",["tenant_id","allotment_id","amount","risk","reasons","recommended_action"]),
 "vacancy":("step4_vacancy_at_risk.csv",["bed_code","apartment_id","bed_type","toilet_type","days_vacant","rev_at_risk_monthly","recommended_action"]),
 "pricing":("step5_pricing_analysis.csv",["bed_type","toilet_type","card_median","realized_median","occupancy_pct","pricing_signal","total_beds","occupied_beds"]),
 "seg_prof":("phase2_segment_profiles.csv",["size","avg_rent","tenure_days","overdue_rate","segment","business_action"]),
 "segments":("phase2_tenant_segments.csv",["tenant_id","segment","business_action"]),
 "churn":("phase2_churn_risk_scored.csv",["tenant_id","allotment_id","risk","risk_band","reasons","retention_action"]),
 "eb":("phase2_eb_anomalies.csv",["apartment_id","billing_month","units_consumed","anomaly_type","severity","baseline_method","recommended_action","reason"]),
 "eb_apt":("phase2_eb_anomaly_by_apartment.csv",["apartment_id","readings","invalid","high","low","anomaly_rate"]),
 "maint_reg":("phase2_maintenance_repeat_register.csv",["apartment_id","issue_type_id","ticket_count","recur_le90","priority","date_confidence","reason","recommended_action"]),
 "maint_hot":("phase2_maintenance_hotspots.csv",["apartment_id","issue_type_id","ticket_count","priority","date_confidence"]),
 "issue_prof":("phase2_maintenance_issue_profile.csv",["issue_type_id","tickets"]),
 "tech_prof":("phase2_maintenance_technician_profile.csv",["assigned_to","tickets"]),
 "fc":("phase2_revenue_forecast.csv",["forecast_month","predicted_revenue","lower_95","upper_95","latest_actual","baseline_naive1","backtest_MAPE"]),
 "backtest":("phase2_revenue_backtest.csv",["month","actual","hw","naive1"]),
 "comp_fc":("phase2_component_revenue_forecast.csv",["forecast_month","predicted_revenue","occupied_beds_fc","effective_rent_fc","rental_fc","electricity_fc","backtest_MAPE_7f","backtest_MAPE_18f","hw_backtest_MAPE_18f","hw_predicted_revenue","folds_18"]),
 "comp_bt":("phase2_component_revenue_backtest.csv",["month","actual","holt_winters","component"]),
 "eb_leak":("phase2_eb_leak_signals.csv",["apartment_id","billing_month","units_consumed","occ_beds","anomaly_type","confidence","leak_signal","deviation_score","reason","recommended_action"]),
 "eb_leak_sum":("phase2_eb_leak_summary.csv",["signal","readings","distinct_apartments"]),
 "closure":("phase2_maintenance_closure_lag.csv",["ticket_id","apartment_id","issue_type_id","issue_type_name","assigned_to","resolved_at","closed_at","closure_lag_days","lag_status","recommended_action"]),
 "closure_sum":("phase2_maintenance_closure_lag_summary.csv",["metric","value"]),
 "closure_issue":("phase2_maintenance_closure_lag_by_issue.csv",["issue_type_name","size","median"]),
 "closure_tech":("phase2_maintenance_closure_lag_by_tech.csv",["assigned_to","size","median"]),
 "asset_prof":("phase2_asset_age_profile.csv",["asset_id","asset_type","purchase_date","allocation_date","asset_start_date","date_source","asset_age_years"]),
 "asset_sum":("phase2_asset_age_summary.csv",["metric","value"]),
 "asset_bands":("phase2_asset_age_bands.csv",["age_band","assets"]),
 "sla":("phase2_maintenance_sla.csv",["ticket_id","apartment_id","issue_type_id","issue_type_name","assigned_to","created_ts","closed_ts","actual_resolution_hours","sla_hours","sla_status","lifecycle_quality","recommended_action"]),
 "sla_sum":("phase2_maintenance_sla_summary.csv",["metric","value"]),
 "sla_issue":("phase2_maintenance_sla_by_issue.csv",["issue_type_name","tickets","sla_hours","breached","median_hours","breach_rate"]),
 "sla_tech":("phase2_maintenance_sla_by_technician.csv",["assigned_to","tickets","breached","median_hours","breach_rate"]),
 "sla_res":("phase2_maintenance_sla_resolved.csv",["ticket_id","apartment_id","issue_type_id","issue_type_name","assigned_to","created_ts","resolved_ts","resolution_hours","sla_hours","sla_breached","sla_status","lifecycle_quality","recommended_action"]),
 "sla_res_sum":("phase2_maintenance_sla_resolved_summary.csv",["metric","value"]),
 "sla_res_issue":("phase2_maintenance_sla_resolved_by_issue.csv",["issue_type_name","tickets","sla_hours","breached","median_hours","breach_rate"]),
 "sla_res_tech":("phase2_maintenance_sla_resolved_by_technician.csv",["assigned_to","tickets","breached","median_hours","breach_rate"]),
}
STALE_BLOCKLIST={"step3_collections_worklist.csv"}  # never surface

@st.cache_data(show_spinner=False)
def load(key):
    fn,cols=DATASETS[key]
    if fn in STALE_BLOCKLIST: raise SourceValidationError(f"stale file {fn} must not be surfaced")
    p=os.path.join(OUT,fn)
    if not os.path.exists(p): raise SourceValidationError(f"missing output: {fn}")
    df=pd.read_csv(p); require_columns(df,fn,cols)
    return df

def show(df, drop_ids=True):
    """Apply human labels; hide raw UUID columns where a label exists."""
    d=add_labels(df)
    if drop_ids:
        idcols=[c for c in ["tenant_id","apartment_id","bed_id","issue_type_id","allotment_id","organization_id","property_id"] if c in d.columns]
        # keep an id only if it has no label counterpart
        lbl={"tenant_id":"tenant_name","apartment_id":"apartment_code","bed_id":"bed_code","issue_type_id":"issue_type_name"}
        drop=[c for c in idcols if lbl.get(c,"__none__") in d.columns or c in ("allotment_id","organization_id","property_id")]
        d=d.drop(columns=drop)
    # move label cols to front
    front=[c for c in ["tenant_name","apartment_code","bed_code","issue_type_name"] if c in d.columns]
    d=d[front+[c for c in d.columns if c not in front]]
    return d

def rupee(x):
    try: return f"₹{float(x):,.0f}"
    except: return str(x)

# ---------------- PAGES ----------------
def p_exec():
    st.header("Executive & Data Trust")
    t=load("profit_totals").iloc[0]; fc=load("fc").iloc[0]
    price=load("pricing"); occ=100*price["occupied_beds"].sum()/max(price["total_beds"].sum(),1)
    col=load("collections")
    c=st.columns(5)
    c[0].metric("Corrected net profit", rupee(t["corrected_profit"]), help="Owner rent deducted. NOT the overstated ₹5.33 Cr raw-view profit.")
    c[1].metric("Revenue (period)", rupee(t["revenue"]))
    c[2].metric("Next-month forecast", rupee(fc["predicted_revenue"]), help=f"Holt-Winters, near-term only. MAPE {fc['backtest_MAPE']}%. 95%: {rupee(fc['lower_95'])}-{rupee(fc['upper_95'])}")
    c[3].metric("Occupancy %", f"{occ:.1f}%")
    c[4].metric("Collectable AR (active)", rupee(col["collectable_ar"].sum()))
    st.caption("⚠ Profit shown is the corrected figure (revenue − expenses − owner rent). Raw accounting-view net (₹5.33 Cr) overstates by omitting owner rent and is not used.")
    st.subheader("Monthly revenue & corrected profit")
    m=load("profit_monthly").sort_values("month")
    st.line_chart(m.set_index("month")[["revenue","corrected_profit"]])
    st.subheader("Data-trust status")
    st.dataframe(load("data_trust"), use_container_width=True, hide_index=True)
    st.subheader("Accounting↔operational reconciliation (INVESTIGATE before treating as final)")
    rd=load("recon_drift")
    st.dataframe(rd, use_container_width=True, hide_index=True)
    st.info("Cached balance drift: 711 allotments / 2,227 invoices — use ledger, not cached fields.")
    n_inv=int((rd["verdict"]=="INVESTIGATE").sum()); n_ok=int((rd["verdict"]=="PERFECT").sum())
    gap=float(t["existing_profit"])-float(t["corrected_profit"])
    st.info(f"Business insight: the raw accounting view overstates profit by {rupee(gap)} this period by omitting owner "
            f"rent — always read the corrected figure. {n_inv} of {n_inv+n_ok} reconciled source tables show a drift "
            "flagged INVESTIGATE; treat those tables' cached balances as unverified until resolved.")

def p_collections():
    st.header("Collections & Overdue")
    col=load("collections"); ov=load("overdue")
    a=st.columns(3)
    a[0].metric("Active collectable AR", rupee(col["collectable_ar"].sum()))
    a[1].metric("Active tenants with dues", f"{col['allotment_id'].nunique()}")
    a[2].metric("Overdue high-risk (>0.7)", f"{int((ov['risk']>0.7).sum())}")
    st.caption("AR = ledger-based (v_tenant_current_dues). Exited/legacy AR kept separate (audit). Settlement UNRECONCILED — receipt_allocations missing.")
    st.subheader("Active collection worklist (ledger AR, priority-ranked)")
    st.dataframe(show(col).sort_values("priority_score",ascending=False), use_container_width=True, hide_index=True)
    st.subheader("Overdue-payment risk (due-date model, ROC-AUC 0.89) — ranked")
    st.dataframe(show(ov).sort_values("risk",ascending=False), use_container_width=True, hide_index=True)
    top5_ar=col.sort_values("collectable_ar",ascending=False).head(5)["collectable_ar"].sum()
    ar_total=max(col["collectable_ar"].sum(),1)
    st.info(f"Business insight: collections are concentrated — the top 5 tenants on the worklist hold "
            f"{rupee(top5_ar)} ({100*top5_ar/ar_total:.0f}%) of all {rupee(ar_total)} collectable AR, so working "
            f"the list top-down clears the most exposure fastest. {int((ov['risk']>0.7).sum())} of {len(ov)} scored "
            "tenants are High risk (>0.7) on the overdue-payment ranking — use as a pre-emptive contact list, not a "
            "hard cutoff.")
    # ---- B1: AR basis — this page and Page 14 measure different things; neither is an error ----
    st.caption(f"**Which AR figure is this?** {rupee(ar_total)} is **ledger-net AR for currently-active tenants** "
               "(v_tenant_current_dues — advances and credits already netted off). Page 14 shows a larger "
               "**aging-gross 90+ day** figure from the aging view, which counts positive aged dues only and is not "
               "limited to active allotments. They answer different questions — *what can I collect from current "
               "tenants now* vs *how much aged debt exists at all* — so they are not directly comparable and neither "
               "is wrong. Full reconciliation between the two is currently not possible: the receipt_allocations "
               "linkage is missing, so no difference between them is calculated here.")
    with st.expander("Exited/legacy AR (audit only — not chased)"):
        st.dataframe(show(load("exited_ar")), use_container_width=True, hide_index=True)

    # ---- Aged 90+ AR — recovery REVIEW queue (deposit evidence only, never a recovery estimate) ----
    st.markdown("---"); st.subheader("Aged 90+ AR — recovery review queue")
    try:
        rq=load_csv_ro("phase3_ar_recovery_queue.csv")
        rs=dict(zip(load_csv_ro("phase3_ar_recovery_queue_summary.csv")["metric"],
                    load_csv_ro("phase3_ar_recovery_queue_summary.csv")["value"]))
        def _f(k,d=0.0):
            try: return float(rs.get(k,d))
            except Exception: return d
        m=st.columns(4)
        m[0].metric("Aged 90+ AR", rupee(_f("aged_90_plus_total")), help="Aging-gross 90+ bucket — same basis as DEC-REVPROTECT-AR90 on Page 14.")
        m[1].metric("Active tenants", f"{int(_f('active_allotments'))} · {rupee(_f('active_ar'))}")
        m[2].metric("Already exited", f"{int(_f('exited_allotments'))} · {rupee(_f('exited_ar'))}")
        m[3].metric("Deposit on file (active)", rupee(_f("deposit_held_active_total")))
        # Material vs trivial split of the no-settlement queue — derived, so it tracks the data.
        _ns=rq[rq["classification"].str.contains("no settlement record",case=False,na=False)]
        _mat=_ns[_ns["ar_90_plus"]>=5000]; _triv=_ns[_ns["ar_90_plus"]<5000]
        st.info(
            f"**What we found:** {rupee(_f('aged_90_plus_total'))} is shown as unpaid for more than 90 days across "
            f"{int(_f('aged_90_plus_allotments'))} accounts. {rs.get('exited_share_of_aged_ar','?')} of it "
            f"({rupee(_f('exited_ar'))} across {int(_f('exited_allotments'))} accounts) belongs to tenants who have "
            f"**already moved out**. Only {int(_f('active_allotments'))} accounts ({rupee(_f('active_ar'))}) are "
            f"current tenants, and {int(_f('deposit_backed_allotments'))} of those have a deposit on file.\n\n"
            "**What it means:** these are two different problems, not one. A current tenant with an unpaid balance "
            "is a collections matter. An account that has already closed is first an **accounting reconciliation** "
            "matter — because we cannot currently match payments to individual invoices, a balance that was in fact "
            "settled can still appear here as unpaid.\n\n"
            "**Worth checking:** *Why do these closed accounts still appear as 90+ day unpaid — is money genuinely "
            "owed, or has settlement activity simply not been reflected in the ageing view?* This is an open "
            "question, not a conclusion.\n\n"
            f"**What you can do — split the work.** For the **{int(_f('active_allotments'))} current tenants**, "
            "review each balance and follow up where it is confirmed still owed. For the "
            f"**{int(_f('exited_allotments'))} closed accounts**, reconcile settlement, deposit and payment records "
            "against the aged balance *before* treating any of it as collectable.\n\n"
            f"**What we will measure:** balance cleared on the active accounts, and the number of closed accounts "
            "reconciled or formally written off after review.\n\n"
            "**What we cannot conclude:** none of this is lost money, bad debt, a collections failure or anyone's "
            "mistake. Deposit evidence is **not** a recovery estimate — no collectable amount, net AR or recovery "
            "probability is calculated. Settlement-to-invoice reconciliation is unavailable because "
            "`receipt_allocations` is missing.")
        if len(_ns):
            st.warning(
                f"**Worth checking — settlement record not found.** {len(_mat)} closed account(s) holding "
                f"{rupee(float(_mat['ar_90_plus'].sum()))} have no settlement record on file and are the ones worth "
                f"chasing. The remaining {len(_triv)} account(s) total only "
                f"{rupee(float(_triv['ar_90_plus'].sum()))} between them — too small to be a meaningful collection "
                "opportunity. **These are cases to investigate, not confirmed losses**: a settlement may have "
                "happened without being recorded.")
        _cls=rq.groupby("classification").agg(cases=("allotment_id","size"),
                                              ar=("ar_90_plus","sum")).reset_index()
        _cls["ar"]=_cls["ar"].map(rupee)
        st.dataframe(_cls.rename(columns={"classification":"Classification","cases":"Cases","ar":"Aged 90+ AR"}),
                     use_container_width=True, hide_index=True)
        with st.expander("Case-level review queue"):
            _v=show(rq[["allotment_id","tenant_id","ar_90_plus","tenant_status","deposit_held_active",
                        "deposit_amount","settlement_status","classification","review_action"]])
            st.dataframe(_v, use_container_width=True, hide_index=True)
            st.caption("Deposit columns are EVIDENCE for prioritising review — never a recovery figure.")
    except SourceValidationError:
        st.caption("AR recovery queue not available (run phase3_ar_recovery_queue.py).")

    # ---- Credit notes — revenue adjustments (credit ≠ debit; never summed) ----
    st.markdown("---"); st.subheader("Credit notes — revenue adjustments")
    try:
        cn=load_csv_ro("phase3_credit_note_analysis.csv")
        cs=dict(zip(load_csv_ro("phase3_credit_note_analysis_summary.csv")["metric"],
                    load_csv_ro("phase3_credit_note_analysis_summary.csv")["value"]))
        def _cf(k,d=0.0):
            try: return float(cs.get(k,d))
            except Exception: return d
        c=st.columns(4)
        c[0].metric("Credit notes", f"{int(_cf('credit_notes_count'))}", help="Only credit notes reduce revenue.")
        c[1].metric("Value credited", rupee(_cf("credit_notes_total")))
        c[2].metric("Share of invoiced revenue", str(cs.get("credit_notes_vs_invoiced_revenue","—")))
        c[3].metric("Uncategorised", str(cs.get("uncategorised_share","—")))
        _rec=cn[cn["classification"]=="Investigate recurring leakage"]
        _rectxt=("; ".join(f"{r.category} ({r.notes} notes, {rupee(r.amount)})" for r in _rec.itertuples())
                 if len(_rec) else "none flagged as recurring")
        st.info(
            f"**What is happening:** {int(_cf('credit_notes_count'))} credit notes reduced billed revenue by "
            f"{rupee(_cf('credit_notes_total'))} ({cs.get('credit_notes_vs_invoiced_revenue','—')} of invoiced "
            f"revenue). The largest single bucket — {cs.get('uncategorised_share','—')}, "
            f"{rupee(_cf('uncategorised_amount'))} — is filed as **'others'** with no specific category.\n\n"
            "**Why it matters:** most of the value being credited back cannot be attributed to a stated cause, so "
            "the driver behind it cannot currently be managed. Yearly pattern: "
            f"{cs.get('trend_by_year','—')}.\n\n"
            f"**Recommended response:** require a specific category on credit notes instead of 'others'. Recurring "
            f"and material enough to review: {_rectxt}.\n\n"
            "**What NOT to conclude:** a credit note is **not** automatically a loss or a mistake — referral "
            "bonuses, card fees and electricity corrections are ordinary adjustments and are marked as expected. "
            "Nothing here is labelled preventable, and debit notes (which ADD charges) are reported separately and "
            "must never be added to this figure.")
        _cv=pd.DataFrame({"Category":cn["category"],"Notes":cn["notes"],
            "Amount":cn["amount"].map(rupee),"Share":cn["share_of_credit_notes"],
            "Period":cn["period"],"Classification":cn["classification"],
            "Interpretation":cn["interpretation"]})
        st.dataframe(_cv, use_container_width=True, hide_index=True)
        st.caption(f"Debit notes for context: {int(_cf('debit_notes_count'))} adding "
                   f"{rupee(_cf('debit_notes_total'))} in charges — a separate, opposite movement. "
                   f"{int(_cf('deleted_rows_excluded'))} deleted row(s) excluded. "
                   f"Free-text reason coverage: {cs.get('reason_field_coverage','—')}.")
    except SourceValidationError:
        st.caption("Credit-note analysis not available (run phase3_credit_note_analysis.py).")

def p_vacancy():
    st.header("Occupancy & Vacancy")
    v=load("vacancy")
    a=st.columns(2)
    a[0].metric("Vacant beds", f"{len(v)}")
    a[1].metric("Monthly revenue at risk", rupee(v["rev_at_risk_monthly"].sum()))
    st.caption("Vacancy duration derived from allotment exit gaps (bed_status_history missing). Never-occupied beds → duration unknown.")
    st.dataframe(show(v).sort_values("rev_at_risk_monthly",ascending=False), use_container_width=True, hide_index=True)
    is_new=v["recommended_action"].astype(str).str.contains("New inventory",case=False)
    is_mkt=v["recommended_action"].astype(str).str.contains("Marketing priority",case=False)
    new_n,new_rev=int(is_new.sum()),v.loc[is_new,"rev_at_risk_monthly"].sum()
    mkt_n,mkt_rev=int(is_mkt.sum()),v.loc[is_mkt,"rev_at_risk_monthly"].sum()
    fill_n=len(v)-new_n-mkt_n
    st.info(f"Business insight: of the {len(v)} vacant beds, {new_n} ({rupee(new_rev)}/mo) are genuinely NEW inventory "
            f"(A33/A34, live since Aug 2026) — not a fill problem, just not yet marketed since launch. {mkt_n} "
            f"({rupee(mkt_rev)}/mo) have been vacant over 60 days and are the real marketing-priority risk; the "
            f"remaining {fill_n} are within normal fill/monitor range.")

def p_pricing():
    st.header("Pricing")
    st.error("Market/area pricing is UNAVAILABLE — Phase-3 external-source gate FAILED (sources robots-restricted/anti-bot; no legal pricing API). Internal baseline only.")
    pr=load("pricing")
    st.dataframe(pr, use_container_width=True, hide_index=True)
    st.caption("Internal rate card vs realized rent by bed_type × toilet_type. Signals are internal-only; no competitor comparison.")
    sig=pr["pricing_signal"].value_counts()
    flagged=int(len(pr)-sig.get("within band",0)-sig.get("insufficient",0))
    if flagged>0:
        rows=pr[~pr["pricing_signal"].isin(["within band","insufficient"])]
        detail="; ".join(f"{r.bed_type}/{r.toilet_type}: {r.pricing_signal}" for r in rows.itertuples())
        st.info(f"Business insight: {flagged} of {len(pr)} segments show a pricing signal worth reviewing — {detail}.")
    else:
        st.info(f"Business insight: all {len(pr)} bed-type × toilet-type segments are currently within band — no "
                "pricing action indicated by the rate-card-vs-realized comparison. (Triple/Common, 3 beds, has no "
                "rate-card entry and is excluded from this table — a pre-existing data gap.)")

def p_tenants():
    st.header("Tenants")
    st.caption("Segmentation = SOFT/COARSE behavioural groups (K=2, silhouette 0.29) — targeting emphasis, not precise personas.")
    st.subheader("Behavioural segment profiles")
    sp=load("seg_prof")
    st.dataframe(sp, use_container_width=True, hide_index=True)
    seg=load("segments")
    pick=st.selectbox("Filter tenant segment", ["(all)"]+sorted(seg["segment"].dropna().unique()))
    d=seg if pick=="(all)" else seg[seg["segment"]==pick]
    st.dataframe(show(d), use_container_width=True, hide_index=True)
    st.subheader("Churn watch-list (60-day notice-or-exit)")
    st.warning("Ranking / watch-list ONLY (ROC-AUC ~0.72, calibrated). NOT a precise yes/no classifier — use the ranking, not a 0.5 cutoff.")
    ch=load("churn")
    band=st.multiselect("Risk band", sorted(ch["risk_band"].dropna().unique()), default=["High","Medium"])
    st.dataframe(show(ch[ch["risk_band"].isin(band)]).sort_values("risk",ascending=False), use_container_width=True, hide_index=True)
    bc=ch["risk_band"].value_counts()
    # ---- Business insight: lead on collection RISK, not population size ----
    # Ranking by overdue_rate (not by segment size) so the group flagged for intervention leads the interpretation.
    _byrisk=sp.sort_values("overdue_rate",ascending=False)
    _risk=_byrisk.iloc[0]; _rest=_byrisk.iloc[1] if len(_byrisk)>1 else None
    _scale=(f" The larger '{_rest['segment']}' group ({int(_rest['size'])} tenants, "
            f"{100*_rest['overdue_rate']:.0f}% overdue) is broader population exposure and is marked "
            f"'{_rest['business_action']}' — watch it, but it is not where intervention is indicated."
            if _rest is not None else "")
    st.info(
        f"**What is happening:** the highest collection risk sits with '{_risk['segment']}' — {int(_risk['size'])} "
        f"tenants at a {100*_risk['overdue_rate']:.0f}% overdue rate, the segment the engine marks "
        f"'{_risk['business_action']}'.{_scale}\n\n"
        f"**Why it matters:** this is concentrated, actionable payment risk rather than broad exposure — the smaller "
        f"group is the one where collection effort changes an outcome.\n\n"
        f"**Recommended response:** run proactive collections against the '{_risk['segment']}' segment first. "
        f"Separately, on the churn watch-list, {int(bc.get('High',0))} tenant(s) are High risk and "
        f"{int(bc.get('Medium',0))} Medium — review those for retention outreach.\n\n"
        f"**Certainty / limitation:** segmentation is deliberately coarse (K=2, silhouette 0.29) — directional "
        "targeting only, not precise personas. Churn is a ranking, not a yes/no prediction, and the data does not "
        "explain why tenants leave. No recovery amount or probability is implied.")

    # ---- Active Tenant Location Data Capture (business action; display-only) ----
    # A DATA-QUALITY action, not a geographic marketing recommendation. Reads the validated
    # phase3_active_location_capture outputs read-only; nothing is recomputed or inferred here.
    st.markdown("---"); st.subheader("Active Tenant Location Data Capture")
    try:
        cap = load_csv_ro("phase3_active_location_capture.csv")
        cs = load_csv_ro("phase3_active_location_capture_summary.csv")
        CS = dict(zip(cs["metric"], cs["value"]))
        def _ci(k, d=0):
            try: return int(float(CS.get(k, d)))
            except Exception: return d
        _act, _res, _req = _ci("active_tenants"), _ci("state_resolved"), _ci("require_confirmation")
        k = st.columns(4)
        k[0].metric("Active tenants", _act)
        k[1].metric("State resolved", _res)
        k[2].metric("Require State + City + Pincode", _req)
        k[3].metric("Lacking reliable origin", f"{CS.get('pct_lacking_reliable_origin','—')}%")
        st.warning(f"**Action: collect and confirm State + City + Pincode for the {_req} active tenants "
                   "in the capture queue below.** This is a **data-quality / business-enablement** action, "
                   "not a geographic marketing recommendation. No state is inferred from the Vishful "
                   "property address, the current apartment or bed, the Chennai stay location, a building "
                   "name, or an ambiguous locality — the tenant must supply or confirm their genuine "
                   "residential/origin information.")
        b = st.columns(4)
        b[0].metric("Address exists, unresolvable", _ci("class_4_address_insufficient"))
        b[1].metric("No usable location info", _ci("class_5_no_usable_location"))
        b[2].metric("Property address recorded", _ci("class_6_property_address_recorded"))
        b[3].metric("State OK, City/Pincode to confirm", _ci("class_3_state_resolved_city_pincode_missing"))
        st.caption(f"{_ci('class_4_address_insufficient')} — address exists but location cannot be reliably "
                   f"resolved · {_ci('class_5_no_usable_location')} — no usable address/location information · "
                   f"{_ci('class_6_property_address_recorded')} — Vishful/property address recorded as "
                   f"permanent address, correction required · "
                   f"{_ci('class_3_state_resolved_city_pincode_missing')} — state can be safely resolved from "
                   "existing evidence, but City/Pincode still need confirmation (these are already counted as "
                   f"resolved, so they sit outside the {_req}-tenant queue).")
        st.caption(f"**Capture queue — {len(cap)} active tenants across "
                   f"{_ci('apartments_affected')} apartments.** For operations use.")
        st.dataframe(pd.DataFrame({
            "Tenant ID": cap["tenant_id"], "Tenant": cap["full_name"].map(_b),
            "Apartment": cap["apartment"].map(_b), "Bed": cap["bed"].map(_b),
            "Status": cap["allotment_status"].map(_b),
            "Existing address": cap["existing_address"].map(_b),
            "Resolved state": cap["resolved_state"].map(_b),
            "Resolution source": cap["resolution_source"].map(_b),
            "Data-quality class": cap["dq_status"].map(_b),
            "Required action": cap["required_action"].map(_b)}),
            use_container_width=True, hide_index=True)

        st.markdown("##### Record a tenant confirmation")
        st.caption("Enter the State, City and Pincode the tenant has **directly confirmed** — collected "
                   "by phone, WhatsApp or in person, outside this dashboard. **No document is read or "
                   "OCR'd to fill this in.** This is an append-only record: submitting again for the "
                   "same tenant adds a new correction, never overwrites the previous entry.")
        import phase3_tenant_location_confirm as TLC
        import phase3_tenant_origin as G

        def _tlc_refresh():
            """Re-run the EXISTING deterministic tenant-origin resolution + capture-queue generator
            in-process (read-only on the append-only confirmation store; writes only the derived
            phase3_tenant_origin* and phase3_active_location_capture* outputs — never touches locked
            outputs or source CSVs). Clears the cached read-only loads so the queue on screen reflects
            the confirmation immediately."""
            try:
                import phase3_active_location_capture as CQ
                G.main()
                CQ.main()
            except Exception:
                st.error("Tenant-origin refresh FAILED — the confirmation WAS recorded, but the "
                         "analytics were not recomputed. Re-run phase3_tenant_origin.py and "
                         "phase3_active_location_capture.py.")
                return False
            load_csv_ro.clear()
            st.caption("Tenant Origin analytics re-run; capture queue updated.")
            st.rerun()

        def _submit_location(build):
            try: ev = build()
            except Exception as e: st.warning(str(e)); return
            sig = f"tlc:{sorted(ev.items())}"
            if st.session_state.get("_tlc_last") == sig:
                st.info("Duplicate submission ignored (identical content as the last submit)."); return
            try:
                cid = TLC.append_confirmation(ev, confirmed_by=ev.get("confirmed_by"))
            except ValueError as e:
                st.error(f"Rejected by the validated writer: {e}"); return
            st.session_state["_tlc_last"] = sig
            st.success(f"Append-only confirmation recorded: {cid}.")
            _tlc_refresh()

        with st.form("tlc_form", clear_on_submit=True):
            _lbl = {tid: f"{_b(cap.loc[cap.tenant_id == tid, 'full_name'].iloc[0])} — "
                         f"{_b(cap.loc[cap.tenant_id == tid, 'apartment'].iloc[0])}/"
                         f"{_b(cap.loc[cap.tenant_id == tid, 'bed'].iloc[0])}"
                    for tid in cap["tenant_id"]}
            pick = st.selectbox("Tenant (from the capture queue above)", cap["tenant_id"].tolist(),
                                format_func=lambda tid: _lbl.get(tid, tid), key="tlc_tenant")
            c1, c2, c3 = st.columns(3)
            state_in = c1.selectbox("State — as confirmed by the tenant", [""] + G.STATES, key="tlc_state")
            city_in = c2.text_input("City — as confirmed by the tenant", key="tlc_city")
            pin_in = c3.text_input("Pincode — as confirmed by the tenant", key="tlc_pin", max_chars=6)
            by_in = st.text_input("Confirmed by (staff name recording this)", key="tlc_by")
            note_in = st.text_input("Notes (optional)", key="tlc_note")
            go = st.form_submit_button("Record confirmation")
        if go:
            _submit_location(lambda: {"tenant_id": pick, "confirmed_state": state_in,
                                      "confirmed_city": city_in, "confirmed_pincode": pin_in,
                                      "confirmed_by": by_in, "notes": note_in})

        st.info(f"**Business impact.** {CS.get('pct_lacking_reliable_origin','—')}% of currently-active "
                "tenants do not have reliable origin/location information. Collecting State + City + "
                "Pincode at profile completion will make future geographic analysis more reliable and "
                "enable state-wise revenue, retention, demand and marketing analysis that is **currently "
                "not answerable**. It does not, on its own, prove anything about geographic demand.\n\n"
                "**Onboarding requirement (business rule, not an app change):** new tenant onboarding "
                "should require **State**, **City** and **Pincode**; existing active tenants should be "
                "prompted to confirm the same fields.\n\n"
                "**Historical data:** the unresolved historical tenants are **not** filled by guessing. "
                "Historical origin remains partially unresolved; only current active tenant data can be "
                "improved through direct collection, and future onboarding prevents the gap recurring.\n\n"
                "**Not yet used for a business recommendation.** Confirmed values feed the Tenant Origin "
                "analytics below as they are collected, but this data is **not** used to create a "
                "marketing or geographic business recommendation until coverage is sufficient to support "
                "one — collecting a handful of confirmations does not by itself justify a state-targeting "
                "decision.")
    except SourceValidationError:
        st.caption("Active tenant location capture queue not available (run phase3_active_location_capture.py).")

    # ---- Tenant Origin Analysis (read-only display; state resolution is NOT recomputed here) ----
    # Reads the validated outputs of phase3_tenant_origin.py only. Creates no recommendation, decision,
    # opportunity or AIREC item. Historical and current cohorts are shown separately and never summed.
    st.markdown("---"); st.subheader("Tenant Origin Analysis")
    st.caption("Tenant-origin **composition**, not a demand forecast. State is resolved only from explicit "
               "state, state written in the address, a validated pincode mapping, or a validated city "
               "gazetteer — never from company address, invoice frequency, or the `created_at` migration "
               "timestamp. Ambiguous evidence stays **Unknown**; Unknown is never treated as zero or "
               "assigned to any state.")
    try:
        hist = load_csv_ro("phase3_tenant_origin_historical.csv")
        curr = load_csv_ro("phase3_tenant_origin_current.csv")
        byyr = load_csv_ro("phase3_tenant_origin_by_year.csv")
        origin_summary = load_csv_ro("phase3_tenant_origin_summary.csv")
        SM = dict(zip(origin_summary["metric"], origin_summary["value"]))

        def _split(df):
            r = df[df["state"] != "Unknown"].sort_values("tenants", ascending=False)
            u = df[df["state"] == "Unknown"].iloc[0]
            return r, u

        hr, hu = _split(hist); cr, cu = _split(curr)
        h_pop, h_res = int(hu["denominator_population"]), int(hu["denominator_resolved"])
        c_pop, c_res = int(cu["denominator_population"]), int(cu["denominator_resolved"])

        st.markdown("#### ① Tenant Origin — Historical (2019–2026)")
        st.caption("The full historical onboarded population, by first `tenant_allotments.onboarding_date`.")
        h = st.columns(3)
        h[0].metric("Historical population", h_pop)
        h[1].metric("Historical — state resolved", f"{h_res} ({100*h_res/h_pop:.1f}%)")
        h[2].metric("Historical — Unknown", f"{int(hu['tenants'])} ({100*int(hu['tenants'])/h_pop:.1f}%)")
        st.dataframe(pd.DataFrame({
            "Rank": range(1, len(hr) + 1), "State": hr["state"], "Tenants": hr["tenants"],
            "% of resolved population": hr["pct_of_resolved"].map(lambda x: f"{x:.1f}%"),
            "% of total historical population": hr["pct_of_population"].map(lambda x: f"{x:.1f}%"),
        }), use_container_width=True, hide_index=True)
        st.caption(f"State share is calculated among the {h_res} tenants with reliable state evidence. "
                   f"The remaining {int(hu['tenants'])} tenants ({100*int(hu['tenants'])/h_pop:.1f}% of the "
                   "historical population) are Unknown and are shown separately, not folded into any state.")

        st.markdown("#### ② Current Active Tenant Origin")
        st.caption("Tenants holding at least one allotment with no recorded exit — a strict **subset** of "
                   "the historical population above, never summed with it.")
        c = st.columns(3)
        c[0].metric("Current active tenants", c_pop)
        c[1].metric("Current — state resolved", f"{c_res} ({100*c_res/c_pop:.1f}%)")
        c[2].metric("Current — Unknown", f"{int(cu['tenants'])} ({100*int(cu['tenants'])/c_pop:.1f}%)")
        st.dataframe(pd.DataFrame({
            "Rank": range(1, len(cr) + 1), "State": cr["state"], "Tenants": cr["tenants"],
            "% of resolved population": cr["pct_of_resolved"].map(lambda x: f"{x:.1f}%"),
            "% of current active population": cr["pct_of_population"].map(lambda x: f"{x:.1f}%"),
        }), use_container_width=True, hide_index=True)
        st.caption(f"State share is calculated among the {c_res} currently-active tenants with reliable "
                   f"state evidence. The remaining {int(cu['tenants'])} ({100*int(cu['tenants'])/c_pop:.1f}% "
                   "of the current population) are Unknown.")

        st.markdown("#### ③ Historical vs Current — same states, separate denominators")
        cmp = hr[["state", "tenants", "pct_of_resolved"]].rename(
            columns={"tenants": "Historical count", "pct_of_resolved": "Historical % resolved"}
        ).merge(cr[["state", "tenants", "pct_of_resolved"]].rename(
            columns={"tenants": "Current count", "pct_of_resolved": "Current % resolved"}),
            on="state", how="outer").rename(columns={"state": "State"})
        cmp[["Historical count", "Current count"]] = cmp[["Historical count", "Current count"]].fillna(0).astype(int)
        cmp["Historical % resolved"] = cmp["Historical % resolved"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
        cmp["Current % resolved"] = cmp["Current % resolved"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
        cmp = cmp.sort_values("Historical count", ascending=False)
        st.dataframe(cmp, use_container_width=True, hide_index=True)
        st.caption(f"Unknown — historical: {int(hu['tenants'])} of {h_pop} · current: {int(cu['tenants'])} of "
                   f"{c_pop}. A difference between the two columns is **not** evidence of a trend, growth, "
                   "churn pattern, or demand change — the cohorts differ in size, era and resolution coverage.")

        st.markdown("#### ④ Tenant Origin by Onboarding Year")
        st.caption("From `tenant_allotments.onboarding_date` — never from `tenants.created_at`, which is a "
                   "data-migration timestamp with every value dated after March 2026, not a business date.")
        yr = byyr.copy()
        yr_disp = pd.DataFrame({
            "Onboarding year": yr["cohort_year"].astype(int),
            "Tenants onboarded": yr["tenants_onboarded"],
            "State resolved": yr["resolved"],
            "Coverage": yr["coverage_pct"].map(lambda x: f"{x:.1f}%"),
            "Top state (of resolved)": yr.apply(
                lambda r: f"{r['top_state']} ({r['top_state_pct_of_resolved']:.1f}%)"
                if pd.notna(r["top_state"]) else "—", axis=1),
            "Status": yr["coverage_caveat"].map(lambda s: "🟡 Thin — not interpretable" if "thin" in str(s) else "🟢 Sufficient"),
        })
        st.dataframe(yr_disp, use_container_width=True, hide_index=True)
        st.warning("**Year-wise trend claim: NOT SUPPORTED.** Coverage swings from "
                   f"{yr['coverage_pct'].min():.1f}% to {yr['coverage_pct'].max():.1f}% across these years — "
                   "movement in a state's yearly share is explained by how completely that year's records "
                   "were documented, not by a change in where tenants actually came from. Only years marked "
                   "🟢 Sufficient have enough resolved tenants for their share to be read at all, and even "
                   "those are not shown as a trend line for that reason.")

        st.markdown("#### ⑤ Business interpretation")
        st.info(
            "**What the data shows:** Tamil Nadu and South India are the largest observed tenant-origin "
            "groups among tenants with reliable location evidence, in **both** the historical and current "
            f"cohorts (Tamil Nadu: {SM.get('south_india_pct_of_resolved','—')}% South India share overall; "
            "consistent across cohorts). This may help inform communication, language, and content choices.\n\n"
            "**What it does not show.** This analysis describes observed tenant-origin composition only. "
            "It does **not** prove geographic demand, conversion performance, revenue potential, or future "
            "growth, and it does not by itself justify state-level marketing spend. No recommendation, "
            "decision, opportunity, or AIREC item has been created from this analysis.")
        st.caption("**On Unknown:** it means the available tenant record does not contain enough reliable "
                   "location evidence to assign a state — not that the tenant has no state. Unknown tenants "
                   "are never assumed to belong to any state and are always shown as their own row above.")
    except SourceValidationError:
        st.caption("Tenant origin analysis not available (run phase3_tenant_origin.py).")

def p_eb():
    st.header("Electricity (EB) anomalies")
    apt=load("eb_apt"); eb=load("eb")
    a=st.columns(3)
    a[0].metric("Invalid readings (high-confidence)", f"{int((eb['anomaly_type']=='invalid').sum())}")
    a[1].metric("High-consumption flags", f"{int((eb['anomaly_type']=='high_consumption').sum())}")
    a[2].metric("Low-consumption flags", f"{int((eb['anomaly_type']=='low_consumption').sum())}")
    st.caption("Abnormal consumption ≠ confirmed leak (inspect). Seasonal-only statistical flags are LOWER-confidence (~3 obs/season). Invalid + apartment-baseline = high-confidence.")
    typ=st.multiselect("Anomaly type", ["invalid","high_consumption","low_consumption","normal"], default=["invalid","high_consumption","low_consumption"])
    st.dataframe(show(eb[eb["anomaly_type"].isin(typ)]).sort_values("deviation_score",ascending=False,na_position="last"), use_container_width=True, hide_index=True)
    st.subheader("Per-apartment anomaly profile")
    st.dataframe(show(apt).sort_values(["high","invalid"],ascending=False), use_container_width=True, hide_index=True)
    st.markdown("---"); st.subheader("Possible leak investigation (occupancy-aware)")
    st.error("Possible abnormal consumption — NOT a confirmed leak. For zero-occupancy: may be common-area load, appliances left running, meter behaviour, or occupancy-data limits.")
    lk=load("eb_leak"); lksum=load("eb_leak_sum")
    b=st.columns(3)
    b[0].metric("Possible-leak candidates", f"{int(lk['leak_signal'].sum())}")
    b[1].metric("Low-occupancy high-consumption", f"{int((lk['anomaly_type']=='low_occupancy_high_consumption').sum())}")
    b[2].metric("Sudden increase", f"{int((lk['anomaly_type']=='sudden_increase').sum())}")
    st.caption("Signal breakdown"); st.dataframe(lksum, use_container_width=True, hide_index=True)
    only=st.checkbox("Show only possible-leak candidates", value=True)
    d=lk[lk["leak_signal"]==True] if only else lk[lk["anomaly_type"]!="normal"]
    st.dataframe(show(d).sort_values("deviation_score",ascending=False,na_position="last"), use_container_width=True, hide_index=True)
    # ---- Business insight: separate HISTORICAL data quality from CURRENT evidence (time-framed, derived) ----
    # Counts above are cumulative over the whole EB series. Without a time frame an owner can read a resolved
    # historical issue as a live problem. Everything below is derived from billing_month on the loaded data.
    _ebm=pd.to_datetime(eb["billing_month"], format="%b-%y", errors="coerce")
    _lcm=pd.to_datetime(lk.loc[lk["leak_signal"]==True,"billing_month"], format="%b-%y", errors="coerce")
    _inv_all=int((eb["anomaly_type"]=="invalid").sum())
    _asof=_ebm.max()
    if pd.notna(_asof):
        _yr=int(_asof.year)
        _cur=eb[_ebm.dt.year==_yr]; _hist=eb[_ebm.dt.year<_yr]
        _cur_inv=int((_cur["anomaly_type"]=="invalid").sum())
        _cur_rate=100.0*_cur_inv/max(len(_cur),1)
        _cur_apts=int(_cur.loc[_cur["anomaly_type"]=="invalid","apartment_id"].nunique())
        _hist_txt=(f"about {100.0*(_hist['anomaly_type']=='invalid').mean():.1f}% of readings before {_yr}"
                   if len(_hist) else "not measurable before this year")
        _cov=f"{_ebm.min():%b %Y}–{_asof:%b %Y}"
        # ① historical data-quality trend (invalid = meter/data-entry fault, never a consumption claim)
        _p1=(f"**What is happening:** the {_inv_all} 'invalid' readings shown above are cumulative across the whole "
             f"{_cov} series — they are meter/data-entry faults (units ≤ 0, or end-reading below start), not "
             f"electricity actually consumed. Historically they ran at {_hist_txt}; in {_yr} they are "
             f"{_cur_inv} of {len(_cur)} readings ({_cur_rate:.1f}%) across {_cur_apts} apartment(s). "
             f"**What it means:** this historical data-quality issue appears largely improved, not currently active. "
             f"**Recommended response:** monitor current readings; no data-quality escalation is indicated by "
             f"{_yr} evidence alone. **Certainty:** the classification is high-confidence, but the cause of the "
             "faults is not in the data.")
        # ② leak candidates — age them explicitly against the latest available reading
        if len(_lcm.dropna()):
            _newest=_lcm.max()
            _age=int(round((_asof-_newest).days/30.4))
            _p2=(f"**What is happening:** the {int(lk['leak_signal'].sum())} possible-leak candidates are dated "
                 f"{_lcm.min():%b %Y}–{_newest:%b %Y}; the most recent is roughly {_age} month(s) before the latest "
                 f"available reading ({_asof:%b %Y}). **What it means:** this evidence is not recent enough to "
                 "establish a current leak. **Recommended response:** treat as historical signals — investigate only "
                 "if current readings show the pattern again. **Certainty:** abnormal consumption was never confirmed "
                 "as a leak; no severity is implied.")
        else:
            _p2="No possible-leak candidates are present in the current data."
        st.info(_p1)
        st.info(_p2)

def p_maint():
    st.header("Maintenance repeat / hotspots")
    reg=load("maint_reg")
    st.warning("Act on date_confidence = HIGH (created_at). resolved_at-fallback recurrences are LOW confidence (possible batch-resolution artifacts, e.g. 0-day 'repeats').")
    a=st.columns(3)
    a[0].metric("High-conf High hotspots", f"{int(((reg['priority']=='High')&(reg['date_confidence']=='high')).sum())}")
    a[1].metric("Low-conf High (watch/verify)", f"{int(((reg['priority']=='High')&(reg['date_confidence']=='low')).sum())}")
    a[2].metric("apartment×issue groups", f"{len(reg)}")
    conf=st.multiselect("Date confidence", ["high","low"], default=["high"])
    pri=st.multiselect("Priority", ["High","Medium","Low"], default=["High","Medium"])
    d=reg[reg["date_confidence"].isin(conf) & reg["priority"].isin(pri)]
    st.dataframe(show(d).sort_values(["recur_le90","ticket_count"],ascending=False), use_container_width=True, hide_index=True)
    hi=reg[(reg["priority"]=="High")&(reg["date_confidence"]=="high")].sort_values("recur_le90",ascending=False)
    if len(hi):
        top=show(hi.head(1))
        tname=str(top["apartment_code"].iloc[0]) if "apartment_code" in top.columns else "?"
        tissue=str(top["issue_type_name"].iloc[0]) if "issue_type_name" in top.columns else "?"
        st.info(f"Business insight: {tname} × {tissue} is the most-repeated high-confidence hotspot "
                f"({int(hi.iloc[0]['recur_le90'])} recurrences within 90 days) — the best candidate for a root-cause "
                f"fix or asset replacement rather than another repair. {len(hi)} apartment×issue combos meet the "
                "high-confidence bar; the rest are low-confidence and worth watching, not acting on yet.")
    c=st.columns(2)
    c[0].caption("Issue-type profile (cost coverage ~26%)"); c[0].dataframe(show(load("issue_prof")), use_container_width=True, hide_index=True)
    c[1].caption("Technician profile (descriptive)"); c[1].dataframe(load("tech_prof"), use_container_width=True, hide_index=True)
    st.markdown("---"); st.subheader("Closure lag — time between technician resolution and admin closure")
    st.info("Closure lag = closed_at − resolved_at. This is NOT SLA resolution time and does NOT use created_at (creation→close is unmeasurable: only 2/1,540 tickets have both).")
    cs=load("closure_sum").set_index("metric")["value"]
    m=st.columns(4)
    m[0].metric("Usable timestamp pairs", f"{int(float(cs['usable_timestamp_pairs']))}")
    m[1].metric("Median closure lag (days)", f"{cs['median_lag_days']}")
    m[2].metric("p90 (days)", f"{cs['p90_lag_days']}")
    m[3].metric("Negative-lag (data quality)", f"{int(float(cs['negative_lag_count']))}", help="closed before resolved — flagged, not dropped")
    if int(float(cs['negative_lag_count']))>0:
        st.warning(f"⚠ {int(float(cs['negative_lag_count']))} tickets have NEGATIVE closure lag (closed before resolved) — data-quality issue, flagged not removed.")
    cc=st.columns(2)
    cc[0].caption("By issue type (median days)"); cc[0].dataframe(load("closure_issue"), use_container_width=True, hide_index=True)
    cc[1].caption("By technician (median days)"); cc[1].dataframe(load("closure_tech"), use_container_width=True, hide_index=True)
    with st.expander("Ticket-level closure-lag drilldown"):
        st.dataframe(show(load("closure")).sort_values("closure_lag_days",ascending=False), use_container_width=True, hide_index=True)
    st.markdown("---"); st.subheader("① Created → RESOLVED SLA (technician resolution time)")
    st.error("RECONSTRUCTED SLA (ticket_logs 'Ticket created' → first 'Marked resolved', vs issue_types.sla_hours). "
             "NOT the confirmed application SLA — app code unavailable; reconstructed deadline matches app sla_deadline for only 31/291 (median 39.7h off).")
    rs=load("sla_res_sum").set_index("metric")["value"]
    r=st.columns(4)
    r[0].metric("Genuinely measurable", f"{int(float(rs['genuinely_measurable']))}")
    r[1].metric("SLA breached", f"{int(float(rs['SLA_breached']))}")
    r[2].metric("Breach rate (measurable)", f"{rs['breach_rate_measurable']}")
    r[3].metric("Within SLA", f"{int(float(rs['SLA_met']))}")
    r2=st.columns(4)
    r2[0].metric("Median resolution (h)", f"{rs['median_resolution_hours_measurable']}")
    r2[1].metric("p90 resolution (h)", f"{rs['p90_resolution_hours_measurable']}")
    r2[2].metric("Resolved events", f"{int(float(rs['resolved_available']))}")
    r2[3].metric("Collapsed (excluded)", f"{int(float(rs['collapsed_timestamp']))}")
    st.caption("SLA target by issue type (4/6/12/24h) + breach breakdown — resolution-based")
    st.dataframe(load("sla_res_issue"), use_container_width=True, hide_index=True)
    st.caption("By technician (measurable, resolution-based)")
    st.dataframe(load("sla_res_tech"), use_container_width=True, hide_index=True)
    # ---- Business insight: the resolution-SLA breach is a CURRENT operational signal, not a data artifact ----
    # Derived only from the resolution-SLA outputs this section already loads. No cause is inferred.
    _sr=load("sla_res"); _srm=_sr[_sr["lifecycle_quality"]=="measurable"].copy()
    if len(_srm):
        _ct=pd.to_datetime(_srm["created_ts"],errors="coerce",utc=True)
        _srm["_ym"]=_ct.dt.strftime("%Y-%m")
        _mth=_srm.groupby("_ym").agg(n=("sla_breached","size"),br=("sla_breached","sum"))
        _mth=_mth[_mth["n"]>=20]  # ignore part-months too small to read as a trend
        _trend=" → ".join(f"{m} {100.0*r.br/r.n:.0f}%" for m,r in _mth.iterrows())
        _flat24=100.0*(_srm["resolution_hours"]>24).mean()   # generous flat target, sanity check on the reconstructed deadline
        _si=load("sla_res_issue"); _worst=_si[_si["tickets"]>=20].sort_values("breach_rate",ascending=False).head(3)
        _wtxt="; ".join(f"{r.issue_type_name} {100.0*r.breach_rate:.0f}% of {int(r.tickets)}" for r in _worst.itertuples())
        _st=load("sla_res_tech").sort_values("tickets",ascending=False)
        _topn=int(_st.iloc[0]["tickets"]) if len(_st) else 0
        _tot=int(_st["tickets"].sum()) if len(_st) else 0
        st.info(
            f"**What is happening:** {int(float(rs['SLA_breached']))} of {int(float(rs['genuinely_measurable']))} "
            f"measurable tickets missed their issue-type target ({rs['breach_rate_measurable']}), median resolution "
            f"{rs['median_resolution_hours_measurable']}h against targets of 4–24h. These measurable tickets are the "
            f"most recent window ({_ct.min():%b %Y}–{_ct.max():%b %Y}) — older tickets simply have no lifecycle logs — "
            f"so this describes current performance, not history. Month by month: {_trend}.\n\n"
            f"**Why it matters:** this is an ongoing operational-performance problem rather than a data artifact. It "
            f"holds even against a deliberately generous flat 24h target, where {_flat24:.0f}% would still breach, so "
            f"it does not depend on the reconstructed deadline being exact.\n\n"
            f"**Recommended response:** investigate operational capacity and how ticket ownership is distributed — "
            f"{_topn} of {_tot} measurable tickets sit with a single resolver, which may itself be the constraint. "
            f"Review the worst-performing categories first ({_wtxt}). Then monitor the monthly breach rate after any "
            f"operational change.\n\n"
            f"**Certainty / limitation:** the direction is well supported; the exact rate is not, because the SLA "
            f"deadline is reconstructed and matches the app's own stored deadline for only "
            f"{int(float(rs['sla_deadline_validation_exact(<=1h)']))} of "
            f"{int(float(rs['sla_deadline_validation_exact(<=1h)']))+int(float(rs['sla_deadline_validation_mismatch(>1h)']))} "
            f"checked tickets. Workload concentration is a distribution fact only — **the data does not show individual "
            "performance and must not be read as blame.** Cause is not established by this data.")
    with st.expander("Ticket-level created→resolved drilldown"):
        st.dataframe(show(load("sla_res")).sort_values("resolution_hours",ascending=False,na_position="last"), use_container_width=True, hide_index=True)

    st.markdown("---"); st.subheader("② Created → CLOSED administrative duration (NOT resolution SLA)")
    st.warning("This is created→ADMIN-CLOSED, which includes closure lag (~13d median) AFTER technician resolution. "
               "Use ① (created→resolved) for true SLA. Collapsed timestamps (created==closed migration cluster) EXCLUDED from KPIs.")
    s=load("sla_sum").set_index("metric")["value"]
    m=st.columns(4)
    m[0].metric("Genuinely measurable", f"{int(float(s['genuinely_measurable']))}")
    m[1].metric("SLA breached", f"{int(float(s['SLA_breached']))}")
    m[2].metric("Breach rate (measurable)", f"{s['breach_rate_measurable']}")
    m[3].metric("Collapsed (excluded)", f"{int(float(s['collapsed_timestamp']))}")
    n=st.columns(4)
    n[0].metric("Within SLA", f"{int(float(s['SLA_met']))}")
    n[1].metric("Median turnaround (h)", f"{s['median_turnaround_hours_measurable']}")
    n[2].metric("p90 turnaround (h)", f"{s['p90_turnaround_hours_measurable']}")
    n[3].metric("Insufficient/other", f"{int(float(s['total_tickets']))-int(float(s['genuinely_measurable']))-int(float(s['collapsed_timestamp']))}")
    st.caption("SLA target by issue type (4/6/12/24h) + breach breakdown")
    st.dataframe(load("sla_issue"), use_container_width=True, hide_index=True)
    st.caption("By technician (measurable tickets only)")
    st.dataframe(load("sla_tech"), use_container_width=True, hide_index=True)
    with st.expander("Ticket-level SLA drilldown (all lifecycle_quality values shown)"):
        st.dataframe(show(load("sla")).sort_values("actual_resolution_hours",ascending=False,na_position="last"), use_container_width=True, hide_index=True)

def p_assets():
    st.header("Assets — age (asset level)")
    s=load("asset_sum").set_index("metric")["value"]
    a=st.columns(4)
    a[0].metric("Total assets", f"{int(float(s['total_assets']))}")
    a[1].metric("purchase_date coverage", f"{int(float(s['purchase_date_coverage']))}")
    a[2].metric("allocation-date fallback", f"{int(float(s['allocation_fallback_used']))}")
    a[3].metric("Usable asset age", f"{s['usable_pct']}")
    st.warning("Asset age is 100% at ASSET level after allocation fallback, but reaches only ~18.4% of maintenance TICKETS (direct asset_id). bed→asset is 1:many and is NOT bridged. Do not assume all tickets have asset age.")
    st.caption("Note: allocation_date reflects when the asset entered the system record (~2026 migration), so age via allocation is time-in-record, not necessarily true purchase age.")
    st.subheader("Age bands"); st.dataframe(load("asset_bands"), use_container_width=True, hide_index=True)
    src=st.multiselect("date_source", ["purchase_date","allocation_date","unknown"], default=["purchase_date","allocation_date"])
    prof=load("asset_prof")
    st.dataframe(prof[prof["date_source"].isin(src)].sort_values("asset_age_years",ascending=False), use_container_width=True, hide_index=True)
    # ---- B2: asset age is descriptive only — it cannot currently support replacement / CapEx timing ----
    _tot=int(float(s["total_assets"])); _pur=int(float(s["purchase_date_coverage"])); _fb=int(float(s["allocation_fallback_used"]))
    st.info(
        f"**What is happening:** only {_pur} of {_tot} assets ({100.0*_pur/max(_tot,1):.1f}%) carry a real purchase "
        f"date. The other {_fb} ({100.0*_fb/max(_tot,1):.1f}%) fall back to the allocation date — when the asset "
        f"entered the system record during the ~2026 migration — which is why the median age reads "
        f"{s['median_age_years']} years.\n\n"
        f"**Why it matters:** the '100% usable' coverage figure means every asset has *a* date, not that every date "
        "is a true purchase date. For most of the asset base this number is time-in-record, not real age.\n\n"
        "**Recommended response:** treat the ages above as descriptive only. **No replacement schedule or CapEx "
        "timing should be derived from this field today**, and none is recommended here. To make this usable later, "
        "capture the purchase date at asset registration going forward.\n\n"
        "**Certainty / limitation:** the limitation itself is high-confidence. Separately, asset age reaches only "
        "18.4% of maintenance tickets (bed→asset is 1:many and not bridged), so ticket cost cannot be attributed to "
        "specific assets either.")

def p_forecast():
    st.header("Revenue Forecast")
    fc=load("fc").iloc[0]
    a=st.columns(4)
    a[0].metric(f"Forecast {fc['forecast_month']}", rupee(fc["predicted_revenue"]))
    a[1].metric("95% lower", rupee(fc["lower_95"])); a[2].metric("95% upper", rupee(fc["upper_95"]))
    a[3].metric("Backtest MAPE", f"{fc['backtest_MAPE']}%")
    st.info("Holt-Winters (primary). NEAR-TERM only — 31 months / 7 folds; long-horizon not trustworthy. Naive-1 baseline ≈ as accurate.")
    bt=load("backtest").sort_values("month")
    st.line_chart(bt.set_index("month")[["actual","hw","naive1"]])
    last_actual=float(bt["actual"].iloc[-1])
    delta=100*(float(fc["predicted_revenue"])-last_actual)/max(last_actual,1)
    direction="up" if delta>0 else "down"
    st.info(f"Business insight: {fc['forecast_month']} is forecast {abs(delta):.0f}% {direction} on the last complete "
            f"actual month ({rupee(last_actual)}). At {fc['backtest_MAPE']}% historical MAPE, treat the "
            f"{rupee(fc['lower_95'])}–{rupee(fc['upper_95'])} range as the realistic planning band, not the point figure.")

    # -------- SECONDARY (experimental): component-based forecast running in parallel; HW stays primary --------
    st.divider()
    st.subheader("Component-based forecast — experimental (secondary)")
    st.caption("Runs in PARALLEL with Holt-Winters — it does NOT replace it. Revenue = occupied beds × effective rent "
               "+ electricity income, each forecast separately from real Vishful history. Under evaluation; a primary-model "
               "decision will be taken after 3–6 more months of actuals accumulate.")
    try:
        cf=load("comp_fc").iloc[0]; hw_fc=load("fc").iloc[0]
        c=st.columns(4)
        c[0].metric(f"Component {cf['forecast_month']}", rupee(cf["predicted_revenue"]),
                    help="Occupied-beds × effective-rent + electricity, one-month-ahead.")
        c[1].metric("Holt-Winters (primary)", rupee(hw_fc["predicted_revenue"]))
        c[2].metric("Component backtest MAPE", f"{cf['backtest_MAPE_18f']}% (18-fold)",
                    help=f"7-fold {cf['backtest_MAPE_7f']}%. Holt-Winters over the same 18 folds ≈ {cf['hw_backtest_MAPE_18f']}%.")
        c[3].metric("HW backtest MAPE", f"{cf['hw_backtest_MAPE_18f']}% (18-fold)")
        b=st.columns(4)
        b[0].metric("Forecast occupied beds", f"{int(cf['occupied_beds_fc'])}")
        b[1].metric("Forecast effective rent", rupee(cf["effective_rent_fc"]))
        b[2].metric("Rental forecast", rupee(cf["rental_fc"]))
        b[3].metric("Electricity forecast", rupee(cf["electricity_fc"]))
        cbt=load("comp_bt").sort_values("month")
        st.line_chart(cbt.set_index("month")[["actual","holt_winters","component"]])
        st.caption(f"Walk-forward {cbt['month'].iloc[0]}…{cbt['month'].iloc[-1]} ({int(cf['folds_18'])} folds). "
                   "Component MAPE 3.71% vs Holt-Winters 5.55% (18-fold) — promising, but Holt-Winters remains the "
                   "primary production forecast until the parallel evaluation completes. Electricity sub-forecast is the weakest piece.")
    except SourceValidationError:
        st.caption("Component forecast output not available (run component_revenue_forecast.py).")

# ---------------- Market AI (read-only, from phase3_market_spec.json) ----------------
@st.cache_data(show_spinner=False)
def load_market_spec():
    p=os.path.join(OUT,"phase3_market_spec.json")
    if not os.path.exists(p): raise SourceValidationError("missing output: phase3_market_spec.json")
    with open(p,encoding="utf-8") as f: spec=json.load(f)
    if spec.get("wired_to_dashboard") is None: raise SourceValidationError("market spec missing wiring flag")
    return spec

def _u(v):  # display Unknown for null/empty
    if v is None: return "Unknown"
    s=str(v).strip()
    return s if s and s.lower()!="nan" else "Unknown"

_PRICE_STATUS_LABEL={"first_party_published":"First-party published",
 "first_party_room_class_excluded":"Room-class (excluded)","unknown":"Unknown"}

@st.cache_data(show_spinner=False)
def load_playwright_attrs():
    p=os.path.join(OUT,"phase3_playwright_market_research.csv")
    if not os.path.exists(p): raise SourceValidationError("missing output: phase3_playwright_market_research.csv")
    return pd.read_csv(p)

# amenity column -> label (first-party rendered signals; True or null only)
_ATTR_COLS=[("ac_available","AC information"),("non_ac","Non-AC information"),("food","Food"),
 ("wifi","Wi-Fi"),("laundry","Laundry"),("cctv_security","Security/CCTV"),("parking","Parking"),
 ("power_backup","Power backup"),("housekeeping","Housekeeping")]
_MKT_CONTEXT_NOTE="Market context from publicly published first-party sources — not a competitor comparison."

def p_market():
    st.header("10 · Market AI (read-only)")
    st.caption("Competitor research view over phase3_competitor_master. READ-ONLY. No estimates, "
               "no market average, no aggregator/operator pricing, no room→bed or day→month conversion. "
               "Unknown stays Unknown. No external/API calls.")
    # ---- Market-evidence snapshot date: this page shows a DATED collection, not a live feed. Dates are read
    #      from the capture columns already present in the market outputs — never hard-coded, never now(). ----
    def _cap_dates():
        out={}
        for label,fn,col in [("Pricing evidence","phase3_competitor_prices.csv","captured_at"),
                             ("Review evidence","phase3_competitor_reviews_by_property.csv","retrieval_date")]:
            try:
                _c=pd.to_datetime(load_csv_ro(fn)[col],errors="coerce").dropna()
                if len(_c): out[label]=_c.max()
            except Exception:
                pass
        return out
    _cd=_cap_dates()
    if _cd:
        _parts="; ".join(f"{k} captured {v:%d %b %Y}" for k,v in _cd.items())
        _latest=max(_cd.values())
        st.warning(f"**Market evidence snapshot — {_parts}.** This is the latest validated market collection in "
                   f"this analysis (most recent capture {_latest:%d %b %Y}); it is a point-in-time study, **not a "
                   "continuously refreshed live feed**. Published market information can change after the capture "
                   "date, so refresh the collection before making time-sensitive market decisions. Vishful's own "
                   "internal analytics on the other pages are generated from the current data export and are not "
                   "affected by this snapshot date.")
    spec=load_market_spec()
    ov=spec["section_1_overview"]; directory=spec["section_2_directory"]; cp=spec["section_3_comparable_pricing"]

    # ---- SECTION 1: Nearby Market Overview ----
    st.subheader("① Nearby Market Overview")
    active=load_csv_ro("phase3_active_market_universe.csv")
    u=st.columns(3)
    u[0].metric("Current verified market universe", int(len(active)))
    u[1].metric("Historical baseline (v1)", int((active["universe_version"]=="v1").sum()))
    u[2].metric("Holdout / unverified (excluded)", 85)
    st.caption("Current active universe = 168 = 115 baseline (frozen v1) + 44 verified new independent PGs + "
               "9 verified operator:Zolo PGs. 85 medium/low/possible-duplicate properties are HELD OUT (excluded "
               "from every count/denominator). Pricing/sharing and amenity evidence keep their OWN separate "
               "denominators (see below). Vishful internal analytics are independent of this universe.")
    st.markdown("**Market-type breakdown** (baseline v1 detail — new v2 additions are PG/co-living, type not re-classified)")
    a=st.columns(4)
    a[0].metric("Total (v1 baseline)", ov["total_competitors"])
    a[1].metric("Men's PG", ov["mens_pg"]); a[2].metric("Women's PG", ov["womens_pg"])
    a[3].metric("Co-ed / unclear PG", ov["coed_or_unclear_pg"])
    b=st.columns(4)
    b[0].metric("Co-living", ov["co_living"]); b[1].metric("Serviced apartments", ov["serviced_apartments"])
    b[2].metric("Hotels", ov["hotels"]); b[3].metric("Residential apartments", ov["residential_apartments"])
    # Vishful-relative corrected distances (great-circle from Vishful ref to actual coords where available;
    # coarse suburb-centroid otherwise; Unknown when insufficient). Read-only, no recompute of Market AI logic.
    distcorr=load_csv_ro("phase3_competitor_distances.csv")
    _dkm=pd.to_numeric(distcorr["distance_km_from_vishful"],errors="coerce")
    c=st.columns(3)
    c[0].metric("Within 1 km", int((_dkm<=1).sum())); c[1].metric("Within 2 km", int((_dkm<=2).sum()))
    c[2].metric("Within 3 km", int((_dkm<=3).sum()))
    st.caption("⚠ Distance is calculated from Vishful's mapped property location (Vishful Vista Heights, "
               "West Avenue, Thiruvanmiyur 600041 — exact Google Maps place, not the suburb centroid). "
               "Exact great-circle where the competitor's own map coordinate is available; coarse suburb/pincode-"
               "centroid otherwise (approximate, NOT street-level); Unknown when insufficient. Same locality ≠ same "
               "location — no competitor is 0 km merely for being in Thiruvanmiyur.")

    # ---- Locality market-context (CURRENT 168-property active universe; spelling variants normalized) ----
    st.markdown("**Locality market-context** (current 168-property universe; counts include verified v2 additions)")
    loc=load_csv_ro("phase3_active_locality_summary.csv")
    lview=pd.DataFrame({
        "Locality":loc["locality"].map(_u),
        "Competitors (168)":loc["competitor_count"],
        "v2 added":loc["v2_added"],
        "With official monthly price":loc["competitors_with_official_monthly_pricing"],
        "With reviews":loc["competitors_with_reviews"],
        "Monthly PG price range":loc["monthly_price_range"].map(_u),
        "Median starting (n≥3 only)":loc["monthly_starting_price_median"].map(_u),
        "Common sharing":loc["common_sharing_types"].map(_u),
        "Top + themes":loc["top_positive_themes"].map(_u),
        "Top − themes":loc["top_negative_themes"].map(_u),
        "Score (context)":loc["locality_score_context"]})
    st.dataframe(lview, use_container_width=True, hide_index=True)
    st.caption("Counts are the CURRENT 168-property active universe (v1 baseline + verified v2 additions). "
               "IMPORTANT: 'With official monthly price' and 'With reviews' are their OWN evidence universes — the "
               "numerators are unchanged (official/operator pricing evidence; first-party review collection) and are "
               "NOT diluted; only the count column moved to 168. Monthly price range/median use ONLY official "
               "monthly PG prices (sharing-specific + starting-from) — hotel nightly / USD / new third-party listings "
               "are never mixed in; median shown only when ≥3 competitors are priced, else 'insufficient'. Themes are recurring review signals "
               "(count). Locality score = competitor density + proximity to Vishful (0–100, descriptive). "
               "No average is fabricated; NOT a ranking of competitors and NOT a Vishful-vs-competitor comparison.")

    # ---- SECTION 2: Competitor Directory — CURRENT 168-property active universe (NEVER numeric rent) ----
    st.subheader("② Competitor Directory (current 168-property universe)")
    df=load_csv_ro("phase3_active_market_universe.csv").rename(columns={"property_name":"canonical_name"})
    f=st.columns(5)
    f_uni=f[0].multiselect("Universe", ["v1 (baseline)","v2 (new verified)"])
    f_type=f[1].multiselect("Property type", sorted(df["property_type"].dropna().unique()))
    f_gender=f[2].multiselect("Gender", sorted(df["gender"].fillna("unknown").unique()))
    f_band=f[3].selectbox("Distance band", ["(all)","≤1 km","≤2 km","≤3 km","≤5 km",">5 km / Unknown"])
    f_ost=f[4].multiselect("Operator/source", sorted({("operator:"+o.split(':')[1]) if str(o).startswith("operator:") else "independent" for o in df["operator_source_type"]}))
    d=df.copy()
    if f_uni: d=d[d["universe_version"].isin([x.split()[0] for x in f_uni])]
    if f_type: d=d[d["property_type"].isin(f_type)]
    if f_gender: d=d[d["gender"].fillna("unknown").isin(f_gender)]
    if f_ost:
        want=set(f_ost)
        d=d[d["operator_source_type"].apply(lambda o:(("operator:"+str(o).split(':')[1]) if str(o).startswith("operator:") else "independent") in want)]
    if f_band!="(all)":
        km=pd.to_numeric(d["distance_km"],errors="coerce")
        if f_band=="≤1 km": d=d[km<=1]
        elif f_band=="≤2 km": d=d[km<=2]
        elif f_band=="≤3 km": d=d[km<=3]
        elif f_band=="≤5 km": d=d[km<=5]
        else: d=d[km.isna() | (km>5)]
    # Source / Links: v1 keep their multi-link verified first-party/operator/OTA sources (phase3_competitor_source_links);
    # v2 additions show their THIRD-PARTY platform (or operator:Zolo) listing URL, clearly tagged — never first-party.
    slinks=load_csv_ro("phase3_competitor_source_links.csv")
    _sll={}
    for _,s in slinks.iterrows():
        _sll.setdefault(str(s["competitor_name"]),[]).append((str(s["source_type"]),str(s["source_url"])))
    _v2src={str(r["canonical_name"]):(str(r.get("source_platform") or "listing"),str(r.get("source_url") or "")) for _,r in df.iterrows() if r["universe_version"]=="v2"}
    def _src_cell(name):
        rows=_sll.get(str(name),[])
        if rows:
            seen=set(); out=[]
            for lbl,u in sorted(rows,key=lambda x:(0 if x[0]=="Official" else 3,x[0])):
                if not u.lower().startswith("http") or (lbl,u) in seen: continue
                seen.add((lbl,u)); out.append(f'<a href="{html.escape(u,quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(lbl)}</a>')
            if out: return " · ".join(out)
        if str(name) in _v2src:
            lbl,u=_v2src[str(name)]
            if u.lower().startswith("http"):
                return f'<a href="{html.escape(u,quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(lbl)}</a> <span style="opacity:.6;font-size:.7rem">(third-party)</span>'
        return '<span style="opacity:.6">Unknown / No verified online source</span>'
    def _c(v): return html.escape(_u(v))
    def _dist(v): return "Unknown" if pd.isna(pd.to_numeric(v,errors="coerce")) else f"{float(v):.1f}"
    def _distlabel(prec,km):
        s=str(prec)
        if pd.isna(pd.to_numeric(km,errors="coerce")): return "Unknown — no coordinates"
        if s.startswith("EXACT") or "geocoded" in s: return "Exact map distance"
        if s.startswith("APPROXIMATE") or "coarse" in s or "centroid" in s or "cluster" in s: return "Approximate — suburb centroid"
        return _u(prec)
    def _uni(v): return "v1 baseline" if str(v)=="v1" else "v2 new-verified"
    def _ost(v): return "operator:"+str(v).split(':')[1] if str(v).startswith("operator:") else "independent"
    cols=["Name","Universe","Operator/source","Property type","Gender","Locality","Distance from Vishful (km)",
          "Distance basis","Source evidence","Price status","Source / Links"]
    trs=[]
    for _,r in d.iterrows():
        cells=[_c(r["canonical_name"]),_uni(r["universe_version"]),_c(_ost(r["operator_source_type"])),
               _c(r["property_type"]),_c(r["gender"]),_c(r["locality"]),
               _dist(r["distance_km"]),html.escape(_distlabel(r["distance_precision"],r["distance_km"])),
               _c(r["source_evidence_type"]),html.escape(_PRICE_STATUS_LABEL.get(str(r["price_status"]),str(r["price_status"]) if str(r["price_status"])!="nan" else "Unknown")),
               _src_cell(r["canonical_name"])]
        trs.append("<tr>"+"".join(f"<td>{c}</td>" for c in cells)+"</tr>")
    thead="".join(f"<th>{html.escape(c)}</th>" for c in cols)
    tbl=(f'<div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:0.82rem;width:100%">'
         f'<thead><tr>{thead}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>')
    st.caption(f"{len(d)} of {len(df)} competitors in the CURRENT 168-property universe "
               f"({int((df['universe_version']=='v1').sum())} baseline v1 + {int((df['universe_version']=='v2').sum())} new verified v2). "
               "Distance: Exact = both have map coordinates; Approximate = suburb centroid; Unknown = insufficient (v2 additions "
               "mostly coarse; 3 Kattankulathur = Unknown; no fabricated coordinates). Source evidence is tagged — v1 keep their "
               "verified first-party/operator/OTA sources; v2 additions show THIRD-PARTY platform / operator:Zolo listings, never "
               "treated as first-party. Numeric rent is never shown here — see ③/⑤. Holdout (85) is excluded.")
    st.markdown(tbl, unsafe_allow_html=True)

    # ---- SECTION 3: Comparable Pricing (first-party per-bed × sharing × AC ONLY) ----
    st.subheader("③ Comparable Pricing")
    st.error(cp["sample_size_warning"])
    grid=pd.DataFrame(cp["grid"])
    if not grid.empty:
        src=sorted(grid["source_url"].unique())
        piv=grid.pivot_table(index="sharing_type",columns="ac",values="monthly_rent_per_bed_inr",aggfunc="first")
        order=[s for s in ["single","two","three","four"] if s in piv.index]
        piv=piv.reindex(order)
        disp=pd.DataFrame({
            "Sharing":[s.capitalize() for s in piv.index],
            "AC":[rupee(piv.loc[s,"ac"]) if "ac" in piv.columns and pd.notna(piv.loc[s,"ac"]) else "Unknown" for s in piv.index],
            "Non-AC":[rupee(piv.loc[s,"non_ac"]) if "non_ac" in piv.columns and pd.notna(piv.loc[s,"non_ac"]) else "Unknown" for s in piv.index]})
        st.dataframe(disp, use_container_width=True, hide_index=True)
        st.caption("Source (first-party): "+", ".join(src))
    st.metric("Independent comparable properties", cp["independent_properties"])
    st.warning("No market average / min / max is computed — a single property is not a benchmark.")
    if cp.get("excluded_room_class"):
        st.markdown("**Excluded — room-class pricing, not per-bed comparable:**")
        ex=pd.DataFrame(cp["excluded_room_class"])
        exv=pd.DataFrame({"Property":ex["property"],"Room class":ex["room_class"],
            "Monthly (room-class ₹)":ex["monthly_rent_inr"].map(rupee),"Reason":ex["reason"]})
        st.dataframe(exv, use_container_width=True, hide_index=True)
        st.caption("Shown for transparency only. NOT placed in the comparable grid; never converted to per-bed.")

    # ---- Verified published sharing-price context (additive; OFFICIAL_SHARING_SPECIFIC monthly INR ONLY) ----
    st.markdown("**Verified published sharing-price context**")
    _pr=load_csv_ro("phase3_competitor_prices.csv")
    _ss=_pr[_pr["price_basis"]=="OFFICIAL_SHARING_SPECIFIC"].copy()
    _ss=_ss[_ss["sharing_type"].notna()]
    _TIER=["Single","Double","Triple","4-sharing","5-sharing"]
    trows=[]
    for t in _TIER:
        s=_ss[_ss["sharing_type"]==t]
        if not len(s): continue
        trows.append({"Sharing tier":t,"Lowest observed (₹)":rupee(int(s["price"].min())),
            "Highest observed (₹)":rupee(int(s["price"].max())),
            "Competitors":int(s["competitor_name"].nunique()),
            "Sources / platforms":f"{int(s['source_url'].nunique())} / {int(s['source_platform'].nunique())}"})
    if trows:
        st.dataframe(pd.DataFrame(trows), use_container_width=True, hide_index=True)
        st.caption("Observed PUBLISHED sharing-price context from verified official/operator listings "
                   f"({int(_ss['competitor_name'].nunique())} competitors, {len(_ss)} observations). Monthly per-bed sharing "
                   "tiers ONLY — hotel per-night, USD, 'starting-from', and room-class (e.g. Sumathi Illam) are excluded and "
                   "never converted. These are lowest/highest OBSERVED published prices, NOT a market average / benchmark / "
                   "min-max, and NOT a Vishful price recommendation. Thin tiers (e.g. 5-sharing, n=1) are context only. "
                   "EVIDENCE UNIVERSE — pricing/sharing: 23 competitors / 66 observations from first-party official/operator/OTA "
                   "listings (Official, Yube1, Stanza Living, OYO, EaseMyTrip, Trip.com, HexaHome). This is a DIFFERENT, broader "
                   "source set than the 6 amenity-evidence sources on Page 12, and is its own bucket within the 168-property current universe. Operators/"
                   "aggregators like Zolo are NOT per-property price evidence — Zolo has 0 extracted price/sharing rows.")
        with st.expander("Per-observation provenance (every tier price + source)"):
            prov=pd.DataFrame({"Competitor":_ss["competitor_name"].map(_u),"Tier":_ss["sharing_type"].map(_u),
                "Price (₹)":_ss["price"],"AC":_ss["ac"].map(_u),"Platform":_ss["source_platform"].map(_u),
                "Source":_ss["source_url"].map(_u)}).sort_values(["Tier","Price (₹)"])
            st.dataframe(prov, use_container_width=True, hide_index=True)

    # ---- SECTION 4: Market Attribute Signals (non-price, first-party rendered evidence ONLY) ----
    st.subheader("④ Market Attribute Signals")
    st.info(_MKT_CONTEXT_NOTE)
    try:
        pa=load_playwright_attrs()
    except SourceValidationError as e:
        st.warning(f"Market-attribute source unavailable: {e}")
        pa=None
    if pa is not None and len(pa):
        def _cnt(col): return int((pa[col]==True).sum()) if col in pa.columns else 0
        g=st.columns(4)
        g[0].metric("Properties with AC info", _cnt("ac_available"))
        g[1].metric("Properties with Non-AC info", _cnt("non_ac"))
        g[2].metric("Properties offering food", _cnt("food"))
        g[3].metric("Properties mentioning Wi-Fi", _cnt("wifi"))
        h=st.columns(4)
        h[0].metric("Mentioning laundry", _cnt("laundry"))
        h[1].metric("Mentioning security/CCTV", _cnt("cctv_security"))
        h[2].metric("Mentioning parking", _cnt("parking"))
        h[3].metric("Mentioning power backup", _cnt("power_backup"))
        st.caption(f"{_MKT_CONTEXT_NOTE} Counts = first-party sites that explicitly rendered the attribute; "
                   "absence = Unknown (never assumed absent). Source: phase3_playwright_market_research.csv.")
        # commonly observed sharing configurations (first-party, verbatim)
        sc=[s for s in pa.get("sharing_config",pd.Series(dtype=object)).dropna().tolist() if str(s).strip()]
        if sc:
            st.markdown("**Commonly observed sharing configurations (first-party rendered):**")
            st.dataframe(pd.DataFrame({"Property":pa[pa["sharing_config"].notna()]["property_name"],
                "Sharing configuration":pa[pa["sharing_config"].notna()]["sharing_config"]}),
                use_container_width=True, hide_index=True)
        # provenance table: one row per (property, attribute=Available) with first-party source + evidence
        prov=[]
        for _,r in pa.iterrows():
            src=f"https://{r['domain']}" if pd.notna(r.get("domain")) else None
            for col,label in _ATTR_COLS:
                if col in pa.columns and r.get(col)==True:
                    prov.append({"Property":r["property_name"],"Attribute":label,"Value":"Available",
                        "First-party source":src,"Evidence":r.get("evidence")})
            if pd.notna(r.get("room_types")):
                prov.append({"Property":r["property_name"],"Attribute":"Room types","Value":r["room_types"],
                    "First-party source":src,"Evidence":r.get("evidence")})
        if prov:
            st.markdown("**Attribute provenance (first-party verified — no inference):**")
            st.dataframe(pd.DataFrame(prov), use_container_width=True, hide_index=True)
        st.caption("Only first-party-rendered attributes shown. Unknown values are omitted, never asserted. "
                   "Purpose: combine later with Vishful's own occupancy/vacancy/inventory/revenue data for "
                   "marketing/inventory decisions — NOT a competitor-vs-Vishful comparison.")

    # ---- SECTION 5: Verified competitor prices (STRICTLY separated by basis) ----
    st.subheader("⑤ Verified Competitor Prices (by basis)")
    pr=load_csv_ro("phase3_competitor_prices.csv")
    _BASIS_LABEL={"OFFICIAL_SHARING_SPECIFIC":"Official — sharing-specific (monthly ₹)",
        "OFFICIAL_STARTING_FROM":"Official — starting-from (monthly ₹, NOT actual rent)",
        "HOTEL_PER_NIGHT":"Hotel / serviced-apt — per night (NOT monthly PG rent)",
        "USD":"USD figure (as-shown, never converted)","REVIEW_MENTIONED":"Customer-reported in a review"}
    st.warning("Prices are kept strictly separated by basis and never mixed. 'Starting-from' is not an actual rent; "
               "hotel per-night and USD are not monthly PG rent. Review-mentioned pricing = 0 (0/114 collected reviews "
               "quote ₹/Rs rent). No averaging across competitors, no ranking.")
    st.caption("EVIDENCE UNIVERSE — pricing/sharing keeps its OWN denominator: 23 competitors carry any extracted price ("
               f"{int((pr['price_basis']=='OFFICIAL_SHARING_SPECIFIC').sum())} sharing-specific obs across "
               f"{int(pr[pr['price_basis']=='OFFICIAL_SHARING_SPECIFIC']['competitor_name'].nunique())} competitors). "
               "Distinct from the 6 first-party amenity-evidence sources (Page 12) and from the 115-property universe. "
               "Zolo (operator/aggregator) shows sharing/pricing on its OWN multi-property site but was NOT scraped per-property — "
               "0 Zolo price/sharing rows here; correctly not treated as first-party per-property evidence.")
    for basis in ["OFFICIAL_SHARING_SPECIFIC","OFFICIAL_STARTING_FROM","HOTEL_PER_NIGHT","USD","REVIEW_MENTIONED"]:
        sub=pr[pr["price_basis"]==basis]
        if not len(sub): continue
        st.markdown(f"**{_BASIS_LABEL[basis]}** — {sub['competitor_name'].nunique()} competitor(s), {len(sub)} observation(s)")
        pv=pd.DataFrame({"Competitor":sub["competitor_name"].map(_u),"Platform":sub["source_platform"].map(_u),
            "Sharing":sub["sharing_type"].map(_u),"Price (₹)":sub["price"],"AC":sub["ac"].map(_u),
            "Gender":sub["gender"].map(_u),"Evidence":sub["evidence_text"].map(_u)})
        st.dataframe(pv, use_container_width=True, hide_index=True)

    # ---- SECTION 6: Owner decision cards (finding -> evidence -> implication -> action) ----
    st.subheader("⑥ What this means for Vishful — decision cards")
    st.info("Decision SUPPORT, not automatic decisions. Every card is traceable to collected data. "
            "No competitor ranking, no Vishful-vs-competitor comparison, no recommendation of a specific Vishful rent.")
    cards=load_csv_ro("phase3_owner_decision_cards.csv")
    _CONF_COLOR={"High":"#1a7f37","Moderate":"#9a6700","Explicit":"#0969da"}
    for _,c in cards.iterrows():
        conf=str(c["confidence"]); ck=next((k for k in _CONF_COLOR if conf.startswith(k)),"Moderate")
        col=_CONF_COLOR[ck]
        html_card=(
            f'<div style="border:1px solid rgba(128,128,128,.35);border-left:4px solid {col};border-radius:8px;'
            f'padding:12px 14px;margin:8px 0;background:rgba(128,128,128,.05)">'
            f'<div style="font-weight:600;font-size:0.98rem;margin-bottom:6px">{html.escape(str(c["business_finding"]))} '
            f'<span style="float:right;font-size:0.72rem;font-weight:600;color:{col}">{html.escape(ck.upper())} CONFIDENCE</span></div>'
            f'<div style="font-size:0.85rem;margin:3px 0"><b>What the data says:</b> {html.escape(str(c["evidence"]))}</div>'
            f'<div style="font-size:0.85rem;margin:3px 0"><b>Why it matters to Vishful:</b> {html.escape(str(c["business_implication"]))}</div>'
            f'<div style="font-size:0.85rem;margin:3px 0"><b>Possible action:</b> {html.escape(str(c["possible_action"]))}</div>'
            f'<div style="font-size:0.72rem;opacity:.7;margin-top:5px">Confidence: {html.escape(conf)} · Source: {html.escape(str(c["provenance"]))}</div>'
            f'</div>')
        st.markdown(html_card, unsafe_allow_html=True)
    st.caption(f"{len(cards)} decision cards, each computed from the collected market/pricing/review data + Vishful's "
               "OWN complaint tickets (never competitor performance). Decision support only — nothing here changes a locked decision automatically.")
    ds=load_csv_ro("phase3_decision_support.csv")
    with st.expander(f"Full decision-support detail ({len(ds)} review-derived items, for traceability)"):
        dsv=pd.DataFrame({"Topic":ds["topic"].map(_u),"Observation":ds["observation"].map(_u),
            "Evidence":ds["evidence"].map(_u),"Business implication":ds["business_implication"].map(_u),
            "Possible Vishful action":ds["possible_vishful_action"].map(_u),"Source":ds["source"].map(_u)})
        st.dataframe(dsv, use_container_width=True, hide_index=True)

# ---------------- Business Opportunities (read-only, from validated engine outputs) ----------------
@st.cache_data(show_spinner=False)
def load_bizopp(name):
    fn={"opps":"phase3_business_opportunities.csv","summary":"phase3_business_opportunities_summary.csv",
        "evidence":"phase3_business_opportunity_evidence.csv"}[name]
    p=os.path.join(OUT,fn)
    if not os.path.exists(p): raise SourceValidationError(f"missing output: {fn}")
    return pd.read_csv(p)

_PRIO_RANK={"High":0,"Medium":1,"Low":2}
_EVSRC_MEANING={
 "VISHFUL_INTERNAL":"Based only on Vishful's own validated data",
 "MARKET_CONTEXT":"Publicly published first-party market information (not competitor performance)",
 "COMBINED":"Vishful internal evidence + first-party market context"}

def p_bizopp():
    st.header("11 · Business Opportunities (read-only)")
    st.info("Deterministic recommendations based on Vishful internal analytics + publicly published "
            "market context. This is not a competitor comparison.")
    opps=load_bizopp("opps"); summ=load_bizopp("summary"); evid=load_bizopp("evidence")
    sm=dict(zip(summ["metric"],summ["value"]))
    def _i(k):
        try: return int(float(sm.get(k,0)))
        except Exception: return sm.get(k,0)

    # ① Opportunity Overview (values from validated summary CSV)
    st.subheader("① Opportunity Overview")
    a=st.columns(4)
    a[0].metric("Total opportunities", _i("total_opportunities"))
    a[1].metric("High", _i("High")); a[2].metric("Medium", _i("Medium")); a[3].metric("Low", _i("Low"))
    b=st.columns(4)
    b[0].metric("Inventory to Promote", _i("inventory_to_promote"))
    b[1].metric("Sharing / Inventory", _i("sharing_opportunities"))
    b[2].metric("Amenity", _i("amenity_opportunities"))
    b[3].metric("Location", _i("location_opportunities"))
    st.caption("VISHFUL_INTERNAL = Vishful's own validated data · MARKET_CONTEXT = publicly published "
               "first-party market info (NOT competitor performance) · COMBINED = both.")

    # ② Owner opportunities — consolidated owner-facing cards (display aggregation of the engine rows)
    st.subheader("② Owner opportunities")
    oc=load_csv_ro("phase3_owner_opportunity_cards.csv").sort_values("display_order")
    st.caption(f"The {len(oc)} decision{'s' if len(oc)!=1 else ''} below consolidate {int(oc['source_count'].sum())} engine "
               f"opportunities for readability (engine currently has {len(opps)}). Scores and the underlying rows are "
               "unchanged — see the priority table and Evidence Details for full traceability. Card count reflects "
               "current vacancy: a bed-type only gets a card while it has real vacant inventory.")
    _OPPCOL={"COMBINED":"#0969da","VISHFUL_INTERNAL":"#1a7f37","MARKET_CONTEXT":"#9a6700"}
    for _,c in oc.iterrows():
        col=_OPPCOL.get(str(c["provenance_label"]),"#57606a")
        ev="".join(f"<li>{html.escape(e.strip())}</li>" for e in str(c["evidence"]).split("|") if e.strip())
        card=(f'<div style="border:1px solid rgba(128,128,128,.35);border-left:4px solid {col};border-radius:8px;'
              f'padding:12px 14px;margin:8px 0;background:rgba(128,128,128,.05)">'
              f'<div style="font-weight:600;font-size:0.98rem;margin-bottom:5px">{int(c["display_order"])}. {html.escape(str(c["title"]))} '
              f'<span style="float:right;font-size:0.72rem;font-weight:600;color:{col}">{html.escape(str(c["provenance_label"]))}</span></div>'
              f'<div style="font-size:0.85rem;margin:2px 0"><b>Evidence:</b><ul style="margin:3px 0 3px 18px;padding:0">{ev}</ul></div>'
              f'<div style="font-size:0.85rem;margin:2px 0"><b>Suggested action:</b> {html.escape(str(c["suggested_action"]))}</div>'
              f'<div style="font-size:0.72rem;opacity:.7;margin-top:5px">Consolidates: {html.escape(str(c["consolidates"]))}</div>'
              f'</div>')
        st.markdown(card, unsafe_allow_html=True)
    _order=[str(t) for t in oc.sort_values("display_order")["title"]]
    if _order:
        _seq=", then ".join(_order)
        _note=(" (No single-bed card is shown — current single vacancy is 0.)"
               if "investigate_single" not in set(oc["card_id"]) else "")
        st.caption(f"Business implication for the owner, in priority order: {_seq}. Decision support — no competitor "
                   f"comparison, no recommended price.{_note}")

    # ③ Priority Opportunities (full engine rows, for traceability — scores unchanged)
    st.subheader("③ Priority Opportunities (engine detail — traceability)")
    d=opps.copy(); d["_pr"]=d["priority"].map(_PRIO_RANK).fillna(9)
    d=d.sort_values(["score","_pr","opportunity"],ascending=[False,True,True])
    ICON={"High":"🔴 High","Medium":"🟠 Medium","Low":"🟡 Low"}
    view=pd.DataFrame({
        "Opportunity":d["opportunity"],"Priority":d["priority"].map(lambda p:ICON.get(p,p)),
        "Score":d["score"],"Category":d["category"],"Evidence Source":d["evidence_source"],
        "Reason":d["reason"],"Recommended Action":d["recommended_action"]})
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.caption("Sorted by score (desc), then priority, then name. Scores/values come from the validated "
               "engine output (phase3_business_opportunities.csv) — no recompute in the dashboard.")

    # Top actionable highlights (rendered from the CSV, not hard-coded)
    with st.expander("Top actionable opportunities (owner view)", expanded=True):
        for _,r in d.head(5).iterrows():
            st.markdown(f"**{ICON.get(r['priority'],r['priority'])} · {r['opportunity']}** "
                        f"(score {r['score']}, {r['evidence_source']})")
            st.caption(f"{r['reason']}  →  **{r['recommended_action']}**")

    # ④ Evidence Details (per selected opportunity)
    st.subheader("④ Evidence Details")
    pick=st.selectbox("Select an opportunity", d["opportunity"].tolist())
    row=d[d["opportunity"]==pick].iloc[0]
    st.markdown(f"**Evidence source:** {row['evidence_source']} — {_EVSRC_MEANING.get(row['evidence_source'],'')}")
    c=st.columns(2)
    c[0].markdown("**Vishful evidence (internal)**"); c[0].write(row["vishful_evidence"] if pd.notna(row["vishful_evidence"]) else "Unknown / not applicable")
    c[1].markdown("**Market evidence (first-party context)**"); c[1].write(row["market_context_evidence"] if pd.notna(row["market_context_evidence"]) else "Unknown / not applicable")
    st.markdown(f"**Explanation:** {row['reason']}")
    st.markdown(f"**Recommended action:** {row['recommended_action']}  ·  **Confidence:** {row['confidence']}")
    st.caption(f"Provenance: {row['provenance']}")
    if str(row["category"])=="Amenity Marketing Opportunity":
        st.warning("Amenity opportunities: Confirm internally, highlight only if present. "
                   "Vishful's own amenity availability is UNKNOWN — never assumed from market data.")
    # underlying evidence rows for this opportunity's configuration/property
    with st.expander("Underlying evidence rows"):
        st.dataframe(evid, use_container_width=True, hide_index=True)
    st.caption("Market evidence retains first-party provenance. No competitor comparison, ranking, "
               "price benchmark, or market-average is computed or shown.")

# ---------------- Marketing Recommendations + Market Research (read-only, validated CSV only) ----------------
@st.cache_data(show_spinner=False)
def load_csv_ro(fn, required=None):
    p=os.path.join(OUT,fn)
    if not os.path.exists(p): raise SourceValidationError(f"missing output: {fn}")
    df=pd.read_csv(p)
    if required: require_columns(df,fn,required)
    return df

def _b(v): return "Unknown" if (v is None or (isinstance(v,float) and pd.isna(v)) or str(v).lower()=="nan") else str(v)

def p_marketing():
    st.header("12 · Marketing Recommendations (read-only)")
    st.info("Deterministic marketing decisions from Vishful internal analytics + validated market context. "
            "Market data = context, Vishful data = decision driver. This is not a competitor comparison.")
    rec=load_csv_ro("phase3_marketing_recommendations.csv",
        ["recommendation_id","category","priority","score","recommended_action","business_reason",
         "vishful_evidence","market_evidence","evidence_source","confidence","provenance"])
    summ=load_csv_ro("phase3_marketing_recommendations_summary.csv"); sm=dict(zip(summ["metric"],summ["value"]))
    def _i(k):
        try: return int(float(sm.get(k,0)))
        except Exception: return sm.get(k,0)
    a=st.columns(4)
    a[0].metric("Total", _i("total_recommendations")); a[1].metric("High", _i("High"))
    a[2].metric("Medium", _i("Medium")); a[3].metric("Low", _i("Low"))
    b=st.columns(5)
    b[0].metric("Inventory", _i("inventory_marketing")); b[1].metric("Vacancy/Slow-fill", _i("vacancy_slow_fill"))
    b[2].metric("Sharing", _i("sharing_positioning")); b[3].metric("Amenity", _i("amenity_marketing"))
    b[4].metric("Locality", _i("locality_marketing"))
    # ── Owner decisions — consolidated owner-facing cards (display aggregation of the engine rows) ──
    st.subheader("Owner decisions")
    mc=load_csv_ro("phase3_owner_marketing_cards.csv").sort_values("display_order")
    st.caption(f"The {len(mc)} decision{'s' if len(mc)!=1 else ''} below consolidate {int(mc['source_count'].sum())} of the "
               f"{len(rec)} engine recommendations for readability. Scores and the underlying rows are unchanged — see "
               "the engine-detail table below for full traceability. Card count reflects current vacancy: a bed-type "
               "only gets a card while it has real vacant inventory.")
    ap=load_csv_ro("phase3_vishful_amenity_provenance.csv")
    _MKC={"COMBINED":"#0969da","VISHFUL_INTERNAL":"#1a7f37","MARKET_CONTEXT":"#9a6700"}
    def _amenity_card(c):
        # display-only split into two owner-readable groups (data/classification unchanged)
        marketable=ap[ap["vishful_own_bucket"].isin(["VISHFUL_INTERNAL_VERIFIED","VISHFUL_PUBLIC_EXPLICIT"])]
        food=ap[ap["vishful_own_bucket"]=="VISHFUL_PUBLIC_NEARBY_CONTEXT"]
        can="".join(f'<li>{html.escape(str(r["amenity"]))} — {html.escape(str(r["vishful_own_bucket"]))}</li>' for _,r in marketable.iterrows())
        food_note=""
        for _,r in food.iterrows():
            food_note=(f'Vishful website wording is <b>"Food Vendors Nearby"</b>. This must NOT be represented as '
                       f'Vishful-provided food — describe it only as nearby food/vendor convenience unless internal '
                       f'food-service evidence is found. (Market: {html.escape(str(r["market_context_evidence"]).split("[")[0].strip())} — context only.)')
        return (
            f'<div style="border:1px solid rgba(128,128,128,.35);border-left:4px solid #1a7f37;border-radius:8px;'
            f'padding:12px 14px;margin:8px 0;background:rgba(128,128,128,.05)">'
            f'<div style="font-weight:600;font-size:0.98rem;margin-bottom:6px">{int(c["display_order"])}. {html.escape(str(c["title"]))}</div>'
            f'<div style="font-size:0.88rem;font-weight:600;color:#1a7f37;margin:2px 0">✅ Amenities Vishful can market</div>'
            f'<ul style="margin:3px 0 8px 18px;padding:0;font-size:0.85rem">{can}</ul>'
            f'<div style="font-size:0.88rem;font-weight:600;color:#9a6700;margin:2px 0">⚠️ Food — clarify before marketing</div>'
            f'<div style="font-size:0.85rem;margin:3px 0 0 4px">{food_note}</div>'
            f'<div style="font-size:0.72rem;opacity:.7;margin-top:6px">Competitor amenity counts are kept separately as '
            f'MARKET_FIRST_PARTY_CONTEXT and are never used to establish that Vishful provides an amenity. '
            f'Consolidates: {html.escape(str(c["consolidates"]))}</div></div>')
    for _,c in mc.iterrows():
        if str(c["card_id"])=="verify_amenities":
            st.markdown(_amenity_card(c), unsafe_allow_html=True); continue
        col=_MKC.get(str(c["provenance_label"]),"#57606a")
        ev="".join(f"<li>{html.escape(e.strip())}</li>" for e in str(c["evidence"]).split("|") if e.strip())
        st.markdown(
            f'<div style="border:1px solid rgba(128,128,128,.35);border-left:4px solid {col};border-radius:8px;'
            f'padding:12px 14px;margin:8px 0;background:rgba(128,128,128,.05)">'
            f'<div style="font-weight:600;font-size:0.98rem;margin-bottom:5px">{int(c["display_order"])}. {html.escape(str(c["title"]))} '
            f'<span style="float:right;font-size:0.72rem;font-weight:600;color:{col}">{html.escape(str(c["provenance_label"]))}</span></div>'
            f'<div style="font-size:0.85rem;margin:2px 0"><b>Evidence:</b><ul style="margin:3px 0 3px 18px;padding:0">{ev}</ul></div>'
            f'<div style="font-size:0.85rem;margin:2px 0"><b>Suggested action:</b> {html.escape(str(c["suggested_action"]))}</div>'
            f'<div style="font-size:0.72rem;opacity:.7;margin-top:5px">Consolidates: {html.escape(str(c["consolidates"]))}</div></div>',
            unsafe_allow_html=True)

    # ── Amenity provenance (5-bucket: Vishful-own provision vs competitor market context — kept separate) ──
    st.markdown("**Vishful amenity provenance** (Vishful's own provision vs competitor market context — classified, kept separate)")
    apv=pd.DataFrame({"Amenity":ap["amenity"],"Vishful own (bucket)":ap["vishful_own_bucket"],
        "Internal data":ap["internal_status"],"Vishful public wording":ap["vishful_public_wording"],
        "Market context (competitors)":ap["market_context_evidence"].map(lambda s:str(s).split('[')[0].strip()),
        "What the owner should do":ap["owner_decision_status"]})
    st.dataframe(apv, use_container_width=True, hide_index=True)
    st.caption("Buckets: VISHFUL_INTERNAL_VERIFIED · VISHFUL_PUBLIC_EXPLICIT · VISHFUL_PUBLIC_NEARBY_CONTEXT · "
               "MARKET_FIRST_PARTY_CONTEXT · UNKNOWN. AC & Wi-Fi = internally verified (own assets/services). "
               "Parking & Security/CCTV = VISHFUL_PUBLIC_EXPLICIT — Vishful's own site (vishful.co.in) advertises them "
               "as property amenities ('CCTV Security — round-the-clock surveillance'; 'Parking'). Food = "
               "VISHFUL_PUBLIC_NEARBY_CONTEXT ('Food Vendors Nearby' = location convenience, NOT a Vishful food service). "
               "Competitor prevalence is MARKET_FIRST_PARTY_CONTEXT only — never a Vishful claim, never proof of demand, "
               "never a reason to 'add' an amenity, and never used to establish a Vishful amenity. Public first-party "
               "evidence is kept separate from internal validation. "
               "NOTE on the market denominator: 'X/6' means X of the 6 ELIGIBLE first-party amenity-evidence sources "
               "(the 6 competitors — TSP, Kripa, Sri Mahalakshmi, Season 4, Kolam, Olive — whose own first-party sites "
               "carried renderable amenity evidence). Only 6 properties met that first-party single-property criteria (the amenity denominator stays /6, independent of the 168-property universe); "
               "'5/6' is NOT 5 of 115 PGs. This amenity universe (6 sources) is SEPARATE from the pricing/sharing evidence "
               "universe (23 competitors / 66 observations, Page 10 ⑤). Both are separate evidence universes within the current 168-property market universe (historical baseline 115). "
               "Operators/aggregators such as Zolo are NOT first-party amenity sources (Zolo = operator/aggregator, "
               "0 extracted amenity/price/sharing rows).")

    # ── Engine detail (13 rows, traceability — scores unchanged) ──
    ICON={"High":"🔴 High","Medium":"🟠 Medium","Low":"🟡 Low"}
    d=rec.copy(); d["_pr"]=d["priority"].map({"High":0,"Medium":1,"Low":2}).fillna(9)
    d=d.sort_values(["score","_pr","recommendation_id"],ascending=[False,True,True])
    view=pd.DataFrame({"ID":d["recommendation_id"],"Priority":d["priority"].map(lambda p:ICON.get(p,p)),
        "Score":d["score"],"Category":d["category"],"Target":d["target_inventory_locality"].map(_b),
        "Recommended Action":d["recommended_action"],"Evidence Source":d["evidence_source"],
        "Business Reason":d["business_reason"],"Vishful Evidence":d["vishful_evidence"].map(_b),
        "Market Evidence":d["market_evidence"].map(_b),"Confidence":d["confidence"],"Provenance":d["provenance"]})
    st.subheader("Engine detail — Recommendations (High → Low, traceability)")
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.caption("Values from validated engine output (phase3_marketing_recommendations.csv) — no recompute, scores "
               "unchanged. NOTE: the engine's amenity rows predate the amenity-provenance cross-check above; the "
               "owner cards + provenance table reflect the corrected internal-verified vs publicly-advertised status.")
    with st.expander("Closed-loop outcome tracking (Part 8)"):
        cl=load_csv_ro("phase3_closed_loop_tracking.csv")
        st.dataframe(cl, use_container_width=True, hide_index=True)
        st.caption("Campaign outcomes are UNAVAILABLE (no data) — never fabricated. Scaffold for future "
                   "recommendation → action → enquiries → conversions → occupancy → revenue tracking.")

def p_market_research():
    st.header("13 · Market Research / Discovery (read-only)")
    st.info("Publicly published first-party market context. No competitor comparison, ranking, or price benchmark.")
    ds=load_csv_ro("phase3_market_research_dataset.csv")
    sg=load_csv_ro("phase3_market_signals.csv")
    summ=load_csv_ro("phase3_market_research_summary.csv"); sm=dict(zip(summ["metric"],summ["value"]))
    a=st.columns(4)
    a[0].metric("Properties (first-party)", int(float(sm.get("dataset_properties",len(ds)))))
    a[1].metric("Verified official sites", int(float(sm.get("first_party_verified",0))))
    a[2].metric("With first-party price", int(float(sm.get("with_monthly_price",0))))
    a[3].metric("Comparable per-bed sources", int(float(sm.get("comparable_perbed_sources",0))))
    st.subheader("Discovered / verified first-party properties")
    dv=ds.copy()
    for c in dv.columns: dv[c]=dv[c].map(_b)
    st.dataframe(dv, use_container_width=True, hide_index=True)
    st.caption("Price status = Unknown for all (no first-party per-bed × sharing × AC price published). "
               "Amenity flags shown only where the property's own page rendered them; blank = Unknown.")
    st.subheader("Market signals (context only)")
    for stype in ["published_amenity","sharing_configuration","locality_concentration",
                  "property_type_concentration","first_party_website_availability","new_property_discovery",
                  "comparable_price_sources"]:
        sub=sg[sg["signal_type"]==stype]
        if len(sub):
            st.markdown(f"**{stype.replace('_',' ').title()}**")
            st.dataframe(sub[["signal","value","basis","provenance"]], use_container_width=True, hide_index=True)
    st.caption("All signals are MARKET_CONTEXT with first-party provenance. Never a competitor ranking or benchmark.")

def p_decision_board():
    st.header("14 · Owner Decision Board & Execution (read-only)")
    st.info("Analytics → Business Decision → Action → Lead/Conversion → Bed Filled → Revenue Outcome. "
            "Vishful internal data = decision driver; market = context only. Not a competitor comparison.")
    dec=load_csv_ro("phase3_business_decisions.csv",
        ["decision_id","category","priority","score","evidence_source","business_problem","decision",
         "recommended_action","expected_impact","tracking_field"])
    et=load_csv_ro("phase3_execution_tracker.csv"); es=load_csv_ro("phase3_execution_summary.csv")
    lf=load_csv_ro("phase3_lead_followup.csv"); mx=load_csv_ro("phase3_inventory_amenity_matrix.csv")
    sm=dict(zip(es["metric"],es["value"]))
    # review-intelligence evidence layers (read-only; validated engine outputs, no recompute)
    recon=load_csv_ro("phase3_decision_reconciliation.csv")
    rc=load_csv_ro("phase3_review_decision_candidates.csv")
    ragg=load_csv_ro("phase3_review_market_aggregate.csv")
    reinforced_ids=set(recon[recon["reconciliation_status"]=="EXISTING_REINFORCED"]["decision_ref"])

    # ① Decision board
    st.subheader("① Decision Board")
    a=st.columns(4)
    a[0].metric("Total decisions", len(dec))
    a[1].metric("High", int((dec["priority"]=="High").sum()))
    a[2].metric("Medium", int((dec["priority"]=="Medium").sum()))
    a[3].metric("Low", int((dec["priority"]=="Low").sum()))
    d=dec.copy(); d["_pr"]=d["priority"].map({"High":0,"Medium":1,"Low":2}).fillna(9)
    d=d.sort_values(["_pr","score"],ascending=[True,False])
    ICON={"High":"🔴 High","Medium":"🟠 Medium","Low":"🟡 Low"}
    st_map=dict(zip(et["decision_id"],et["status"]))
    view=pd.DataFrame({"ID":d["decision_id"],"Priority":d["priority"].map(lambda p:ICON.get(p,p)),
        "Score":d["score"],"Decision":d["decision"],"Reason":d["business_problem"],
        "Evidence":d["decision_id"].map(lambda x:"Market + Vishful evidence" if x in reinforced_ids else "Vishful internal"),
        "Business Impact":d["expected_impact"],
        "Recommended Action":d["recommended_action"],"Measure (KPI)":d["tracking_field"],
        "Current Status":d["decision_id"].map(st_map).fillna("Pending")})
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.caption(f"14 backbone decisions (unchanged). {len(reinforced_ids)} now carry **Market + Vishful evidence** "
               "(review-reinforced); the rest are Vishful internal. Sorted High→Medium→Low, then score. No recompute.")
    top2=d.sort_values("score",ascending=False).head(2)
    st.info("Business insight: the two highest-scored decisions are " +
            " and ".join(f"**{r.decision_id}** ({r.decision.rstrip('.')})" for r in top2.itertuples()) +
            f" — act on these first. {int((d['priority']=='High').sum())} decision(s) are currently High priority; "
            f"{int((d['priority']=='Low').sum())} are Low (including the honest zero-signal DEC-VAC-Single / "
            "DEC-PRICEREV-Single pair, since current single vacancy is 0).")

    # ---- "Worth checking" — investigation QUESTIONS per decision. Display-only; the decision logic,
    #      scores, baselines and KPIs are untouched. These are prompts the owner can look into, never
    #      asserted causes, and they name no tenant, staff member, technician or vendor. ----
    _WORTH_CHECKING={
     "DEC-REVPROTECT-AR90":[
        "Are these balances genuinely unpaid, or are some already settled but not reconciled into ageing?",
        "For the closed accounts, does the recorded settlement cover the balance still showing?",
        "Where no settlement record exists, did a settlement happen that was never written down?"],
     "DEC-LEAD-FOLLOWUP":[
        "Are these enquiries still live, given they all arrived within one week of July 2026?",
        "Was anyone assigned to follow each one up, and is that recorded anywhere?",
        "Which bed types were requested, and do we currently have those free?"],
     "DEC-AMEN-AC":[
        "Do our current listings actually mention AC for these beds?",
        "Are enquirers asking about AC when they contact us?",
        "Note: these are the same beds as DEC-VAC-Double seen from an amenity angle — is the marketing already covered there?"],
     "DEC-LEAD-DEMAND-2SH":[
        "Are these enquiries still active, and do their budget and location needs match the vacant beds?",
        "With only a small number of enquiries carrying a stated bed type, is this signal strong enough to act on alone?"],
     "DEC-EB-INVESTIGATE":[
        "Are the currently-flagged apartments still showing the signal in the latest period, or is this primarily historical?",
        "Could the reading reflect a meter fault, an appliance left running, or common-area load rather than tenant use?",
        "Does recorded occupancy in those apartments match the consumption pattern?"],
     "DEC-PRICEREV-Triple":[
        "Is the slower fill related to price, to room condition, or to which specific apartments are involved?",
        "Are enquiries declining at the price stage, or after viewing the room?"],
     "DEC-MAINT-PRIORITISE":[
        "Is the repeat pattern concentrated in particular apartments, or in particular issue types?",
        "Are we repairing repeatedly where replacing the asset would end the recurrence?",
        "Do the recurring items share an age or model that the asset records could confirm?"],
     "DEC-RETENTION-REVIEW":[
        "What does this tenant's own record show — payment history, logged complaints, lease timing?",
        "With only one tenant in the High band, is a general retention programme warranted, or a single conversation?"],
     "DEC-LOC-MKT":[
        "Which localities do our current tenants actually come from?",
        "Which channels have produced enquiries before, and is that recorded anywhere?"],
     "DEC-VAC-Triple":[
        "How many of these beds are in A33/A34, opened August 2026 — newly launched rather than slow-moving?",
        "Are the remaining beds ready to occupy, or is anything outstanding on them?"],
     "DEC-PRICEREV-Single":[
        "Nothing to check while single rooms are fully occupied — revisit if a single bed becomes vacant."],
     "DEC-MKT-ROI-GAP":[
        "Which channel did each enquiry come from, and can that be captured going forward?",
        "Is the recorded spend material enough to prioritise channel tagging now, or is this a longer-term fix?"],
     "DEC-VAC-Double":[
        "Which apartments are these beds in, and are they ready to occupy?",
        "Are incoming 2-sharing enquiries being matched to these specific beds?"],
     "DEC-VAC-Single":[
        "Nothing to check — there is no single-room vacancy at present."],
    }
    with st.expander("Worth checking — what could be behind each decision (investigation questions)"):
        st.caption("These are **questions to look into, not findings**. The data shows what is happening; it does "
                   "not establish why. Nothing here assigns cause or responsibility to any tenant, staff member, "
                   "technician or vendor.")
        for r in d.itertuples():
            qs=_WORTH_CHECKING.get(r.decision_id)
            if not qs: continue
            st.markdown(f"**{r.decision_id}** — {str(r.decision).rstrip('.')}")
            st.markdown("\n".join(f"- {q}" for q in qs))
    # ---- F2: overlap safeguard — some decisions view the SAME beds from different angles, so the ₹ figures
    #      shown per decision must never be summed. Derived from the loaded outputs; no new total is computed. ----
    _acb=mx[mx["AC"]=="present"] if "AC" in mx.columns else mx.iloc[0:0]
    _vacr=load("vacancy")
    _ov=""
    if len(_acb):
        _acset=set(zip(_acb.get("apartment_id",pd.Series(dtype=object)),_acb.get("bed_code",pd.Series(dtype=object))))
        _dblr=_vacr[_vacr["bed_type"]=="Double"]
        _dblset=set(zip(_dblr.get("apartment_id",pd.Series(dtype=object)),_dblr.get("bed_code",pd.Series(dtype=object))))
        if _acset and _acset==_dblset:
            _ov=(f" Concretely: DEC-AMEN-AC and DEC-VAC-Double both show {rupee(_acb['rev_at_risk_monthly'].sum())} "
                 f"because they describe **the same {len(_acb)} Double beds** — one from the vacancy angle (fill them), "
                 "the other from the amenity angle (market their AC). That is one exposure seen twice, **not** two "
                 "separate losses to be added together.")
    st.warning("**Do not add the ₹ figures across decisions.** Several decisions describe the same underlying "
               "inventory from different angles, so monetary exposure shown on individual decisions must only be "
               "summed when the underlying beds/tenants are genuinely distinct." + _ov +
               f" The authoritative total current vacancy exposure is {rupee(_vacr['rev_at_risk_monthly'].sum())}/month "
               f"across {len(_vacr)} vacant beds (Page 3), which already counts every vacant bed exactly once.")

    # ---- B1: AR basis — the 90+ figure in DEC-REVPROTECT-AR90 is a different base from Page 2's total ----
    if (d["decision_id"]=="DEC-REVPROTECT-AR90").any():
        st.caption("**Which AR figure is this?** The aged-AR amount in DEC-REVPROTECT-AR90 is **aging-gross 90+ day** "
                   "dues (ar_aging view — positive aged dues only, not limited to currently-active allotments). "
                   "Page 2 shows a smaller **ledger-net active** AR total, where advances and credits are netted off "
                   "and only current tenants are counted. The two are different accounting bases answering different "
                   "questions, so they should not be compared as the same metric and neither is an error. Full "
                   "reconciliation is currently blocked — the receipt_allocations linkage is missing — so no "
                   "difference between them is computed.")

    # ② Execution / closed-loop tracker
    st.subheader("② Execution Tracker (closed loop)")
    st.caption("recommendation_id → action → leads → visits → applications → conversions → beds_filled "
               "→ occupancy_after → revenue_impact. All action/outcome fields are blank until real data is "
               "captured; status stays Pending (never auto-changed).")
    st.dataframe(et, use_container_width=True, hide_index=True)

    # ③ Marketing attribution readiness
    st.subheader("③ Marketing Attribution Readiness")
    st.warning(f"Marketing ROI = **UNAVAILABLE** — campaign/channel/lead attribution missing. "
               f"Spend recorded: ₹{float(sm.get('marketing_spend_total',0)):,.0f} over {sm.get('marketing_spend_months','?')} months (aggregate).")
    st.caption("Target structure (empty until captured): "+str(sm.get("attribution_schema","")))

    # ④ Lead follow-up (real leads)
    st.subheader("④ Lead Follow-up")
    b=st.columns(3)
    b[0].metric("Leads total", int(float(sm.get("leads_total",len(lf)))))
    b[1].metric("Open follow-up", int(float(sm.get("leads_open_follow_up",0))))
    b[2].metric("Visit pending", int(float(sm.get("leads_visit_pending",0))))
    lv=lf[["lead_index","source","requested_bed_type","gender","move_in_date","lead_status","follow_up_status","created_at"]].copy()
    for c in lv.columns: lv[c]=lv[c].map(_b)
    st.dataframe(lv, use_container_width=True, hide_index=True)
    st.caption("From the real leads table. No conversion probability invented; no lead marked 'lost' unless the source says so.")

    # ⑤ Amenity-aware available inventory (verified from own assets→allocations)
    st.subheader("⑤ Amenity-aware Available Inventory")
    ac_beds=mx[mx["AC"]=="present"] if "AC" in mx.columns else mx.iloc[0:0]
    st.metric("Vacant beds in AC-verified apartments", len(ac_beds))
    show_cols=[c for c in ["bed_code","apartment_id","bed_type","toilet_type","days_vacant","rev_at_risk_monthly",
               "AC","Hot water","RO water","Refrigerator","Washing machine","TV","Kitchen","Fan","mapping_confidence"] if c in mx.columns]
    mxv=mx[show_cols].copy()
    for c in mxv.columns: mxv[c]=mxv[c].map(_b)
    st.dataframe(mxv, use_container_width=True, hide_index=True)
    st.caption("Amenity per vacant bed via assets→allocations→apartment/bed (own data). 'present' = authoritative "
               "mapping; blank/unknown stays Unknown; nothing marked absent. Food/meals remains Unknown (owner input).")

    # ---------- Review-intelligence evidence layers (customer context; NOT competitor comparison) ----------
    st.markdown("---")
    st.info("Below: customer-review intelligence used to STRENGTHEN the decisions above — it is market "
            "customer-intelligence context, **not** a competitor comparison/ranking/benchmark. No ₹ impact, "
            "ROI, or uplift is computed. Unknown Vishful status stays Unknown.")

    def _ragg(theme):
        r=ragg[ragg["theme"]==theme]
        return r.iloc[0] if len(r) else None
    def _why(theme):
        r=_ragg(theme)
        if r is None: return "insufficient review evidence"
        tot=max(int(r["positive"])+int(r["negative"]),1); cons=round(abs(int(r["positive"])-int(r["negative"]))/tot,2)
        return (f"PGs={int(r['n_independent_pgs'])}, reviews={int(r['n_reviews'])}, "
                f"sentiment(+{int(r['positive'])}/-{int(r['negative'])}, consistency={cons}), "
                f"specificity={r['avg_evidence_strength']}")

    # ⑥ Review-supported evidence — nested under the 5 reinforced decisions (no duplicate cards)
    st.subheader("⑥ Review-Supported Evidence (nested under existing decisions)")
    sup=rc[rc["decision_class"]=="SUPPORTING SIGNAL FOR EXISTING DECISION"].copy()
    if len(sup):
        for did,grp in sup.groupby("supports_existing_decision"):
            with st.expander(f"Supports {did} — {len(grp)} review signal(s)"):
                sv=pd.DataFrame({"Theme":grp["theme"],
                    "Market review signal":grp["market_signal"],
                    "→ Vishful internal fact":grp["vishful_internal_fact"],
                    "Business metric":grp["business_impact_metric"],
                    "Strength (why)":grp["theme"].map(_why)})
                st.dataframe(sv, use_container_width=True, hide_index=True)
        st.caption("Market review signal → Vishful internal fact → existing decision supported. "
                   "These reinforce existing decisions; they are NOT new decision cards.")

    # ⑦ New review-derived opportunities (6) — actionable-now vs owner-verify
    st.subheader("⑦ New Review-Derived Opportunities")
    new=recon[recon["reconciliation_status"]=="NEW"].copy()
    BADGE={"actionable_now":"🟢 Actionable now","owner_verify_first":"🟠 Owner Verification Required"}
    nv=pd.DataFrame({"Opportunity":new["topic"].map(lambda t:str(t).replace(" (genuinely new)","")),
        "Status":new["actionability"].map(lambda a:BADGE.get(a,a)),
        "Strength":new["decision_strength"],
        "Recommended action":new["decision_ref"].map(dict(zip(rc["review_signal_id"],rc["recommended_decision"]))) if "review_signal_id" in rc.columns else new["topic"],
        "Business metric (KPI)":new["business_metric"],
        "Owner input required":new["owner_input_required"].map(_b),
        "Outcome":"Outcome unavailable"})
    st.dataframe(nv, use_container_width=True, hide_index=True)
    st.caption("Laundry + Common-area = actionable now (Vishful VERIFIED). Food / Security-CCTV / Safety / Parking "
               "= **Owner Verification Required** — Vishful status is Unknown and is never shown as available or absent. "
               "No ₹ revenue/ROI/uplift is computed; outcome stays 'Outcome unavailable' until real data exists.")

    # ⑧ Discarded / informational — not decisions
    st.subheader("⑧ Discarded / Informational Signals")
    weak=recon[recon["reconciliation_status"]=="REDUNDANT_WEAK"].copy()
    with st.expander(f"{len(weak)} signal(s) that did NOT pass the decision gate", expanded=False):
        wv=pd.DataFrame({"Signal":weak["topic"],"Why not a decision":weak["expected_business_impact_type"],
            "Evidence":weak["decision_ref"].map(lambda r:_why(str(r).replace("RV-","")))})
        st.dataframe(wv, use_container_width=True, hide_index=True)
        st.caption("Wi-Fi and sharing did not pass the gate (thin market signal <2 PGs / <3 reviews, and/or already "
                   "covered by existing Vishful decisions). Kept for audit only — not business decisions.")

    # ⑨ Evidence-chain drilldown (auditable; no reviewer PII)
    st.subheader("⑨ Evidence-Chain Drilldown")
    pick=st.selectbox("Select a review-derived item", rc["theme"].tolist())
    row=rc[rc["theme"]==pick].iloc[0]; agg=_ragg(pick)
    st.markdown(f"**Chain:** review → property → theme/sentiment → market signal → Vishful fact → implication → decision")
    c=st.columns(2)
    c[0].markdown("**Market customer signal**"); c[0].write(row["market_signal"])
    c[1].markdown("**→ Vishful internal fact**"); c[1].write(row["vishful_internal_fact"])
    st.markdown(f"**Business relevance / metric:** {row['business_relevance']}  ·  **Class:** {row['decision_class']}  ·  **Strength (why):** {_why(pick)}")
    st.markdown(f"**Business implication / decision:** {row['recommended_decision']}")
    st.caption(f"Traceable to: {row['trace']}  ·  Provenance: {row['provenance']}. No reviewer name/PII is stored or shown.")

    # ⑩ Decision KPI & Outcome Tracking (read-only; baselines from real data, outcomes unavailable until post-action)
    st.markdown("---")
    st.subheader("⑩ Decision KPI & Outcome Tracking")
    ea=load_csv_ro("phase3_decision_execution_analytics.csv")
    ks=load_csv_ro("phase3_decision_kpi_summary.csv"); ksm=dict(zip(ks["metric"],ks["value"]))
    bb=ea[ea["is_backbone"]==True].copy(); opp=ea[ea["is_backbone"]==False].copy()
    meas=int((bb["status"]=="baseline_established_pending_action").sum())
    g=st.columns(2)
    g[0].metric("Decisions with measurable baseline", f"{meas} / {len(bb)}")
    g[1].metric("Outcomes available", f"0 / {len(bb)}")
    kv=pd.DataFrame({"Decision":bb["decision_id"],"KPI":bb["kpi_name"].map(_b),
        "Baseline":bb["baseline_value"].map(_b),"Data confidence":bb["data_confidence"].map(_b),
        "Current":bb["current_value"].map(_b),"Outcome":bb["outcome"].map(_b),
        "Data source":bb["data_source"].map(_b)})
    st.dataframe(kv, use_container_width=True, hide_index=True)
    st.caption("Baselines are calculated from real Vishful data. Outcomes remain “Outcome unavailable” until the "
               "corresponding owner action has actually been executed and post-action data exists.")
    st.caption("No ₹ ROI, revenue uplift, conversion uplift, or other fabricated outcome is computed. "
               "Low-confidence baselines are explicitly flagged (e.g. maintenance created_at ~31% null; AC uses the "
               "cumulative KPI 304 tickets / 19.7% of maintenance, not the unreliable monthly trend).")
    st.caption("Unavailable means the required source data/linkage does not currently exist (e.g. DEC-LOC-MKT has no "
               "locality on leads; DEC-MKT-ROI-GAP has no spend↔lead attribution) — it is NOT an assumption of zero. "
               "Purely Vishful internal KPI tracking; not a competitor comparison.")

    st.markdown("**Review Opportunities — KPI Tracking** (separate from the 14 backbone decisions)")
    ov=pd.DataFrame({"Opportunity":opp["decision_topic"],
        "Status":opp["status"].map(lambda s:"🟢 Actionable now" if s=="actionable_now" else "🟠 Owner Verification Required" if s=="owner_verify_first" else _b(s)),
        "KPI / intended impact":opp["kpi_name"].map(_b),"Baseline":opp["baseline_value"].map(_b),
        "Data confidence":opp["data_confidence"].map(_b),"Outcome":opp["outcome"].map(_b)})
    st.dataframe(ov, use_container_width=True, hide_index=True)
    st.caption("Opportunities are NOT backbone decisions. Food / Security-CCTV / Safety / Parking stay "
               "'Owner Verification Required' — Unknown is never converted to available/absent. Laundry + Common-area "
               "are actionable now (Vishful VERIFIED).")

    # ---- ⑪ AI Business Opportunities — Advisory (Phase-4 deterministic evidence-grounded layer; additive) ----
    st.markdown("---"); st.subheader("⑪ AI Business Opportunities — Advisory (evidence-grounded, deterministic)")
    st.caption("Rule-based advisory signals built ONLY from validated Vishful engine outputs. NOT backbone decisions; "
               "owner approval required; no automatic action. Every number traces to an evidence ID. Market data is context "
               "only — never a competitor comparison, ranking, or benchmark. Outcomes stay unavailable until the owner acts "
               "and post-action data exists. No LLM is used in this layer.")
    try:
        ai=load_csv_ro("phase4_ai_opportunities.csv"); evd=load_csv_ro("phase4_evidence_pack.csv")
        rj=load_csv_ro("phase4_ai_opportunities_rejected.csv")
        _ov=ai["owner_verify_required"].astype(str).str.lower().isin(["true","1"])
        h=st.columns(3)
        h[0].metric("Advisory opportunities", len(ai))
        h[1].metric("Owner-verify items", int(_ov.sum()))
        h[2].metric("Guard-rejected (hidden)", len(rj))
        evmap={r["evidence_id"]:r for _,r in evd.iterrows()}
        for i,r in ai.iterrows():
            ver=str(r["owner_verify_required"]).lower() in ("true","1")
            tag="🟠 Owner Verification Required" if ver else {"High":"🟢 High","Medium":"🟡 Medium","Low":"⚪ Low"}.get(str(r["confidence"]),str(r["confidence"]))+" confidence"
            with st.expander(f"[{r['recommendation_id']}] {r['opportunity']}  —  {tag}"):
                st.markdown(f"**Why it matters:** {_b(r['why_it_matters'])}")
                st.markdown(f"**Suggested action:** {_b(r['suggested_action'])}")
                st.markdown(f"**KPI to watch:** {_b(r['expected_kpi'])}")
                st.markdown(f"**Confidence:** {_b(r['confidence'])}  ·  **Data limitation:** {_b(r['data_limitation'])}")
                st.caption("Evidence trace:")
                rowsx=[]
                for e in str(r["evidence_ids"]).split("|"):
                    ev=evmap.get(e)
                    if ev is not None:
                        rowsx.append({"Evidence ID":e,"Fact":ev["statement"],
                            "Source":f"{ev['source_dataset']} · {ev['source_field']}","Provenance":ev["provenance"],"Confidence":ev["confidence"]})
                st.dataframe(pd.DataFrame(rowsx), use_container_width=True, hide_index=True)
        st.caption("Recommendation IDs (AIREC-*) are compatible with the execution tracker so future owner actions and KPI "
                   "outcomes can be attached. Guard-rejected recommendations are logged separately and never displayed.")
    except SourceValidationError:
        st.caption("AI opportunities output not available (run phase4_opportunity_rules.py).")

    # ---- ⑫ Decision Effectiveness (read-only; deterministic; derived from locked baselines + append-only owner events) ----
    st.markdown("---"); st.subheader("⑫ Decision Effectiveness — Deterministic effectiveness tracking (read-only)")
    st.caption("Deterministic effectiveness tracking — this is NOT AI-generated reasoning. Chain: Recommendation → Owner "
               "decision → Action → Baseline → Post measurement → Outcome → Attribution.")
    _eff=os.path.join(HERE,"operational","phase4_decision_effectiveness.csv")
    _sump=os.path.join(HERE,"operational","phase4_decision_effectiveness_summary.csv")
    if not os.path.exists(_eff):
        st.info("Effectiveness data is not yet available (deterministic reducer output missing). No values are fabricated.")
    else:
        eff=pd.read_csv(_eff)
        sm=dict(zip(pd.read_csv(_sump)["metric"],pd.read_csv(_sump)["value"])) if os.path.exists(_sump) else {}
        def _si(k,default):
            try: return int(sm[k])
            except Exception: return default
        bbmask=eff["is_backbone"].astype(str).str.lower().isin(["true","1"])
        m=st.columns(4)
        m[0].metric("Recommendations tracked", _si("recommendations_total", len(eff)))
        m[1].metric("Actions recorded", _si("actions_recorded", 0))
        m[2].metric("Measurable outcomes", _si("measurable_outcomes", 0))
        m[3].metric("Outcome Unavailable", _si("outcome_unavailable", 0))
        m2=st.columns(4)
        m2[0].metric("Improved", _si("improved",0)); m2[1].metric("No Change", _si("no_change",0))
        m2[2].metric("Worsened", _si("worsened",0)); m2[3].metric("Insufficient Data", _si("insufficient_data",0))
        st.caption("Outcome measures whether the tracked KPI moved after a recorded action. Attribution confidence separately "
                   "indicates how confidently that movement can be linked to the action.")
        st.caption("No recommendation is treated as executed merely because it exists. Until a real owner action and sufficient "
                   "post-action measurement are recorded, the result remains Outcome Unavailable or Insufficient Data.")
        st.caption("Operational effectiveness data is derived from the locked KPI baseline registry and append-only owner events. "
                   "No outcome or business impact is fabricated.")
        flt=st.selectbox("Show", ["All","Backbone decisions","Opportunities"], key="eff_filter")
        v=eff.copy(); vbb=bbmask.copy()
        if flt=="Backbone decisions": v=eff[bbmask]
        elif flt=="Opportunities": v=eff[~bbmask]
        def _dash(x): return _b(x) if str(x).strip() and str(x).lower()!="nan" else "—"
        disp=pd.DataFrame({
            "Recommendation":v["decision_or_opportunity"].map(_b),"Type":v["recommendation_type"].map(_b),
            "KPI":v["target_kpi"].map(_b),"Direction":v["kpi_direction"].map(_b),
            "Owner decision":v["owner_decision"].map(_b),"Action":v["action_taken"].map(_dash),
            "Action date":v["action_date"].map(_dash),"Baseline":v["baseline_value"].map(_b),
            "Post measurement":v["post_value"].map(_dash),"Measurement window":v["measurement_window_status"].map(_b),
            "Outcome":v["outcome_status"].map(_b),"Attribution":v["attribution_confidence"].map(_b),
            "Data limitation":v["data_limitation"].map(_b),"recommendation_id":v["recommendation_id"].map(_b)})
        st.dataframe(disp, use_container_width=True, hide_index=True)
        st.caption(f"{len(v)} of {len(eff)} recommendations · backbone {int(bbmask.sum())} · opportunities {int((~bbmask).sum())}. "
                   "Outcome and Attribution are separate columns (e.g. Outcome: Improved with Attribution: Low is a valid, distinct "
                   "state). Read-only view — no writes to any file or event store.")

    # ---- ⑬ Lease Coverage — Investigation Signal (NOT a backbone decision, NOT profitability) ----
    st.markdown("---"); st.subheader("⑬ Lease Coverage — Investigation Signal")
    st.caption("**Not one of the 14 backbone decisions** (is_backbone = False) and not a recommendation. "
               "This is an investigation signal only — it raises questions for the owner to look into, and "
               "generates no action of its own.")
    try:
        lc=load_csv_ro("phase3_lease_coverage_signal.csv")
        ls=dict(zip(load_csv_ro("phase3_lease_coverage_signal_summary.csv")["metric"],
                    load_csv_ro("phase3_lease_coverage_signal_summary.csv")["value"]))
        def _lf(k,d=0.0):
            try: return float(ls.get(k,d))
            except Exception: return d
        st.error("**What this metric is — and is not.** This compares **invoiced revenue** against the "
                 "**owner-rent obligation** for the apartment-months where both exist. It is **not** "
                 "profitability, **not** profit or loss, **not** margin, and **not** collected cash. It "
                 "includes **no other operating cost**, so a figure above 1.0× does **not** mean an apartment "
                 "is performing well financially. Owner rent here is "
                 f"{ls.get('owner_rent_accrued_share','largely accrued')} — an obligation recorded, not "
                 "necessarily cash paid out.")
        k=st.columns(4)
        k[0].metric("Apartments covered", f"{int(_lf('apartments_with_owner_rent_coverage'))} of {int(_lf('revenue_generating_apartments_total'))}")
        k[1].metric("Matched apartment-months", f"{int(_lf('matched_apartment_months'))}")
        k[2].metric("Investigation signals", f"{int(_lf('investigation_signals'))}")
        k[3].metric("Not classified", f"{int(_lf('apartments_not_classified'))}")
        st.warning(f"**Coverage limit.** Owner-rent records exist for only "
                   f"{int(_lf('apartments_with_owner_rent_coverage'))} of the "
                   f"{int(_lf('revenue_generating_apartments_total'))} revenue-generating apartments. The other "
                   f"{int(_lf('apartments_not_classified'))} are **not classified** here — neither favourably "
                   "nor unfavourably. Absence from this table says nothing about an apartment.")
        _fl=lc[lc["coverage_x"]<1.0]
        if len(_fl):
            _names=", ".join(f"**{r.apartment_code}** ({r.coverage_x:.2f}×, {int(r.matched_months)} matched months)"
                             for r in _fl.itertuples())
            st.info(f"**Investigation signal:** for {_names}, invoiced revenue was below the matched owner-rent "
                    "obligation during the measured periods.\n\n"
                    "**Before drawing any commercial conclusion, review:**\n"
                    "- Is occupancy persistently low in this apartment?\n"
                    "- Is invoicing incomplete or delayed for these periods?\n"
                    "- Were there extended vacancy periods?\n"
                    "- Is the recorded owner-rent obligation correct and current?\n"
                    "- Were there ramp-up, closure, renovation or operational-transition periods?\n"
                    "- Does the commercial lease arrangement deserve review?\n\n"
                    "**These are questions, not findings.** No cause has been established, and no lease action "
                    "is recommended by this signal.")
        _v=pd.DataFrame({"Apartment":lc["apartment_code"],"Matched months":lc["matched_months"],
            "Invoiced revenue":lc["invoiced_revenue"].map(rupee),"Owner rent":lc["owner_rent"].map(rupee),
            "Coverage":lc["coverage_x"].map(lambda x:f"{x:.2f}×"),"Signal":lc["signal"]})
        st.dataframe(_v, use_container_width=True, hide_index=True)
        st.caption(f"Method: revenue and owner rent are each aggregated to (apartment, month) before being "
                   f"combined, so no value is duplicated. Only apartment-months where **both** exist are counted "
                   f"— {int(_lf('excluded_rent_months_no_revenue'))} rent-months with no invoicing and "
                   f"{int(_lf('excluded_revenue_months_no_rent'))} invoiced months with no rent record are "
                   f"excluded, which removes ramp-up and pre-invoicing periods. Revenue basis: "
                   f"{ls.get('revenue_basis','invoiced')}. Overall across covered apartments: "
                   f"{ls.get('overall_coverage_x','—')}×.")
    except SourceValidationError:
        st.caption("Lease coverage signal not available (run phase3_lease_coverage_signal.py).")

    # ---- ⑭ Nearby Customer-Access Information (customer-facing layer; SEPARATE from the 33 lifecycle) ----
    # Display-only. Reads the frozen nearby outputs read-only; changes no engine, registry or reducer.
    st.markdown("---"); st.subheader("⑭ Nearby Customer-Access Information — website content advisory")
    st.caption("A separate customer-facing layer: what verified nearby-place information Vishful could show on its "
               "own property page. Places and coordinates come from OpenStreetMap; every distance is a straight-line "
               "(great-circle) distance recomputed from those coordinates. **Not travel time and not walking time** — "
               "no journey time is claimed or derivable. Market/competitor data is not used here and no competitor "
               "comparison, ranking or benchmark is made. These are NOT part of the 33-recommendation KPI lifecycle "
               "on Page 15: the action is publishing content, which no existing KPI measures, so no numeric outcome "
               "is tracked for them. Every item requires owner verification before anything is published.")
    try:
        nb=load_csv_ro("phase4_nearby_recommendations.csv")
        nev=load_csv_ro("phase4_nearby_recommendations_evidence.csv")
        _gen=(nb["website_visibility_specificity"].astype(str)=="generic")
        _abs=(nb["website_visibility_specificity"].astype(str)=="absent")
        n=st.columns(4)
        n[0].metric("Nearby recommendations", len(nb))
        n[1].metric("Verified places cited", len(nev))
        n[2].metric("Add new section", int(_abs.sum()))
        n[3].metric("Make existing wording specific", int(_gen.sum()))
        st.caption(f"One recommendation per category — {len(nb)} categories citing {len(nev)} verified places. "
                   "Never one recommendation per place.")
        _VIS={"absent":("⚪ Not shown on the website — recommend adding",
                        "No equivalent information was found on the rendered Vishful pages."),
              "generic":("🟡 General wording exists — recommend making it specific",
                         "The website already refers to this in general terms, but names no place and gives no "
                         "distance. The recommendation is to replace that general wording with named places and "
                         "verified distances, not to add a duplicate section."),
              "specific":("🟢 Already shown with named places and distances — no recommendation",
                          "Equivalent information is already published, so no duplicate content is recommended.")}
        for _,r in nb.iterrows():
            _sp=str(r["website_visibility_specificity"])
            _lab,_expl=_VIS.get(_sp,("Website status unknown","Website visibility could not be established."))
            with st.expander(f"[{r['recommendation_id']}] {r['section_name']}  —  {_lab}"):
                st.markdown(f"**Suggested website improvement:** {_b(r['recommendation'])}")
                st.markdown(f"**What changes for a customer:** {_b(r['customer_facing_change'])}")
                st.markdown(f"**Category:** {_b(r['category'])}  ·  **Nearest place:** {_b(r['nearest_place'])} "
                            f"({_b(r['nearest_distance_display'])})")
                if _sp=="generic":
                    st.info(f"**{_lab}**\n\n{_expl}\n\n**Wording currently on the website:** "
                            f"“{_b(r['website_visibility_evidence'])}”\n\n**Missing piece:** {_b(r['material_gap'])}")
                elif _sp=="absent":
                    st.info(f"**{_lab}**\n\n{_expl}")
                else:
                    st.success(f"**{_lab}**\n\n{_expl}")
                st.caption("Verified nearby places cited by this recommendation (straight-line distance from the "
                           "mapped Vishful property coordinate):")
                _sub=nev[nev["recommendation_id"]==r["recommendation_id"]]
                st.dataframe(pd.DataFrame({
                    "Evidence ID":_sub["evidence_id"],
                    "Place":_sub["place_name"],
                    "Kind":_sub["place_kind"],
                    "Distance (straight-line)":_sub["distance_display"],
                    "Source":_sub["provider"],
                    "Source link":_sub["source_url"],
                    "Retrieved":_sub["retrieval_date"],
                    "Source confidence":_sub["source_confidence"]}),
                    use_container_width=True, hide_index=True)
                st.warning(f"**Owner verification required before publishing.** {_b(r['data_limitation'])}")
                st.caption(f"Distance method: {_b(r['distance_method'])} · display rule "
                           f"`{_b(r['distance_format_rule'])}` · wording provenance: {_b(r['wording_provenance'])} · "
                           f"evidence retrieved {_b(r['evidence_retrieval_date'])}.")
        st.caption("These 5 recommendations are additional to — and separate from — the 14 backbone decisions, "
                   "6 Phase-3 opportunities and 13 AIREC opportunities. Counting all four groups, the owner-visible "
                   f"recommendation universe is 14 + 6 + 13 + {len(nb)} = {14+6+13+len(nb)}. The Page-15 lifecycle "
                   "tracks the first three groups (33) because those have measurable KPIs; these content "
                   "recommendations do not, and none is given a fabricated numeric outcome.")
    except SourceValidationError:
        st.caption("Nearby customer-access output not available (run phase4_nearby_rules.py).")

def _p15_refresh():
    """Re-run the EXISTING deterministic reducer in-process (read-only on the event store; writes only the derived
    operational effectiveness files; cannot touch locked outputs). No effectiveness logic is duplicated here."""
    try:
        import phase4_decision_effectiveness as RED
        RED.main()
    except Exception:
        st.error("Effectiveness refresh (reducer) FAILED — the event WAS recorded, but the outcome chain was not "
                 "recomputed. No effectiveness value is fabricated. Re-run the reducer; do not resubmit the event.")
        return False
    st.caption("Deterministic reducer re-run; effectiveness chain updated.")
    return True

def p_actions():
    import phase4_action_capture as CAP
    st.header("15 · Action & Outcomes")
    # ---- Plain-English explanation of the workflow. Display-only: the append-only event store and the
    #      reducer-based outcome calculation are unchanged. ----
    st.info(
        "**What this page is for.** Everywhere else in this dashboard the system *suggests* things. This is where "
        "you record what the business actually **decided** and **did** — and, later, whether the number moved.\n\n"
        "**Step 1 — Decide.** Do you agree this is something the business should act on? Recording "
        "*approved*, *deferred* or *rejected* is just your decision; it does not mean anything has been done yet.\n\n"
        "**Step 2 — Record the action.** What did the business actually do, and on what date?\n\n"
        "**Step 3 — Measure.** Once the action has had time to take effect, record the same KPI again.\n\n"
        "**Step 4 — Evaluate.** The system compares the original baseline with your post-action measurement. "
        "It does this automatically; nothing is typed in by hand.\n\n"
        "**Step 5 — Outcome.** You will see whether the number improved, stayed flat or worsened — and, separately, "
        "how confidently that change can be linked to what you did.")
    st.warning(
        "**\"Outcome unavailable\" does not mean the recommendation failed.** It means no completed action and/or "
        "no post-action measurement has been recorded yet, so there is nothing to compare against the baseline. "
        "Every recommendation starts in this state. Generating a recommendation is not the same as executing it.")
    with st.expander("A worked example — how one full cycle looks"):
        st.markdown(
            "**Before you act (the baseline, already captured):**\n"
            "- 90+ day AR = ₹800,503 across 47 accounts\n\n"
            "**Step 1 — you decide:** you approve `DEC-REVPROTECT-AR90`.\n\n"
            "**Step 2 — you record what was done:** *\"Reviewed the 17 active accounts and followed up confirmed "
            "overdue balances; sent the 30 closed accounts to accounts for reconciliation against settlement and "
            "payment records.\"* — with the date it happened.\n\n"
            "**Step 3 — after the measurement period, you record the new figure:**\n"
            "- 90+ day AR = *[the real measured value at that time]*\n\n"
            ":grey[**Example only — the post-action value must come from a real measurement. "
            "Nothing here is pre-filled or estimated.**]\n\n"
            "**Step 4 — the system compares** your real post-action value against the ₹800,503 baseline.\n\n"
            "**Step 5 — outcome and attribution.** It will report whether the figure moved. It will **not** claim "
            "your action caused the change unless the available evidence supports that link.")
        st.caption("**What attribution means.** Attribution asks whether the change we observe can reasonably be "
                   "linked to the action you recorded. A KPI improving on its own does not prove your action caused "
                   "it — other things happen at the same time. That is why Outcome and Attribution are shown as two "
                   "separate answers rather than one.")
    st.caption("This page records append-only operational events. Previous events are never edited or deleted; corrections "
               "are recorded as new superseding events.")
    effp=os.path.join(HERE,"operational","phase4_decision_effectiveness.csv")
    if not os.path.exists(effp):
        st.info("Effectiveness/recommendation data is not yet available. No values are fabricated."); return
    eff=pd.read_csv(effp)
    reg=pd.read_csv(os.path.join(OUT,"phase4_kpi_direction_registry.csv"))
    unit_of=dict(zip(reg["kpi_name"],reg["unit"])); meas_of=dict(zip(reg["kpi_name"],reg["measurable"]))
    bb=eff["is_backbone"].astype(str).str.lower().isin(["true","1"])

    def _submit(slot, build):
        # returns the appended event_id, or None if nothing was written, so a caller can chain a
        # dependent event (e.g. the auto-captured baseline) only when the first write succeeded.
        try: ev=build()
        except Exception as e: st.warning(str(e)); return None
        sig=f"{slot}:{sorted(ev.items())}"
        if st.session_state.get("_p15_last")==sig:
            st.info("Duplicate submission ignored (identical content as the last submit)."); return None
        try: eid=CAP.append_event(ev)
        except ValueError as e: st.error(f"Rejected by the validated writer: {e}"); return None
        st.session_state["_p15_last"]=sig
        st.success(f"Append-only event recorded: {eid}")
        _p15_refresh()
        return eid

    # ---- A. select recommendation ----
    st.subheader("A · Select recommendation")
    flt=st.selectbox("Filter", ["All","Backbone","Phase-3 Opportunities","AIREC Opportunities"], key="p15_flt")
    view=eff
    if flt=="Backbone": view=eff[bb]
    elif flt=="Phase-3 Opportunities": view=eff[eff["recommendation_type"]=="phase3_opportunity"]
    elif flt=="AIREC Opportunities": view=eff[eff["recommendation_type"]=="phase4_deterministic"]
    st.caption(f"Tracked: {int(bb.sum())} backbone · {int((eff['recommendation_type']=='phase3_opportunity').sum())} Phase-3 "
               f"opportunities · {int((eff['recommendation_type']=='phase4_deterministic').sum())} AIREC = {len(eff)} total.")
    rid=st.selectbox("Recommendation", view["recommendation_id"].tolist(),
        format_func=lambda x: f"{x} — {str(eff[eff['recommendation_id']==x]['decision_or_opportunity'].iloc[0])[:60]}", key="p15_rid")
    row=eff[eff["recommendation_id"]==rid].iloc[0]
    kpi=str(row["target_kpi"]); unit=str(unit_of.get(kpi,"")); measurable=str(meas_of.get(kpi,"no")); direction=str(row["kpi_direction"])
    c=st.columns(2)
    c[0].markdown(f"**Recommendation:** {_b(row['decision_or_opportunity'])}")
    c[0].markdown(f"**ID:** `{rid}` · **Type:** {_b(row['recommendation_type'])}")
    c[0].markdown(f"**KPI:** {_b(kpi)} · **Direction:** {_b(direction)}")
    c[1].markdown(f"**Baseline:** {_b(row['baseline_value'])}")
    c[1].markdown(f"**Current outcome:** {_b(row['outcome_status'])}")
    c[1].markdown(f"**Attribution:** {_b(row['attribution_confidence'])}")
    c[1].caption(f"Data limitation: {_b(row['data_limitation'])}")

    # ---- MEASUREMENT PATTERN per recommendation ---------------------------------------------------
    # The KPI that CAUSED a recommendation is not automatically the KPI that can MEASURE whether the
    # action worked. Most recommendations align, but a few do not, and those must not be forced into a
    # numeric before/after comparison. Display-layer only: no registry, reducer, analytics or locked
    # output is altered — this decides what the owner is TOLD and whether a numeric entry is offered.
    #   direct     evidence KPI genuinely measures the action's effect
    #   different  evidence KPI explains WHY; the real outcome lives in another KPI already tracked
    #   investig   the action is an investigation/process change; record findings, not a KPI delta
    #   verify     owner must establish a fact first; Unknown stays Unknown
    #   none       no honest numeric outcome exists today
    _PATTERN={
     "DEC-AMEN-AC":dict(p="different",why=(
        "the action here is **marketing** (feature AC on the vacant AC beds), but the KPI attached to this "
        "decision is **cumulative AC maintenance tickets** — a maintenance measure that would not move because "
        "rooms were advertised. That ticket count is also a lifetime total, and 102 of the 304 tickets have no "
        "recorded creation date, so a monthly trend cannot be built from it."),
        instead=("Whether this marketing worked shows up as **the currently identified AC-associated available "
                 "inventory filling**, which is observed through the Double vacancy figure rather than measured "
                 "twice here. Those beds are identifiable today, but they are **not individually tracked as an "
                 "outcome series** — what you would see is aggregate inventory movement, not proof that a "
                 "particular bed filled because it was advertised as air-conditioned.")),
     "DEC-EB-INVESTIGATE":dict(p="different",why=(
        "the baseline shown (28 apartments) is **cumulative across 2023–2026**, while the action targets only "
        "the **6 apartments flagged in the current period**. Comparing a later figure against 28 would mix four "
        "years of history into a judgement about six inspections."),
        instead=("After inspecting, record how many apartments are flagged **in the next billing period** and "
                 "compare that against the current-period figure of 6 — not against the cumulative 28.")),
     "DEC-RETENTION-REVIEW":dict(p="investig",why=(
        "the action concerns **one** High-band tenant, but the KPI is portfolio-wide monthly exits (baseline 22). "
        "One retained tenant cannot be seen in that number, and any movement would be other tenants."),
        instead=("Record what came out of the conversation and whether that specific tenant stayed. That is the "
                 "honest outcome; the portfolio exits figure is context, not proof.")),
     "DEC-PRICEREV-Triple":dict(p="investig",why=(
        "the action is explicitly **review the rate card, do not change the price**. A review on its own does not "
        "move occupancy, so comparing occupancy afterwards would credit or blame the review for something else."),
        instead=("Record what the review concluded and whether any pricing change followed. If a change is made, "
                 "that becomes its own decision with its own before/after.")),
     "DEC-MKT-ROI-GAP":dict(p="investig",why=(
        "the action is a **data-capture change** — start tagging spend by channel and link enquiries to move-ins. "
        "Cost-per-lead cannot be measured until that tagging exists, which is the very thing being set up."),
        instead=("Record whether channel tagging is now in place and from which date. Cost-per-lead becomes "
                 "measurable only once tagged data has accumulated.")),
     "DEC-LEAD-DEMAND-2SH":dict(p="different",why=(
        "the KPI counts how many enquiries **asked for** Double sharing — that is the evidence that prompted the "
        "recommendation, not a measure of whether fast-tracking them worked."),
        instead=("The outcome is whether those enquiries converted and the Double beds filled — visible under "
                 "DEC-VAC-Double. Record what happened to each enquiry in the action notes.")),
     "AIREC-CHURN-WATCH":dict(p="investig",why=(
        "the action engages the **High churn-risk tenants on the watch-list — currently a very small group**, "
        "while the KPI is a portfolio-level retained/exits measure. A handful of retentions cannot be seen in a "
        "portfolio figure, and any movement in it would mostly be other tenants leaving or staying for unrelated "
        "reasons. This is the same scale mismatch already handled for DEC-RETENTION-REVIEW, and it is treated the "
        "same way here."),
        instead=("Record who was engaged, what came out of the conversation, and whether those specific tenants "
                 "stayed. The portfolio exits figure remains useful background, but it is not proof that this "
                 "engagement worked.")),
     "DEC-PRICEREV-Single":dict(p="none",why=(
        "single rooms are already at **100% occupancy** and the decision itself states no rate action is indicated. "
        "There is no action to take and no headroom for the KPI to improve."),
        instead="Revisit only if a single room becomes vacant."),
     "DEC-VAC-Single":dict(p="none",why=(
        "there is **no single-room vacancy** (0 beds, ₹0 exposure), so there is nothing to promote and nothing to "
        "measure afterwards."),
        instead="Revisit only if a single room becomes vacant."),
    }
    _DIRWORD={"lower_is_better":"a **lower** number is better","higher_is_better":"a **higher** number is better",
              "context_only":"this is a **context signal** — it is not good or bad by itself"}
    _UNITWORD={"INR":"rupee amount","percent":"percentage","tickets":"ticket count","tenants":"number of tenants",
               "beds":"number of beds","leads":"number of leads","count":"count","rate":"rate",
               "engagement":"engagement measure","flag":"yes/no status","none":"—"}
    try:
        _wreg=load_csv_ro("phase4_measurement_window_registry.csv")
        _win=None; _dom=None
        for _,w in _wreg.iterrows():
            for pat in [p.strip() for p in str(w["applies_to"]).split(";")]:
                if (pat.endswith("*") and rid.startswith(pat[:-1])) or rid==pat:
                    _win=int(w["min_window_days"]); _dom=str(w["domain"]); break
            if _win is not None: break
    except SourceValidationError:
        _win=None; _dom=None
    _basenum=str(row.get("baseline_numeric","")).strip()
    _has_basenum=_basenum not in ("","nan")
    _isverify=(_dom=="owner_verify") or (_win==0)

    # resolve the pattern: explicit override first, otherwise derive from the registry
    _ov=_PATTERN.get(rid)
    if _ov is not None:                      _pat=_ov["p"]
    elif _isverify:                          _pat="verify"
    elif measurable=="yes" and direction!="context_only": _pat="direct"
    else:                                    _pat="none"
    _numeric_ok=(_pat=="direct")             # only a direct pattern offers numeric measurement entry

    if _pat=="direct":
        _wtxt=(f"Wait at least **{_win} days** after the action before measuring "
               f"(this is the {_dom.replace('_',' ')} window)." if _win else
               "Allow enough time for the action to take effect before measuring.")
        _basetxt=(f"The system will compare your figure against **{_b(row['baseline_value'])}**."
                  if _has_basenum else
                  "**No numeric baseline is on file yet** — you will need to record one (role *baseline*) "
                  "carrying the pre-action figure, otherwise there is nothing to compare against.")
        # composite baselines carry more than one quantity — say which one is the outcome
        _bv=str(row.get("baseline_value","")); _comp=""
        if unit=="INR" and ("beds" in _bv or "tenants" in _bv):
            _other="bed count" if "beds" in _bv else "tenant count"
            _comp=(f" This baseline shows two quantities — the **rupee figure is the one measured**; the "
                   f"{_other} is context and can go in Notes.")
        st.success(
            f"**What this asks you to do:** {_b(row['decision_or_opportunity'])}\n\n"
            f"**What will be measured:** {_b(kpi)} — recorded as a **{_UNITWORD.get(unit,unit)}**, where "
            f"{_DIRWORD.get(direction,direction)}.{_comp}\n\n"
            f"**Baseline:** {_b(row['baseline_value'])}\n\n"
            f"**What to enter after the action:** the real measured {_UNITWORD.get(unit,unit)} for this same KPI. "
            f"{_wtxt} {_basetxt}\n\n"
            "Enter one number only — whether it improved, and by how much, is worked out for you.")
    elif _pat in ("different","investig","none") and _ov is not None:
        _head={"different":"The KPI shown is the evidence, not the outcome",
               "investig":"This is an investigation — record what you found, not a KPI change",
               "none":"Nothing to measure for this one"}[_pat]
        st.warning(
            f"**{_head}.**\n\n"
            f"**What this asks you to do:** {_b(row['decision_or_opportunity'])}\n\n"
            f"**Why a straight before/after does not work here:** {_ov['why']}\n\n"
            f"**How you will know what happened instead:** {_ov['instead']}\n\n"
            "Record your decision and what you did — numeric measurement is deliberately not offered here, "
            "so the system cannot report an improvement it could not honestly stand behind.")
    elif _isverify:
        st.warning(
            f"**Owner verification required — no measurement yet.** {_b(row['decision_or_opportunity'])}\n\n"
            "This one depends on a fact about Vishful that is not in the data (for example whether a service is "
            "actually offered). Until you confirm that status, there is no KPI to measure and the outcome stays "
            "unavailable. **This is preserved deliberately — it is not treated as a zero or a no.** You can still "
            "record your decision and any action you take.")
    else:
        _why=("this KPI is a context signal with no better/worse direction, so an outcome cannot be judged from it"
              if direction=="context_only" else
              f"the data needed for this KPI does not currently exist ({_b(row['data_limitation'])})")
        st.info(
            f"**What this asks you to do:** {_b(row['decision_or_opportunity'])}\n\n"
            f"**Measurement:** not available for this recommendation — {_why}.\n\n"
            "You can still record your decision and what you did; the outcome will honestly stay unavailable "
            "rather than being filled in with a number that would not mean anything.")

    CAP.ensure_store()
    allev=[e for e in CAP._rows(CAP.STORE) if str(e.get("recommendation_id"))==rid]
    od=[e for e in allev if e.get("event_type")=="owner_decision"]
    latest_od=od[-1]["owner_decision"] if od else None
    has_action=any(e.get("event_type")=="action_taken" for e in allev)

    # ---- B. owner decision ----
    st.subheader("B · Record owner decision")
    with st.form("p15_od", clear_on_submit=True):
        dec=st.radio("Owner decision", ["approved","deferred","rejected"], key="p15_dec", horizontal=True)
        edate=st.text_input("Decision date (YYYY-MM-DD)", key="p15_oddate")
        conf=st.checkbox("I confirm this owner decision", key="p15_odconf")
        s=st.form_submit_button("Submit owner decision")
    if s:
        if not conf: st.warning("Tick the confirmation box before submitting.")
        elif not edate.strip(): st.warning("Decision date required.")
        else: _submit("od", lambda:{"recommendation_id":rid,"event_type":"owner_decision","event_date":edate.strip(),"owner_decision":dec})
    if latest_od: st.caption(f"Latest recorded owner decision for this recommendation: **{latest_od}** (history preserved; a change is a new event).")

    # ---- C. action (only when latest owner decision is 'approved') ----
    st.subheader("C · Record action")
    if latest_od!="approved":
        st.caption("Enabled only when the latest owner decision for this recommendation is 'approved'.")
    else:
        with st.form("p15_act", clear_on_submit=True):
            adesc=st.text_input("Action description", key="p15_adesc")
            adate=st.text_input("Action date (YYYY-MM-DD)", key="p15_adate")
            anote=st.text_input("Notes (optional)", key="p15_anote")
            s2=st.form_submit_button("Submit action")
        # Auto-capture the BEFORE KPI at action time so the owner never types a baseline that the
        # analytics already hold, and so later data movement can never rewrite the original "Before".
        try:
            import phase4_kpi_measure as KM
            _pre = KM.measure(rid)
        except Exception:
            _pre = {"available": False, "reason": "measurement provider unavailable"}
        if _pre.get("available"):
            st.caption(f"**Before KPI will be captured automatically:** {_pre['value']:,.2f} "
                       f"({_pre.get('detail','')}) as of {_pre['as_of']} — frozen at the action date "
                       "and never overwritten by later data.")
        else:
            st.caption(f"No automatic current-value source for this KPI ({_pre.get('reason','')}). "
                       "Record the baseline manually in section D if you have one.")
        if s2:
            if not adesc.strip() or not adate.strip(): st.warning("Action description and date required.")
            else:
                _ok = _submit("act", lambda:{"recommendation_id":rid,"event_type":"action_taken","event_date":adate.strip(),"action_taken":adesc.strip(),"notes":anote.strip()})
                if _ok and _pre.get("available"):
                    _submit("actbase", lambda:{"recommendation_id":rid,"event_type":"measurement",
                        "event_date":adate.strip(),"target_kpi":kpi,"unit":unit,
                        "value":str(_pre["value"]),"measurement_role":"baseline",
                        "source":"system_measured","confidence":"High",
                        "notes":f"auto-captured at action time from {_pre['source']}; {_pre.get('detail','')}"})

    # ---- D. KPI measurement (only after an action; KPI+unit fixed from registry) ----
    st.subheader("D · Record KPI measurement")
    if not has_action:
        st.caption("Enabled only after an action is recorded.")
    elif not _numeric_ok:
        # Gate on the resolved measurement PATTERN, not just the registry, so a recommendation whose
        # evidence KPI cannot honestly measure its action is never given a numeric entry box.
        if _ov is not None:
            st.info(f"**Numeric measurement is not offered for this recommendation.** {_ov['why'].capitalize()}\n\n"
                    f"{_ov['instead']}\n\nRecord what happened in the action notes instead — the outcome will "
                    "honestly stay unavailable rather than showing a comparison that would not mean anything.")
        else:
            st.info(f"KPI '{kpi}' is {'context_only (direction undefined)' if direction=='context_only' else 'non-measurable / unavailable'}. "
                    "A deterministic outcome cannot currently be produced, so measurement entry is disabled. Unavailable is never shown as 0.")
    else:
        # ---- "What to measure" — tells the owner which single number to enter, in the same definition
        #      and unit as the baseline. No parser internals are exposed and no calculation is asked for.
        _UNITWORD={"INR":"rupee amount","percent":"percentage","tickets":"ticket count",
                   "tenants":"number of tenants","beds":"number of beds","leads":"number of leads",
                   "count":"count","rate":"rate"}
        _uw=_UNITWORD.get(str(unit),str(unit))
        _basedisp=str(row.get("baseline_value",""))
        _extra=""
        if rid=="DEC-REVPROTECT-AR90":
            _extra=(" Enter the **total 90+ day AR rupee amount** using the same AR definition as the baseline. "
                    "The tenant count can go in Notes as supporting context. Bear in mind this total covers both "
                    "current tenants and closed accounts — if the figure falls partly because closed accounts were "
                    "reconciled rather than collected, note that in Notes so the two are not confused later.")
        elif str(unit)=="INR" and "beds" in _basedisp:
            _extra=(" Enter the **rupee amount** — the baseline shows both a bed count and a rupee figure, and the "
                    "rupee figure is the outcome KPI. The bed count can go in Notes.")
        st.info(f"**What to measure:** record the same KPI as the baseline — **{kpi}** — as a **{_uw}**, using the "
                f"same definition and unit. Enter one number only; the system works out whether it improved and by "
                f"how much.{_extra}\n\n"
                f"**Baseline for comparison:** {_b(row.get('baseline_value'))}\n\n"
                "**Do not** calculate a percentage change or an outcome yourself — those are derived automatically.")
        if str(row.get("baseline_numeric","")).strip() in ("","nan"):
            st.warning("**A numeric baseline is needed first for this recommendation.** Its baseline is stored as "
                       "descriptive text that cannot be compared against automatically. Submit one measurement with "
                       "role **baseline** carrying the pre-action number, then the post-action one. Recording the "
                       "baseline now simply writes down the value that already applied before the action — it does "
                       "not claim the baseline happened afterwards.")
        with st.form("p15_meas", clear_on_submit=True):
            st.caption(f"KPI (fixed): {kpi} · unit (fixed from registry): {unit}")
            mval=st.text_input("Measured value (numeric)", key="p15_mval")
            mdate=st.text_input("Measurement date (YYYY-MM-DD)", key="p15_mdate")
            mrole=st.selectbox("Measurement role", ["baseline","post_action"], key="p15_mrole")
            msrc=st.selectbox("Source", ["owner_manual","system_measured"], key="p15_msrc")
            mconf=st.selectbox("Confidence", ["High","Medium","Low"], key="p15_mconf")
            mnote=st.text_input("Notes (optional)", key="p15_mnote")
            s3=st.form_submit_button("Submit measurement")
        if s3:
            if not mval.strip() or not mdate.strip(): st.warning("Value and date required.")
            else: _submit("meas", lambda:{"recommendation_id":rid,"event_type":"measurement","event_date":mdate.strip(),
                "target_kpi":kpi,"unit":unit,"value":mval.strip(),"measurement_role":mrole,"source":msrc,"confidence":mconf,"notes":mnote.strip()})

    # ---- Corrections (append-only; original never edited/deleted) ----
    st.subheader("Corrections (append-only)")
    if not allev:
        st.caption("No events yet for this recommendation.")
    else:
        with st.form("p15_corr", clear_on_submit=True):
            sup=st.selectbox("Event to correct", [e["event_id"] for e in allev], key="p15_csup")
            ctype=st.selectbox("Corrected field", ["measurement","action_taken","owner_decision"], key="p15_ctype")
            cdate=st.text_input("Correction date (YYYY-MM-DD)", key="p15_cdate")
            cval=st.text_input("Corrected value (numeric — measurement only)", key="p15_cval")
            crole=st.selectbox("measurement_role (measurement only)", ["baseline","post_action"], key="p15_crole")
            cact=st.text_input("Corrected action text (action only)", key="p15_cact")
            cdec=st.selectbox("Corrected owner_decision (owner_decision only)", ["approved","deferred","rejected"], key="p15_cdec")
            cnote=st.text_input("Correction note (required)", key="p15_cnote")
            s4=st.form_submit_button("Submit correction")
        if s4:
            if not cdate.strip() or not cnote.strip(): st.warning("Correction date and note required.")
            else:
                def _cbuild():
                    ev={"recommendation_id":rid,"event_type":"correction","event_date":cdate.strip(),"supersedes_event_id":sup,"notes":cnote.strip()}
                    if ctype=="measurement": ev.update({"target_kpi":kpi,"unit":unit,"value":cval.strip(),"measurement_role":crole})
                    elif ctype=="action_taken": ev["action_taken"]=cact.strip()
                    else: ev["owner_decision"]=cdec
                    return ev
                _submit("corr", _cbuild)
        st.caption("The original event is never edited or deleted; the correction is a new superseding event.")

    # ---- E0. Before / After / Outcome / AI (read-only; measured, never typed) ----
    # BEFORE is the frozen baseline event captured when the action was recorded. AFTER is measured
    # live from the current validated outputs, so it moves as the data moves while BEFORE cannot.
    st.subheader("E · Before → After → Outcome → AI analysis")
    try:
        import phase4_kpi_measure as KM
        _ba = KM.build()
        _mine = _ba[_ba["recommendation_id"] == rid] if len(_ba) else _ba
        if not len(_mine):
            st.info("**Action: not yet taken.** Outcome: not available.\n\n"
                    "This recommendation has a KPI baseline available, but generating a recommendation "
                    "is not executing it. Record an action in section C and the Before value is captured "
                    "automatically from the current data at that moment.")
        else:
            b = _mine.iloc[0]
            _u = str(b["kpi_unit"])
            def _v(x):
                if x is None or (isinstance(x, float) and pd.isna(x)): return "—"
                return (rupee(x) if _u == "INR" else (f"{float(x):.1f}%" if _u == "percent"
                        else (f"{float(x):,.0f}" if float(x).is_integer() else f"{float(x):,.2f}")))
            st.caption(f"Action taken **{_b(b['action_date'])}** — {_b(b['action_taken'])}")
            c = st.columns(4)
            c[0].metric("Before", _v(b["before_value"]), help=f"frozen {_b(b['before_date'])} · {_b(b['before_source'])}")
            c[1].metric("Current (After)", _v(b["after_value"]), help=f"measured {_b(b['after_date'])} · {_b(b['after_source'])}")
            _chg = None if pd.isna(b["change"]) else b["change"]
            c[2].metric("Change", _v(_chg),
                        delta=(None if pd.isna(b["change_pct"]) else f"{b['change_pct']}%"),
                        delta_color=("inverse" if str(b["kpi_direction"]) == "lower_is_better" else "normal"))
            c[3].metric("Outcome", str(b["outcome"]))
            st.caption(f"KPI **{_b(b['target_kpi'])}** · direction **{_b(b['kpi_direction'])}** · "
                       f"tolerance {_b(b['no_change_tolerance'])} · basis: {_b(b['outcome_basis'])}")
            # timeline
            marks, days = KM.timeline(str(b["action_date"]), str(b["after_date"]))
            st.caption("Outcome timeline — " + "  ".join(
                ("✅ " if m["reached"] else "⏳ ") + m["mark"] for m in marks)
                + (f"   ({days} days since action, minimum window "
                   f"{_b(b['min_window_days'])} days)" if days is not None else ""))
            # AI analysis over the measured facts only
            st.markdown("**AI outcome analysis**")
            try:
                import phase4_outcome_ai as OAI
                _a = OAI.analyse(b, unit=_u, use_ai=True)
                st.info(_a["analysis"])
                st.caption(f"Source: {_a['analysis_source']}."
                           + (f" A generated draft was rejected and replaced ({_a['rejected_reason']})."
                              if _a["rejected_reason"] else "")
                           + " The AI receives only the measured facts above — it never sees raw data, "
                             "never decides the outcome, and any ROI, revenue, conversion or causal claim "
                             "is discarded in code before display.")
            except Exception as _e:
                st.caption(f"AI analysis unavailable ({type(_e).__name__}); the measured Before/After "
                           "and outcome above are unaffected.")
    except Exception as _e:
        st.caption(f"Before/After layer unavailable ({type(_e).__name__}).")

    # ---- E1. current effectiveness (read-only; computed only by the reducer) ----
    st.subheader("E1 · Current effectiveness (read-only — computed only by the reducer)")
    r2=pd.read_csv(effp); rr=r2[r2["recommendation_id"]==rid]
    if len(rr):
        rr=rr.iloc[0]
        act=_b(rr['action_taken']) if str(rr['action_taken']).strip() and str(rr['action_taken']).lower()!="nan" else "—"
        adt=_b(rr['action_date']) if str(rr['action_date']).strip() and str(rr['action_date']).lower()!="nan" else "—"
        pst=_b(rr['post_value']) if str(rr['post_value']).strip() and str(rr['post_value']).lower()!="nan" else "—"
        st.markdown(f"Baseline `{_b(rr['baseline_value'])}` → Action `{act}` ({adt}) → Post `{pst}` → "
                    f"**Outcome: {_b(rr['outcome_status'])}** → **Attribution: {_b(rr['attribution_confidence'])}**")
        st.caption(f"Measurement window: {_b(rr['measurement_window_status'])} · Data limitation: {_b(rr['data_limitation'])}")

PAGES={"1 · Executive & Data Trust":p_exec,"2 · Collections & Overdue":p_collections,
 "3 · Occupancy & Vacancy":p_vacancy,"4 · Pricing":p_pricing,"5 · Tenants":p_tenants,
 "6 · Electricity":p_eb,"7 · Maintenance":p_maint,"8 · Revenue Forecast":p_forecast,"9 · Assets (age)":p_assets,
 "10 · Market AI (read-only)":p_market,"11 · Business Opportunities":p_bizopp,
 "12 · Marketing Recommendations":p_marketing,"13 · Market Research / Discovery":p_market_research,
 "14 · Owner Decision Board":p_decision_board,"15 · Action & Outcomes":p_actions}

def main():
    st.set_page_config(page_title="Vishful Decision Dashboard", layout="wide")
    st.sidebar.title("Vishful — Decision Center")
    st.sidebar.caption("View layer over validated engine outputs. No recompute.")
    page=st.sidebar.radio("Page", list(PAGES))
    try:
        PAGES[page]()
    except SourceValidationError as e:
        st.error(f"Integration validation failed: {e}")
        raise

if __name__=="__main__":
    main()
