"""
Phase 2 - Revenue forecasting (authoritative CSV, walk-forward).
- Authoritative monthly revenue = v_pnl_by_category (journal/accounting truth), NOT invoices raw.
- Primary model = Holt-Winters (statsmodels), per project rule. Baseline = seasonal-naive / naive-1.
- XGBoost challenger evaluated only as an additional challenger (real as-of lag features).
- One-step-ahead rolling / walk-forward. No random split. Read-only source CSVs.
"""
from __future__ import annotations
import os, sys, warnings
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
from loader import load_all, num, to_dt

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)
D,_=load_all()

# ---------- authoritative monthly revenue (accounting truth) ----------
p=D["v_pnl_by_category"].copy(); p["revenue"]=num(p["revenue"])
s=p.groupby("month")["revenue"].sum().sort_index()
s.index=pd.to_datetime(s.index)
# keep dense contiguous tail (drop leading sparse/near-zero months)
dense=s[s>s.max()*0.2]                      # months with material revenue
first=dense.index.min()
s=s[s.index>=first].asfreq("MS")
print("="*72); print("AUTHORITATIVE MONTHLY REVENUE (v_pnl_by_category)"); print("="*72)
print(f"usable months={len(s)}  range {s.index.min().date()} -> {s.index.max().date()}  missing={int(s.isna().sum())}")
print(f"latest actual ({s.index.max().date()}) = {s.iloc[-1]:,.0f}   NOTE: last month may be partial (data end 2026-08-11)")
y=s.values.astype(float); idx=s.index

# ---------- build real as-of monthly features (for XGB challenger) ----------
al=D["tenant_allotments"].copy()
for c in ["onboarding_date","booking_date","actual_exit_date"]: al[c]=to_dt(al[c])
al["start"]=al["onboarding_date"].fillna(al["booking_date"])
rc=D["receipts"].copy(); rc["payment_date"]=to_dt(rc["payment_date"]); rc["amount_paid"]=num(rc["amount_paid"])
rows=[]
for m in idx:
    act=al[(al["start"]<=m)&((al["actual_exit_date"].isna())|(al["actual_exit_date"]>m))]
    coll=rc[(rc["payment_date"]>=m)&(rc["payment_date"]<m+pd.offsets.MonthBegin(1))]["amount_paid"].sum()
    rows.append(dict(month=m, active_tenants=len(act), occupied_beds=act["bed_id"].nunique(), collections=coll))
pm=pd.DataFrame(rows).set_index("month"); pm["revenue"]=y
pm["arpu"]=pm["revenue"]/pm["active_tenants"].replace(0,np.nan)
for l in (1,2,3,12): pm[f"rev_lag{l}"]=pm["revenue"].shift(l)
pm["rev_roll3"]=pm["revenue"].shift(1).rolling(3).mean()
pm["active_lag1"]=pm["active_tenants"].shift(1); pm["occ_lag1"]=pm["occupied_beds"].shift(1)
pm["coll_lag1"]=pm["collections"].shift(1); pm["month_num"]=pm.index.month

# ---------- models ----------
from statsmodels.tsa.holtwinters import ExponentialSmoothing
import xgboost as xgb
def hw_fit(train, steps=1):
    n=len(train)
    try:
        if n>=24: mdl=ExponentialSmoothing(train,trend="add",seasonal="add",seasonal_periods=12)
        else:     mdl=ExponentialSmoothing(train,trend="add",seasonal=None)
        return float(mdl.fit(optimized=True).forecast(steps)[-1])
    except Exception:
        return float(train[-1])
def naive1(train): return float(train[-1])
def snaive(train): return float(train[-12]) if len(train)>=12 else float(train[-1])

# ---------- walk-forward one-step ----------
XFEAT=["rev_lag1","rev_lag2","rev_lag3","rev_lag12","rev_roll3","active_lag1","occ_lag1","coll_lag1","month_num"]
START=max(24, 13)   # need history for HW seasonal + lag12
res=[]
for i in range(START, len(y)):
    tr=y[:i]; actual=y[i]
    hw=hw_fit(tr); nv=naive1(tr); sn=snaive(tr)
    # xgb: train on rows < i with complete features
    dtr=pm.iloc[:i].dropna(subset=XFEAT+["revenue"])
    xgp=np.nan
    if len(dtr)>=10 and pm.iloc[i][XFEAT].notna().all():
        m=xgb.XGBRegressor(n_estimators=200,max_depth=3,learning_rate=0.05,subsample=0.9,
                           colsample_bytree=0.9,reg_lambda=1.0,random_state=42)
        m.fit(dtr[XFEAT],dtr["revenue"])
        xgp=float(m.predict(pm.iloc[[i]][XFEAT])[0])
    res.append(dict(month=idx[i].strftime("%Y-%m"),actual=actual,hw=hw,naive1=nv,snaive=sn,xgb=xgp))
R=pd.DataFrame(res)
def met(a,pp):
    mask=~np.isnan(pp); a=np.array(a)[mask]; pp=np.array(pp)[mask]
    if len(a)==0: return {}
    e=a-pp
    return dict(n=len(a),MAE=round(np.abs(e).mean()),RMSE=round(np.sqrt((e**2).mean())),
                MAPE=round(np.mean(np.abs(e/a))*100,2))
print("\n"+"="*72); print(f"WALK-FORWARD ONE-STEP (folds={len(R)}, test {R['month'].iloc[0]}..{R['month'].iloc[-1]})"); print("="*72)
for name in ["naive1","snaive","hw","xgb"]:
    print(f"  {name:8}: {met(R['actual'],R[name])}")
# fold stability (HW abs % error)
hw_ape=(np.abs(R['actual']-R['hw'])/R['actual']*100)
print(f"  HW per-fold APE: median={hw_ape.median():.1f}% min={hw_ape.min():.1f}% max={hw_ape.max():.1f}% std={hw_ape.std():.1f}")
R.to_csv(os.path.join(OUT,"phase2_revenue_backtest.csv"),index=False)

# ---------- final forecast next month (HW on all data) + interval from backtest RMSE ----------
hw_next=hw_fit(y); nv_next=naive1(y); rmse=met(R['actual'],R['hw'])["RMSE"]
fc=pd.DataFrame([dict(forecast_month=(idx.max()+pd.offsets.MonthBegin(1)).strftime("%Y-%m"),
    model="Holt-Winters", predicted_revenue=round(hw_next),
    lower_95=round(hw_next-1.96*rmse), upper_95=round(hw_next+1.96*rmse),
    latest_actual_month=idx.max().strftime("%Y-%m"), latest_actual=round(y[-1]),
    baseline_naive1=round(nv_next), backtest_MAE=met(R['actual'],R['hw'])["MAE"],
    backtest_RMSE=rmse, backtest_MAPE=met(R['actual'],R['hw'])["MAPE"])])
fc.to_csv(os.path.join(OUT,"phase2_revenue_forecast.csv"),index=False)
print("\nNEXT-MONTH FORECAST (Holt-Winters):")
print(fc.T.to_string(header=False))
print("\nOutputs: phase2_revenue_backtest.csv, phase2_revenue_forecast.csv")
