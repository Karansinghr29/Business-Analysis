"""
ISOLATED occupancy sub-forecast experiment (read-only; writes ONLY to outputs/). Production untouched.
Revenue architecture FIXED: revenue = occupied_beds_forecast × effective_rent_forecast + electricity_forecast
(no minor/other). Only the OCCUPANCY forecaster is varied; rent + electricity forecasts stay the current ES.

Occupancy candidates (small, defensible, leakage-safe — each uses only occupied_beds strictly before month t):
  es_seasonal (CURRENT)  ExponentialSmoothing trend=add + seasonal(12 if n>=24 else none)
  es_trend               ExponentialSmoothing trend=add, no seasonal
  es_damped              ExponentialSmoothing damped trend (+seasonal if n>=24)
  snaive                 seasonal-naive: occ[t-12] (fallback occ[t-1])
  naive1                 occ[t-1]
  median3                median(occ[t-3:t])
Decision is on DOWNSTREAM revenue accuracy, not occupancy MAPE alone. Benchmarks: production HW (7-fold read-only;
18-fold reproduced same method) and current rental+electricity. Same windows: 7-fold 2026-02..2026-08, 18-fold
2025-03..2026-08. No synthetic/backfilled occupancy, no future bookings, no random shuffle. Deterministic.
"""
from __future__ import annotations
import os, sys, warnings
HERE=os.path.dirname(os.path.abspath(__file__)); ENGINE=os.path.dirname(HERE)
sys.path.insert(0, ENGINE); sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from component_revenue_experiment import build_monthly, es_fit
OUTX=os.path.join(HERE,"outputs")
HW_BACKTEST=os.path.join(ENGINE,"outputs","phase2_revenue_backtest.csv")

def _es(series, seasonal, damped=False, steps=1):
    r=np.asarray(series,float); n=len(r)
    try:
        sea = "add" if (seasonal and n>=24) else None
        mdl=ExponentialSmoothing(r,trend="add",seasonal=sea,seasonal_periods=(12 if sea else None),damped_trend=damped)
        return float(mdl.fit(optimized=True).forecast(steps)[-1])
    except Exception:
        return float(r[-1]) if n else 0.0

def occ_candidates(ho):
    r=np.asarray(ho,float); n=len(r)
    return {
      "es_seasonal": _es(r,True,False),          # current
      "es_trend":    _es(r,False,False),
      "es_damped":   _es(r,True,True),
      "snaive":      float(r[-12]) if n>=12 else float(r[-1]),
      "naive1":      float(r[-1]),
      "median3":     float(np.median(r[-3:])),
    }
OCC_METHODS=["es_seasonal","es_trend","es_damped","snaive","naive1","median3"]

def met(a,pp):
    a=np.array(a,float); pp=np.array(pp,float); e=a-pp
    return dict(MAE=int(round(np.abs(e).mean())),RMSE=int(round(np.sqrt((e**2).mean()))),MAPE=round(float(np.mean(np.abs(e/a))*100),2))

def fold_table(g, start):
    hwprod=dict(zip(*[pd.read_csv(HW_BACKTEST)[c] for c in ["month","hw"]]))
    rows=[]
    for i in range(start,len(g)):
        h=g.iloc[:i]; period=g.iloc[i]["period"]
        rent_fc=es_fit(h["effective_rent"],False); elec_fc=es_fit(h["electricity_income"],True)  # fixed (current)
        cand=occ_candidates(h["occupied_beds"].values)
        rec=dict(period=period, actual=round(float(g.iloc[i]["revenue"])), occ_actual=int(g.iloc[i]["occupied_beds"]),
                 rent_fc=round(rent_fc), elec_fc=round(elec_fc),
                 hw=(round(hwprod[period]) if period in hwprod else round(es_fit(h["revenue"],True))))
        for mname in OCC_METHODS:
            of=cand[mname]
            rec[f"occ_{mname}"]=round(of,1)
            rec[f"rev_{mname}"]=round(of*rent_fc+elec_fc)
        rows.append(rec)
    return pd.DataFrame(rows)

def summarize(F, label):
    occ_rows=[]; rev_rows=[]
    for mname in OCC_METHODS:
        occ_rows.append(dict(window=label,occ_method=mname,**met(F["occ_actual"],F[f"occ_{mname}"])))
        rev_rows.append(dict(window=label,occ_method=mname,**met(F["actual"],F[f"rev_{mname}"])))
    rev_rows.append(dict(window=label,occ_method="[benchmark] Holt-Winters",**met(F["actual"],F["hw"])))
    return pd.DataFrame(occ_rows), pd.DataFrame(rev_rows)

def main():
    g=build_monthly()
    F7=fold_table(g,24); F18=fold_table(g,13)
    o7,r7=summarize(F7,"7-fold"); o18,r18=summarize(F18,"18-fold")
    OCC=pd.concat([o7,o18],ignore_index=True); REV=pd.concat([r7,r18],ignore_index=True)
    OCC.to_csv(os.path.join(OUTX,"occupancy_experiment_occ_accuracy.csv"),index=False)
    REV.to_csv(os.path.join(OUTX,"occupancy_experiment_revenue_accuracy.csv"),index=False)
    F7.to_csv(os.path.join(OUTX,"occupancy_experiment_folds_7.csv"),index=False)
    F18.to_csv(os.path.join(OUTX,"occupancy_experiment_folds_18.csv"),index=False)

    print("="*92); print("OCCUPANCY SUB-FORECAST EXPERIMENT — downstream revenue decision (production untouched)"); print("="*92)
    print("\n[Occupancy accuracy]"); print(OCC.to_string(index=False))
    print("\n[Downstream REVENUE accuracy: occ x rent + electricity]"); print(REV.to_string(index=False))

    # decision helper: is any candidate better than CURRENT (es_seasonal) on revenue in BOTH windows?
    def rev_mape(F,m): return met(F["actual"],F[f"rev_{m}"])["MAPE"]
    cur7=rev_mape(F7,"es_seasonal"); cur18=rev_mape(F18,"es_seasonal")
    hw7=met(F7["actual"],F7["hw"])["MAPE"]; hw18=met(F18["actual"],F18["hw"])["MAPE"]
    print(f"\nCurrent occupancy (es_seasonal) revenue MAPE: 7-fold {cur7}%  18-fold {cur18}%  | HW {hw7}% / {hw18}%")
    better=[m for m in OCC_METHODS if m!="es_seasonal" and rev_mape(F7,m)<cur7 and rev_mape(F18,m)<cur18]
    print("Candidates that beat CURRENT on revenue in BOTH windows:", better or "NONE")
    for m in OCC_METHODS:
        print(f"  {m:12} rev MAPE 7f {rev_mape(F7,m):.2f}%  18f {rev_mape(F18,m):.2f}%  | occ MAPE 7f {met(F7['occ_actual'],F7['occ_'+m])['MAPE']:.2f}% 18f {met(F18['occ_actual'],F18['occ_'+m])['MAPE']:.2f}%")

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,4.5))
    xs=OCC_METHODS
    ax.bar(np.arange(len(xs))-0.2,[rev_mape(F18,m) for m in xs],0.4,label="revenue MAPE (18-fold)",color="#d62728")
    ax.bar(np.arange(len(xs))+0.2,[met(F18['occ_actual'],F18['occ_'+m])['MAPE'] for m in xs],0.4,label="occupancy MAPE (18-fold)",color="#1f77b4")
    ax.axhline(hw18,ls="--",color="#555",label=f"HW revenue {hw18}%")
    ax.set_xticks(range(len(xs))); ax.set_xticklabels(xs,rotation=30); ax.set_ylabel("MAPE %"); ax.legend(fontsize=8)
    ax.set_title("Occupancy method: occupancy vs downstream-revenue MAPE (18-fold)")
    fig.tight_layout(); fig.savefig(os.path.join(OUTX,"occupancy_experiment_compare.png"),dpi=110); plt.close(fig)
    return REV

if __name__=="__main__": main()
