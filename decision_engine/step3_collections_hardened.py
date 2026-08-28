"""
Phase-1 hardening: actionable collection queue = ACTIVE/STAYING tenants only.
- Source of truth: v_tenant_current_dues (ledger-based AR). NOT invoices.balance / allotment.balance_due.
- Exited/legacy allotments -> separate audit file (not mixed into the queue).
- Collectable = positive ledger AR only (exclude credit/negative).
- Aging/recency from VALID dates only (no imputation).
- Read-only; does not modify source CSVs.
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
D,_ = load_all()

cd = D["v_tenant_current_dues"].copy()
for c in ["ar_balance","net_dues","deposit_held","booking_advance"]:
    if c in cd: cd[c]=num(cd[c])
cd["last_payment_date"]=to_dt(cd.get("last_payment_date"))
cd["last_charge_date"]=to_dt(cd.get("last_charge_date"))

# ---- active vs exited via tenant_allotments (authoritative tenancy state) ----
al = D["tenant_allotments"][["id","staying_status","actual_exit_date"]].copy()
al["actual_exit_date"]=to_dt(al["actual_exit_date"])
al["status_norm"]=al["staying_status"].astype(str).str.strip().str.lower()
ACTIVE_STATUS={"staying","on-notice","booked","new"}
al["is_active"]=al["actual_exit_date"].isna() & al["status_norm"].isin(ACTIVE_STATUS)
cd=cd.merge(al.rename(columns={"id":"allotment_id"})[["allotment_id","status_norm","actual_exit_date","is_active"]],
            on="allotment_id", how="left")
cd["is_active"]=cd["is_active"].fillna(False)

# aging buckets
if "v_tenant_aging" in D:
    ag=D["v_tenant_aging"].copy()
    for c in ["bucket_31_60","bucket_61_90","bucket_90_plus"]: ag[c]=num(ag[c])
    cd=cd.merge(ag[["allotment_id","bucket_31_60","bucket_61_90","bucket_90_plus"]],on="allotment_id",how="left")

# ---- collectable = positive ledger AR only ----
cd["collectable_ar"]=cd["ar_balance"].where(cd["ar_balance"]>0)

# ---- recency from VALID dates only (no imputation) ----
cd["days_since_payment"]=(TODAY-cd["last_payment_date"]).dt.days
cd["days_since_charge"]=(TODAY-cd["last_charge_date"]).dt.days
def recency_factor(r):
    d=r["days_since_payment"]
    if pd.notna(d): return 1+min(max(d,0),365)/180
    d=r["days_since_charge"]
    if pd.notna(d): return 1+min(max(d,0),365)/180
    return 1.0  # no valid date -> neutral, flagged
cd["recency_factor"]=cd.apply(recency_factor,axis=1)
cd["recency_source"]=cd.apply(lambda r: "payment" if pd.notna(r["days_since_payment"])
                              else ("charge" if pd.notna(r["days_since_charge"]) else "none"),axis=1)

# severity from positive aging buckets only
b90=cd.get("bucket_90_plus"); b60=cd.get("bucket_61_90"); b30=cd.get("bucket_31_60")
sev=(b90.clip(lower=0).fillna(0)*3 + b60.clip(lower=0).fillna(0)*2 + b30.clip(lower=0).fillna(0)) if b90 is not None else 0
cd["aging_severity"]=sev

# ---- split ----
active_q = cd[(cd["is_active"]) & (cd["collectable_ar"]>0)].copy()
exited_ar = cd[(~cd["is_active"]) & (cd["collectable_ar"]>0)].copy()

# ---- deterministic priority ----
active_q["priority_score"]=(active_q["collectable_ar"]*active_q["recency_factor"]
                            *(1+active_q["aging_severity"]/(active_q["collectable_ar"].abs()+1))).round(0)
def reason(r):
    bits=[f"AR ₹{r['collectable_ar']:,.0f}"]
    if pd.notna(r.get("bucket_90_plus")) and r["bucket_90_plus"]>0: bits.append(f"90+ ₹{r['bucket_90_plus']:,.0f}")
    if r["recency_source"]=="payment": bits.append(f"{int(r['days_since_payment'])}d since pay")
    elif r["recency_source"]=="charge": bits.append(f"{int(r['days_since_charge'])}d since charge (no pay date)")
    else: bits.append("no valid date")
    return "; ".join(bits)
active_q["reason"]=active_q.apply(reason,axis=1)
active_q["recommended_action"]=active_q.apply(
    lambda r: "Escalate/notice" if (r.get("bucket_90_plus",0) or 0)>0 else "Follow-up call",axis=1)
active_q["settlement_note"]="invoice<->receipt settlement UNRECONCILED (receipt_allocations missing)"

cols=["tenant_id","allotment_id","status_norm","collectable_ar","net_dues","deposit_held",
      "days_since_payment","recency_source","bucket_90_plus","aging_severity","priority_score",
      "reason","recommended_action","settlement_note"]
cols=[c for c in cols if c in active_q.columns]
active_out=active_q.sort_values("priority_score",ascending=False)[cols]
active_out.to_csv(os.path.join(OUT,"step3_active_collections_worklist.csv"),index=False)
exited_out=exited_ar.sort_values("collectable_ar",ascending=False)[
    [c for c in ["tenant_id","allotment_id","status_norm","collectable_ar","net_dues","last_payment_date","last_charge_date"] if c in exited_ar.columns]]
exited_out.to_csv(os.path.join(OUT,"step3_exited_ar_audit.csv"),index=False)

# ---- verification report ----
neg_in_queue=int((active_q["collectable_ar"]<=0).sum())
removed_exited=int(len(exited_ar))
print("="*70); print("PHASE-1 HARDENING — ACTIVE COLLECTION QUEUE"); print("="*70)
print(f"Official collectable figure basis : v_tenant_current_dues.ar_balance (ledger, positive only)")
print(f"Active tenants with collectible AR : {active_q['allotment_id'].nunique()}  (rows={len(active_q)})")
print(f"TOTAL COLLECTIBLE AR (active)      : ₹{active_q['collectable_ar'].sum():,.0f}")
print(f"Exited/legacy rows removed to audit: {removed_exited}  (₹{exited_ar['collectable_ar'].sum():,.0f} residual AR)")
print(f"Negative/credit balances in queue  : {neg_in_queue}")
print(f"Rows with no valid payment date    : {(active_q['recency_source']!='payment').sum()} (recency from charge/none — flagged)")
print(f"Reference: all-tenant positive AR pool = ₹{cd['collectable_ar'].sum():,.0f} (was the ₹3.54L 'official' figure; now split active vs exited)")
print("SETTLEMENT LIMITATION: receipt_allocations MISSING -> invoice<->receipt settlement still unreconciled.")
print("\nTOP 20 ACTIVE COLLECTION PRIORITIES:")
show=active_out.head(20)[["allotment_id","status_norm","collectable_ar","days_since_payment","recommended_action","reason"]]
with pd.option_context("display.max_colwidth",60,"display.width",200):
    print(show.to_string(index=False))
print("\nWritten: outputs/step3_active_collections_worklist.csv , outputs/step3_exited_ar_audit.csv")
