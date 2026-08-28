"""
Phase-2 Maintenance SLA — RECONSTRUCTED from ticket_logs lifecycle events + issue-type SLA target.
NOT the confirmed application algorithm (React/Supabase app code unavailable locally).
Created = ticket_logs first 'Ticket created' event (100% coverage). Close = ticket_logs
new_status='closed'/'Marked closed'. SLA target = issue_types.sla_hours (4/6/12/24h).
Collapsed (created==closed) tickets flagged and EXCLUDED from genuine SLA-performance KPIs.
NEW outputs only. Read-only source CSVs.
"""
from __future__ import annotations
import os, sys, glob
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np, pandas as pd
from loader import load_all, num, to_dt

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)
BD=r"D:/data science/Business Decision"
D,_=load_all()
mt=D["maintenance_tickets"].copy(); it=D["issue_types"].copy()
def naive(s):
    d=to_dt(s)
    try:
        if getattr(d.dt,"tz",None) is not None: d=d.dt.tz_localize(None)
    except Exception: pass
    return d
def find(sig):
    for f in glob.glob(os.path.join(BD,"*.csv")):
        try:h=set(pd.read_csv(f,nrows=0).columns)
        except:continue
        if sig<=h: return pd.read_csv(f,low_memory=False)
    return None
tl=find({"ticket_id","action","old_status","new_status","created_at"})
tl["created_at"]=naive(tl["created_at"])

# ---- lifecycle timestamps from ticket_logs ----
created=tl[tl["action"].astype(str).eq("Ticket created")].groupby("ticket_id")["created_at"].min().rename("created_ts")
# fallback creation = first log if no explicit 'Ticket created'
firstlog=tl.groupby("ticket_id")["created_at"].min().rename("first_log_ts")
closed=tl[tl["new_status"].astype(str).str.lower().eq("closed")].groupby("ticket_id")["created_at"].max().rename("closed_ts")

sla_map=it.set_index("id")["sla_hours"].to_dict()
name_map=it.set_index("id")["name"].to_dict()

df=mt[["id","apartment_id","issue_type_id","assigned_to","status"]].copy().rename(columns={"id":"ticket_id"})
df=df.merge(created,on="ticket_id",how="left").merge(firstlog,on="ticket_id",how="left").merge(closed,on="ticket_id",how="left")
df["created_ts"]=df["created_ts"].fillna(df["first_log_ts"])   # first log validated == created_at (diff 0)
df["created_source"]=np.where(mt.set_index('id').reindex(df['ticket_id'])['created_at'].notna().values,"logs+mt_match","logs_only")
df["sla_hours"]=df["issue_type_id"].map(sla_map)
df["issue_type_name"]=df["issue_type_id"].map(name_map)

df["actual_resolution_hours"]=(df["closed_ts"]-df["created_ts"]).dt.total_seconds()/3600
df["sla_remaining_hours"]=df["sla_hours"]-df["actual_resolution_hours"]

def lifecycle_quality(r):
    if pd.isna(r["created_ts"]) or pd.isna(r["closed_ts"]): return "insufficient_lifecycle_data"
    if r["created_ts"]==r["closed_ts"]: return "collapsed_timestamp"
    return "measurable"
df["lifecycle_quality"]=df.apply(lifecycle_quality,axis=1)

def status(r):
    q=r["lifecycle_quality"]
    if q=="insufficient_lifecycle_data": return "Insufficient lifecycle data"
    if q=="collapsed_timestamp": return "Collapsed timestamp"
    if pd.isna(r["sla_hours"]): return "SLA target missing"
    return "SLA Breached" if r["actual_resolution_hours"]>r["sla_hours"] else "Within SLA"
df["sla_status"]=df.apply(status,axis=1)
df["sla_breached"]=np.where(df["sla_status"]=="SLA Breached",True,np.where(df["sla_status"]=="Within SLA",False,pd.NA))
df["reason"]=df.apply(lambda r: (f"reconstructed {r['actual_resolution_hours']:.1f}h vs {r['sla_hours']}h SLA"
    if r["lifecycle_quality"]=="measurable" and pd.notna(r["sla_hours"]) else r["lifecycle_quality"]),axis=1)
df["recommended_action"]=np.select(
    [df["sla_status"]=="SLA Breached", df["sla_status"]=="Within SLA",
     df["sla_status"]=="Collapsed timestamp", df["sla_status"]=="Insufficient lifecycle data"],
    ["Review breach — slow resolution for this issue type","OK",
     "Excluded from genuine SLA KPI (migration-collapsed timestamps)","No closed event yet / open"],
    default="Check SLA target for this issue type")
df["method"]="Reconstructed SLA from ticket_logs lifecycle + issue_types.sla_hours (NOT verified app formula)"

cols=["ticket_id","apartment_id","issue_type_id","issue_type_name","assigned_to","created_ts","closed_ts",
      "created_source","actual_resolution_hours","sla_hours","sla_remaining_hours","sla_breached",
      "sla_status","lifecycle_quality","reason","recommended_action","method"]
df[cols].to_csv(os.path.join(OUT,"phase2_maintenance_sla.csv"),index=False)

# ---- validation vs sla_deadline (evidence only, do not force) ----
mt["sla_deadline"]=naive(mt.get("sla_deadline")); mt["created_at"]=naive(mt["created_at"])
val=mt.dropna(subset=["sla_deadline"]).copy()
val=val.merge(df[["ticket_id","created_ts","sla_hours"]],left_on="id",right_on="ticket_id",how="left")
val["recon_deadline"]=val["created_ts"]+pd.to_timedelta(val["sla_hours"],unit="h")
vd=(val["sla_deadline"]-val["recon_deadline"]).dt.total_seconds()/3600
exact=int((vd.abs()<=1).sum()); mism=int((vd.abs()>1).sum())

# ---- summary ----
meas=df[df["lifecycle_quality"]=="measurable"]
br=int((meas["sla_status"]=="SLA Breached").sum()); met=int((meas["sla_status"]=="Within SLA").sum())
rows=[("total_tickets",len(mt)),
      ("creation_available",int(df["created_ts"].notna().sum())),
      ("close_available",int(df["closed_ts"].notna().sum())),
      ("both_available",int((df["created_ts"].notna()&df["closed_ts"].notna()).sum())),
      ("collapsed_timestamp",int((df["lifecycle_quality"]=="collapsed_timestamp").sum())),
      ("genuinely_measurable",len(meas)),
      ("SLA_met",met),("SLA_breached",br),
      ("breach_rate_measurable","%.1f%%"%(100*br/max(len(meas),1))),
      ("median_turnaround_hours_measurable",round(meas["actual_resolution_hours"].median(),1)),
      ("p90_turnaround_hours_measurable",round(meas["actual_resolution_hours"].quantile(.9),1)),
      ("sla_deadline_validation_exact(<=1h)",exact),
      ("sla_deadline_validation_mismatch(>1h)",mism),
      ("sla_deadline_validation_median_diff_hours",round(float(vd.median()),2) if len(vd) else None)]
pd.DataFrame(rows,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase2_maintenance_sla_summary.csv"),index=False)

by_issue=meas.groupby("issue_type_name").agg(
    tickets=("ticket_id","size"), sla_hours=("sla_hours","first"),
    breached=("sla_status",lambda s:(s=="SLA Breached").sum()),
    median_hours=("actual_resolution_hours","median")).reset_index()
by_issue["breach_rate"]=(by_issue["breached"]/by_issue["tickets"]).round(3)
by_issue.round(1).to_csv(os.path.join(OUT,"phase2_maintenance_sla_by_issue.csv"),index=False)
by_tech=meas.groupby("assigned_to").agg(
    tickets=("ticket_id","size"),
    breached=("sla_status",lambda s:(s=="SLA Breached").sum()),
    median_hours=("actual_resolution_hours","median")).reset_index()
by_tech["breach_rate"]=(by_tech["breached"]/by_tech["tickets"]).round(3)
by_tech.round(1).to_csv(os.path.join(OUT,"phase2_maintenance_sla_by_technician.csv"),index=False)

print("RECONSTRUCTED SLA written (NOT verified app formula).")
for m,vv in rows: print(f"  {m}: {vv}")
print("\nSLA deadline validation: exact(<=1h)=%d mismatch(>1h)=%d median_diff=%.2fh"%(exact,mism,float(vd.median()) if len(vd) else 0))
