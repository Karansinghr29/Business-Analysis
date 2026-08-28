"""
Phase-2 COMPONENT-BASED revenue forecast (PARALLEL to Holt-Winters; SECONDARY/experimental).
Does NOT replace or modify revenue_forecast.py or the Holt-Winters outputs. Runs alongside as a challenger while
3-6 future months of actuals accumulate for a primary-model decision.

Approved architecture (validated in component_revenue_experiment/):
    revenue = OccupiedBeds(es_trend) x EffectiveRent(es_trend) + Electricity(es_seasonal)
Minor/other components excluded (added noise). Walk-forward robustness (18-fold 2025-03..2026-08): MAPE 3.71% vs
production Holt-Winters 5.55%; leave-one-out stable; leakage-safe; deterministic.

Reads authoritative Vishful data read-only (loader). Writes ONLY two NEW outputs:
    phase2_component_revenue_forecast.csv   (next-month forecast + component breakdown + backtest metrics)
    phase2_component_revenue_backtest.csv   (18-fold walk-forward: month, actual, holt_winters, component)
Holt-Winters values here are REPRODUCED with the identical ES config (verified 0 gap vs production) for the
extended window; production HW files are never touched.
"""
from __future__ import annotations
import os, sys, warnings
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from loader import load_all, num, to_dt
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")

def es(series, seasonal, damped=False, steps=1):
    r=np.asarray(series,float); n=len(r)
    try:
        sea="add" if (seasonal and n>=24) else None
        mdl=ExponentialSmoothing(r,trend="add",seasonal=sea,seasonal_periods=(12 if sea else None),damped_trend=damped)
        return float(mdl.fit(optimized=True).forecast(steps)[-1])
    except Exception:
        return float(r[-1]) if n else 0.0

def build_monthly():
    D,_=load_all()
    comps=["rental_income","electricity_income"]
    p=D["v_pnl_by_category"].copy()
    for c in ["revenue"]+comps: p[c]=num(p[c])
    g=p.groupby("month")[["revenue"]+comps].sum().sort_index(); g.index=pd.to_datetime(g.index)
    dense=g[g["revenue"]>g["revenue"].max()*0.2]; g=g[g.index>=dense.index.min()].asfreq("MS"); idx=g.index
    al=D["tenant_allotments"].copy()
    for c in ["onboarding_date","booking_date","actual_exit_date"]: al[c]=to_dt(al[c])
    al["start"]=al["onboarding_date"].fillna(al["booking_date"])
    g["occupied_beds"]=[al[(al["start"]<=m)&((al["actual_exit_date"].isna())|(al["actual_exit_date"]>m))]["bed_id"].nunique() for m in idx]
    g["effective_rent"]=g["rental_income"]/g["occupied_beds"]
    # ---- fail-loud apartment-lifecycle guard (occupied_beds is allotment-driven; this asserts the lifecycle) ----
    # A33/A34 are operational only from 2026-08 (apartments.start_date=2026-08-01) -> zero occupancy before Aug-2026.
    # A22 is Not-Active (closed 2026-01-20) -> zero occupancy once inactive (from 2026-02 onward).
    _U=lambda s: s.astype(str).str.upper().str.replace(" ","")
    _ap=D["apartments"]; _bd=D["beds"]
    _new=set(_bd[_bd["apartment_id"].isin(_ap[_U(_ap["apartment_code"]).isin(["A33","A34"])]["id"])]["id"])
    _a22=set(_bd[_bd["apartment_id"].isin(_ap[_U(_ap["apartment_code"])=="A22"]["id"])]["id"])
    for m in idx:
        ob=set(al[(al["start"]<=m)&((al["actual_exit_date"].isna())|(al["actual_exit_date"]>m))]["bed_id"])
        k=m.strftime("%Y-%m")
        if k<"2026-08": assert not (ob & _new), f"lifecycle violation: A33/A34 occupied before Aug-2026 ({k})"
        if k>="2026-02": assert not (ob & _a22), f"lifecycle violation: A22 (inactive) counted in {k}"
    g=g.reset_index(); g=g.rename(columns={g.columns[0]:"period"}); g["period"]=pd.to_datetime(g["period"]).dt.strftime("%Y-%m")
    return g

def met(a,pp):
    a=np.array(a,float); pp=np.array(pp,float); e=a-pp
    return dict(MAE=int(round(np.abs(e).mean())),RMSE=int(round(np.sqrt((e**2).mean()))),MAPE=round(float(np.mean(np.abs(e/a))*100),2))

def component_forecast(h):
    occ=es(h["occupied_beds"].values,False,False)      # es_trend
    rent=es(h["effective_rent"].values,False,False)    # es_trend
    elec=es(h["electricity_income"].values,True,False) # es_seasonal
    return occ, rent, elec, occ*rent+elec

def main():
    g=build_monthly(); n=len(g)
    # ---- 18-fold + 7-fold walk-forward backtest (component vs reproduced HW) ----
    rows=[]
    for i in range(13,n):
        h=g.iloc[:i]; occ,rent,elec,tot=component_forecast(h)
        rows.append(dict(month=g.iloc[i]["period"], actual=round(float(g.iloc[i]["revenue"])),
            holt_winters=round(es(h["revenue"].values,True)), component=round(tot),
            occupied_beds_fc=round(occ,1), effective_rent_fc=round(rent), electricity_fc=round(elec)))
    bt=pd.DataFrame(rows); bt.to_csv(os.path.join(OUT,"phase2_component_revenue_backtest.csv"),index=False)
    f18=bt; f7=bt[bt["month"]>="2026-02"]
    mC18=met(f18["actual"],f18["component"]); mH18=met(f18["actual"],f18["holt_winters"])
    mC7=met(f7["actual"],f7["component"]);   mH7=met(f7["actual"],f7["holt_winters"])

    # ---- next-month forecast (fit on all data) ----
    fmonth=(pd.to_datetime(g["period"].iloc[-1]+"-01")+pd.offsets.MonthBegin(1)).strftime("%Y-%m")
    occ,rent,elec,tot=component_forecast(g)
    # production HW next-month, read-only (side-by-side reference)
    hw_ref=np.nan
    fp=os.path.join(OUT,"phase2_revenue_forecast.csv")
    if os.path.exists(fp):
        hwdf=pd.read_csv(fp)
        if "predicted_revenue" in hwdf.columns and len(hwdf): hw_ref=int(hwdf["predicted_revenue"].iloc[0])
    band=mC18["MAPE"]/100.0
    pd.DataFrame([dict(
        forecast_month=fmonth, model="component (occ es_trend x rent + electricity)", status="parallel/secondary; HW remains primary",
        occupied_beds_fc=int(round(occ)), effective_rent_fc=int(round(rent)), rental_fc=int(round(occ*rent)),
        electricity_fc=int(round(elec)), predicted_revenue=int(round(tot)),
        lower_band=int(round(tot*(1-band))), upper_band=int(round(tot*(1+band))),
        backtest_MAPE_7f=mC7["MAPE"], backtest_MAPE_18f=mC18["MAPE"],
        backtest_MAE_18f=mC18["MAE"], backtest_RMSE_18f=mC18["RMSE"],
        hw_backtest_MAPE_18f=mH18["MAPE"], hw_predicted_revenue=hw_ref,
        folds_18=len(f18), folds_7=len(f7),
    )]).to_csv(os.path.join(OUT,"phase2_component_revenue_forecast.csv"),index=False)

    print("PHASE-2 COMPONENT REVENUE FORECAST (parallel/secondary; HW untouched):")
    print(f"  next month {fmonth}: occ {occ:.0f} x rent Rs{int(rent):,} + elec Rs{int(elec):,} = Rs{int(tot):,}")
    print(f"  backtest 18-fold: component {mC18} | Holt-Winters {mH18}")
    print(f"  backtest  7-fold: component {mC7} | Holt-Winters {mH7}")

if __name__=="__main__": main()
