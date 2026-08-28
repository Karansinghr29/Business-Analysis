"""
Phase-3 LEASE COVERAGE — INVESTIGATION SIGNAL (isolated, deterministic, read-only on sources).

Business purpose: identify leased apartments where INVOICED revenue was below the OWNER-RENT
obligation over the matched periods, so the owner can INVESTIGATE the commercial arrangement.

THIS IS NOT PROFITABILITY. It compares one revenue line against one cost line. It is not
profit, not margin, not collected cash, and it does not include any other operating cost.
No commercial action (lease exit, renegotiation, price change) is recommended by this file —
those are owner decisions that require review of the questions raised here.

METHOD (validated):
  * owner_payments : 1 row per apartment-month (319 rows / 319 unique pairs). `escalated_amount`
                     totals ₹17,623,800, reconciling exactly to the P&L owner-rent figure.
                     NOTE: the majority of these rows are status='pending' — the obligation is
                     largely ACCRUED, not cash paid out.
  * invoices       : 1 row per invoice; `apartment_id` populated on all rows. `total_amount` is
                     INVOICED (billed), never collected cash.
  * Both sides are aggregated to (apartment_id, month) BEFORE being combined, and combined on a
    shared index rather than a row-level merge, so no monetary value can be duplicated by fan-out.
  * MATCHED-PERIOD RULE: only apartment-months where BOTH owner rent and invoiced revenue exist are
    counted. This removes ramp-up / pre-invoicing / unmatched months that would otherwise depress
    coverage for reasons unrelated to the commercial arrangement.

COVERAGE LIMIT: owner-rent records exist for only 13 of the 36 revenue-generating apartments.
Apartments without owner-rent coverage are NOT classified — neither favourably nor unfavourably.

Writes ONLY phase3_lease_coverage_signal.csv + _summary.csv. Creates no decision, changes no
existing output, and is NOT part of the 14-decision backbone (is_backbone=False by construction).
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import loader

HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
num=lambda s: pd.to_numeric(s,errors="coerce")

# Investigation prompts — questions the owner can look into. Never asserted as causes.
PROMPTS=("Is occupancy persistently low in this apartment? | "
         "Is invoicing incomplete or delayed for these periods? | "
         "Were there extended vacancy periods? | "
         "Is the recorded owner-rent obligation correct and current? | "
         "Were there ramp-up, closure, renovation or operational-transition periods? | "
         "Does the commercial lease arrangement deserve review?")

def main():
    D,_=loader.load_all()
    op=D["owner_payments"].copy(); inv=D["invoices"].copy(); ap=D["apartments"].copy()

    # ---- grain validation: fail loud rather than silently inflating money ----
    assert len(op)==op["id"].nunique(), "owner_payments is not 1 row per id"
    assert len(op)==len(op.drop_duplicates(["apartment_id","payment_month"])), \
        "owner_payments is not 1 row per apartment-month"
    assert len(inv)==inv["id"].nunique(), "invoices is not 1 row per id"

    code=dict(zip(ap["id"],ap["apartment_code"]))
    op["_m"]=pd.to_datetime(op["payment_month"],errors="coerce").dt.to_period("M")
    op["_rent"]=num(op["escalated_amount"])
    inv["_m"]=pd.to_datetime(inv["invoice_date"],errors="coerce").dt.to_period("M")
    inv["_rev"]=num(inv["total_amount"])

    # aggregate each side to (apartment, month) FIRST, then align on the shared index -> no fan-out
    R=op.groupby(["apartment_id","_m"])["_rent"].sum().rename("rent")
    V=inv.groupby(["apartment_id","_m"])["_rev"].sum().rename("rev")
    both=pd.concat([R,V],axis=1)
    matched=both.dropna()                      # MATCHED-PERIOD RULE (excludes ramp-up/unmatched)
    excluded_rent_months=int(both["rev"].isna().sum())
    excluded_rev_months=int(both["rent"].isna().sum())

    g=matched.groupby(level=0).agg(invoiced_revenue=("rev","sum"),
                                   owner_rent=("rent","sum"),
                                   matched_months=("rev","size"))
    g["coverage_x"]=(g["invoiced_revenue"]/g["owner_rent"]).round(2)

    def signal(c):
        if c<1.0:  return "Investigation signal — invoiced revenue below matched owner-rent obligation"
        if c<1.1:  return "Close to parity — monitor"
        return "Above matched owner-rent obligation"

    out=g.reset_index().rename(columns={"apartment_id":"apartment_id_raw"})
    out["apartment_code"]=out["apartment_id_raw"].map(lambda x: code.get(x,str(x)[:8]))
    out["signal"]=out["coverage_x"].map(signal)
    out["investigation_prompts"]=out["coverage_x"].map(
        lambda c: PROMPTS if c<1.0 else "(not flagged — no investigation prompted)")
    out["basis"]=("invoiced revenue (invoices.total_amount) vs owner-rent obligation "
                  "(owner_payments.escalated_amount), matched apartment-months only")
    out["limitation"]=("NOT profitability, NOT margin, NOT collected cash. One revenue line vs one cost "
                       "line; no other operating cost is included. Owner rent is largely accrued rather "
                       "than paid. Coverage above 1.0x does not indicate a favourable commercial outcome.")
    out["invoiced_revenue"]=out["invoiced_revenue"].round(2)
    out["owner_rent"]=out["owner_rent"].round(2)

    cols=["apartment_code","matched_months","invoiced_revenue","owner_rent","coverage_x",
          "signal","investigation_prompts","basis","limitation"]
    out=out[cols].sort_values("coverage_x").reset_index(drop=True)
    out.to_csv(os.path.join(OUT,"phase3_lease_coverage_signal.csv"),index=False)

    flagged=out[out["coverage_x"]<1.0]
    rev_apts=int(inv["apartment_id"].nunique())
    pend=op["status"].astype(str).str.lower().eq("pending")
    summary=[
     ("apartments_with_owner_rent_coverage",int(len(out))),
     ("revenue_generating_apartments_total",rev_apts),
     ("apartments_not_classified",rev_apts-int(len(out))),
     ("coverage_note",f"{len(out)} of {rev_apts} apartments have owner-rent records; the other "
                      f"{rev_apts-len(out)} are NOT classified as favourable or unfavourable"),
     ("matched_apartment_months",int(len(matched))),
     ("excluded_rent_months_no_revenue",excluded_rent_months),
     ("excluded_revenue_months_no_rent",excluded_rev_months),
     ("investigation_signals",int(len(flagged))),
     ("investigation_signal_apartments",", ".join(f"{r.apartment_code} {r.coverage_x:.2f}x" for r in flagged.itertuples())),
     ("total_invoiced_revenue_matched",round(float(out["invoiced_revenue"].sum()),2)),
     ("total_owner_rent_matched",round(float(out["owner_rent"].sum()),2)),
     ("overall_coverage_x",round(float(out["invoiced_revenue"].sum()/out["owner_rent"].sum()),2)),
     ("owner_rent_accrued_share",f"{100*pend.mean():.0f}% of owner-rent rows are status='pending' (accrued, not paid)"),
     ("revenue_basis","INVOICED (billed) — not collected cash"),
     ("is_backbone","False — investigation signal only, not one of the 14 backbone decisions"),
     ("not_profitability","CONFIRMED — one revenue line vs one cost line; no other operating cost included"),
     ("recommended_action","NONE auto-generated. Owner review required before any commercial decision."),
    ]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(
        os.path.join(OUT,"phase3_lease_coverage_signal_summary.csv"),index=False)

    print("PHASE-3 LEASE COVERAGE — INVESTIGATION SIGNAL:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nper apartment (matched periods only):")
    for r in out.itertuples():
        print(f"  {r.apartment_code:6} {r.matched_months:>3}mo  rev ₹{r.invoiced_revenue:>12,.0f}  "
              f"rent ₹{r.owner_rent:>12,.0f}  {r.coverage_x:>5.2f}x  {r.signal}")

if __name__=="__main__": main()
