"""
ISOLATED XGBoost revenue-forecasting experiment (read-only; writes ONLY to xgb_revenue_experiment/outputs/).
Adapts the Vishful analytics XGBoost-challenger principle (real monthly business features + valid lags) and
compares it to the EXISTING production Holt-Winters over the SAME unseen walk-forward window (2026-02..2026-08).

Holt-Winters is NOT modified/retrained — its predictions are READ from outputs/phase2_revenue_backtest.csv.
No existing file is modified. Deterministic (fixed seeds). No synthetic data; features are all real & leakage-free.

Real monthly business series (authoritative Vishful tables, read-only via loader):
  revenue          v_pnl_by_category.revenue        (accrual, monthly sum)  -> TARGET
  active_tenants   tenant_allotments active as-of m (count)
  occupied_beds    tenant_allotments active as-of m (nunique bed_id)
  collections      receipts.amount_paid in month m  (cash collected)
  eb_billed        electricity_readings units_consumed*unit_cost by billing_month
  collection_rate  collections / revenue            (used ONLY as a lag -> no leakage)

Leakage rule: for predicting revenue[t], every feature uses information dated <= t-1 (lags/rollings on prior
months only) or a deterministic calendar. The target month's own revenue/occupancy/collections/EB are never used.
"""
from __future__ import annotations
import os, sys, warnings
HERE=os.path.dirname(os.path.abspath(__file__)); ENGINE=os.path.dirname(HERE)
sys.path.insert(0, ENGINE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
import xgboost as xgb
from loader import load_all, num, to_dt
OUTX=os.path.join(HERE,"outputs"); os.makedirs(OUTX,exist_ok=True)
HW_BACKTEST=os.path.join(ENGINE,"outputs","phase2_revenue_backtest.csv")   # READ-ONLY
START=24  # match production Holt-Winters walk-forward window

# XGBoost features — all real, all available at/before prediction time (lags or calendar)
XFEAT=["rev_lag1","rev_lag2","rev_lag3","rev_lag6","rev_lag12","rev_roll3",
       "active_lag1","occ_lag1","usable_lag1","occrate_lag1","coll_lag1","collrate_lag1","eb_billed_lag1",
       "month_num","quarter","sin_m","cos_m"]

def build_monthly():
    D,_=load_all()
    p=D["v_pnl_by_category"].copy(); p["revenue"]=num(p["revenue"])
    s=p.groupby("month")["revenue"].sum().sort_index(); s.index=pd.to_datetime(s.index)
    dense=s[s>s.max()*0.2]; s=s[s.index>=dense.index.min()].asfreq("MS"); idx=s.index; y=s.values.astype(float)
    al=D["tenant_allotments"].copy()
    for c in ["onboarding_date","booking_date","actual_exit_date"]: al[c]=to_dt(al[c])
    al["start"]=al["onboarding_date"].fillna(al["booking_date"])
    rc=D["receipts"].copy(); rc["payment_date"]=to_dt(rc["payment_date"]); rc["amount_paid"]=num(rc["amount_paid"])
    er=D["electricity_readings"].copy(); er["units_consumed"]=num(er["units_consumed"]); er["unit_cost"]=num(er["unit_cost"])
    er["bm"]=pd.to_datetime(er["billing_month"],format="%b-%y",errors="coerce").dt.strftime("%Y-%m")
    eb=(er["units_consumed"]*er["unit_cost"]).groupby(er["bm"]).sum()
    # ---- usable beds via apartment LIFECYCLE (start_date phase-in + closure phase-out for Not-Active apts;
    #      current/forward Live-only; beds.created_at never used) — reproduced locally, no production edit ----
    def _naive(x):
        x=to_dt(x)
        try: return x.dt.tz_localize(None)
        except Exception: return x
    ap=D["apartments"].copy(); bd=D["beds"].copy()
    apsd=_naive(ap["start_date"]); apsd=apsd.where(apsd.dt.year>2000)
    aped=_naive(ap["end_date"]);   aped=aped.where(aped.dt.year>2000)
    apclosed=aped.where(ap["status"].astype(str).str.strip().eq("Not-Active"))
    aptab=pd.DataFrame({"aid":ap["id"].values,"apt_start":apsd.values,"apt_closed":apclosed.values})
    bd=bd.merge(aptab,left_on="apartment_id",right_on="aid",how="left")
    bd["apt_start"]=bd["apt_start"].fillna(pd.Timestamp("2000-01-01"))
    CUR=idx[-1]; A_ST=bd["apt_start"]; A_CL=bd["apt_closed"]; LIVE=(bd["status"]=="Live")
    def usable_asof(m):
        op=(A_ST<m+pd.offsets.MonthBegin(1))&(A_CL.isna()|(A_CL>=m))
        if m>=CUR: op=op&LIVE
        return int(op.sum())
    rows=[]
    for m in idx:
        act=al[(al["start"]<=m)&((al["actual_exit_date"].isna())|(al["actual_exit_date"]>m))]
        coll=rc[(rc["payment_date"]>=m)&(rc["payment_date"]<m+pd.offsets.MonthBegin(1))]["amount_paid"].sum()
        rev=float(s.loc[m]); key=m.strftime("%Y-%m")
        occ=int(act["bed_id"].nunique()); usable=usable_asof(m)
        rows.append(dict(period=key, revenue=round(rev), active_tenants=int(len(act)),
            occupied_beds=occ, usable_beds=usable,
            occupancy_rate=round(min(occ/usable,1.0),4) if usable else np.nan,
            collections=round(float(coll)),
            eb_billed=(round(float(eb[key])) if key in eb.index else np.nan),
            collection_rate=round(float(coll)/rev,4) if rev else np.nan))
    df=pd.DataFrame(rows)
    dt=pd.to_datetime(df["period"]+"-01")
    df["month_num"]=dt.dt.month; df["quarter"]=dt.dt.quarter
    df["sin_m"]=np.sin(2*np.pi*df["month_num"]/12); df["cos_m"]=np.cos(2*np.pi*df["month_num"]/12)
    for l in (1,2,3,6,12): df[f"rev_lag{l}"]=df["revenue"].shift(l)
    df["rev_roll3"]=df["revenue"].shift(1).rolling(3).mean()
    df["active_lag1"]=df["active_tenants"].shift(1); df["occ_lag1"]=df["occupied_beds"].shift(1)
    df["usable_lag1"]=df["usable_beds"].shift(1); df["occrate_lag1"]=df["occupancy_rate"].shift(1)
    df["coll_lag1"]=df["collections"].shift(1); df["collrate_lag1"]=df["collection_rate"].shift(1)
    df["eb_billed_lag1"]=df["eb_billed"].shift(1)
    df.to_csv(os.path.join(OUTX,"xgb_revenue_experiment_dataset.csv"),index=False)
    return df

def met(a,pp):
    a=np.array(a,float); pp=np.array(pp,float); e=a-pp
    return dict(MAE=int(round(np.abs(e).mean())),RMSE=int(round(np.sqrt((e**2).mean()))),MAPE=round(float(np.mean(np.abs(e/a))*100),2))

def new_xgb():
    return xgb.XGBRegressor(n_estimators=200,max_depth=3,learning_rate=0.05,subsample=0.9,
                            colsample_bytree=0.9,reg_lambda=1.0,random_state=42,n_jobs=1,verbosity=0)

def run():
    df=build_monthly().reset_index(drop=True); n=len(df)
    hwbt=pd.read_csv(HW_BACKTEST); hw_map=dict(zip(hwbt["month"],hwbt["hw"]))
    xgprod_map=dict(zip(hwbt["month"],hwbt["xgb"])) if "xgb" in hwbt.columns else {}
    rows=[]; imps=[]
    for i in range(START,n):
        period=df.iloc[i]["period"]; actual=float(df.iloc[i]["revenue"])
        tr=df.iloc[:i].dropna(subset=XFEAT+["revenue"])
        rec=dict(period=period, actual=round(actual), hw=(round(hw_map[period]) if period in hw_map else np.nan),
                 xgb_production=(round(xgprod_map[period]) if period in xgprod_map and pd.notna(xgprod_map[period]) else np.nan))
        if len(tr)>=10 and df.iloc[i][XFEAT].notna().all():
            m=new_xgb(); m.fit(tr[XFEAT],tr["revenue"])
            rec["xgboost"]=round(float(m.predict(df.iloc[[i]][XFEAT])[0]))
            imps.append(dict(zip(XFEAT,m.feature_importances_)))
        else:
            rec["xgboost"]=np.nan
        rows.append(rec)
    P=pd.DataFrame(rows); P.to_csv(os.path.join(OUTX,"xgb_revenue_experiment_predictions.csv"),index=False)

    mHW=met(P["actual"],P["hw"]); mXG=met(P.dropna(subset=["xgboost"])["actual"],P.dropna(subset=["xgboost"])["xgboost"])
    comp_rows=[dict(model="Existing Holt-Winters",features="historical revenue time series",folds=int(P["hw"].notna().sum()),**mHW),
               dict(model="XGBoost (this experiment)",features=f"{len(XFEAT)} real business lags + calendar",folds=int(P["xgboost"].notna().sum()),**mXG)]
    if P["xgb_production"].notna().any():
        pp=P.dropna(subset=["xgb_production"]); mXP=met(pp["actual"],pp["xgb_production"])
        comp_rows.append(dict(model="XGBoost (existing challenger)",features="9 lags (rev/active/occ/coll/month) — read from production backtest",folds=int(P["xgb_production"].notna().sum()),**mXP))
    comp=pd.DataFrame(comp_rows)
    comp.to_csv(os.path.join(OUTX,"xgb_revenue_experiment_comparison.csv"),index=False)

    imp=(pd.DataFrame(imps).mean().sort_values(ascending=False).rename("importance").reset_index()
         .rename(columns={"index":"feature"}))
    imp.to_csv(os.path.join(OUTX,"xgb_revenue_experiment_feature_importance.csv"),index=False)

    ea=P.copy(); ea["abs_error_xgb"]=(ea["actual"]-ea["xgboost"]).abs(); ea["signed_error_xgb"]=ea["actual"]-ea["xgboost"]
    ea["abs_error_hw"]=(ea["actual"]-ea["hw"]).abs()
    ea.to_csv(os.path.join(OUTX,"xgb_revenue_experiment_error_analysis.csv"),index=False)

    # ---- plots (isolated) ----
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,4.5))
    ax.plot(P["period"],P["actual"],marker="o",color="#222",label="Actual")
    ax.plot(P["period"],P["hw"],marker="s",color="#1f77b4",label="Holt-Winters (existing)")
    ax.plot(P["period"],P["xgboost"],marker="^",color="#d62728",label="XGBoost")
    ax.set_title("Actual vs predicted revenue (unseen 2026-02..2026-08)"); ax.tick_params(axis="x",rotation=45)
    ax.legend(); fig.tight_layout(); fig.savefig(os.path.join(OUTX,"xgb_revenue_experiment_actual_vs_predicted.png"),dpi=110); plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4))
    w=0.4; x=np.arange(len(P))
    ax.bar(x-w/2,ea["abs_error_hw"],w,label="HW",color="#1f77b4"); ax.bar(x+w/2,ea["abs_error_xgb"],w,label="XGBoost",color="#d62728")
    ax.set_xticks(x); ax.set_xticklabels(P["period"],rotation=45); ax.set_title("Absolute error over time"); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(OUTX,"xgb_revenue_experiment_errors.png"),dpi=110); plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4))
    ax.barh(imp["feature"][::-1],imp["importance"][::-1],color="#ff7f0e"); ax.set_title("XGBoost feature importance (mean gain across folds)")
    fig.tight_layout(); fig.savefig(os.path.join(OUTX,"xgb_revenue_experiment_feature_importance.png"),dpi=110); plt.close(fig)

    print("="*74); print(f"ISOLATED XGBoost vs HOLT-WINTERS — walk-forward {P['period'].iloc[0]}..{P['period'].iloc[-1]} ({len(P)} folds, START={START})")
    print("="*74)
    print(comp.to_string(index=False))
    print("\nTop features:", ", ".join(f"{r.feature} {r.importance:.3f}" for r in imp.head(6).itertuples()))
    better=[k for k in ("MAE","RMSE","MAPE") if mXG[k]<mHW[k]]
    if len(better)==3: verdict="XGBoost better on all three metrics."
    elif not better:   verdict="Holt-Winters better on all three metrics."
    else:              verdict=f"Mixed: XGBoost better on {better}; Holt-Winters better on the rest."
    print("\nVERDICT:",verdict)
    return comp

if __name__=="__main__": run()
