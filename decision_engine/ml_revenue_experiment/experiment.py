"""
ISOLATED ML experiment — orchestrator. Writes ONLY to ml_revenue_experiment/outputs/.
Walk-forward one-step, SAME unseen window as production Holt-Winters (START=24 -> 2026-02..2026-08, 7 folds).
Holt-Winters results are READ from outputs/phase2_revenue_backtest.csv (read-only) — never retrained/modified.
Experiment A = revenue-history + calendar. Experiment B = A + lagged/forecast occupancy + business vars.
No existing file is written. Deterministic (fixed seeds).
"""
from __future__ import annotations
import os, sys, warnings
HERE=os.path.dirname(os.path.abspath(__file__)); ENGINE=os.path.dirname(HERE)
sys.path.insert(0, ENGINE); sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
from dataset import build
from features import FEATS_A, FEATS_B_BASE, FEATS_B_OCC, FEATURE_DOC
from occupancy_forecast import forecast_occupancy_at
from models import make_models
from evaluation import metrics, add_ranks
import plots

OUTX=os.path.join(HERE,"outputs")
HW_BACKTEST=os.path.join(ENGINE,"outputs","phase2_revenue_backtest.csv")   # READ-ONLY
START=24   # match production Holt-Winters walk-forward window

def run():
    df=build().reset_index(drop=True)
    y=df["revenue"].values.astype(float); n=len(df)
    hw=pd.read_csv(HW_BACKTEST)[["month","hw"]]; hw_map=dict(zip(hw["month"],hw["hw"]))
    modnames=list(make_models().keys())

    rows=[]; occ_rows=[]
    for i in range(START,n):
        period=df.iloc[i]["period"]; actual=y[i]
        rec=dict(period=period, actual=round(actual), hw=(round(hw_map[period]) if period in hw_map else np.nan))
        # ---- chronological occupancy forecast (no actual future occupancy) ----
        occ_pred,rate_pred=forecast_occupancy_at(df,i,"rf")
        rec["occ_pred"]=occ_pred; rec["rate_pred"]=round(rate_pred,4)
        occ_rows.append(dict(period=period, actual_occupied=int(df.iloc[i]["occupied_beds"]),
                             occ_pred=occ_pred, actual_rate=round(float(df.iloc[i]["occupancy_rate"]),4),
                             rate_pred=round(rate_pred,4)))
        # ---- Experiment A ----
        trA=df.iloc[:i].dropna(subset=FEATS_A+["revenue"])
        for mn,mdl in make_models().items():
            mdl.fit(trA[FEATS_A],trA["revenue"]); rec[f"A_{mn}"]=round(float(mdl.predict(df.iloc[[i]][FEATS_A])[0]))
        # ---- Experiment B (train uses realized past occupancy; test uses FORECAST occupancy) ----
        trB=df.iloc[:i].dropna(subset=FEATS_B_BASE+["revenue"]).copy()
        trB["occ_pred"]=trB["occupied_beds"].astype(float); trB["rate_pred"]=trB["occupancy_rate"].astype(float)
        teB=df.iloc[[i]][FEATS_B_BASE].copy(); teB["occ_pred"]=float(occ_pred); teB["rate_pred"]=float(rate_pred)
        Xtr=trB[FEATS_B_BASE+FEATS_B_OCC]; Xte=teB[FEATS_B_BASE+FEATS_B_OCC]
        for mn,mdl in make_models().items():
            mdl.fit(Xtr,trB["revenue"]); rec[f"B_{mn}"]=round(float(mdl.predict(Xte)[0]))
        rows.append(rec)

    P=pd.DataFrame(rows); P.to_csv(os.path.join(OUTX,"ml_revenue_experiment_predictions.csv"),index=False)
    OC=pd.DataFrame(occ_rows); OC.to_csv(os.path.join(OUTX,"ml_revenue_experiment_occupancy_forecast.csv"),index=False)

    # ---- comparison (HW read-only + all models x both experiments) ----
    comp=[dict(model="Holt-Winters (existing)",experiment="benchmark",**metrics(P["actual"],P["hw"]))]
    for mn in modnames: comp.append(dict(model=mn,experiment="A revenue-history",**metrics(P["actual"],P[f"A_{mn}"])))
    for mn in modnames: comp.append(dict(model=mn,experiment="B occupancy-aware",**metrics(P["actual"],P[f"B_{mn}"])))
    C=add_ranks(pd.DataFrame(comp)); C.to_csv(os.path.join(OUTX,"ml_revenue_experiment_comparison.csv"),index=False)

    # ---- feature summary ----
    pd.DataFrame(FEATURE_DOC,columns=["feature","source","availability","why_valid"]).to_csv(
        os.path.join(OUTX,"ml_revenue_experiment_feature_summary.csv"),index=False)

    # ---- best A / best B / overall ----
    A=C[C["experiment"]=="A revenue-history"]; B=C[C["experiment"]=="B occupancy-aware"]
    bestA=A.loc[A["MAPE"].idxmin()]; bestB=B.loc[B["MAPE"].idxmin()]

    # ---- error analysis (best B) + occupancy value ----
    col=f"B_{bestB['model']}"
    ea=P[["period","actual","hw",col,"occ_pred"]].copy()
    ea["abs_error"]=(ea["actual"]-ea[col]).abs(); ea["signed_error"]=ea["actual"]-ea[col]
    ea["occupancy_bucket"]=pd.cut(df.set_index("period").loc[ea["period"],"occupancy_rate"].values,
                                  bins=[0,0.85,0.95,1.01],labels=["low(<85%)","mid(85-95%)","high(>95%)"])
    ea=ea.rename(columns={col:"pred_bestB"})
    ea.to_csv(os.path.join(OUTX,"ml_revenue_experiment_error_analysis.csv"),index=False)

    # ---- plots (isolated) ----
    plots.actual_vs_predicted(P, hw_col="hw", a_col=f"A_{bestA['model']}", b_col=f"B_{bestB['model']}",
        labels=(f"Best-A {bestA['model']}",f"Best-B {bestB['model']}"), out=OUTX)
    plots.errors_over_time(ea, out=OUTX)
    plots.error_by_occupancy(ea, out=OUTX)
    plots.scatter_actual_pred(P, f"B_{bestB['model']}", f"Best-B {bestB['model']}", out=OUTX)

    om=metrics(OC["actual_occupied"],OC["occ_pred"])
    print("="*76); print(f"ISOLATED ML REVENUE EXPERIMENT — walk-forward {P['period'].iloc[0]}..{P['period'].iloc[-1]} ({len(P)} folds, START={START})")
    print("="*76)
    print(C.to_string(index=False))
    print(f"\nOccupancy forecaster (chronological): occupied-bed {om}")
    d=round(bestB["MAPE"]-bestA["MAPE"],2)
    print(f"\nExperiment A best: {bestA['model']} MAPE {bestA['MAPE']}%  |  Experiment B best: {bestB['model']} MAPE {bestB['MAPE']}%  |  B-A = {d:+} pp")
    print(("Occupancy IMPROVED ML accuracy." if bestB['MAPE']<bestA['MAPE'] else
           "Occupancy did NOT improve ML accuracy on this window."))
    w=C.iloc[0]; print(f"Overall best (MAPE): {w['model']} / {w['experiment']} = {w['MAPE']}% (MAE {w['MAE']}, RMSE {w['RMSE']})")
    return C

if __name__=="__main__": run()
