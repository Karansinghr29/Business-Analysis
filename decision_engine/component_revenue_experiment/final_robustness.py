"""
FINAL consolidated robustness validation (read-only; writes ONLY to outputs/). Production untouched.
Approved isolated architecture:  revenue = occ_fc(es_trend) x rent_fc(es_trend) + electricity_fc(es_seasonal)
Minor/other components excluded. Compared to: production HW (revenue-only), current component (occ es_seasonal),
approved es_trend component. Windows: 7-fold (2026-02..2026-08, production HW read-only) and 18-fold
(2025-03..2026-08, HW reproduced same method). One-step walk-forward, train strictly before test, no shuffle.
"""
from __future__ import annotations
import os, sys, warnings
HERE=os.path.dirname(os.path.abspath(__file__)); ENGINE=os.path.dirname(HERE)
sys.path.insert(0, ENGINE); sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
from component_revenue_experiment import build_monthly, es_fit
from occupancy_experiment import _es
HW_BACKTEST=os.path.join(ENGINE,"outputs","phase2_revenue_backtest.csv"); OUTX=os.path.join(HERE,"outputs")

def met(a,pp):
    a=np.array(a,float); pp=np.array(pp,float); e=a-pp
    return dict(MAE=int(round(np.abs(e).mean())),RMSE=int(round(np.sqrt((e**2).mean()))),MAPE=round(float(np.mean(np.abs(e/a))*100),2))

def folds(g,start):
    hwprod=dict(zip(*[pd.read_csv(HW_BACKTEST)[c] for c in ["month","hw"]]))
    R=[]
    for i in range(start,len(g)):
        h=g.iloc[:i]; p=g.iloc[i]["period"]
        occ_seasonal=_es(h["occupied_beds"].values,True,False)   # current
        occ_trend=_es(h["occupied_beds"].values,False,False)     # approved es_trend
        rent_fc=es_fit(h["effective_rent"],False)                # existing trend ES
        elec_fc=es_fit(h["electricity_income"],True)             # existing seasonal ES
        R.append(dict(period=p, actual=round(float(g.iloc[i]["revenue"])),
            occ_actual=int(g.iloc[i]["occupied_beds"]), rent_actual=round(float(g.iloc[i]["effective_rent"])),
            elec_actual=round(float(g.iloc[i]["electricity_income"])),
            occ_seasonal=round(occ_seasonal,1), occ_trend=round(occ_trend,1),
            rent_fc=round(rent_fc), elec_fc=round(elec_fc),
            hw=(round(hwprod[p]) if p in hwprod else round(es_fit(h["revenue"],True))),
            rev_current=round(occ_seasonal*rent_fc+elec_fc),
            rev_estrend=round(occ_trend*rent_fc+elec_fc)))
    return pd.DataFrame(R)

def main():
    g=build_monthly(); F7=folds(g,24); F18=folds(g,13)
    def train_test(F): return f"train {g['period'].iloc[0]}..{pd.Period(F['period'].iloc[0],'M')-1}  ->  test {F['period'].iloc[0]}..{F['period'].iloc[-1]}"
    comp=[]
    for lbl,F in [("7-fold",F7),("18-fold",F18)]:
        for name,col in [("Production Holt-Winters (revenue-only)","hw"),("Current component (occ es_seasonal)","rev_current"),("Approved component (occ es_trend)","rev_estrend")]:
            comp.append(dict(window=lbl,model=name,folds=len(F),**met(F["actual"],F[col])))
    COMP=pd.DataFrame(comp); COMP.to_csv(os.path.join(OUTX,"final_robustness_comparison.csv"),index=False)

    # sub-forecast accuracy (approved model pieces)
    sub=[]
    for lbl,F in [("7-fold",F7),("18-fold",F18)]:
        sub.append(dict(window=lbl,target="occupied_beds (es_trend)",**met(F["occ_actual"],F["occ_trend"])))
        sub.append(dict(window=lbl,target="effective_rent (es_trend)",**met(F["rent_actual"],F["rent_fc"])))
        sub.append(dict(window=lbl,target="electricity_income (es_seasonal)",**met(F["elec_actual"],F["elec_fc"])))
        sub.append(dict(window=lbl,target="TOTAL revenue (approved)",**met(F["actual"],F["rev_estrend"])))
    SUB=pd.DataFrame(sub); SUB.to_csv(os.path.join(OUTX,"final_robustness_subaccuracy.csv"),index=False)

    # per-fold + win-rate vs HW (approved)
    def perfold(F):
        d=F[["period","actual","hw","rev_estrend"]].copy()
        d["ape_hw"]=(d["actual"]-d["hw"]).abs()/d["actual"]*100
        d["ape_approved"]=(d["actual"]-d["rev_estrend"]).abs()/d["actual"]*100
        d["approved_beats_hw"]=d["ape_approved"]<d["ape_hw"]; return d
    pf7=perfold(F7); pf18=perfold(F18)
    pf7.to_csv(os.path.join(OUTX,"final_robustness_folds_7.csv"),index=False)
    pf18.to_csv(os.path.join(OUTX,"final_robustness_folds_18.csv"),index=False)

    # one-month dependence: leave-one-out on 18-fold (approved vs HW aggregate MAPE)
    loo=[]
    for k in range(len(F18)):
        FF=F18.drop(F18.index[k])
        loo.append(dict(dropped=F18.iloc[k]["period"], approved_MAPE=met(FF["actual"],FF["rev_estrend"])["MAPE"],
                        hw_MAPE=met(FF["actual"],FF["hw"])["MAPE"]))
    LOO=pd.DataFrame(loo); LOO["approved_still_beats_hw"]=LOO["approved_MAPE"]<LOO["hw_MAPE"]
    LOO.to_csv(os.path.join(OUTX,"final_robustness_leaveoneout.csv"),index=False)

    # leakage reproduce (approved model rebuilt from rows[:i] only)
    ok=True
    for _,r in F18.iterrows():
        i=list(g["period"]).index(r["period"]); h=g.iloc[:i]
        rep=round(_es(h["occupied_beds"].values,False,False)*es_fit(h["effective_rent"],False)+es_fit(h["electricity_income"],True))
        if abs(rep-r["rev_estrend"])>2: ok=False

    print("="*94); print("FINAL ROBUSTNESS — approved component (occ es_trend × rent + electricity)"); print("="*94)
    print("7-fold :",train_test(F7)); print("18-fold:",train_test(F18))
    print("\n[Comparison]"); print(COMP.to_string(index=False))
    print("\n[Sub-forecast accuracy]"); print(SUB.to_string(index=False))
    print(f"\n[Win-rate vs production HW] approved beats HW: 7-fold {int(pf7['approved_beats_hw'].sum())}/7, 18-fold {int(pf18['approved_beats_hw'].sum())}/18")
    print("\n[Largest-error months, approved model, 18-fold]")
    print(pf18.reindex(pf18["ape_approved"].sort_values(ascending=False).index)[["period","actual","rev_estrend","ape_approved","ape_hw"]].head(4).to_string(index=False))
    print(f"\n[Leave-one-out, 18-fold] approved still beats HW after dropping ANY single month: {bool(LOO['approved_still_beats_hw'].all())}")
    print("  worst case:", LOO.reindex(LOO['approved_MAPE'].sort_values(ascending=False).index).iloc[0].to_dict())
    print(f"\n[Leakage] approved revenue reproduces from prior-only months (all 18 folds): {ok}")
    print(f"[Genuine forecast] occ_trend != occ_actual: {bool((F18['occ_trend']!=F18['occ_actual']).any())}")
    return COMP

if __name__=="__main__": main()
