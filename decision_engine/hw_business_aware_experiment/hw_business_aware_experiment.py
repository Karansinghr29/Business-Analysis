"""
ISOLATED business-aware Holt-Winters experiment (read-only; writes ONLY to this dir's outputs/).

Architecture (approved Option 3 — regression + Holt-Winters-on-residuals; HW preserved as the time-series core):
    1. business-driver REGRESSION (Ridge) predicts revenue from LAGGED business drivers (leakage-safe)
    2. residual = actual_revenue - regression_pred        (training months only)
    3. Holt-Winters / ExponentialSmoothing is fit to the RESIDUAL series
    4. HW forecasts the next-month residual
    5. final forecast = regression_forecast + HW_residual_forecast
Holt-Winters still does the time-series job (on residuals); business drivers explain the level.

Compared against the EXISTING production revenue-only Holt-Winters (read from phase2_revenue_backtest.csv, NOT
retrained/modified) over the SAME unseen walk-forward window (2026-02..2026-08, 7 folds, START=24).

No existing file is modified. No synthetic/estimated/future data. Deterministic. All features are lags/rolling of
prior months or calendar — the target month's own revenue/occupancy/collections/electricity are never used.
"""
from __future__ import annotations
import os, sys, warnings
HERE=os.path.dirname(os.path.abspath(__file__)); ENGINE=os.path.dirname(HERE)
sys.path.insert(0, ENGINE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from loader import load_all, num, to_dt
OUTX=os.path.join(HERE,"outputs"); os.makedirs(OUTX,exist_ok=True)
HW_BACKTEST=os.path.join(ENGINE,"outputs","phase2_revenue_backtest.csv")   # READ-ONLY
START=24

REGFEAT=["rev_lag1","rev_lag2","rev_lag3","rev_roll3","active_lag1","occ_lag1","usable_lag1",
         "occrate_lag1","coll_lag1","collrate_lag1","eb_billed_lag1","month_num","sin_m","cos_m"]

def _naive(x):
    x=to_dt(x)
    try: return x.dt.tz_localize(None)
    except Exception: return x

def build_monthly():
    D,_=load_all()
    p=D["v_pnl_by_category"].copy(); p["revenue"]=num(p["revenue"])
    s=p.groupby("month")["revenue"].sum().sort_index(); s.index=pd.to_datetime(s.index)
    dense=s[s>s.max()*0.2]; s=s[s.index>=dense.index.min()].asfreq("MS"); idx=s.index
    al=D["tenant_allotments"].copy()
    for c in ["onboarding_date","booking_date","actual_exit_date"]: al[c]=to_dt(al[c])
    al["start"]=al["onboarding_date"].fillna(al["booking_date"])
    rc=D["receipts"].copy(); rc["payment_date"]=to_dt(rc["payment_date"]); rc["amount_paid"]=num(rc["amount_paid"])
    er=D["electricity_readings"].copy(); er["units_consumed"]=num(er["units_consumed"]); er["unit_cost"]=num(er["unit_cost"])
    er["bm"]=pd.to_datetime(er["billing_month"],format="%b-%y",errors="coerce").dt.strftime("%Y-%m")
    eb=(er["units_consumed"]*er["unit_cost"]).groupby(er["bm"]).sum()
    ap=D["apartments"].copy(); bd=D["beds"].copy()
    apsd=_naive(ap["start_date"]); apsd=apsd.where(apsd.dt.year>2000)
    aped=_naive(ap["end_date"]);   aped=aped.where(aped.dt.year>2000)
    apclosed=aped.where(ap["status"].astype(str).str.strip().eq("Not-Active"))
    aptab=pd.DataFrame({"aid":ap["id"].values,"apt_start":apsd.values,"apt_closed":apclosed.values})
    bd=bd.merge(aptab,left_on="apartment_id",right_on="aid",how="left"); bd["apt_start"]=bd["apt_start"].fillna(pd.Timestamp("2000-01-01"))
    CUR=idx[-1]; A_ST=bd["apt_start"]; A_CL=bd["apt_closed"]; LIVE=(bd["status"]=="Live")
    def usable_asof(m):
        op=(A_ST<m+pd.offsets.MonthBegin(1))&(A_CL.isna()|(A_CL>=m))
        if m>=CUR: op=op&LIVE
        return int(op.sum())
    rows=[]
    for m in idx:
        act=al[(al["start"]<=m)&((al["actual_exit_date"].isna())|(al["actual_exit_date"]>m))]
        coll=rc[(rc["payment_date"]>=m)&(rc["payment_date"]<m+pd.offsets.MonthBegin(1))]["amount_paid"].sum()
        rev=float(s.loc[m]); key=m.strftime("%Y-%m"); occ=int(act["bed_id"].nunique()); usable=usable_asof(m)
        rows.append(dict(period=key, revenue=round(rev), active_tenants=int(len(act)), occupied_beds=occ,
            usable_beds=usable, occupancy_rate=round(min(occ/usable,1.0),4) if usable else np.nan,
            collections=round(float(coll)), collection_rate=round(float(coll)/rev,4) if rev else np.nan,
            eb_billed=(round(float(eb[key])) if key in eb.index else np.nan)))
    df=pd.DataFrame(rows); dt=pd.to_datetime(df["period"]+"-01")
    df["month_num"]=dt.dt.month; df["quarter"]=dt.dt.quarter
    df["sin_m"]=np.sin(2*np.pi*df["month_num"]/12); df["cos_m"]=np.cos(2*np.pi*df["month_num"]/12)
    for l in (1,2,3): df[f"rev_lag{l}"]=df["revenue"].shift(l)
    df["rev_roll3"]=df["revenue"].shift(1).rolling(3).mean()
    df["active_lag1"]=df["active_tenants"].shift(1); df["occ_lag1"]=df["occupied_beds"].shift(1)
    df["usable_lag1"]=df["usable_beds"].shift(1); df["occrate_lag1"]=df["occupancy_rate"].shift(1)
    df["coll_lag1"]=df["collections"].shift(1); df["collrate_lag1"]=df["collection_rate"].shift(1)
    df["eb_billed_lag1"]=df["eb_billed"].shift(1)
    df["period_dt"]=dt
    df.to_csv(os.path.join(OUTX,"hw_business_aware_dataset.csv"),index=False)
    return df

def hw_resid_fit(res, steps=1):
    r=np.asarray(res,float); n=len(r)
    try:
        mdl=ExponentialSmoothing(r,trend="add",seasonal="add",seasonal_periods=12) if n>=24 else ExponentialSmoothing(r,trend="add",seasonal=None)
        return float(mdl.fit(optimized=True).forecast(steps)[-1])
    except Exception:
        return float(r[-1]) if n else 0.0

def met(a,pp):
    a=np.array(a,float); pp=np.array(pp,float); e=a-pp
    return dict(MAE=int(round(np.abs(e).mean())),RMSE=int(round(np.sqrt((e**2).mean()))),MAPE=round(float(np.mean(np.abs(e/a))*100),2))

def run():
    df=build_monthly().reset_index(drop=True); n=len(df)
    hw=pd.read_csv(HW_BACKTEST)[["month","hw"]]; hw_map=dict(zip(hw["month"],hw["hw"]))
    rows=[]
    for i in range(START,n):
        period=df.iloc[i]["period"]; actual=float(df.iloc[i]["revenue"])
        tr=df.iloc[:i].dropna(subset=REGFEAT+["revenue"]).copy()
        rec=dict(period=period, actual=round(actual), hw_baseline=(round(hw_map[period]) if period in hw_map else np.nan))
        if len(tr)>=10 and df.iloc[i][REGFEAT].notna().all():
            reg=Ridge(alpha=10.0); reg.fit(tr[REGFEAT],tr["revenue"])
            reg_test=float(reg.predict(df.iloc[[i]][REGFEAT])[0])
            resid_tr=tr["revenue"].values - reg.predict(tr[REGFEAT])          # training-only residuals
            resid_fc=hw_resid_fit(resid_tr,1)                                 # HW on residual series
            rec["regression_only"]=round(reg_test)
            rec["residual_forecast"]=round(resid_fc)
            rec["business_aware_hw"]=round(reg_test+resid_fc)
        else:
            rec["regression_only"]=rec["residual_forecast"]=rec["business_aware_hw"]=np.nan
        rows.append(rec)
    P=pd.DataFrame(rows); P.to_csv(os.path.join(OUTX,"hw_business_aware_predictions.csv"),index=False)

    comp=pd.DataFrame([
        dict(model="A. Existing Holt-Winters (revenue-only)",features="revenue history (univariate ES)",folds=int(P["hw_baseline"].notna().sum()),**met(P["actual"],P["hw_baseline"])),
        dict(model="B. Business-aware HW (regression + HW residual)",features=f"{len(REGFEAT)} lagged business drivers -> Ridge; HW on residuals",folds=int(P["business_aware_hw"].notna().sum()),**met(P.dropna(subset=["business_aware_hw"])["actual"],P.dropna(subset=["business_aware_hw"])["business_aware_hw"])),
        dict(model="   (diagnostic) regression component only",features="Ridge on lagged drivers, no HW residual",folds=int(P["regression_only"].notna().sum()),**met(P.dropna(subset=["regression_only"])["actual"],P.dropna(subset=["regression_only"])["regression_only"])),
    ])
    comp.to_csv(os.path.join(OUTX,"hw_business_aware_comparison.csv"),index=False)

    ea=P.copy(); ea["abs_err_hw"]=(ea["actual"]-ea["hw_baseline"]).abs(); ea["abs_err_bahw"]=(ea["actual"]-ea["business_aware_hw"]).abs()
    ea["signed_err_bahw"]=ea["actual"]-ea["business_aware_hw"]; ea.to_csv(os.path.join(OUTX,"hw_business_aware_error_analysis.csv"),index=False)

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,4.5))
    ax.plot(P["period"],P["actual"],marker="o",color="#222",label="Actual")
    ax.plot(P["period"],P["hw_baseline"],marker="s",color="#1f77b4",label="A. Revenue-only HW")
    ax.plot(P["period"],P["business_aware_hw"],marker="^",color="#d62728",label="B. Business-aware HW")
    ax.set_title("Actual vs predicted revenue (unseen 2026-02..2026-08)"); ax.tick_params(axis="x",rotation=45); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(OUTX,"hw_business_aware_actual_vs_predicted.png"),dpi=110); plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4)); x=np.arange(len(P)); w=0.4
    ax.bar(x-w/2,ea["abs_err_hw"],w,label="A. Revenue-only HW",color="#1f77b4")
    ax.bar(x+w/2,ea["abs_err_bahw"],w,label="B. Business-aware HW",color="#d62728")
    ax.set_xticks(x); ax.set_xticklabels(P["period"],rotation=45); ax.set_title("Absolute error by month"); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(OUTX,"hw_business_aware_errors.png"),dpi=110); plt.close(fig)

    print("="*80); print(f"BUSINESS-AWARE HOLT-WINTERS (regression + HW residual) — walk-forward {P['period'].iloc[0]}..{P['period'].iloc[-1]} ({len(P)} folds, START={START})")
    print("="*80); print(comp.to_string(index=False))
    mA=met(P["actual"],P["hw_baseline"]); mB=met(P["actual"],P["business_aware_hw"])
    better=[k for k in ("MAE","RMSE","MAPE") if mB[k]<mA[k]]
    print("\nVERDICT:", "Business-aware HW better on "+str(better) if better and len(better)==3 else
          ("Revenue-only HW better on all three" if not better else f"Mixed: business-aware better on {better}"))
    return comp

if __name__=="__main__": run()
