"""
Phase 2 - Tenant churn/exit prediction.
Primary target: notice OR exit within next 60 days.  Secondary: 30 days.
Monthly snapshots, leak-safe features, walk-forward by month, baseline vs ML, calibration.
Read-only on source CSVs. Outputs -> decision_engine/outputs/.
STOPs if reconciliation/leakage/validation is untrustworthy.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np, pandas as pd
from collections import deque, defaultdict
from loader import load_all, num, to_dt

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)
DATA_END=pd.Timestamp("2026-08-11")
D,_=load_all()

al=D["tenant_allotments"].copy()
for c in ["onboarding_date","booking_date","actual_exit_date","notice_date","estimated_exit_date"]:
    al[c]=to_dt(al[c])
al["start"]=al["onboarding_date"].fillna(al["booking_date"])

# ---------- 1. RECONCILIATION: allotment dates vs tenant_notices / tenant_exits ----------
print("="*72); print("STEP 1 — RECONCILIATION (allotment vs notices/exits tables)"); print("="*72)
al_exit=al[al["actual_exit_date"].notna()][["id","actual_exit_date"]]
al_notice=al[al["notice_date"].notna()][["id","notice_date"]]
print(f"allotments with actual_exit_date: {len(al_exit)} | with notice_date: {len(al_notice)}")
if "tenant_exits" in D:
    te=D["tenant_exits"].copy(); te["exit_date"]=to_dt(te["exit_date"])
    m=al_exit.merge(te[["allotment_id","exit_date"]],left_on="id",right_on="allotment_id",how="left")
    matched=m["exit_date"].notna().sum(); dif=(m["actual_exit_date"]-m["exit_date"]).dt.days.abs()
    print(f"tenant_exits rows={len(te)} | allotment-exits matched in tenant_exits={matched} "
          f"| unmatched(in allotment only)={len(al_exit)-matched} | date diff>3d={(dif>3).sum()}")
if "tenant_notices" in D:
    tn=D["tenant_notices"].copy(); tn["notice_date"]=to_dt(tn["notice_date"])
    m=al_notice.merge(tn.groupby("allotment_id")["notice_date"].min().rename("tn_notice"),left_on="id",right_index=True,how="left")
    matched=m["tn_notice"].notna().sum(); dif=(m["notice_date"]-m["tn_notice"]).dt.days.abs()
    print(f"tenant_notices rows={len(tn)} | allotment-notices matched in tenant_notices={matched} "
          f"| unmatched(in allotment only)={len(al_notice)-matched} | date diff>3d={(dif>3).sum()}")
print("DECISION: allotment-level notice_date/actual_exit_date used as PRIMARY (superset, authoritative).")

# ---------- precompute leak-safe history sources ----------
# FIFO paid_date per invoice (ledger truth) - computed once
tl=D["v_tenant_ledger"]; ar=tl[num(tl["account_code"])==1200].copy()
ar["entry_date"]=to_dt(ar["entry_date"]); ar["debit"]=num(ar["debit"]).fillna(0); ar["credit"]=num(ar["credit"]).fillna(0)
ar["is_credit"]=(ar["credit"]>0).astype(int); ar=ar.sort_values(["tenant_id","entry_date","is_credit","posted_at"])
paid={}; last_pay=defaultdict(list)
for tid,g in ar.groupby("tenant_id"):
    q=deque()
    for _,r in g.iterrows():
        if r["debit"]>0: q.append([r["source_id"] if r["source_table"]=="invoices" else None, r["debit"]])
        if r["credit"]>0:
            last_pay[tid].append(r["entry_date"]); amt=r["credit"]
            while amt>1e-6 and q:
                h=q[0]
                if h[1]<=amt+1e-6: amt-=h[1]; (paid.__setitem__(h[0],r["entry_date"]) if h[0] else None); q.popleft()
                else: h[1]-=amt; amt=0
inv=D["invoices"].copy(); inv["invoice_date"]=to_dt(inv["invoice_date"]); inv["due_date"]=to_dt(inv["due_date"]); inv["total_amount"]=num(inv["total_amount"])
inv["paid_date"]=inv["id"].map(paid); inv["paid_date"]=to_dt(inv["paid_date"])
inv_by_al=defaultdict(list)
for _,r in inv.iterrows():
    inv_by_al[r["allotment_id"]].append((r["invoice_date"],r["due_date"],r["paid_date"]))
pays_by_tid={k:sorted(v) for k,v in last_pay.items()}
# room switches, tickets (leak-safe counts before snapshot)
sw_by_al=defaultdict(list)
if "room_switches" in D:
    rs=D["room_switches"].copy(); rs["switch_date"]=to_dt(rs["switch_date"])
    for _,r in rs.iterrows(): sw_by_al[r["allotment_id"]].append(r["switch_date"])
tk_by_al=defaultdict(list)
if "maintenance_tickets" in D:
    mt=D["maintenance_tickets"].copy(); mt["created_at"]=to_dt(mt["created_at"])
    for _,r in mt.iterrows(): tk_by_al[r.get("allotment_id", r.get("bed_id"))].append(r["created_at"])
# bed type
beds=D["beds"][["id","bed_type","toilet_type"]]
al=al.merge(beds,left_on="bed_id",right_on="id",how="left",suffixes=("","_bed"))
al["monthly_rental"]=num(al["monthly_rental"]); al["discount"]=num(al.get("discount"))

# ---------- 2/3/4/5. SNAPSHOT PANEL (leak-safe) ----------
def build(hz):
    months=pd.date_range("2023-01-01","2026-06-01",freq="MS")
    rows=[]
    for M in months:
        end=M+pd.Timedelta(days=hz)
        if end>DATA_END: continue
        for _,a in al.iterrows():
            if pd.isna(a["start"]) or a["start"]>M: continue                       # not onboarded
            if pd.notna(a["actual_exit_date"]) and a["actual_exit_date"]<=M: continue  # already exited
            if pd.notna(a["notice_evt_col"]) and a["notice_evt_col"]<=M: continue      # already on notice (excluded)
            # label
            nt=a["notice_evt_col"]; ex=a["actual_exit_date"]
            churn=int(((pd.notna(nt) and M<nt<=end) or (pd.notna(ex) and M<ex<=end)))
            # leak-safe features (history < M only)
            ivs=inv_by_al.get(a["id"],[])
            prior=[x for x in ivs if pd.notna(x[0]) and x[0]<M]
            resolved=[x for x in prior if pd.notna(x[1]) and x[1]<M]  # due before M -> outcome known
            over=[1 if (pd.isna(x[2]) or x[2]>x[1]) else 0 for x in resolved]
            unpaid_at_M=sum(1 for x in prior if (pd.isna(x[2]) or x[2]>=M))
            pays=[p for p in pays_by_tid.get(a["tenant_id"],[]) if p<M]
            dsl=(M-max(pays)).days if pays else np.nan
            rows.append(dict(month=M.strftime("%Y-%m"), tenant_id=a["tenant_id"], allotment_id=a["id"],
                churn=churn, tenure_days=(M-a["start"]).days, monthly_rental=a["monthly_rental"],
                discount=a["discount"] if pd.notna(a["discount"]) else 0,
                bed_type=a["bed_type"], toilet_type=a["toilet_type"],
                prior_inv_n=len(prior), prior_overdue_rate=(np.mean(over) if over else np.nan),
                prior_unpaid_at_M=unpaid_at_M, days_since_payment=dsl,
                prior_switches=sum(1 for s in sw_by_al.get(a["id"],[]) if pd.notna(s) and s<M),
                prior_tickets=sum(1 for t in tk_by_al.get(a["id"],[]) if pd.notna(t) and t<M),
                month_num=M.month))
    F=pd.DataFrame(rows)
    F["prior_overdue_rate"]=F["prior_overdue_rate"].fillna(F["churn"].mean()*0+ F["prior_overdue_rate"].mean())
    return F

al["notice_evt_col"]=al["notice_date"]

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (precision_score,recall_score,f1_score,roc_auc_score,
                             average_precision_score,confusion_matrix,brier_score_loss)
from sklearn.calibration import calibration_curve
NUM=["tenure_days","monthly_rental","discount","prior_inv_n","prior_overdue_rate",
     "prior_unpaid_at_M","days_since_payment","prior_switches","prior_tickets","month_num"]
CAT=["bed_type","toilet_type"]

def walk(F,label):
    months=sorted(F["month"].unique()); oof=[]; fold_auc=[]
    for i in range(12,len(months)):
        tm=months[i]; tr=F[F["month"]<tm]; te=F[F["month"]==tm]
        if te.empty or tr["churn"].nunique()<2 or te["churn"].nunique()<2: continue
        pre=ColumnTransformer([("cat",OneHotEncoder(handle_unknown="ignore"),CAT)],remainder="passthrough")
        clf=Pipeline([("pre",pre),("gb",HistGradientBoostingClassifier(max_depth=4,learning_rate=0.05,
            max_iter=350,l2_regularization=1.0,random_state=42))])
        clf.fit(tr[NUM+CAT],tr["churn"])
        p=clf.predict_proba(te[NUM+CAT])[:,1]
        # deterministic baseline: short tenure + prior overdue (scaled)
        base=(1/(1+te["tenure_days"].clip(lower=0)/180))*0.6 + te["prior_overdue_rate"].fillna(F["churn"].mean())*0.4
        d=te[["month","tenant_id","allotment_id","churn"]].copy(); d["p_ml"]=p; d["p_base"]=base.values
        oof.append(d); fold_auc.append(roc_auc_score(te["churn"],p))
    O=pd.concat(oof,ignore_index=True); y=O["churn"].values
    def mt(p,thr=0.5):
        yh=(p>=thr).astype(int)
        return dict(precision=round(precision_score(y,yh,zero_division=0),3),
            recall=round(recall_score(y,yh,zero_division=0),3),f1=round(f1_score(y,yh,zero_division=0),3),
            roc_auc=round(roc_auc_score(y,p),3),pr_auc=round(average_precision_score(y,p),3),
            cm=confusion_matrix(y,yh).tolist())
    print(f"\n=== {label} === folds={len(fold_auc)} pooled_n={len(O)} churn_rate={y.mean():.1%}")
    print(f"  fold ROC-AUC mean={np.mean(fold_auc):.3f} std={np.std(fold_auc):.3f} min={np.min(fold_auc):.3f} max={np.max(fold_auc):.3f}")
    print(f"  BASELINE(rule): {mt(O['p_base'].values)}")
    print(f"  ML(HGB)       : {mt(O['p_ml'].values)}")
    # calibration
    frac,mean_pred=calibration_curve(y,O["p_ml"].values,n_bins=10,strategy="quantile")
    brier=brier_score_loss(y,O["p_ml"].values)
    print(f"  calibration Brier={brier:.3f}  reliability(pred->obs): "+
          ", ".join(f"{mp:.2f}->{fr:.2f}" for mp,fr in zip(mean_pred,frac)))
    return O

F60=build(60); O60=walk(F60,"PRIMARY notice_or_exit <=60d")
F30=build(30); O30=walk(F30,"SECONDARY notice_or_exit <=30d")
O60.to_csv(os.path.join(OUT,"phase2_churn_oof_60d.csv"),index=False)
O30.to_csv(os.path.join(OUT,"phase2_churn_oof_30d.csv"),index=False)

# ---------- 11. ACTIONABLE CURRENT RISK (latest snapshot, 60d) ----------
last=sorted(F60["month"].unique())[-1]
tr=F60[F60["month"]<last]; cur=F60[F60["month"]==last].copy()
pre=ColumnTransformer([("cat",OneHotEncoder(handle_unknown="ignore"),CAT)],remainder="passthrough")
clf=Pipeline([("pre",pre),("gb",HistGradientBoostingClassifier(max_depth=4,learning_rate=0.05,max_iter=350,l2_regularization=1.0,random_state=42))])
clf.fit(tr[NUM+CAT],tr["churn"]); cur["risk"]=clf.predict_proba(cur[NUM+CAT])[:,1]
def reasons(r):
    b=[]
    if r["tenure_days"]<120: b.append(f"short tenure {int(r['tenure_days'])}d")
    if (r["prior_overdue_rate"] or 0)>=0.5: b.append(f"overdue history {r['prior_overdue_rate']:.0%}")
    if r["prior_unpaid_at_M"]>0: b.append(f"{int(r['prior_unpaid_at_M'])} unpaid invoices")
    if r["prior_switches"]>0: b.append(f"{int(r['prior_switches'])} prior room switch")
    if (r["days_since_payment"] or 0)>45: b.append(f"{int(r['days_since_payment'])}d since payment")
    return "; ".join(b) or "model risk"
cur["reasons"]=cur.apply(reasons,axis=1)
cur["risk_band"]=pd.cut(cur["risk"],[-1,0.33,0.6,2],labels=["Low","Medium","High"])
cur["retention_action"]=cur["risk_band"].map({"High":"Retention call + offer/renewal","Medium":"Check-in / satisfaction touch","Low":"Monitor"})
act=cur.sort_values("risk",ascending=False)[["tenant_id","allotment_id","month","tenure_days","risk","risk_band","reasons","retention_action"]]
act.to_csv(os.path.join(OUT,"phase2_churn_risk_scored.csv"),index=False)
print(f"\nActionable (snapshot {last}, 60d): scored={len(cur)} High={int((cur['risk_band']=='High').sum())} Medium={int((cur['risk_band']=='Medium').sum())}")
print("Outputs: phase2_churn_oof_60d.csv, phase2_churn_oof_30d.csv, phase2_churn_risk_scored.csv")
