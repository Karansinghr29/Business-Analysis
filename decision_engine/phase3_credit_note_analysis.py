"""
Phase-3 CREDIT-NOTE / REVENUE-ADJUSTMENT ANALYSIS (isolated, deterministic, read-only on sources).

Business question: why is billed revenue being credited back, and does any pattern recur enough to
justify a process review?

IMPORTANT DEFINITION: only `credit_note` rows REDUCE revenue. `debit_note` rows ADD charges and are
reported separately for context — the two must never be summed into a single "leakage" figure.

A credit note is NOT automatically a loss or a mistake. Referral bonuses, card-processing fees and
EB pass-through credits are ordinary business adjustments. Only recurrence + materiality + a stated
reason can justify calling something worth reviewing, and even then this file says "investigate",
never "preventable loss".

GRAIN NOTES (validated before aggregation):
  * tenant_adjustments : 1 row per adjustment id; `is_deleted` rows are excluded. No join is performed,
                         so no monetary value can be duplicated. Asserted below.
  * `category` is fully populated (7 controlled values) and is the usable dimension.
    Free-text `reason` is populated on roughly half the rows across ~85 distinct values — too sparse
    and too fragmented to aggregate, so it is surfaced only as an example, never as a grouping key.

Writes ONLY phase3_credit_note_analysis.csv + _summary.csv. Modifies no existing output, decision,
engine, or validator.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import loader

HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
num=lambda s: pd.to_numeric(s,errors="coerce")

# Ordinary, expected adjustments vs those whose recurrence makes them worth a process review.
EXPECTED={"referral_bonus":"Deliberate tenant-acquisition cost — expected, not leakage",
          "cc_charges":"Card-processing fee pass-through — expected",
          "eb_credit":"Electricity pass-through correction — expected",
          "late_fees":"Late-fee reversal — expected within policy"}

def main():
    D,_=loader.load_all()
    a=D["tenant_adjustments"].copy()
    assert len(a)==a["id"].nunique(), "tenant_adjustments is not 1 row per id"

    a["_del"]=a["is_deleted"].astype(str).str.lower().isin(["true","1"])
    live=a[~a["_del"]].copy()
    live["_amt"]=num(live["amount"])
    live["_dt"]=pd.to_datetime(live["adjustment_date"],errors="coerce")
    live["_yr"]=live["_dt"].dt.year
    live["category"]=live["category"].fillna("others").astype(str)

    cn=live[live["adjustment_type"]=="credit_note"].copy()
    dn=live[live["adjustment_type"]=="debit_note"].copy()
    tot=float(cn["_amt"].sum())

    rows=[]
    for cat,g in cn.groupby("category"):
        amt=float(g["_amt"].sum()); n=int(len(g))
        yrs=g["_yr"].dropna()
        span=f"{int(yrs.min())}-{int(yrs.max())}" if len(yrs) else "unknown"
        recurring = n>=10 and yrs.nunique()>=2
        if cat in EXPECTED:
            cls="Expected/normal adjustment"; note=EXPECTED[cat]
        elif cat=="others":
            cls="Insufficient reason data"
            note=("Largest bucket by value but carries no specific category. The free-text reason field is "
                  "only partly populated and highly fragmented, so the driver cannot be identified from data.")
        elif recurring:
            cls="Investigate recurring leakage"
            note=f"{n} notes across {int(yrs.nunique())} years — recurring and material enough to review the process behind it."
        else:
            cls="Owner/accounting verification required"
            note="Too few or too concentrated to classify from data alone."
        ex=[str(r) for r in g["reason"].dropna().unique()[:3]]
        rows.append(dict(category=cat,notes=n,amount=round(amt,2),
            share_of_credit_notes=f"{100*amt/max(tot,1):.1f}%",
            years_active=int(yrs.nunique()) if len(yrs) else 0, period=span,
            classification=cls, interpretation=note,
            example_reasons=" | ".join(ex) if ex else "(no reason recorded)"))

    out=pd.DataFrame(rows).sort_values("amount",ascending=False).reset_index(drop=True)
    out.to_csv(os.path.join(OUT,"phase3_credit_note_analysis.csv"),index=False)

    by_yr=cn.groupby("_yr")["_amt"].sum().sort_index()
    trend="; ".join(f"{int(y)}: ₹{v:,.0f}" for y,v in by_yr.items() if pd.notna(y))
    inv_tot=float(num(D["invoices"]["total_amount"]).sum())
    unc=out.loc[out["category"]=="others","amount"]
    unc=float(unc.iloc[0]) if len(unc) else 0.0

    summary=[
     ("credit_notes_count",int(len(cn))),("credit_notes_total",round(tot,2)),
     ("debit_notes_count",int(len(dn))),("debit_notes_total",round(float(dn['_amt'].sum()),2)),
     ("note","credit notes REDUCE revenue; debit notes ADD charges — never sum the two"),
     ("deleted_rows_excluded",int(a['_del'].sum())),
     ("categories",int(out['category'].nunique())),
     ("uncategorised_amount",round(unc,2)),
     ("uncategorised_share",f"{100*unc/max(tot,1):.1f}%"),
     ("credit_notes_vs_invoiced_revenue",f"{100*tot/max(inv_tot,1):.2f}%"),
     ("trend_by_year",trend),
     ("date_range",f"{str(cn['_dt'].min())[:10]} .. {str(cn['_dt'].max())[:10]}"),
     ("reason_field_coverage",f"{int(live['reason'].notna().sum())}/{int(len(live))} rows populated"),
     ("causality","NOT established — no credit note is labelled preventable or a loss"),
     ("governing_rule","Recurrence + materiality flags a process review; it never proves avoidable leakage"),
    ]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(
        os.path.join(OUT,"phase3_credit_note_analysis_summary.csv"),index=False)

    print("PHASE-3 CREDIT-NOTE ANALYSIS:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nby category:")
    for r in out.itertuples():
        print(f"  {r.category:20} {r.notes:>4} notes  ₹{r.amount:>12,.0f}  {r.share_of_credit_notes:>6}  {r.classification}")

if __name__=="__main__": main()
