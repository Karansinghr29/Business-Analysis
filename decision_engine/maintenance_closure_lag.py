"""
Phase-2 Maintenance CLOSURE-LAG (deterministic). NOT SLA. Does not use created_at.
closure_lag = closed_at - resolved_at (both must be valid). Negative lag flagged, not dropped.
New outputs only. Read-only source CSVs.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np, pandas as pd
from loader import load_all, num, to_dt

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)
D,_=load_all()
mt=D["maintenance_tickets"].copy()
def naive(s):
    d=to_dt(s)
    try:
        if getattr(d.dt,"tz",None) is not None: d=d.dt.tz_localize(None)
    except Exception: pass
    return d
mt["resolved_at"]=naive(mt["resolved_at"]); mt["closed_at"]=naive(mt["closed_at"])
it=D["issue_types"].set_index("id")["name"].to_dict()

both=mt.dropna(subset=["resolved_at","closed_at"]).copy()
both["closure_lag_hours"]=(both["closed_at"]-both["resolved_at"]).dt.total_seconds()/3600
both["closure_lag_days"]=both["closure_lag_hours"]/24
both["date_confidence"]="closure_timestamps"   # resolved_at+closed_at present; created_at NOT used
def status(h):
    if h<0: return "negative_closure_lag"
    if h<=48: return "closed_promptly"
    if h<=24*14: return "normal_closure"
    return "slow_admin_closure"
both["lag_status"]=both["closure_lag_hours"].apply(status)
both["issue_type_name"]=both["issue_type_id"].map(it)
both["reason"]=both.apply(lambda r: f"resolved {r['resolved_at'].date()} -> closed {r['closed_at'].date()} = {r['closure_lag_days']:.1f}d", axis=1)
both["recommended_action"]=np.where(both["closure_lag_hours"]<0,
    "DATA QUALITY: closed before resolved — verify timestamps",
    np.where(both["closure_lag_hours"]>24*14,"Review admin closure workflow (slow closure)","OK — admin closure lag"))

cols=["id","apartment_id","issue_type_id","issue_type_name","assigned_to","resolved_at","closed_at",
      "closure_lag_hours","closure_lag_days","date_confidence","lag_status","reason","recommended_action"]
both.rename(columns={"id":"ticket_id"})[[ "ticket_id" if c=="id" else c for c in cols]].to_csv(
    os.path.join(OUT,"phase2_maintenance_closure_lag.csv"),index=False)

pos=both[both["closure_lag_hours"]>=0]["closure_lag_days"]
neg=int((both["closure_lag_hours"]<0).sum())
rows=[("total_tickets",len(mt)),("usable_timestamp_pairs",len(both)),
      ("missing_timestamp_count",int(len(mt)-len(both))),("negative_lag_count",neg),
      ("median_lag_days",round(pos.median(),1)),("p75_lag_days",round(pos.quantile(.75),1)),
      ("p90_lag_days",round(pos.quantile(.9),1)),("mean_lag_days",round(pos.mean(),1))]
summ=pd.DataFrame(rows,columns=["metric","value"])
by_issue=both[both["closure_lag_hours"]>=0].groupby("issue_type_name")["closure_lag_days"].agg(["size","median"]).round(1).reset_index()
by_tech=both[both["closure_lag_hours"]>=0].groupby("assigned_to")["closure_lag_days"].agg(["size","median"]).round(1).reset_index()
summ.to_csv(os.path.join(OUT,"phase2_maintenance_closure_lag_summary.csv"),index=False)
by_issue.to_csv(os.path.join(OUT,"phase2_maintenance_closure_lag_by_issue.csv"),index=False)
by_tech.to_csv(os.path.join(OUT,"phase2_maintenance_closure_lag_by_tech.csv"),index=False)
print("CLOSURE-LAG (NOT SLA) written."); print(summ.to_string(index=False))
print("negative_closure_lag flagged (not dropped):", neg)
