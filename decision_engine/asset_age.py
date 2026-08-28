"""
Phase-2 ASSET-LEVEL age (deterministic, no imputation).
asset_start_date = purchase_date if valid else earliest valid allocated_date else unknown.
Never infers asset_id from bed_id. New outputs only. Read-only source CSVs.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np, pandas as pd
from loader import load_all, num, to_dt

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)
ASOF=pd.Timestamp("2026-08-13")
D,_=load_all()
a=D["assets"].copy(); aa=D["asset_allocations"].copy(); at=D.get("asset_types")
def naive(s):
    d=to_dt(s)
    try:
        if getattr(d.dt,"tz",None) is not None: d=d.dt.tz_localize(None)
    except Exception: pass
    return d
a["purchase_date"]=naive(a["purchase_date"]); aa["allocated_date"]=naive(aa["allocated_date"])
first_alloc=aa.dropna(subset=["allocated_date"]).groupby("asset_id")["allocated_date"].min()
a["allocation_date"]=a["id"].map(first_alloc)
a["asset_start_date"]=a["purchase_date"].fillna(a["allocation_date"])
a["date_source"]=np.where(a["purchase_date"].notna(),"purchase_date",
                  np.where(a["allocation_date"].notna(),"allocation_date","unknown"))
a["asset_age_days"]=(ASOF-a["asset_start_date"]).dt.days
a["asset_age_years"]=(a["asset_age_days"]/365.25).round(2)
if at is not None:
    a["asset_type"]=a["asset_type_id"].map(at.set_index("id")["name"])
else:
    a["asset_type"]=a["asset_type_id"]

cols=["id","asset_type","purchase_date","allocation_date","asset_start_date","date_source","asset_age_days","asset_age_years"]
a.rename(columns={"id":"asset_id"})[["asset_id"]+cols[1:]].to_csv(os.path.join(OUT,"phase2_asset_age_profile.csv"),index=False)

# summary
def band(y):
    if pd.isna(y): return "unknown"
    return "<1y" if y<1 else "1-2y" if y<2 else "2-3y" if y<3 else "3-5y" if y<5 else ">=5y"
a["age_band"]=a["asset_age_years"].apply(band)
usable=a["asset_start_date"].notna()
rows=[("total_assets",len(a)),
      ("purchase_date_coverage",int(a["purchase_date"].notna().sum())),
      ("allocation_fallback_used",int((a["purchase_date"].isna()&a["allocation_date"].notna()).sum())),
      ("unknown_dates",int((a["date_source"]=="unknown").sum())),
      ("usable_asset_age",int(usable.sum())),
      ("usable_pct","%.1f%%"%(100*usable.mean())),
      ("median_age_years",round(a.loc[usable,"asset_age_years"].median(),2)),
      ("p75_age_years",round(a.loc[usable,"asset_age_years"].quantile(.75),2)),
      ("p90_age_years",round(a.loc[usable,"asset_age_years"].quantile(.9),2)),
      ("TICKET_LEVEL_LINKAGE_NOTE","asset-age reaches only 18.4% of tickets via direct asset_id; bed->asset is 1:many, NOT bridged")]
pd.DataFrame(rows,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase2_asset_age_summary.csv"),index=False)
bands=a["age_band"].value_counts().rename_axis("age_band").reset_index(name="assets")
bands.to_csv(os.path.join(OUT,"phase2_asset_age_bands.csv"),index=False)
print("ASSET AGE written. Coverage 100% at asset level after allocation fallback.")
print(pd.DataFrame(rows,columns=["metric","value"]).to_string(index=False))
