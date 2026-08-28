"""
Phase 2 - Overdue-payment prediction (LEDGER-BASED TARGET, leak-safe, walk-forward).
- Target from v_tenant_ledger AR account (1200) via FIFO payment application (journal truth).
  NOT invoices.balance / allotment.balance_due.
- Prediction point = invoice_date. Features use ONLY tenant history whose outcome is known
  strictly before invoice_date (leak-safe). Label = overdue by due_date.
- Walk-forward by billing_month (no random split). Baseline (rule) vs ML (HistGradientBoosting).
- Read-only on source CSVs. Writes only to decision_engine/outputs/.
STOP-gates if positives/negatives insufficient.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np, pandas as pd
from loader import load_all, num, to_dt

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)
DATA_END=pd.Timestamp("2026-08-11")   # max ledger entry_date
D,_=load_all()
inv=D["invoices"].copy(); tl=D["v_tenant_ledger"].copy()
for c in ["total_amount","rent_amount","electricity_amount"]:
    if c in inv: inv[c]=num(inv[c])
inv["invoice_date"]=to_dt(inv["invoice_date"]); inv["due_date"]=to_dt(inv["due_date"])
inv_meta=inv.set_index("id")[["invoice_date","due_date","billing_month","total_amount","rent_amount","electricity_amount","tenant_id","allotment_id"]]

# ---------------- 1. LEDGER-FIFO OVERDUE LABEL ----------------
ar=tl[num(tl["account_code"])==1200].copy()
ar["entry_date"]=to_dt(ar["entry_date"]); ar["debit"]=num(ar["debit"]).fillna(0); ar["credit"]=num(ar["credit"]).fillna(0)
ar["is_credit"]=(ar["credit"]>0).astype(int)  # debits first within a day
ar=ar.sort_values(["tenant_id","entry_date","is_credit","posted_at"])
paid_date={}   # invoice_id -> date fully covered
from collections import deque
for tid,g in ar.groupby("tenant_id"):
    q=deque()  # open debits: [invoice_id_or_None, remaining]
    for _,r in g.iterrows():
        if r["debit"]>0:
            iid=r["source_id"] if r["source_table"]=="invoices" else None
            q.append([iid, r["debit"]])
        if r["credit"]>0:
            amt=r["credit"]
            while amt>1e-6 and q:
                head=q[0]
                if head[1]<=amt+1e-6:
                    amt-=head[1]
                    if head[0] is not None: paid_date[head[0]]=r["entry_date"]
                    q.popleft()
                else:
                    head[1]-=amt; amt=0
# label only invoices that have an AR charge in the ledger
charged_ids=set(ar.loc[(ar["debit"]>0)&(ar["source_table"]=="invoices"),"source_id"])
lab=inv_meta[inv_meta.index.isin(charged_ids)].copy()
lab["paid_date"]=lab.index.map(paid_date)
lab["paid_date"]=to_dt(lab["paid_date"])
lab["overdue"]=((lab["paid_date"].isna()) | (lab["paid_date"]>lab["due_date"])).astype(int)
lab["days_late"]=(lab["paid_date"]-lab["due_date"]).dt.days
lab["bmonth"]=lab["billing_month"]

# ---------------- 2. TARGET VERIFICATION GATE ----------------
pos=int(lab["overdue"].sum()); neg=int((lab["overdue"]==0).sum()); n=len(lab)
months=sorted(lab["bmonth"].dropna().unique())
permonth=lab.groupby("bmonth")["overdue"].agg(["size","sum"])
print("="*72); print("TARGET VERIFICATION (ledger-FIFO overdue)"); print("="*72)
print(f"labeled invoices={n}  overdue(pos)={pos} ({pos/n:.1%})  ontime(neg)={neg}  months={len(months)}")
print(f"unpaid-as-of-data-end (paid_date null)={int(lab['paid_date'].isna().sum())}")
print("per-month (last 8):"); print(permonth.tail(8).to_string())
GATE = (pos>=150 and neg>=150 and len(months)>=12)
if not GATE:
    print("\nSTOP: insufficient positives/negatives/history for trustworthy walk-forward ML.")
    print("Do NOT invent labels. Report limitation."); sys.exit(0)
print("GATE PASSED -> proceed to leak-safe features + walk-forward.\n")

# ---------------- 3. LEAK-SAFE FEATURES (as-of invoice_date) ----------------
lab=lab.sort_values(["tenant_id","invoice_date"])
# tenant->bed type via allotment/bed
al=D["tenant_allotments"][["id","bed_id"]]; beds=D["beds"][["id","bed_type","toilet_type"]]
al=al.merge(beds,left_on="bed_id",right_on="id",how="left",suffixes=("","_b"))
btype=al.set_index("id")[["bed_type","toilet_type"]]
lab=lab.join(btype, on="allotment_id")
rows=[]
for tid,g in lab.groupby("tenant_id"):
    g=g.sort_values("invoice_date")
    hist=[]  # (due_date, overdue, paid_date, invoice_date)
    first_inv=g["invoice_date"].min()
    for iid,r in g.iterrows():
        idt=r["invoice_date"]
        # prior invoices whose outcome is known strictly before this invoice_date
        prior=[h for h in hist if h[0] < idt]
        pn=len(prior)
        pr_over=np.mean([h[1] for h in prior]) if pn else np.nan
        pr_late=np.mean([max((h[2]-h[0]).days,0) if pd.notna(h[2]) else 0 for h in prior]) if pn else np.nan
        # prior invoices still unpaid at this invoice_date
        pr_unpaid=sum(1 for h in prior if (pd.isna(h[2]) or h[2]>=idt))
        rows.append(dict(invoice_id=iid, tenant_id=tid, allotment_id=r["allotment_id"],
            bmonth=r["bmonth"], invoice_date=idt, overdue=r["overdue"],
            amount=r["total_amount"], rent=r["rent_amount"], eb=r["electricity_amount"],
            due_gap=(r["due_date"]-idt).days, month_num=int(str(r["bmonth"])[-2:]) if pd.notna(r["bmonth"]) else np.nan,
            tenure_days=(idt-first_inv).days, prior_n=pn, prior_overdue_rate=pr_over,
            prior_avg_days_late=pr_late, prior_unpaid=pr_unpaid, first_invoice=int(pn==0),
            bed_type=r.get("bed_type"), toilet_type=r.get("toilet_type")))
        hist.append((r["due_date"], r["overdue"], r["paid_date"], idt))
F=pd.DataFrame(rows)
global_rate=lab["overdue"].mean()
F["prior_overdue_rate"]=F["prior_overdue_rate"].fillna(global_rate)
F["prior_avg_days_late"]=F["prior_avg_days_late"].fillna(0)

# ---------------- 4. WALK-FORWARD (baseline vs ML) ----------------
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (precision_score,recall_score,f1_score,roc_auc_score,
                             average_precision_score,confusion_matrix)
NUM=["amount","rent","eb","due_gap","month_num","tenure_days","prior_n",
     "prior_overdue_rate","prior_avg_days_late","prior_unpaid","first_invoice"]
CAT=["bed_type","toilet_type"]
months=sorted(F["bmonth"].dropna().unique())
start_idx=12  # need >=12 months history before first test
oof=[]  # pooled out-of-fold test predictions
for i in range(start_idx,len(months)):
    test_m=months[i]; tr=F[F["bmonth"]<test_m]; te=F[F["bmonth"]==test_m]
    if te.empty or tr["overdue"].nunique()<2: continue
    pre=ColumnTransformer([("cat",OneHotEncoder(handle_unknown="ignore"),CAT)],remainder="passthrough")
    clf=Pipeline([("pre",pre),("gb",HistGradientBoostingClassifier(max_depth=4,learning_rate=0.06,
        max_iter=300,l2_regularization=1.0,random_state=42))])
    clf.fit(tr[NUM+CAT],tr["overdue"])
    p_ml=clf.predict_proba(te[NUM+CAT])[:,1]
    p_base=te["prior_overdue_rate"].values  # rule/baseline score = tenant's prior overdue rate
    d=te[["invoice_id","tenant_id","allotment_id","bmonth","overdue"]].copy()
    d["p_ml"]=p_ml; d["p_base"]=p_base
    oof.append(d)
OOF=pd.concat(oof,ignore_index=True)
y=OOF["overdue"].values
def metrics(y,p,thr=0.5):
    yhat=(p>=thr).astype(int)
    return dict(precision=round(precision_score(y,yhat,zero_division=0),3),
               recall=round(recall_score(y,yhat,zero_division=0),3),
               f1=round(f1_score(y,yhat,zero_division=0),3),
               roc_auc=round(roc_auc_score(y,p),3),
               pr_auc=round(average_precision_score(y,p),3),
               cm=confusion_matrix(y,yhat).tolist())
m_ml=metrics(y,OOF["p_ml"].values); m_base=metrics(y,OOF["p_base"].values)
OOF.to_csv(os.path.join(OUT,"phase2_overdue_oof_predictions.csv"),index=False)

# ---------------- 5. ACTIONABLE OUTPUT (latest month, model on all prior) ----------------
last_m=months[-1]; tr=F[F["bmonth"]<last_m]; cur=F[F["bmonth"]==last_m].copy()
pre=ColumnTransformer([("cat",OneHotEncoder(handle_unknown="ignore"),CAT)],remainder="passthrough")
clf=Pipeline([("pre",pre),("gb",HistGradientBoostingClassifier(max_depth=4,learning_rate=0.06,max_iter=300,l2_regularization=1.0,random_state=42))])
clf.fit(tr[NUM+CAT],tr["overdue"]); cur["risk"]=clf.predict_proba(cur[NUM+CAT])[:,1]
def reasons(r):
    b=[]
    if r["prior_overdue_rate"]>=0.5: b.append(f"prior overdue rate {r['prior_overdue_rate']:.0%}")
    if r["prior_unpaid"]>0: b.append(f"{int(r['prior_unpaid'])} prior unpaid")
    if r["first_invoice"]: b.append("new tenant (no history)")
    if r["amount"]>=20000: b.append(f"high amount ₹{r['amount']:,.0f}")
    if r["prior_avg_days_late"]>7: b.append(f"avg {r['prior_avg_days_late']:.0f}d late historically")
    return "; ".join(b) or "baseline risk"
cur["reasons"]=cur.apply(reasons,axis=1)
cur["recommended_action"]=pd.cut(cur["risk"],[-1,0.4,0.7,2],labels=["Monitor","Pre-emptive reminder","Priority reminder + call"])
act=cur.sort_values("risk",ascending=False)[["invoice_id","tenant_id","allotment_id","bmonth","amount","risk","reasons","recommended_action"]]
act.to_csv(os.path.join(OUT,"phase2_overdue_risk_scored.csv"),index=False)

# ---------------- STOP REPORT ----------------
print("="*72); print("PHASE 2 - OVERDUE MODEL: WALK-FORWARD RESULTS"); print("="*72)
print(f"walk-forward folds (test months): {len(oof)}  pooled test invoices: {len(OOF)}")
print(f"pooled class balance: overdue={y.mean():.1%}")
print(f"BASELINE (prior overdue rate): {m_base}")
print(f"ML (HistGradientBoosting)   : {m_ml}")
print(f"\nActionable scored (month {last_m}): {len(cur)} invoices  high-risk(>0.7)={int((cur['risk']>0.7).sum())}")
print("Top 8 risk:")
print(act.head(8).to_string(index=False,max_colwidth=48))
print("\nOutputs: phase2_overdue_oof_predictions.csv , phase2_overdue_risk_scored.csv")
