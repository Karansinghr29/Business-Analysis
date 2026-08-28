"""Canonical FIFO ledger utility (centralizes the identical inline logic used in
overdue_model.py / churn_model.py / segmentation.py). Behaviour is IDENTICAL to those
inline copies; locked modules are NOT edited. Future/dashboard code should import this.

fifo_paid_dates(D): apply AR-account (1200) credits to debits FIFO by entry_date;
returns {invoice_id: paid_date} for invoice-sourced debits (ledger/journal truth).
"""
from __future__ import annotations
import pandas as pd
from collections import deque
from loader import num, to_dt
from validation import require_tables, require_columns

def fifo_paid_dates(D: dict) -> dict:
    require_tables(D, ["v_tenant_ledger"])
    tl=D["v_tenant_ledger"]
    require_columns(tl,"v_tenant_ledger",["account_code","entry_date","debit","credit","source_table","source_id","tenant_id","posted_at"])
    ar=tl[num(tl["account_code"])==1200].copy()
    ar["entry_date"]=to_dt(ar["entry_date"]); ar["debit"]=num(ar["debit"]).fillna(0); ar["credit"]=num(ar["credit"]).fillna(0)
    ar["is_credit"]=(ar["credit"]>0).astype(int)
    ar=ar.sort_values(["tenant_id","entry_date","is_credit","posted_at"])
    paid={}
    for tid,g in ar.groupby("tenant_id"):
        q=deque()
        for _,r in g.iterrows():
            if r["debit"]>0:
                q.append([r["source_id"] if r["source_table"]=="invoices" else None, r["debit"]])
            if r["credit"]>0:
                amt=r["credit"]
                while amt>1e-6 and q:
                    h=q[0]
                    if h[1]<=amt+1e-6:
                        amt-=h[1]
                        if h[0] is not None: paid[h[0]]=r["entry_date"]
                        q.popleft()
                    else:
                        h[1]-=amt; amt=0
    return paid

if __name__=="__main__":
    from loader import load_all
    D,_=load_all(); p=fifo_paid_dates(D)
    print(f"fifo_paid_dates: mapped {len(p)} invoices to paid_date (ledger AR 1200)")
