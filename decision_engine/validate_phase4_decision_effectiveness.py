"""Fail-loud validation of the deterministic decision-effectiveness reducer. Uses ISOLATED in-memory event lists
for the outcome-state scenarios (Improved/No Change/Worsened/Insufficient/context_only/correction) — the real
operational store is never written. Verifies read-only immutability, determinism, backbone/AIREC separation."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import phase4_decision_effectiveness as R
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
dirmap,winrows=R.load_registries()

def bl(rid,kpi,is_bb=False,rtype="phase4_deterministic"):
    return dict(recommendation_id=rid,recommendation_type=rtype,is_backbone=is_bb,
        decision_or_opportunity="test",target_kpi=kpi,baseline_value=R.UNAVAIL,baseline_date="",baseline_source="test")
def ev(rid,et,date,**k): return dict(dict(recommendation_id=rid,event_type=et,event_date=date,event_id=k.pop("eid","EVT-x"),
        owner_decision="",action_taken="",target_kpi="",value="",unit="",measurement_role="",supersedes_event_id="",notes=""),**k)
def outcome(baselines,events):
    E,_=R.compute(baselines,events,dirmap,winrows,"2026-08"); return E.iloc[0]

KPI_L="Monthly vacancy revenue-at-risk"   # lower_is_better, measurable, tol 0, vacancy_fill minw 30
KPI_C="Lead enquiries / campaign conversions"  # context_only
RID="AIREC-VAC-RISK"; RIDC="AIREC-AMEN-AC"

print("[1] outcome scenarios recompute exactly (direction from registry, window from registry)")
base=[bl(RID,KPI_L)]
evs=lambda pv,pd_:[ev(RID,"owner_decision","2026-08-01",eid="EVT-000001",owner_decision="approved"),
    ev(RID,"action_taken","2026-08-01",eid="EVT-000002",action_taken="filled beds"),
    ev(RID,"measurement","2026-08-01",eid="EVT-000003",target_kpi=KPI_L,unit="INR",value="285700",measurement_role="baseline"),
    ev(RID,"measurement",pd_,eid="EVT-000004",target_kpi=KPI_L,unit="INR",value=pv,measurement_role="post_action")]
chk(outcome(base,evs("200000","2026-09-15"))["outcome_status"]=="Improved","Improved (lower_is_better, ↓, window met)")
chk(outcome(base,evs("320000","2026-09-15"))["outcome_status"]=="Worsened","Worsened (lower_is_better, ↑)")
chk(outcome(base,evs("285700","2026-09-15"))["outcome_status"]=="No Change","No Change (Δ within tolerance)")
chk(outcome(base,evs("200000","2026-08-10"))["outcome_status"]=="Insufficient Data","Insufficient Data (window not complete)")
# no post measurement (baseline present, action present, but no post)
noc=[ev(RID,"action_taken","2026-08-01",eid="EVT-1",action_taken="did x"),
     ev(RID,"measurement","2026-08-01",eid="EVT-2",target_kpi=KPI_L,unit="INR",value="285700",measurement_role="baseline")]
chk(outcome(base,noc)["outcome_status"]=="Insufficient Data","Insufficient Data (no post measurement)")
# no action
chk(outcome(base,[])["outcome_status"]==R.NOACT,"Outcome Unavailable — no action executed (empty)")
# context_only
r=outcome([bl(RIDC,KPI_C)],[ev(RIDC,"action_taken","2026-08-01",eid="E1",action_taken="promo"),
    ev(RIDC,"measurement","2026-10-01",eid="E2",target_kpi=KPI_C,value="5",measurement_role="post_action")])
chk(r["outcome_status"].startswith("Not Evaluable"),"Not Evaluable — context_only direction")

print("\n[2] attribution separate from outcome")
imp=outcome(base,evs("200000","2026-09-15"))
chk(imp["outcome_status"]=="Improved" and imp["attribution_confidence"] in ("High","Medium","Low"),"Improved row carries an explicit attribution tier")
# concurrent action on same KPI (other rec) -> attribution Low
conc=evs("200000","2026-09-15")+[ev("AIREC-INV-PROMOTE-DOUBLE","action_taken","2026-08-02",eid="EVT-0009",action_taken="also promoted",target_kpi=KPI_L)]
chk(outcome(base,conc)["attribution_confidence"]=="Low","attribution downgraded to Low when a concurrent action on same KPI exists")

print("\n[3] correction supersedes prior event")
corr=[ev(RID,"action_taken","2026-08-01",eid="EVT-000002",action_taken="filled"),
      ev(RID,"measurement","2026-08-01",eid="EVT-000003",target_kpi=KPI_L,unit="INR",value="285700",measurement_role="baseline"),
      ev(RID,"correction","2026-08-02",eid="EVT-000005",supersedes_event_id="EVT-000003",target_kpi=KPI_L,unit="INR",value="300000",measurement_role="baseline"),
      ev(RID,"measurement","2026-09-15",eid="EVT-000006",target_kpi=KPI_L,unit="INR",value="290000",measurement_role="post_action")]
# corrected baseline 300000 -> post 290000 -> lower_is_better -> Improved (uses corrected, not 285700 which would be Worsened)
chk(outcome(base,corr)["outcome_status"]=="Improved","correction supersedes baseline (uses corrected value)")

print("\n[4] unavailable never zero")
r0=outcome([bl(RID,KPI_L)],[ev(RID,"action_taken","2026-08-01",eid="E1",action_taken="x"),
    ev(RID,"measurement","2026-09-15",eid="E2",target_kpi=KPI_L,unit="INR",value="",measurement_role="post_action",notes=R.UNAVAIL)])
chk("Unavailable" in r0["data_limitation"] or r0["outcome_status"].startswith(("Insufficient","Outcome Unavailable")),"missing baseline/post → Unavailable/Insufficient, never 0")
chk(str(r0["post_value"])!="0","post value not coerced to 0 when unavailable")

print("\n[5] real reducer output (empty store) is honest + backbone/AIREC correct")
subprocess.run([sys.executable,"phase4_decision_effectiveness.py"],cwd=HERE,capture_output=True)
E=pd.read_csv(R.EFF); S=dict(zip(pd.read_csv(R.EFF_SUM)["metric"],pd.read_csv(R.EFF_SUM)["value"]))
chk(int(S["backbone_total"])==14,"backbone_total == 14 (unchanged)")
chk(int(S["deterministic_opportunities_total"])==13,"AIREC deterministic opportunities == 13 (Single promote dropped at 0 single vacancy; separate, non-backbone)")
chk(int((E[E["recommendation_type"]=="phase4_deterministic"]["is_backbone"]==False).sum())==13,"AIREC rows are is_backbone=False (not converted to backbone)")
chk(int(S["actions_recorded"])==0 and int(S["measurable_outcomes"])==0,"empty store → 0 actions, 0 measurable outcomes (no fabrication)")
chk(int(S["outcome_unavailable"])==len(E) and int(S["attribution_unavailable"])==len(E),"all outcomes/attribution Unavailable with empty store")
dea=set(pd.read_csv(os.path.join(OUT,"phase3_decision_execution_analytics.csv"))["decision_id"].astype(str))
bbrows=E[E["is_backbone"]==True]["recommendation_id"].astype(str)
chk(set(bbrows).issubset(dea),"every backbone baseline traces to phase3_decision_execution_analytics.csv")

print("\n[6] KPI direction + window come from the registry")
d=pd.read_csv(os.path.join(OUT,"phase4_kpi_direction_registry.csv")); dmap=dict(zip(d["kpi_name"],d["direction"]))
chk(all(E.loc[i,"kpi_direction"]==dmap.get(E.loc[i,"target_kpi"],"context_only") for i in E.index),"kpi_direction always from registry")

print("\n[7] reducer is READ-ONLY on the event store; deterministic")
h1=hashlib.md5(open(R.EVENTS,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase4_decision_effectiveness.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(R.EVENTS,"rb").read()).hexdigest()
chk(h1==h2,"event store bytes unchanged after running reducer (read-only)")
e1=hashlib.md5(open(R.EFF,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase4_decision_effectiveness.py"],cwd=HERE,capture_output=True)
e2=hashlib.md5(open(R.EFF,"rb").read()).hexdigest()
chk(e1==e2,"effectiveness output deterministic (byte-identical re-run for identical inputs)")
chk(len(R.read_events())==0,"REAL operational event store still has 0 events")
chk(not R.EFF.startswith(OUT),"effectiveness outputs live outside outputs/ (excluded from locked --verify)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
