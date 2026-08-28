"""
ISOLATED ML experiment — monthly ML dataset (read-only; writes ONLY to ml_revenue_experiment/outputs/).
Revenue and occupancy are aligned BY MONTH/PERIOD (never by row number). All revenue/occupancy/inventory logic
is reproduced locally here (read from production code, not imported/edited) so no existing module is modified.
"""
from __future__ import annotations
import os, sys
HERE=os.path.dirname(os.path.abspath(__file__)); ENGINE=os.path.dirname(HERE)
sys.path.insert(0, ENGINE)   # for read-only `import loader`
import numpy as np, pandas as pd
from loader import load_all, num, to_dt   # read-only data access; loader writes nothing
OUTX=os.path.join(HERE,"outputs")

def _tznaive(x):
    x=to_dt(x)
    try: return x.dt.tz_localize(None)
    except Exception: return x

def build():
    D,_=load_all()
    # ----- monthly ACCRUAL revenue (reproduces revenue_forecast.py aggregation) -----
    p=D["v_pnl_by_category"].copy(); p["revenue"]=num(p["revenue"])
    s=p.groupby("month")["revenue"].sum().sort_index(); s.index=pd.to_datetime(s.index)
    dense=s[s>s.max()*0.2]; s=s[s.index>=dense.index.min()].asfreq("MS")
    idx=s.index

    # ----- usable inventory via apartment LIFECYCLE (reproduced locally; created_at never used) -----
    ap=D["apartments"].copy(); beds=D["beds"].copy()
    apsd=_tznaive(ap["start_date"]); apsd=apsd.where(apsd.dt.year>2000)
    aped=_tznaive(ap["end_date"]);   aped=aped.where(aped.dt.year>2000)
    apclosed=aped.where(ap["status"].astype(str).str.strip().eq("Not-Active"))  # closure only for Not-Active apts
    aptab=pd.DataFrame({"aid":ap["id"].values,"apt_start":apsd.values,"apt_closed":apclosed.values})
    beds=beds.merge(aptab,left_on="apartment_id",right_on="aid",how="left")
    beds["apt_start"]=beds["apt_start"].fillna(pd.Timestamp("2000-01-01"))
    CURRENT=idx[-1]
    APT_START=beds["apt_start"]; APT_CLOSED=beds["apt_closed"]; STLIVE=(beds["status"]=="Live")
    def usable_asof(m):
        mend=m+pd.offsets.MonthBegin(1)
        op=(APT_START<mend)&(APT_CLOSED.isna()|(APT_CLOSED>=m))
        if m>=CURRENT: op=op&STLIVE
        return int(op.sum())

    # ----- occupied beds + active tenants (reproduces revenue_forecast.py active-window) -----
    al=D["tenant_allotments"].copy()
    for c in ["onboarding_date","booking_date","actual_exit_date"]: al[c]=_tznaive(al[c])
    al["start"]=al["onboarding_date"].fillna(al["booking_date"])

    # ----- exogenous rate-card avg rent (known ahead; not derived from target revenue) -----
    br=D["bed_rates"].copy(); br["monthly_rate"]=num(br["monthly_rate"])
    br["from"]=_tznaive(br["from_date"]); br["to"]=_tznaive(br["to_date"])
    def card_avg(m):
        c=br[(br["from"]<=m)&((br["to"].isna())|(br["to"]>=m))]
        return round(float(c["monthly_rate"].mean()),2) if len(c) else np.nan

    rows=[]
    for m in idx:
        act=al[(al["start"]<=m)&((al["actual_exit_date"].isna())|(al["actual_exit_date"]>m))]
        occ=int(act["bed_id"].nunique()); usable=usable_asof(m); rev=float(s.loc[m])
        raw=(occ/usable) if usable else np.nan
        rows.append(dict(period=m.strftime("%Y-%m"), revenue=round(rev),
            occupied_beds=occ, usable_beds=usable, active_tenants=int(len(act)),
            occupancy_rate=round(min(raw,1.0),4) if usable else np.nan,
            occupancy_rate_raw=round(raw,4) if usable else np.nan,
            inventory_reliable=bool(usable and occ<=usable),
            avg_rent_card=card_avg(m)))
    df=pd.DataFrame(rows)
    df["avg_rent_card"]=df["avg_rent_card"].ffill().bfill()
    dt=pd.to_datetime(df["period"]+"-01")
    df["month_num"]=dt.dt.month; df["quarter"]=dt.dt.quarter; df["year"]=dt.dt.year
    df["sin_m"]=np.sin(2*np.pi*df["month_num"]/12); df["cos_m"]=np.cos(2*np.pi*df["month_num"]/12)
    # ---- STRICTLY-PRIOR lag/rolling features (shift(1)+ => never uses the target month) ----
    for L in [1,2,3,6,12]: df[f"revenue_lag{L}"]=df["revenue"].shift(L)
    df["revenue_roll3"]=df["revenue"].shift(1).rolling(3).mean()
    df["revenue_roll6"]=df["revenue"].shift(1).rolling(6).mean()
    for L in [1,2,3]:
        df[f"occupied_beds_lag{L}"]=df["occupied_beds"].shift(L)
        df[f"occupancy_rate_lag{L}"]=df["occupancy_rate"].shift(L)
    df["occupied_roll3"]=df["occupied_beds"].shift(1).rolling(3).mean()
    df["tenants_lag1"]=df["active_tenants"].shift(1)
    df["usable_lag1"]=df["usable_beds"].shift(1)
    # usable_beds for the target month is a KNOWN-AHEAD deterministic inventory plan -> allowed as a feature.
    os.makedirs(OUTX,exist_ok=True)
    df.to_csv(os.path.join(OUTX,"ml_revenue_experiment_dataset.csv"),index=False)
    return df

if __name__=="__main__":
    d=build(); print(f"dataset {len(d)} months {d['period'].iloc[0]}..{d['period'].iloc[-1]}")
    print(d[["period","revenue","occupied_beds","usable_beds","occupancy_rate","active_tenants"]].tail(8).to_string(index=False))
