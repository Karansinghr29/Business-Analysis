"""Fail-loud validation that attribution is downgraded for OVERLAPPING real-world mechanisms.

Defect being guarded (reproduced in audit): concurrency was detected by matching KPI-name strings.
Recommendations acting on the same population were authored with different KPI names, so four
same-day actions on the same five vacant Double beds each returned attribution = High — implying
each action independently caused one observed movement.

Every expectation below is DERIVED from the reducer's own `_CLUSTERS` map, so this validator keeps
testing the real behaviour if the mapping changes; it does not hard-code the current answer.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
import phase4_decision_effectiveness as R

fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

BASE=R.load_baselines(); DIRMAP,WINROWS=R.load_registries()
BY={x["recommendation_id"]:x for x in BASE}

def run(ids, action_date="2026-09-01", post_date="2026-11-01"):
    evs=[]; bases=[]
    for rid in ids:
        x=BY[rid]; k=x["target_kpi"]; bases.append(x)
        evs+=[dict(event_id=f"D{rid}",recommendation_id=rid,event_type="owner_decision",
                   event_date=action_date,owner_decision="approved"),
              dict(event_id=f"A{rid}",recommendation_id=rid,event_type="action_taken",
                   event_date=action_date,action_taken="acted"),
              dict(event_id=f"B{rid}",recommendation_id=rid,event_type="measurement",event_date=action_date,
                   target_kpi=k,value="100",measurement_role="baseline"),
              dict(event_id=f"P{rid}",recommendation_id=rid,event_type="measurement",event_date=post_date,
                   target_kpi=k,value="50",measurement_role="post_action")]
    E,_=R.compute(bases,evs,DIRMAP,WINROWS,asof=post_date)
    return {r.recommendation_id:r.attribution_confidence for r in E.itertuples()}

# ---------------------------------------------------------------- map integrity
print("[1] the cluster map is explicit, auditable, and not inferred at runtime")
chk(isinstance(R._CLUSTERS,dict) and len(R._CLUSTERS)>0,"_CLUSTERS map exists in the reducer")
chk(all(isinstance(v,set) and v for v in R._CLUSTERS.values()),"every mapped recommendation has a non-empty cluster set")
known={b["recommendation_id"] for b in BASE}
chk(set(R._CLUSTERS).issubset(known),"every mapped id is a real recommendation")
chk(not R._clusters_overlap("DEC-VAC-Double","__unmapped__"),"unmapped ids never count as concurrent")

# derive the clusters that actually contain more than one recommendation
groups={}
for rid,cl in R._CLUSTERS.items():
    for c in cl: groups.setdefault(c,[]).append(rid)
multi={c:sorted(v) for c,v in groups.items() if len(v)>1}
print(f"\n[2] shared clusters derived from the map: {len(multi)}")
for c,v in multi.items(): print(f"    {c}: {v}")
chk(len(multi)>0,"at least one genuinely shared mechanism is declared")

# ---------------------------------------------------------------- the reproduced defect
print("\n[3] overlapping actions on the SAME mechanism must not all claim High")
for c,members in multi.items():
    # only members that can actually reach an attribution verdict are meaningful here
    usable=[r for r in members if str(DIRMAP[BY[r]["target_kpi"]]["measurable"]).lower()=="yes"
            and DIRMAP[BY[r]["target_kpi"]]["direction"]!="context_only"]
    if len(usable)<2: continue
    att=run(usable)
    highs=[r for r,a in att.items() if a=="High"]
    chk(not highs,f"cluster '{c}': no member claims High when {len(usable)} act together (got {att})")
    chk(all(a in ("Low","Medium") for a in att.values()),
        f"cluster '{c}': attribution downgraded rather than dropped ({set(att.values())})")

print("\n[4] concurrency is detected DESPITE different KPI names")
dbl=[r for r in groups.get("double_inventory_fill",[])
     if str(DIRMAP[BY[r]["target_kpi"]]["measurable"]).lower()=="yes"
     and DIRMAP[BY[r]["target_kpi"]]["direction"]!="context_only"]
if len(dbl)>=2:
    kpis={BY[r]["target_kpi"] for r in dbl}
    chk(len(kpis)>1,f"the Double-inventory members genuinely use different KPI names ({len(kpis)} distinct)")
    att=run(dbl)
    chk(all(a!="High" for a in att.values()),f"all Double-inventory members downgraded (got {att})")

print("\n[5] UNRELATED clusters must NOT be falsely downgraded")
pairs=[]
cl_of=lambda r: R._CLUSTERS.get(r,set())
cands=[r for r in R._CLUSTERS if str(DIRMAP[BY[r]["target_kpi"]]["measurable"]).lower()=="yes"
       and DIRMAP[BY[r]["target_kpi"]]["direction"]!="context_only"]
for i,a in enumerate(cands):
    for b in cands[i+1:]:
        if not (cl_of(a)&cl_of(b)): pairs.append((a,b))
chk(len(pairs)>0,"unrelated measurable pairs exist to test")
for a,b in pairs[:6]:
    att=run([a,b])
    chk(att.get(a)=="High" and att.get(b)=="High",
        f"unrelated pair {a} + {b} both keep High (got {att})")

print("\n[6] a single action alone still earns High")
solo=cands[0]
chk(run([solo]).get(solo)=="High",f"{solo} acting alone keeps High")

print("\n[7] non-overlapping TIME windows are not treated as concurrent")
if len(dbl)>=2:
    a,b=dbl[0],dbl[1]
    # b acts long after a's measurement closed -> outside a's exposure period
    evs=[];bases=[]
    for rid,ad,pd_ in [(a,"2026-09-01","2026-11-01"),(b,"2027-06-01","2027-08-01")]:
        x=BY[rid]; k=x["target_kpi"]; bases.append(x)
        evs+=[dict(event_id=f"A{rid}",recommendation_id=rid,event_type="action_taken",event_date=ad,action_taken="acted"),
              dict(event_id=f"B{rid}",recommendation_id=rid,event_type="measurement",event_date=ad,
                   target_kpi=k,value="100",measurement_role="baseline"),
              dict(event_id=f"P{rid}",recommendation_id=rid,event_type="measurement",event_date=pd_,
                   target_kpi=k,value="50",measurement_role="post_action")]
    E,_=R.compute(bases,evs,DIRMAP,WINROWS,asof="2027-08-01")
    got={r.recommendation_id:r.attribution_confidence for r in E.itertuples()}
    chk(got.get(a)=="High",f"{a} keeps High when the other action is far outside its window (got {got})")

print("\n[8] scale-mismatch pairs are treated consistently (D2)")
SRC=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
import re
m=re.search(r"_PATTERN=\{(.*?)\n    \}",SRC,re.S)
ov=dict(re.findall(r'"([A-Z0-9-]+(?:-[A-Za-z]+)*)":dict\(p="(\w+)"',m.group(1) if m else ""))
chk(ov.get("DEC-RETENTION-REVIEW")=="investig","DEC-RETENTION-REVIEW is an investigation pattern")
chk(ov.get("AIREC-CHURN-WATCH")=="investig","AIREC-CHURN-WATCH matches its backbone twin (not 'direct')")
chk(ov.get("DEC-RETENTION-REVIEW")==ov.get("AIREC-CHURN-WATCH"),
    "both retention recommendations share one scale-aware pattern")
chk(R._clusters_overlap("DEC-RETENTION-REVIEW","AIREC-CHURN-WATCH"),
    "both retention recommendations share an attribution cluster")

print("\n[9] DEC-AMEN-AC claims no fixed bed count and no bed-level tracking (D4)")
blk=m.group(1) if m else ""
i=blk.find('"DEC-AMEN-AC"'); j=blk.find('"DEC-EB-INVESTIGATE"')
amen=blk[i:j] if i>=0 and j>i else blk
chk("5 Double beds" not in amen,"no hard-coded '5 Double beds' claim")
chk(not re.search(r"\bthose same \d+\b",amen),"no hard-coded bed count in the outcome wording")
chk("not individually tracked" in amen,"states the beds are not individually tracked as an outcome series")
chk("aggregate inventory movement" in amen,"states the observed result is aggregate movement")

print("\n[10] event architecture untouched")
cap=open(os.path.join(HERE,"phase4_action_capture.py"),encoding="utf-8").read()
for banned in ["outcome_status","attribution_confidence","improvement_pct"]:
    chk(banned not in cap,f"writer never accepts a typed '{banned}'")
store=os.path.join(HERE,"operational","phase4_outcome_events.csv")
n=(sum(1 for _ in open(store,encoding="utf-8"))-1) if os.path.exists(store) else 0
chk(n==0,f"real event store untouched ({n} events)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
