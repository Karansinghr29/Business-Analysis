"""
ISOLATED component-based revenue forecast (read-only; writes ONLY to this dir's outputs/).

Architecture (approved):
    rental_forecast   = occupied_beds_forecast x effective_rent_forecast     (real P&L identity)
    total_forecast    = rental_forecast + electricity_forecast + minor-component forecasts + reconciling 'other'
Each piece forecast chronologically using ONLY information before the test month. Compared to the EXISTING
production revenue-only Holt-Winters (read from phase2_revenue_backtest.csv, NOT retrained) over the same unseen
window (2026-02..2026-08, 7 folds, START=24).

Methods (deliberately simple, not blind ML):
  occupied_beds       Exponential Smoothing (additive trend + seasonal)   -- stable series, mild seasonality
  effective_rent/bed  Exponential Smoothing (additive trend, NO seasonal) -- ~2.6x escalation is trend, not season
  electricity_income  Exponential Smoothing (additive trend + seasonal)   -- ~9% of revenue, AC seasonality
  minor + other       trailing-3-month MEDIAN (conservative)              -- small, noisy; no model invented
Identity `rental_income == occupied_beds x effective_rent_per_bed` holds by construction (effective rent is
rental/occupied). No manufactured occupancy/rent/electricity values. No test-month actual used anywhere.
No existing file modified. Deterministic.
"""
from __future__ import annotations
import os, sys, warnings
HERE=os.path.dirname(os.path.abspath(__file__)); ENGINE=os.path.dirname(HERE)
sys.path.insert(0, ENGINE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from loader import load_all, num, to_dt
OUTX=os.path.join(HERE,"outputs"); os.makedirs(OUTX,exist_ok=True)
HW_BACKTEST=os.path.join(ENGINE,"outputs","phase2_revenue_backtest.csv")   # READ-ONLY
START=24
MINOR=["guest_stay_income","onboarding_income","late_fees_income","exit_charges_income","other"]

def build_monthly():
    D,_=load_all()
    comps=["rental_income","electricity_income","guest_stay_income","onboarding_income","late_fees_income","exit_charges_income"]
    p=D["v_pnl_by_category"].copy()
    for c in ["revenue"]+comps: p[c]=num(p[c])
    g=p.groupby("month")[["revenue"]+comps].sum().sort_index(); g.index=pd.to_datetime(g.index)
    dense=g[g["revenue"]>g["revenue"].max()*0.2]; g=g[g.index>=dense.index.min()].asfreq("MS")
    g["other"]=g["revenue"]-g[comps].sum(axis=1)     # reconciling residual so components sum to revenue exactly
    al=D["tenant_allotments"].copy()
    for c in ["onboarding_date","booking_date","actual_exit_date"]: al[c]=to_dt(al[c])
    al["start"]=al["onboarding_date"].fillna(al["booking_date"])
    g["occupied_beds"]=[al[(al["start"]<=m)&((al["actual_exit_date"].isna())|(al["actual_exit_date"]>m))]["bed_id"].nunique() for m in g.index]
    g["effective_rent"]=g["rental_income"]/g["occupied_beds"]
    g=g.reset_index(); g=g.rename(columns={g.columns[0]:"period"}); g["period"]=pd.to_datetime(g["period"]).dt.strftime("%Y-%m")
    g.to_csv(os.path.join(OUTX,"component_revenue_dataset.csv"),index=False)
    return g

def es_fit(series, seasonal, steps=1):
    r=np.asarray(series,float); n=len(r)
    try:
        if seasonal and n>=24: mdl=ExponentialSmoothing(r,trend="add",seasonal="add",seasonal_periods=12)
        else:                  mdl=ExponentialSmoothing(r,trend="add",seasonal=None)
        return float(mdl.fit(optimized=True).forecast(steps)[-1])
    except Exception:
        return float(r[-1]) if n else 0.0

def trailing_median(series, k=3):
    r=np.asarray(series,float); return float(np.median(r[-k:])) if len(r) else 0.0

def met(a,pp):
    a=np.array(a,float); pp=np.array(pp,float); e=a-pp
    return dict(MAE=int(round(np.abs(e).mean())),RMSE=int(round(np.sqrt((e**2).mean()))),MAPE=round(float(np.mean(np.abs(e/a))*100),2))

def run():
    g=build_monthly(); n=len(g)
    hw=pd.read_csv(HW_BACKTEST)[["month","hw"]]; hw_map=dict(zip(hw["month"],hw["hw"]))
    rows=[]
    for i in range(START,n):
        period=g.iloc[i]["period"]; actual=float(g.iloc[i]["revenue"])
        h=g.iloc[:i]                                   # strictly prior months only
        occ_fc=es_fit(h["occupied_beds"],seasonal=True)
        rent_fc=es_fit(h["effective_rent"],seasonal=False)
        rental_fc=occ_fc*rent_fc
        elec_fc=es_fit(h["electricity_income"],seasonal=True)
        minor_fc={c:trailing_median(h[c]) for c in MINOR}
        total_fc=rental_fc+elec_fc+sum(minor_fc.values())
        rows.append(dict(period=period, actual=round(actual),
            hw=(round(hw_map[period]) if period in hw_map else np.nan),
            component_total=round(total_fc),
            occ_fc=round(occ_fc,1), occ_actual=int(g.iloc[i]["occupied_beds"]),
            rent_fc=round(rent_fc), rent_actual=round(float(g.iloc[i]["effective_rent"])),
            rental_fc=round(rental_fc), rental_actual=round(float(g.iloc[i]["rental_income"])),
            elec_fc=round(elec_fc), elec_actual=round(float(g.iloc[i]["electricity_income"])),
            minor_fc=round(sum(minor_fc.values())), minor_actual=round(float(g.iloc[i][MINOR].sum()))))
    P=pd.DataFrame(rows); P.to_csv(os.path.join(OUTX,"component_revenue_predictions.csv"),index=False)

    comp=pd.DataFrame([
        dict(model="A. Existing Holt-Winters (revenue-only)",folds=int(P["hw"].notna().sum()),**met(P["actual"],P["hw"])),
        dict(model="B. Component-based (occ x rent + components)",folds=len(P),**met(P["actual"],P["component_total"])),
    ]); comp.to_csv(os.path.join(OUTX,"component_revenue_comparison.csv"),index=False)

    # sub-forecast accuracy
    sub=pd.DataFrame([
        dict(target="occupied_beds",**met(P["occ_actual"],P["occ_fc"])),
        dict(target="effective_rent_per_bed",**met(P["rent_actual"],P["rent_fc"])),
        dict(target="rental_income",**met(P["rental_actual"],P["rental_fc"])),
        dict(target="electricity_income",**met(P["elec_actual"],P["elec_fc"])),
        dict(target="total_revenue (component)",**met(P["actual"],P["component_total"])),
    ]); sub.to_csv(os.path.join(OUTX,"component_revenue_subforecast_accuracy.csv"),index=False)

    ea=P[["period","actual","hw","component_total"]].copy()
    ea["abs_err_hw"]=(ea["actual"]-ea["hw"]).abs(); ea["abs_err_comp"]=(ea["actual"]-ea["component_total"]).abs()
    ea["signed_err_comp"]=ea["actual"]-ea["component_total"]; ea.to_csv(os.path.join(OUTX,"component_revenue_error_analysis.csv"),index=False)

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,4.5))
    ax.plot(P["period"],P["actual"],marker="o",color="#222",label="Actual")
    ax.plot(P["period"],P["hw"],marker="s",color="#1f77b4",label="A. Revenue-only HW")
    ax.plot(P["period"],P["component_total"],marker="^",color="#d62728",label="B. Component-based")
    ax.set_title("Actual vs predicted revenue (unseen 2026-02..2026-08)"); ax.tick_params(axis="x",rotation=45); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(OUTX,"component_revenue_actual_vs_predicted.png"),dpi=110); plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4)); x=np.arange(len(P)); w=0.4
    ax.bar(x-w/2,ea["abs_err_hw"],w,label="A. Revenue-only HW",color="#1f77b4")
    ax.bar(x+w/2,ea["abs_err_comp"],w,label="B. Component-based",color="#d62728")
    ax.set_xticks(x); ax.set_xticklabels(P["period"],rotation=45); ax.set_title("Absolute error by month"); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(OUTX,"component_revenue_errors.png"),dpi=110); plt.close(fig)

    print("="*82); print(f"COMPONENT-BASED REVENUE FORECAST — walk-forward {P['period'].iloc[0]}..{P['period'].iloc[-1]} ({len(P)} folds, START={START})")
    print("="*82); print(comp.to_string(index=False))
    print("\nSub-forecast accuracy:"); print(sub.to_string(index=False))
    print("\nFold-by-fold (actual / HW / component):")
    for _,r in P.iterrows(): print(f"  {r['period']}  act {int(r['actual']):>9,}  HW {int(r['hw']):>9,}  comp {int(r['component_total']):>9,}  | occ {r['occ_fc']:.0f}/{r['occ_actual']} rent {int(r['rent_fc']):,}/{int(r['rent_actual']):,}")
    mA=met(P["actual"],P["hw"]); mB=met(P["actual"],P["component_total"])
    better=[k for k in ("MAE","RMSE","MAPE") if mB[k]<mA[k]]
    print("\nVERDICT:", "Component-based better on all three" if len(better)==3 else ("Revenue-only HW better on all three" if not better else f"Mixed: component better on {better}"))
    return comp

if __name__=="__main__": run()
