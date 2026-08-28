"""
Phase-3 AGED-AR RECOVERY REVIEW QUEUE (isolated, deterministic, read-only on sources).

Business question: of the aged 90+ receivables already reported by DEC-REVPROTECT-AR90, which cases
carry deposit/settlement evidence and should therefore be REVIEWED DIFFERENTLY?

This does NOT compute recovery, collectable amount, or net-AR-after-deposits. Deposit evidence is
reported as EVIDENCE ONLY; whether a deposit is actually applicable to a specific receivable is an
accounting decision that this data cannot settle (receipt_allocations is MISSING — settlement↔invoice
reconciliation is UNAVAILABLE project-wide).

GRAIN NOTES (validated before aggregation):
  * v_tenant_aging        : 1 row per allotment (630 rows / 630 unique) — safe to aggregate directly.
  * deposit_settlements   : 1 row per allotment (299 rows / 299 unique) — EXIT settlements ONLY;
                            every row maps to an EXITED allotment, none to an active one. These
                            deposits are already deducted/refunded and are NOT held against current AR.
  * tenant_allotments     : 1 row per allotment; `deposit_paid` is the deposit held for ACTIVE tenants.
  Left-joins are 1:1 on allotment_id, so no monetary value is duplicated by the join (asserted below).

Writes ONLY phase3_ar_recovery_queue.csv + _summary.csv. Modifies no existing output, decision,
engine, or validator. No fabricated ₹ recovery of any kind.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import loader

HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
num=lambda s: pd.to_numeric(s,errors="coerce")

def main():
    D,_=loader.load_all()
    ag=D["v_tenant_aging"].copy(); al=D["tenant_allotments"].copy(); ds=D["deposit_settlements"].copy()

    # ---- grain validation (fail loud rather than silently inflating money) ----
    assert len(ag)==ag["allotment_id"].nunique(), "v_tenant_aging is not 1 row per allotment"
    assert len(ds)==ds["allotment_id"].nunique(), "deposit_settlements is not 1 row per allotment"
    assert len(al)==al["id"].nunique(), "tenant_allotments is not 1 row per allotment"

    al["_exit"]=pd.to_datetime(al.get("actual_exit_date"),errors="coerce")
    active=set(al.loc[al["_exit"].isna(),"id"]); exited=set(al.loc[al["_exit"].notna(),"id"])
    dep_paid=dict(zip(al["id"],num(al["deposit_paid"])))          # deposit held for ACTIVE tenants

    q=ag[num(ag["bucket_90_plus"])>0].copy()
    q["ar_90_plus"]=num(q["bucket_90_plus"]).round(2)
    n_before=len(q)
    q["tenant_status"]=q["allotment_id"].map(
        lambda x:"ACTIVE" if x in active else ("EXITED" if x in exited else "UNMATCHED"))

    scols=["allotment_id","deposit_amount","pending_rent","refund_amount","status","settlement_date"]
    q=q.merge(ds[scols],on="allotment_id",how="left")
    assert len(q)==n_before, "settlement join inflated the queue — grain violation"

    q["deposit_held_active"]=q.apply(
        lambda r: dep_paid.get(r["allotment_id"]) if r["tenant_status"]=="ACTIVE" else None,axis=1)
    q["settlement_status"]=q["status"].where(q["deposit_amount"].notna())

    def classify(r):
        if r["tenant_status"]=="ACTIVE":
            d=r["deposit_held_active"]
            return ("Deposit-backed — evidence available" if pd.notna(d) and float(d)>0
                    else "No deposit evidence found")
        if r["tenant_status"]=="EXITED":
            if pd.isna(r["deposit_amount"]): return "Insufficient linkage data — no settlement record"
            return "Deposit exists but linkage requires owner/accounting verification"
        return "Insufficient linkage data — allotment unmatched"

    def review(r):
        c=r["classification"]
        if c.startswith("Deposit-backed"):
            return "Active tenant with a deposit on file — review the receivable against the deposit before escalating."
        if c.startswith("No deposit"):
            return "Active tenant with no deposit on file — conventional collections follow-up."
        if c.startswith("Deposit exists"):
            return ("Tenant has exited and a deposit settlement was recorded; the aging view still shows this "
                    "balance. Accounting review required — settlement↔invoice reconciliation is unavailable.")
        return "Tenant has exited with no settlement record found — investigate why the deposit was never settled."

    q["classification"]=q.apply(classify,axis=1)
    q["review_action"]=q.apply(review,axis=1)
    q["evidence_basis"]=("aging-gross 90+ bucket (v_tenant_aging); deposit evidence from "
                         "tenant_allotments.deposit_paid (active) / deposit_settlements (exited)")
    q["limitation"]=("Deposit evidence only — NOT a recovery estimate. No collectable amount, net AR, or "
                     "recovery probability is computed. receipt_allocations is MISSING, so settlement-to-"
                     "invoice reconciliation is UNAVAILABLE.")

    cols=["allotment_id","tenant_id","ar_90_plus","tenant_status","deposit_held_active","deposit_amount",
          "pending_rent","refund_amount","settlement_status","settlement_date","classification",
          "review_action","evidence_basis","limitation"]
    out=q[cols].sort_values(["tenant_status","ar_90_plus"],ascending=[True,False]).reset_index(drop=True)
    out.to_csv(os.path.join(OUT,"phase3_ar_recovery_queue.csv"),index=False)

    tot=float(out["ar_90_plus"].sum())
    def blk(mask):
        s=out[mask]; return len(s), float(s["ar_90_plus"].sum())
    n_act,a_act=blk(out.tenant_status=="ACTIVE")
    n_exi,a_exi=blk(out.tenant_status=="EXITED")
    n_bk ,a_bk =blk(out.classification.str.startswith("Deposit-backed"))
    n_nd ,a_nd =blk(out.classification.str.startswith("No deposit"))
    n_ver,a_ver=blk(out.classification.str.startswith("Deposit exists"))
    n_ins,a_ins=blk(out.classification.str.startswith("Insufficient"))
    summary=[
     ("aged_90_plus_total",round(tot,2)),("aged_90_plus_allotments",len(out)),
     ("active_allotments",n_act),("active_ar",round(a_act,2)),
     ("exited_allotments",n_exi),("exited_ar",round(a_exi,2)),
     ("exited_share_of_aged_ar",f"{100*a_exi/max(tot,1):.1f}%"),
     ("deposit_backed_allotments",n_bk),("deposit_backed_ar",round(a_bk,2)),
     ("deposit_held_active_total",round(float(num(out['deposit_held_active']).sum()),2)),
     ("no_deposit_evidence_allotments",n_nd),("no_deposit_evidence_ar",round(a_nd,2)),
     ("verification_required_allotments",n_ver),("verification_required_ar",round(a_ver,2)),
     ("insufficient_linkage_allotments",n_ins),("insufficient_linkage_ar",round(a_ins,2)),
     ("recovery_estimate","NOT COMPUTED — deposit evidence only, never a recovery forecast"),
     ("reconciliation_status","UNAVAILABLE — receipt_allocations missing"),
     ("governing_rule","Evidence for prioritising review; no collectable amount or net AR is derived"),
    ]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(
        os.path.join(OUT,"phase3_ar_recovery_queue_summary.csv"),index=False)

    print("PHASE-3 AGED-AR RECOVERY REVIEW QUEUE:")
    for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": main()
