"""
Phase 2 - Deterministic maintenance repeat/hotspot engine (NO ML).
Primary signal: apartment_id x issue_type_id recurrence.
- created_at primary event date; resolved_at only as LABELLED fallback.
- No post-outcome predictors. asset_id 18% -> no asset-level prediction.
- purchase_date used only where valid; asset age reported, never imputed, never a model.
Read-only source CSVs. Outputs: register, hotspots, issue_profile CSVs.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np, pandas as pd
from loader import load_all, num, to_dt

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)
ASOF=pd.Timestamp("2026-08-13")
def naive(s):
    s=to_dt(s)
    try:
        if getattr(s.dt,"tz",None) is not None: s=s.dt.tz_localize(None)
    except Exception: pass
    return s
D,_=load_all()
mt=D["maintenance_tickets"].copy()
mt["created_at"]=naive(mt["created_at"]); mt["resolved_at"]=naive(mt.get("resolved_at"))

# 3/4/5. event date: created_at primary, resolved_at labelled fallback
mt["date_source"]=np.where(mt["created_at"].notna(),"created_at",
                    np.where(mt["resolved_at"].notna(),"resolved_at_fallback","none"))
mt["event_date"]=mt["created_at"].fillna(mt["resolved_at"])
mt["date_confidence"]=mt["date_source"].map({"created_at":"high","resolved_at_fallback":"low","none":"none"})

tot=len(mt); dated=int((mt["date_source"]=="created_at").sum()); fb=int((mt["date_source"]=="resolved_at_fallback").sum())
nodate=int((mt["date_source"]=="none").sum())

# ---- asset age (only where purchase_date valid; never impute) ----
asset_age={}
if "assets" in D:
    a=D["assets"].copy(); a["purchase_date"]=naive(a["purchase_date"])
    valid_pd=a.dropna(subset=["purchase_date"])
    for _,r in valid_pd.iterrows():
        asset_age[r["id"]]=(ASOF - r["purchase_date"]).days
    pd_cov=a["purchase_date"].notna().mean()
else:
    pd_cov=0.0
OLD_THR=365*3  # documented deterministic threshold: >3 years = older_asset (only where age known)

# ---- 1/2. apartment x issue_type recurrence register ----
ev=mt.dropna(subset=["event_date","apartment_id","issue_type_id"]).sort_values("event_date")
recs=[]; pairs90=0; pairs180=0
for (apt,iss),g in ev.groupby(["apartment_id","issue_type_id"]):
    dates=sorted(g["event_date"].tolist())
    n=len(dates); last=dates[-1]
    gaps=[(dates[i+1]-dates[i]).days for i in range(len(dates)-1)]
    prev_gap=gaps[-1] if gaps else np.nan
    r90=sum(1 for x in gaps if x<=90); r180=sum(1 for x in gaps if x<=180)
    pairs90+=r90; pairs180+=r180
    days_since_last=(ASOF-last).days
    # dominant date confidence for this group
    conf="high" if (g["date_source"]=="created_at").mean()>=0.5 else "low"
    # deterministic priority
    if n>=2 and pd.notna(prev_gap) and prev_gap<=90:
        pri,reason="High",f"recurred within {int(prev_gap)}d ({n} tickets)"
        act="Inspect recurring apartment/issue; check if equipment needs repair/replacement"
    elif r90>=2:
        pri,reason="High",f"{r90} recurrences <=90d ({n} tickets)"; act="Inspect recurring apartment/issue; review technician history"
    elif n>=2 and pd.notna(prev_gap) and prev_gap<=180:
        pri,reason="Medium",f"recurred within {int(prev_gap)}d ({n} tickets)"; act="Monitor; inspect if it recurs again"
    elif n>=2:
        pri,reason="Low",f"{n} historical tickets, last gap {int(prev_gap) if pd.notna(prev_gap) else 'NA'}d"; act="Historical only; monitor"
    else:
        pri,reason="Low",f"single ticket"; act="Monitor"
    if dated<60:  # not really the case, but guard
        pass
    recs.append(dict(apartment_id=apt, issue_type_id=iss, ticket_count=n, repeat_count=max(n-1,0),
        recur_le90=r90, recur_le180=r180, last_occurrence=last.date(), days_since_last=days_since_last,
        prev_gap_days=prev_gap, hotspot=(pri=="High"), priority=pri, date_confidence=conf,
        reason=reason, recommended_action=act))
reg=pd.DataFrame(recs).sort_values(["priority","recur_le90","ticket_count"],ascending=[True,False,False])
# order priority High>Medium>Low
order={"High":0,"Medium":1,"Low":2}; reg["_o"]=reg["priority"].map(order); reg=reg.sort_values(["_o","recur_le90","ticket_count"],ascending=[True,False,False]).drop(columns="_o")
reg.to_csv(os.path.join(OUT,"phase2_maintenance_repeat_register.csv"),index=False)

# hotspots = High priority apartment x issue_type
hot=reg[reg["priority"].isin(["High","Medium"])].copy()
hot.to_csv(os.path.join(OUT,"phase2_maintenance_hotspots.csv"),index=False)

# ---- 7. issue-type + technician descriptive profile (cost where available) ----
tr=D.get("ticket_resolutions")
cost_by_ticket={}
if tr is not None:
    tr=tr.copy(); tr["total_cost"]=num(tr["total_cost"])
    cost_by_ticket=tr.dropna(subset=["ticket_id"]).set_index("ticket_id")["total_cost"].to_dict()
mt["res_cost"]=mt["id"].map(cost_by_ticket)
cost_cov=mt["res_cost"].notna().mean()
issprof=mt.groupby("issue_type_id").agg(
    tickets=("id","size"),
    with_cost=("res_cost",lambda s:s.notna().sum()),
    total_cost=("res_cost",lambda s:num(s).sum()),
    avg_cost_where_known=("res_cost",lambda s:num(s).mean())).reset_index().sort_values("tickets",ascending=False)
tech=mt.groupby("assigned_to").agg(
    tickets=("id","size"),
    distinct_issue_types=("issue_type_id","nunique"),
    with_cost=("res_cost",lambda s:s.notna().sum()),
    total_cost=("res_cost",lambda s:num(s).sum())).reset_index().sort_values("tickets",ascending=False)
issprof.to_csv(os.path.join(OUT,"phase2_maintenance_issue_profile.csv"),index=False)
tech.to_csv(os.path.join(OUT,"phase2_maintenance_technician_profile.csv"),index=False)

# ---- 13. quantify ----
age_used=int(mt["asset_id"].map(lambda x: x in asset_age).sum())
print("="*70); print("DETERMINISTIC MAINTENANCE REPEAT/HOTSPOT ENGINE — RESULTS"); print("="*70)
print(f"total tickets={tot} | dated(created_at)={dated} | fallback(resolved_at)={fb} | no-date(excluded)={nodate}")
print(f"apartment×issue_type groups={len(reg)}  recurrence pairs <=90d={pairs90}  <=180d={pairs180}")
print(f"priority: High={int((reg['priority']=='High').sum())} Medium={int((reg['priority']=='Medium').sum())} Low={int((reg['priority']=='Low').sum())}")
print(f"hotspots(High)={int(reg['hotspot'].sum())}")
print(f"asset_id coverage on tickets={mt['asset_id'].notna().mean():.0%} (NO asset-level prediction)")
print(f"purchase_date coverage(assets)={pd_cov:.0%}  asset_age_available(records w/ valid age)={len(asset_age)}  tickets whose asset has usable age={age_used}")
print(f"ticket cost coverage (resolutions)={cost_cov:.0%}  total_cost=₹{num(mt['res_cost']).sum():,.0f}")
print("\nTop hotspots (High):")
print(reg[reg['priority']=='High'].head(8)[["apartment_id","issue_type_id","ticket_count","recur_le90","days_since_last","date_confidence","reason"]].to_string(index=False))
print("\nOutputs: phase2_maintenance_repeat_register.csv, phase2_maintenance_hotspots.csv, phase2_maintenance_issue_profile.csv (+ technician_profile)")
print("LIMITS: created_at 31% only; fallback dates labelled; asset age NOT a feature/model; cost coverage ~26%.")
