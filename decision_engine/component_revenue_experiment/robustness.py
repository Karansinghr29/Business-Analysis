"""
ISOLATED robustness validation for the component-based revenue forecast (read-only; writes ONLY to outputs/).
Does NOT modify the primary experiment or any production file. Reuses build_monthly/es_fit/trailing_median.

- Primary 7-fold comparison keeps the EXISTING production HW predictions (read from phase2_revenue_backtest.csv).
- Extended walk-forward (START=13 -> 18 folds, 2025-03..2026-08) reproduces HW with the SAME ES config
  (trend=add, seasonal=add if n>=24 else trend-only) — a faithful reproduction, production code untouched.
- Variant models, sensitivity/oracle diagnostics, per-fold win-rate, and leave-one-out.
No test-month actual enters any FORECAST; oracle rows (which deliberately use actuals) are labelled and excluded
from the leakage-safe comparison. No random shuffle. Deterministic.
"""
from __future__ import annotations
import os, sys, warnings, hashlib, glob, subprocess
HERE=os.path.dirname(os.path.abspath(__file__)); ENGINE=os.path.dirname(HERE)
sys.path.insert(0, ENGINE); sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
from component_revenue_experiment import build_monthly, es_fit, trailing_median, MINOR
OUTX=os.path.join(HERE,"outputs")
HW_BACKTEST=os.path.join(ENGINE,"outputs","phase2_revenue_backtest.csv")

def met(a,pp):
    a=np.array(a,float); pp=np.array(pp,float); e=a-pp
    return dict(MAE=int(round(np.abs(e).mean())),RMSE=int(round(np.sqrt((e**2).mean()))),MAPE=round(float(np.mean(np.abs(e/a))*100),2))

def fold_table(g, start):
    hwprod=dict(zip(*[pd.read_csv(HW_BACKTEST)[c] for c in ["month","hw"]]))
    rows=[]
    for i in range(start,len(g)):
        h=g.iloc[:i]; period=g.iloc[i]["period"]; actual=float(g.iloc[i]["revenue"])
        occ_fc=es_fit(h["occupied_beds"],True); rent_fc=es_fit(h["effective_rent"],False)
        elec_fc=es_fit(h["electricity_income"],True)
        minor_med=sum(trailing_median(h[c]) for c in MINOR); minor_mean=sum(float(np.mean(h[c].values[-3:])) for c in MINOR)
        rental=occ_fc*rent_fc
        occ_a=float(g.iloc[i]["occupied_beds"]); rent_a=float(g.iloc[i]["effective_rent"])
        elec_a=float(g.iloc[i]["electricity_income"]); minor_a=float(g.iloc[i][MINOR].sum())
        rows.append(dict(period=period, actual=round(actual),
            hw_prod=(round(hwprod[period]) if period in hwprod else np.nan),
            hw_repro=round(es_fit(h["revenue"],True)),
            rental_only=round(rental), rental_elec=round(rental+elec_fc),
            full=round(rental+elec_fc+minor_med), full_mean=round(rental+elec_fc+minor_mean),
            # oracles (use actuals — diagnostic only, NOT leakage-safe forecasts)
            oracle_perfect_occ=round(occ_a*rent_fc+elec_fc+minor_med),
            oracle_perfect_rent=round(occ_fc*rent_a+elec_fc+minor_med),
            oracle_perfect_both=round(occ_a*rent_a+elec_fc+minor_med),
            occ_fc=round(occ_fc,1), occ_actual=int(occ_a), rent_fc=round(rent_fc), rent_actual=round(rent_a)))
    return pd.DataFrame(rows)

def main():
    g=build_monthly()
    F7=fold_table(g,24)    # primary window (production HW available)
    F18=fold_table(g,13)   # extended window (HW reproduced)

    # sanity: reproduced HW ~ production HW on the 7 shared months
    shared=F7.dropna(subset=["hw_prod"])
    hw_repro_gap=int((shared["hw_prod"]-shared["hw_repro"]).abs().max())

    def block(F, hwcol, label):
        r=[]
        for name,col in [("Existing Holt-Winters",hwcol),("Component rental-only","rental_only"),
                         ("Component rental+electricity","rental_elec"),("Component full (all components)","full")]:
            m=met(F["actual"],F[col]); r.append(dict(window=label,model=name,folds=len(F),**m))
        return pd.DataFrame(r)
    comp7=block(F7,"hw_prod","7-fold (2026-02..2026-08, production HW)")
    comp18=block(F18,"hw_repro","18-fold (2025-03..2026-08, HW reproduced)")
    COMP=pd.concat([comp7,comp18],ignore_index=True); COMP.to_csv(os.path.join(OUTX,"component_revenue_robustness_comparison.csv"),index=False)

    # fold-by-fold errors (both models, both windows)
    def perfold(F,hwcol):
        d=F[["period","actual",hwcol,"full","occ_fc","occ_actual","rent_fc","rent_actual"]].copy().rename(columns={hwcol:"hw"})
        d["ape_hw"]=(d["actual"]-d["hw"]).abs()/d["actual"]*100; d["ape_comp"]=(d["actual"]-d["full"]).abs()/d["actual"]*100
        d["comp_wins"]=d["ape_comp"]<d["ape_hw"]; return d
    pf7=perfold(F7,"hw_prod"); pf18=perfold(F18,"hw_repro")
    pf7.assign(window="7-fold").to_csv(os.path.join(OUTX,"component_revenue_robustness_folds_7.csv"),index=False)
    pf18.assign(window="18-fold").to_csv(os.path.join(OUTX,"component_revenue_robustness_folds_18.csv"),index=False)

    # one-month domination: leave-one-out on the 7-fold; does component still beat HW?
    def loo(F,hwcol):
        base_c=met(F["actual"],F["full"])["MAPE"]; base_h=met(F["actual"],F[hwcol])["MAPE"]; res=[]
        for k in range(len(F)):
            FF=F.drop(F.index[k]); res.append((F.iloc[k]["period"],met(FF["actual"],FF["full"])["MAPE"],met(FF["actual"],FF[hwcol])["MAPE"]))
        L=pd.DataFrame(res,columns=["dropped_month","comp_MAPE","hw_MAPE"]); L["comp_still_wins"]=L["comp_MAPE"]<L["hw_MAPE"]
        return base_c,base_h,L
    bc,bh,LOO=loo(F7,"hw_prod"); LOO.to_csv(os.path.join(OUTX,"component_revenue_robustness_leaveoneout.csv"),index=False)

    # sensitivity (7-fold MAPE)
    sens=[]
    for lbl,col in [("full component (median minor)","full"),("minor as trailing MEAN","full_mean"),
                    ("rental+electricity (drop minor/other)","rental_elec"),("rental only (drop elec+minor)","rental_only"),
                    ("ORACLE perfect occupancy","oracle_perfect_occ"),("ORACLE perfect rent","oracle_perfect_rent"),
                    ("ORACLE perfect occ & rent","oracle_perfect_both")]:
        sens.append(dict(variant=lbl,**met(F7["actual"],F7[col])))
    SENS=pd.DataFrame(sens); SENS.to_csv(os.path.join(OUTX,"component_revenue_robustness_sensitivity.csv"),index=False)

    print("="*88); print("ROBUSTNESS VALIDATION — component-based revenue forecast (production untouched)")
    print("="*88)
    print(f"reproduced-HW vs production-HW max gap on shared 7 months = Rs{hw_repro_gap:,} (0 => identical method)")
    print("\n[Comparison]"); print(COMP.to_string(index=False))
    print(f"\n[7-fold win-rate] component beats HW in {int(pf7['comp_wins'].sum())}/7 folds")
    print(f"[18-fold win-rate] component beats HW in {int(pf18['comp_wins'].sum())}/18 folds")
    print(f"\n[Leave-one-out, 7-fold] base component {bc}% vs HW {bh}%; component still wins after dropping any single month: {bool(LOO['comp_still_wins'].all())}")
    print("  worst drop -> ", LOO.loc[LOO['comp_MAPE'].idxmax()].to_dict())
    print("\n[Sensitivity, 7-fold MAPE]"); print(SENS.to_string(index=False))

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,4))
    ax.plot(pf18["period"],pf18["ape_hw"],marker="s",color="#1f77b4",label="HW APE%")
    ax.plot(pf18["period"],pf18["ape_comp"],marker="^",color="#d62728",label="Component APE%")
    ax.set_title("Per-fold absolute % error (extended 18-fold)"); ax.tick_params(axis="x",rotation=45); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(OUTX,"component_revenue_robustness_perfold.png"),dpi=110); plt.close(fig)
    return COMP

if __name__=="__main__": main()
