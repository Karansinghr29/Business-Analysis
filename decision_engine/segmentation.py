"""
Phase 2 - Tenant segmentation (behavioural, descriptive; NOT a churn model).
Unit = tenant_id (stable; a tenant may hold multiple allotments/switches).
Leak-safe historical billing behaviour only. No city/profession, no lifecycle-outcome fields.
Read-only source CSVs. STOPs if clustering isn't justified.
"""
from __future__ import annotations
import os, sys, warnings
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
from collections import deque, defaultdict
from loader import load_all, num, to_dt

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)
ASOF=pd.Timestamp("2026-08-11")
D,_=load_all()

# ---------- 1. VERIFY tenant unit ----------
al=D["tenant_allotments"].copy()
for c in ["onboarding_date","booking_date","actual_exit_date"]: al[c]=to_dt(al[c])
al["start"]=al["onboarding_date"].fillna(al["booking_date"])
tn=D["tenants"]
inv=D["invoices"].copy(); inv["invoice_date"]=to_dt(inv["invoice_date"]); inv["due_date"]=to_dt(inv["due_date"])
for c in ["rent_amount","electricity_amount","total_amount"]: inv[c]=num(inv[c])
print("="*72); print("STEP 1 — TENANT UNIT VERIFICATION"); print("="*72)
print(f"unique tenants (tenants table)={tn['id'].nunique()}  allotments={len(al)}")
apt=al.groupby("tenant_id")["id"].nunique()
print(f"tenants with >1 allotment (switches/rebook): {(apt>1).sum()}  max allotments/tenant={apt.max()}")
print(f"invoices={len(inv)}  invoices with tenant_id null={inv['tenant_id'].isna().sum()}")
print("DECISION: unit = tenant_id (aggregate across allotments).")

# ---------- FIFO paid_date (ledger truth) for overdue behaviour ----------
tl=D["v_tenant_ledger"]; ar=tl[num(tl["account_code"])==1200].copy()
ar["entry_date"]=to_dt(ar["entry_date"]); ar["debit"]=num(ar["debit"]).fillna(0); ar["credit"]=num(ar["credit"]).fillna(0)
ar["is_credit"]=(ar["credit"]>0).astype(int); ar=ar.sort_values(["tenant_id","entry_date","is_credit","posted_at"])
paid={}
for tid,g in ar.groupby("tenant_id"):
    q=deque()
    for _,r in g.iterrows():
        if r["debit"]>0: q.append([r["source_id"] if r["source_table"]=="invoices" else None, r["debit"]])
        if r["credit"]>0:
            amt=r["credit"]
            while amt>1e-6 and q:
                h=q[0]
                if h[1]<=amt+1e-6: amt-=h[1]; (paid.__setitem__(h[0],r["entry_date"]) if h[0] else None); q.popleft()
                else: h[1]-=amt; amt=0
inv["paid_date"]=to_dt(inv["id"].map(paid))
inv["overdue"]=((inv["paid_date"].isna())|(inv["paid_date"]>inv["due_date"])).astype(int)
inv["days_late"]=(inv["paid_date"]-inv["due_date"]).dt.days.clip(lower=0)

# ---------- 3. BEHAVIOURAL FEATURES per tenant (as-of ASOF; historical only) ----------
sw=al.groupby("tenant_id")["id"].nunique().rename("n_allotments")
onb=al.groupby("tenant_id")["start"].min().rename("first_start")
rows=[]
for tid,g in inv.groupby("tenant_id"):
    n=len(g)
    if n<2: continue
    first=min(g["invoice_date"].min(), onb.get(tid, g["invoice_date"].min()))
    last=g["invoice_date"].max()
    tenure=max((last-first).days,1)
    rent=g["rent_amount"]
    rows.append(dict(tenant_id=tid, n_invoices=n, tenure_days=tenure,
        n_allotments=int(sw.get(tid,1)),
        avg_rent=rent.mean(), rent_cv=(rent.std()/rent.mean() if rent.mean() else 0),
        overdue_rate=g["overdue"].mean(),
        avg_days_late=g.loc[g["overdue"]==1,"days_late"].mean() if g["overdue"].any() else 0,
        unpaid_count=int(g["paid_date"].isna().sum()),
        avg_eb=g["electricity_amount"].mean(),
        billing_freq=n/max(tenure/30.0,1)))
F=pd.DataFrame(rows).fillna({"avg_days_late":0,"rent_cv":0})
# discount dependency from allotments
al["discount"]=num(al.get("discount")); al["monthly_rental"]=num(al["monthly_rental"])
dd=al.groupby("tenant_id").apply(lambda x:(x["discount"].fillna(0).sum())/max(x["monthly_rental"].sum(),1)).rename("discount_dependency")
F=F.merge(dd,on="tenant_id",how="left").fillna({"discount_dependency":0})
F["n_switches"]=(F["n_allotments"]-1).clip(lower=0)
active_ids=set(al.loc[al["actual_exit_date"].isna(),"tenant_id"])
F["is_active"]=F["tenant_id"].isin(active_ids).astype(int)

FEATS=["tenure_days","n_invoices","avg_rent","rent_cv","overdue_rate","avg_days_late",
       "unpaid_count","avg_eb","billing_freq","discount_dependency","n_switches"]
print("\n"+"="*72); print("STEP 3 — FEATURES (coverage)"); print("="*72)
print(f"tenants with >=2 invoices (segmented population)={len(F)}  active={F['is_active'].sum()}")
for c in FEATS: print(f"  {c:20} null%={F[c].isna().mean():.0%}  mean={F[c].mean():.1f}")
print("\n[LEAKAGE] as-of "+str(ASOF.date())+"; used only historical invoices/ledger. "
      "Excluded: staying_status, notice_date, actual_exit_date, estimated_exit_date, deposit_settlements, city/profession.")

# ---------- 5. K SELECTION ----------
from sklearn.preprocessing import RobustScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, adjusted_rand_score
X=RobustScaler().fit_transform(F[FEATS].fillna(0))
print("\n"+"="*72); print("STEP 5 — K SELECTION (silhouette)"); print("="*72)
sil={}
for k in range(2,7):
    km=KMeans(n_clusters=k,n_init=10,random_state=42).fit(X)
    sc=silhouette_score(X,km.labels_)
    sizes=pd.Series(km.labels_).value_counts().sort_index().tolist()
    sil[k]=(sc,sizes); print(f"  K={k}: silhouette={sc:.3f} sizes={sizes}")
bestK=max(sil,key=lambda k:sil[k][0])
print(f"  -> best silhouette at K={bestK} ({sil[bestK][0]:.3f})")

# guard: is clustering meaningful?
if sil[bestK][0] < 0.15:
    print("\nWARNING: max silhouette < 0.15 -> weak/soft structure. Report as tendencies, not hard segments.")

# ---------- 10. STABILITY (bootstrap ARI) ----------
kmf=KMeans(n_clusters=bestK,n_init=10,random_state=42).fit(X)
base=kmf.labels_
aris=[]
rng=np.random.RandomState(0)
for b in range(15):
    idx=rng.choice(len(F),int(0.8*len(F)),replace=False)
    lb=KMeans(n_clusters=bestK,n_init=10,random_state=b).fit(X[idx]).labels_
    aris.append(adjusted_rand_score(base[idx],lb))
print(f"\nSTEP 10 — stability: bootstrap ARI mean={np.mean(aris):.3f} std={np.std(aris):.3f} min={np.min(aris):.3f}")

# ---------- 8/9. PROFILES + BUSINESS ACTION ----------
F["cluster"]=base
prof=F.groupby("cluster")[FEATS].mean().round(1); prof["size"]=F.groupby("cluster").size(); prof["active"]=F.groupby("cluster")["is_active"].sum()
prof.to_csv(os.path.join(OUT,"phase2_segment_profiles.csv"))
# deterministic label/action from cluster feature ranks (data-driven, no invented traits)
med=F[FEATS].median()
def label_action(r):
    tags=[]; act=[]
    if r["overdue_rate"]>=max(0.7,med["overdue_rate"]) or r["unpaid_count"]>med["unpaid_count"]:
        tags.append("frequent-late-payer"); act.append("Proactive collections")
    if r["avg_rent"]>=F["avg_rent"].quantile(.75):
        tags.append("high-rent/high-value"); act.append("Retention priority")
    if r["tenure_days"]>=F["tenure_days"].quantile(.75) and r["overdue_rate"]<med["overdue_rate"]:
        tags.append("reliable long-tenure"); act.append("Renewal / loyalty")
    if r["discount_dependency"]>=F["discount_dependency"].quantile(.75) and r["discount_dependency"]>0.01:
        tags.append("discount-dependent"); act.append("Pricing review")
    if r["avg_eb"]>=F["avg_eb"].quantile(.8):
        tags.append("high-electricity"); act.append("EB monitoring")
    if not tags: tags=["standard"]; act=["Monitor"]
    return "; ".join(dict.fromkeys(tags)), "; ".join(dict.fromkeys(act))
prof2=prof.copy()
lab=prof2.apply(lambda r: label_action(r),axis=1)
prof2["segment"]=[l[0] for l in lab]; prof2["business_action"]=[l[1] for l in lab]
prof2.to_csv(os.path.join(OUT,"phase2_segment_profiles.csv"))
F["segment"]=F["cluster"].map(prof2["segment"]); F["business_action"]=F["cluster"].map(prof2["business_action"])
F[["tenant_id","is_active","cluster","segment","business_action"]+FEATS].to_csv(os.path.join(OUT,"phase2_tenant_segments.csv"),index=False)

print("\n"+"="*72); print("CLUSTER PROFILES"); print("="*72)
print(prof2[["size","active","avg_rent","tenure_days","overdue_rate","avg_days_late","unpaid_count","avg_eb","discount_dependency","segment","business_action"]].to_string())
print("\nOutputs: phase2_segment_profiles.csv, phase2_tenant_segments.csv")
