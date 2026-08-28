"""
Phase 1 decision engine (CSV-only, no dashboard, no ML training, no source edits).
Steps: 1 data-trust spec, 2 corrected profitability, 3 collections, 4 vacancy at-risk, 5 pricing.
Outputs -> decision_engine/outputs/*.csv  + a printed STOP report.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from loader import load_all, num, to_dt

TODAY = pd.Timestamp("2026-08-13")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUT, exist_ok=True)
def save(df, name): df.to_csv(os.path.join(OUT, name), index=False)

D, MISS = load_all()
def has(*t): return all(x in D for x in t)
report = {}

# =================== STEP 1: DATA-TRUST / RECONCILIATION SPEC ===================
trust_rows = [
 ("journal_entries","authoritative","double-entry source; 2019->2026"),
 ("journal_lines","authoritative","debit=credit balanced"),
 ("coa_accounts","authoritative","chart of accounts"),
 ("v_trial_balance","authoritative","balanced TB"),
 ("v_org_cash_balance","authoritative","cash on hand"),
 ("v_tenant_ledger","authoritative","ledger-based tenant dues"),
 ("v_pnl_by_category","authoritative-with-fix","P&L but owner_rent NOT deducted -> correct in Step2"),
 ("v_tenant_current_dues","supporting","ledger-derived AR/net dues"),
 ("v_tenant_aging","supporting","aging buckets (nets advances)"),
 ("v_outstanding_receivables","supporting","gross outstanding"),
 ("v_invoice_settlement_status","supporting","settlement without receipt_allocations detail"),
 ("v_occupancy","supporting","operational occupancy"),
 ("invoices","operational","raw billing; totals drift +~23L vs JE"),
 ("receipts","operational","raw cash; drift +~50L vs JE"),
 ("deposit_settlements","operational","drift +~6L vs JE"),
 ("tenant_allotments","operational","tenancy facts; monthly_rental reliable"),
 ("tenant_transactions","operational-parallel","NOT posted to journals (0 JE) -> not accounting truth"),
 ("tenant_allotments.balance_due","cached-unreliable","711/1197 drift"),
 ("invoices.balance","cached-unreliable","2227/5193 drift"),
 ("receipt_allocations","MISSING","blocks invoice<->receipt settlement reconciliation"),
 ("lifecycle_config","MISSING","fee/deposit rules -> leakage authority"),
 ("bed_status_history","MISSING","clean vacancy duration"),
 ("eb_payments","partial","only ~Apr-Jun 2026; no full-history EB recovery"),
]
trust = pd.DataFrame(trust_rows, columns=["object","classification","note"])
save(trust, "step1_data_trust.csv")

# drift register from the reconciliation view
drift = D["v_je_amount_reconciliation"].copy() if has("v_je_amount_reconciliation") else pd.DataFrame()
if len(drift):
    for c in ["legacy_amount","je_net_amount","diff"]: drift[c]=num(drift[c])
    save(drift, "step1_reconciliation_drift.csv")
alloc_drift = len(D.get("v_diag_allotment_balance_drift", []))
inv_drift = len(D.get("v_diag_invoice_drift", []))

# what's safe vs investigate
safe = ["cash_on_hand (TB balanced)","occupancy % (v_occupancy)","ledger tenant dues (v_tenant_current_dues)",
        "corrected profit (rev-exp-owner_rent) [label: pre-reconciliation]"]
investigate = ["raw invoice revenue total (+~23L vs JE)","raw receipts collected (+~50L vs JE)",
               "deposit settlement totals (+~6L)","any cached balance_due / invoice.balance"]
report["step1"] = {"trust_rows":len(trust),"alloc_drift":alloc_drift,"inv_drift":inv_drift,
                   "recon_verdicts": drift.set_index("source_table")["verdict"].to_dict() if len(drift) else {}}

# =================== STEP 2: CORRECTED PROFITABILITY ===================
pnl = D["v_pnl_by_category"].copy()
for c in ["revenue","total_expenses","owner_rent","net_profit","rental_income","electricity_income"]:
    if c in pnl: pnl[c]=num(pnl[c])
pnl["corrected_profit"] = pnl["revenue"] - pnl["total_expenses"] - pnl.get("owner_rent",0)
pnl["existing_profit"]  = pnl["revenue"] - pnl["total_expenses"]           # what the view implied (no owner rent)
pnl["profit_margin_pct"] = (pnl["corrected_profit"]/pnl["revenue"].where(pnl["revenue"]!=0)*100).round(1)
monthly = pnl.groupby("month", as_index=False)[["revenue","total_expenses","owner_rent","existing_profit","corrected_profit"]].sum()
monthly["margin_pct"] = (monthly["corrected_profit"]/monthly["revenue"].where(monthly["revenue"]!=0)*100).round(1)
save(monthly.sort_values("month"), "step2_profit_monthly.csv")
tot = dict(revenue=pnl["revenue"].sum(), expenses=pnl["total_expenses"].sum(),
           owner_rent=pnl["owner_rent"].sum(), existing_profit=pnl["existing_profit"].sum(),
           corrected_profit=pnl["corrected_profit"].sum())
tot["margin_pct"]=round(tot["corrected_profit"]/tot["revenue"]*100,1)
save(pd.DataFrame([tot]), "step2_profit_totals.csv")

# owner cost (revenue attribution to owner is limited -> report cost + limitation)
oc_note=""
if has("owner_payments","owner_contracts"):
    op=D["owner_payments"].copy(); op["escalated_amount"]=num(op["escalated_amount"])
    owner_cost=op.groupby("owner_id",as_index=False)["escalated_amount"].sum().rename(columns={"escalated_amount":"owner_cost_accrued"})
    if has("owners"):
        owner_cost=owner_cost.merge(D["owners"][["id","full_name"]],left_on="owner_id",right_on="id",how="left")
    save(owner_cost, "step2_owner_cost.csv")
    paid_ratio = op["paid_date"].notna().mean() if "paid_date" in op else None
    oc_note=f"owner cost by owner computed; paid_date populated {paid_ratio:.0%}; per-owner PROFIT needs apartment->owner revenue attribution (apartments.owner_id ~98% null) -> LIMITATION"
report["step2"]={**tot,"owner_note":oc_note}

# =================== STEP 3: COLLECTIONS DECISION SYSTEM ===================
cd = D["v_tenant_current_dues"].copy()
for c in ["ar_balance","net_dues","deposit_held","booking_advance"]:
    if c in cd: cd[c]=num(cd[c])
cd["last_payment_date"]=to_dt(cd.get("last_payment_date"))
cd["last_charge_date"]=to_dt(cd.get("last_charge_date"))
cd["days_since_payment"]=(TODAY-cd["last_payment_date"]).dt.days
# aging join
if has("v_tenant_aging"):
    ag=D["v_tenant_aging"].copy()
    for c in ["bucket_0_30","bucket_31_60","bucket_61_90","bucket_90_plus","total"]: ag[c]=num(ag[c])
    cd=cd.merge(ag[["allotment_id","bucket_31_60","bucket_61_90","bucket_90_plus"]],on="allotment_id",how="left")
work = cd[cd["ar_balance"]>0].copy()
# priority: amount x recency x aging severity
rec = (work["days_since_payment"].fillna(work["days_since_payment"].median())).clip(0,365)
sev = (work.get("bucket_90_plus",0).fillna(0)*3 + work.get("bucket_61_90",0).fillna(0)*2 + work.get("bucket_31_60",0).fillna(0)).clip(lower=0)
work["priority_score"]=(work["ar_balance"]*(1+rec/180)*(1+sev/(work["ar_balance"].abs()+1))).round(0)
def reason(r):
    bits=[f"AR ₹{r['ar_balance']:,.0f}"]
    if pd.notna(r.get("bucket_90_plus")) and r["bucket_90_plus"]>0: bits.append(f"90+ ₹{r['bucket_90_plus']:,.0f}")
    if pd.notna(r["days_since_payment"]): bits.append(f"{int(r['days_since_payment'])}d since pay")
    if pd.notna(r.get("net_dues")): bits.append(f"net ₹{r['net_dues']:,.0f}")
    return "; ".join(bits)
work["reason"]=work.apply(reason,axis=1)
work["recommended_action"]=work.apply(lambda r: "Escalate/notice" if (r.get("bucket_90_plus",0) or 0)>0 else "Follow-up call", axis=1)
worklist=work.sort_values("priority_score",ascending=False)[
    ["tenant_id","allotment_id","ar_balance","net_dues","days_since_payment","bucket_90_plus","priority_score","reason","recommended_action"]]
save(worklist,"step3_collections_worklist.csv")
# overdue-ML feature frame (PREPARED, NOT TRAINED)
inv=D["invoices"].copy()
for c in ["total_amount","amount_paid","balance","rent_amount","electricity_amount"]:
    if c in inv: inv[c]=num(inv[c])
inv["invoice_date"]=to_dt(inv.get("invoice_date")); inv["due_date"]=to_dt(inv.get("due_date"))
feat=inv[["id","tenant_id","allotment_id","invoice_date","due_date","total_amount","rent_amount","electricity_amount","billing_month"]].copy()
# candidate label (to CONFIRM before training): unpaid past due as of TODAY  (uses cached balance -> flagged)
feat["label_unpaid_pastdue_CANDIDATE"]=((inv["balance"]>0)&(inv["due_date"]<TODAY)).astype(int)
save(feat.head(50),"step3_overdue_ml_feature_SAMPLE.csv")
report["step3"]={"tenants_with_AR":int((cd["ar_balance"]>0).sum()),
                 "total_AR": float(work["ar_balance"].sum()),
                 "top_priority_AR": float(worklist["ar_balance"].head(20).sum()),
                 "ml_label_note":"CANDIDATE label uses invoices.balance (cached, 2227 drift) -> confirm target vs v_tenant_ledger before training",
                 "limitation":"receipt_allocations MISSING -> cannot attribute which receipt settled which invoice (invoice-level settlement unreliable)"}

# =================== STEP 4: VACANCY ₹-AT-RISK (apartment/bed LIFECYCLE-aware) ===================
# Current rentable vacancy = beds in a LIVE apartment, whose own bed status is Live, with no active tenant.
#   - Apartment status != Live (e.g. A22 closed/Not-Active) -> excluded entirely.
#   - Bed status != Live (e.g. A34 B2 Not-Active) -> excluded entirely.
#   - Live-apt/Live-bed, no tenant, no historical exit, apartment operational only this month
#     (apartments.start_date >= start of current month) = NEW INVENTORY (A33/A34, operational 2026-08-01):
#       availability/duration begins at the operational start_date (never before), NOT labelled "never occupied?".
# Lifecycle read from apartments.status / apartments.start_date / beds.status (no beds.created_at, no per-apt hardcode).
al=D["tenant_allotments"].copy()
al["actual_exit_date"]=to_dt(al.get("actual_exit_date"))
ap=D["apartments"].copy()
ap["_astat"]=ap["status"].astype(str).str.strip()
_aps=to_dt(ap.get("start_date")); ap["_astart"]=_aps.where(_aps.dt.year>2000)   # guard 1899 sentinel -> NaT
apstat=dict(zip(ap["id"],ap["_astat"])); apstart=dict(zip(ap["id"],ap["_astart"]))
beds=D["beds"].copy()
beds["_apt_status"]=beds["apartment_id"].map(apstat)
beds["_apt_start"]=beds["apartment_id"].map(apstart)
beds["_bed_status"]=beds["status"].astype(str).str.strip() if "status" in beds.columns else "Live"
rentable=beds[(beds["_apt_status"]=="Live")&(beds["_bed_status"]=="Live")].copy()   # exclude closed apts + Not-Active beds
occupied_bed_ids=set(al.loc[al["actual_exit_date"].isna(),"bed_id"].dropna())
vac=rentable[~rentable["id"].isin(occupied_bed_ids)].copy()
last_exit=al.dropna(subset=["actual_exit_date"]).groupby("bed_id")["actual_exit_date"].max()
vac["last_exit"]=vac["id"].map(last_exit)
CUR_MONTH=TODAY.replace(day=1)   # start of current operating month (2026-08-01) from the fixed TODAY
vac["_is_new"]=vac["_apt_start"].notna() & (vac["_apt_start"]>=CUR_MONTH) & vac["last_exit"].isna()
# vacancy duration: historical exit -> from last exit; new inventory -> from operational start_date (never before);
# else (old, never occupied) -> unknown.
def _dv(r):
    if pd.notna(r["last_exit"]): return (TODAY-r["last_exit"]).days
    if r["_is_new"]: return (TODAY-r["_apt_start"]).days
    return None
vac["days_vacant"]=vac.apply(_dv,axis=1)
vac["duration_known"]=vac["last_exit"].notna() | vac["_is_new"]   # known for historical exit AND new inventory
br=D["bed_rates"].copy(); br["monthly_rate"]=num(br["monthly_rate"])
rate=br.groupby(["bed_type","toilet_type"])["monthly_rate"].median()
vac["monthly_rate"]=vac.apply(lambda r: rate.get((r["bed_type"],r["toilet_type"]), br["monthly_rate"].median()),axis=1)
vac["rev_at_risk_monthly"]=vac["monthly_rate"]
vac["rev_at_risk_todate"]=(vac["monthly_rate"]*vac["days_vacant"]/30).round(0)
vac["priority"]=vac["rev_at_risk_todate"].fillna(vac["rev_at_risk_monthly"])
def _act(r):
    if r["_is_new"]: return f"New inventory — available from {r['_apt_start'].strftime('%b %Y')}"
    if pd.notna(r["days_vacant"]) and r["days_vacant"]>60: return "Marketing priority"
    if not r["duration_known"]: return "Investigate (never occupied?)"
    return "Fill / monitor"
vac["recommended_action"]=vac.apply(_act,axis=1)
vout=vac.sort_values("priority",ascending=False)[
    ["id","bed_code","apartment_id","bed_type","toilet_type","duration_known","days_vacant",
     "monthly_rate","rev_at_risk_monthly","rev_at_risk_todate","recommended_action"]]
save(vout,"step4_vacancy_at_risk.csv")
report["step4"]={"vacant_beds_physical":int(len(vac)),
                 "v_occupancy_vacant": int(num(D["v_occupancy"]["vacant"]).iloc[0]) if has("v_occupancy") else None,
                 "with_known_duration":int(vac["duration_known"].sum()),
                 "new_inventory_beds":int(vac["_is_new"].sum()),
                 "total_rev_at_risk_monthly":float(vac["rev_at_risk_monthly"].sum()),
                 "caveat":"rentable = Live apartment + Live bed + no active tenant; closed apts (A22) and Not-Active beds (A34 B2) excluded; new inventory (A33/A34) vacancy begins at apartments.start_date, not before; older never-occupied beds still Investigate"}

# =================== STEP 5: INTERNAL PRICING ANALYSIS ===================
active=al[al["actual_exit_date"].isna()].copy()
active["monthly_rental"]=num(active["monthly_rental"]); active["discount"]=num(active.get("discount"))
active=active.merge(beds[["id","bed_type","toilet_type"]],left_on="bed_id",right_on="id",how="left",suffixes=("","_bed"))
realized=active.groupby(["bed_type","toilet_type"]).agg(
    n_active=("monthly_rental","size"),
    realized_p25=("monthly_rental",lambda s:s.quantile(.25)),
    realized_median=("monthly_rental","median"),
    realized_p75=("monthly_rental",lambda s:s.quantile(.75)),
    discount_rows=("discount",lambda s:(s>0).sum()),
    discount_sum=("discount","sum")).reset_index()
card=br.groupby(["bed_type","toilet_type"]).agg(card_min=("monthly_rate","min"),
    card_median=("monthly_rate","median"),card_max=("monthly_rate","max")).reset_index()
# occupancy by type — SAME rentable universe as STEP 4 (Live apartment + Live bed); closed apts (A22) and
# Not-Active beds (A34 B2) excluded from total_beds so Step 4/Step 5 never disagree on what counts as inventory.
tot_beds=rentable.groupby(["bed_type","toilet_type"]).size().rename("total_beds")
occ_beds=rentable[rentable["id"].isin(occupied_bed_ids)].groupby(["bed_type","toilet_type"]).size().rename("occupied_beds")
occ=pd.concat([tot_beds,occ_beds],axis=1).fillna(0).reset_index()
occ["occupancy_pct"]=(occ["occupied_beds"]/occ["total_beds"]*100).round(1)
# The RENTABLE OCCUPANCY UNIVERSE is authoritative and must be the primary table. Previously this was
# card.merge(realized, how="outer").merge(occ, how="left"), which kept a (bed_type,toilet_type) group only
# if it had a rate-card row or an active tenant. Triple/Common (A34 TSC1-3) has neither — 3 Live beds in a
# Live apartment, all currently vacant, with no bed_rates entry — so those 3 beds were dropped from
# total_beds and Step 5 reported 194 against Step 4's 197. Driving the merge from `occ` keeps every
# rentable bed in the denominator; pricing columns stay null where no rate card exists, and signal()
# already returns "insufficient" for null medians.
price=occ.merge(card,on=["bed_type","toilet_type"],how="left").merge(realized,on=["bed_type","toilet_type"],how="left")
def signal(r):
    rm,cm,op=r.get("realized_median"),r.get("card_median"),r.get("occupancy_pct")
    if pd.isna(rm) or pd.isna(cm): return "insufficient"
    if rm < cm*0.97 and (op or 0)>=90: return "UNDERPRICED / raise opportunity"
    if rm > cm*1.03 and (op or 0)<80: return "ABOVE card + vacancy -> review"
    if rm < cm*0.9: return "well below card -> check discounts"
    return "within band"
price["pricing_signal"]=price.apply(signal,axis=1)
save(price.sort_values("total_beds",ascending=False),"step5_pricing_analysis.csv")
report["step5"]={"types":len(price),
                 "underpriced": price["pricing_signal"].str.contains("UNDERPRICED").sum(),
                 "discount_total": float(active["discount"].fillna(0).gt(0).mul(active["discount"].fillna(0)).sum())}

# =================== STOP REPORT ===================
print("="*74); print("PHASE 1 — DECISION ENGINE BUILD REPORT (CSV source of truth)"); print("="*74)
print("\n[STEP 1] DATA TRUST")
print(f"  classified {report['step1']['trust_rows']} objects; allotment drift={report['step1']['alloc_drift']} invoice drift={report['step1']['inv_drift']}")
print(f"  reconciliation verdicts: {report['step1']['recon_verdicts']}")
print("\n[STEP 2] CORRECTED PROFITABILITY")
s=report['step2']; print(f"  revenue={s['revenue']:,.0f} expenses={s['expenses']:,.0f} owner_rent={s['owner_rent']:,.0f}")
print(f"  existing_profit(no owner rent)={s['existing_profit']:,.0f}  CORRECTED_profit={s['corrected_profit']:,.0f}  margin={s['margin_pct']}%")
print(f"  {s['owner_note']}")
print("\n[STEP 3] COLLECTIONS")
s=report['step3']; print(f"  tenants with AR>0={s['tenants_with_AR']} total_AR={s['total_AR']:,.0f} top20_AR={s['top_priority_AR']:,.0f}")
print(f"  ML: {s['ml_label_note']}"); print(f"  LIMIT: {s['limitation']}")
print("\n[STEP 4] VACANCY ₹-AT-RISK")
s=report['step4']; print(f"  vacant beds(physical)={s['vacant_beds_physical']} (v_occupancy vacant={s['v_occupancy_vacant']}) known_duration={s['with_known_duration']}")
print(f"  total monthly rev-at-risk=₹{s['total_rev_at_risk_monthly']:,.0f}  caveat: {s['caveat']}")
print("\n[STEP 5] PRICING")
s=report['step5']; print(f"  bed-type bands={s['types']} underpriced_types={s['underpriced']} discount_total=₹{s['discount_total']:,.0f}")
print("\nOUTPUTS written to:", OUT)
for f in sorted(os.listdir(OUT)): print("   ",f)
