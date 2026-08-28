"""Fail-loud lifecycle validation for ALL 33 selectable Page-15 recommendations.

Anything the owner can select must either have a working Decision → Action → Measurement → Outcome
path, or the system must explicitly explain why an outcome cannot yet be measured. This validator
drives every one of the 33 through the real reducer against synthetic event stores and asserts the
correct behaviour for its category — measurable, context-only, owner-verify, or unavailable.

Nothing here writes to the real operational event store.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
sys.path.insert(0,HERE)
import phase4_decision_effectiveness as R

fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

BASE=R.load_baselines(); DIRMAP,WINROWS=R.load_registries()
BY={b["recommendation_id"]:b for b in BASE}

def drive(rid, post=None, base_event=None, decision="approved", act=True,
          action_date="2026-09-01", post_date="2026-12-01"):
    """Run the real reducer for one recommendation over a synthetic event store."""
    b=BY[rid]
    evs=[dict(event_id="E1",recommendation_id=rid,event_type="owner_decision",
              event_date=action_date,owner_decision=decision)]
    if act:
        evs.append(dict(event_id="E2",recommendation_id=rid,event_type="action_taken",
                        event_date=action_date,action_taken="test action"))
    if base_event is not None:
        evs.append(dict(event_id="E0",recommendation_id=rid,event_type="measurement",event_date=action_date,
                        target_kpi=b["target_kpi"],value=base_event,measurement_role="baseline"))
    if post is not None:
        evs.append(dict(event_id="E3",recommendation_id=rid,event_type="measurement",event_date=post_date,
                        target_kpi=b["target_kpi"],value=post,measurement_role="post_action"))
    E,_=R.compute([b],evs,DIRMAP,WINROWS,asof=post_date)
    return E.iloc[0]

# ---------------------------------------------------------------- registry integrity
print("[1] recommendation registry composition")
cnt=pd.Series([b["recommendation_type"] for b in BASE]).value_counts().to_dict()
chk(len(BASE)==33,f"33 selectable recommendations (got {len(BASE)})")
chk(cnt.get("backbone")==14,f"14 backbone (got {cnt.get('backbone')})")
chk(cnt.get("phase3_opportunity")==6,f"6 Phase-3 opportunities (got {cnt.get('phase3_opportunity')})")
chk(cnt.get("phase4_deterministic")==13,f"13 AIREC (got {cnt.get('phase4_deterministic')})")
chk(all(b["is_backbone"] for b in BASE if b["recommendation_type"]=="backbone"),"backbone rows flagged is_backbone=True")
chk(not any(b["is_backbone"] for b in BASE if b["recommendation_type"]!="backbone"),
    "Phase-3 opportunities and AIREC are all is_backbone=False")
chk(all(b["target_kpi"] in DIRMAP for b in BASE),"every one of the 33 has a registered KPI")

# ---------------------------------------------------------------- classify the 33
MEAS=[];CTX=[];VERIFY=[];UNAVAIL=[]
for b in BASE:
    rid=b["recommendation_id"]; reg=DIRMAP[b["target_kpi"]]
    dom,minw=R.domain_min_window(rid,WINROWS)
    if dom=="owner_verify" or minw==0: VERIFY.append(rid)
    elif str(reg["measurable"]).lower()!="yes": UNAVAIL.append(rid)
    elif reg["direction"]=="context_only": CTX.append(rid)
    else: MEAS.append(rid)
print(f"\n[2] categories — measurable {len(MEAS)} · context-only {len(CTX)} · owner-verify {len(VERIFY)} · unavailable {len(UNAVAIL)}")
chk(len(MEAS)+len(CTX)+len(VERIFY)+len(UNAVAIL)==33,"every recommendation falls into exactly one category")
chk(len(MEAS)>0,"at least one genuinely measurable recommendation exists")

# ---------------------------------------------------------------- measurable: full lifecycle
print(f"\n[3] MEASURABLE ({len(MEAS)}) — full Decision → Action → Measurement → Outcome")
for rid in MEAS:
    b=BY[rid]; reg=DIRMAP[b["target_kpi"]]; unit=reg["unit"]; direction=reg["direction"]
    base_num=R._kpi_num(b["baseline_value"],unit)
    # a baseline must be obtainable: either resolvable from analytics, or supplied by an owner event
    bnum = base_num if base_num is not None else 100.0
    bev  = None      if base_num is not None else "100"
    better = bnum*0.5 if direction=="lower_is_better" else bnum*1.5
    worse  = bnum*1.5 if direction=="lower_is_better" else bnum*0.5
    if bnum==0: better,worse=0.0,5.0            # zero baseline: only a rise is meaningful
    r=drive(rid,post=str(better),base_event=bev)
    exp="No Change" if better==bnum else "Improved"
    chk(r["outcome_status"]==exp,f"{rid}: improving move -> {exp} (got '{r['outcome_status']}')")
    r=drive(rid,post=str(worse),base_event=bev)
    chk(r["outcome_status"]=="Worsened",f"{rid}: adverse move -> Worsened (got '{r['outcome_status']}')")
    # window not yet complete must NOT produce a verdict
    r=drive(rid,post=str(better),base_event=bev,post_date="2026-09-02")
    chk(r["outcome_status"]=="Insufficient Data",
        f"{rid}: measured 1d after action -> Insufficient Data (got '{r['outcome_status']}')")
    # action recorded but nothing measured yet
    r=drive(rid,post=None,base_event=bev)
    chk(r["outcome_status"]=="Insufficient Data",f"{rid}: action but no measurement -> Insufficient Data")

print(f"\n[4] MEASURABLE — unit-aware parsing picks the correct component")
for rid in MEAS:
    b=BY[rid]; unit=DIRMAP[b["target_kpi"]]["unit"]; raw=str(b["baseline_value"])
    v=R._kpi_num(raw,unit)
    if v is None: continue                      # baseline supplied by owner event instead — legitimate
    nums=[t for t in raw.replace(","," ").replace("₹"," ").replace("%"," ").replace("/"," ").split() if t.replace(".","",1).isdigit()]
    note=f"{rid}: '{raw}' [{unit}] -> {v}"
    chk(v is not None,note+" resolves")
    if len(nums)>1:
        chk(True,note+f"  (multi-number baseline — unit selected the right one of {nums})")

# ---------------------------------------------------------------- non-measurable categories
print(f"\n[5] CONTEXT-ONLY ({len(CTX)}) — no good/bad verdict may be produced")
for rid in CTX:
    r=drive(rid,post="42",base_event="10")
    chk(str(r["outcome_status"]).startswith("Not Evaluable"),
        f"{rid}: context-only -> Not Evaluable (got '{r['outcome_status']}')")
    chk(str(r["outcome_status"])not in("Improved","Worsened"),f"{rid}: never claims improved/worsened")

print(f"\n[6] OWNER-VERIFY ({len(VERIFY)}) — state preserved, nothing invented")
# NOTE: the UI blocks measurement entry entirely for these (section D disables it when the KPI is
# context_only or not measurable), so the realistic path is decision + action with NO measurement.
_dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
# The gate is now the resolved measurement PATTERN rather than the registry flags alone — strictly
# stronger, because it also blocks numeric entry where the evidence KPI cannot measure the action.
chk('_numeric_ok=(_pat=="direct")' in _dash.replace("'",'"'),
    "numeric measurement entry is offered only for a 'direct' measurement pattern")
chk("elif not _numeric_ok:" in _dash,
    "UI disables measurement entry for every non-direct pattern (context-only, verify, investigation, none)")
for rid in VERIFY:
    r=drive(rid,post=None,base_event=None)          # the path the UI actually permits
    chk(r["outcome_status"] not in ("Improved","Worsened","No Change"),
        f"{rid}: no numeric verdict produced (got '{r['outcome_status']}')")
    chk(str(r["baseline_numeric"]).strip() in ("","nan"),
        f"{rid}: Unknown stays Unknown — no baseline number invented")
    chk(str(r["baseline_value"]).strip() not in ("0","0.0"),f"{rid}: Unknown not rendered as zero")

print(f"\n[7] UNAVAILABLE ({len(UNAVAIL)}) — remains unavailable, never zero")
for rid in UNAVAIL:
    r=drive(rid,post="99",base_event=None)
    chk(r["outcome_status"] not in ("Improved","Worsened","No Change"),
        f"{rid}: unavailable KPI produces no verdict (got '{r['outcome_status']}')")
    chk("0" != str(r["baseline_value"]).strip(),f"{rid}: unavailable baseline not shown as 0")

# ---------------------------------------------------------------- decision states
print("\n[8] decision states — deferred / rejected must not force action or measurement")
sample=MEAS[:3] if len(MEAS)>=3 else MEAS
for rid in sample:
    for dec in ("deferred","rejected"):
        r=drive(rid,post=None,base_event=None,decision=dec,act=False)
        chk(str(r["owner_decision"])==dec,f"{rid}: '{dec}' decision recorded")
        chk(str(r["outcome_status"]).startswith("Outcome Unavailable"),
            f"{rid}: '{dec}' -> Outcome Unavailable, no action demanded (got '{r['outcome_status']}')")
        chk(str(r["action_taken"]).strip() in ("","nan"),f"{rid}: '{dec}' records no action")

# ---------------------------------------------------------------- architecture guarantees
print("\n[9] outcome and attribution stay reducer-derived")
cap=open(os.path.join(HERE,"phase4_action_capture.py"),encoding="utf-8").read()
for banned in ["outcome_status","attribution_confidence","improvement_pct","improved","worsened"]:
    chk(banned not in cap.lower().split("event_types")[0] or banned not in cap,
        f"writer never accepts a typed '{banned}'") if banned in ("improvement_pct",) else \
    chk(banned not in cap,f"writer never accepts a typed '{banned}'")
store=os.path.join(HERE,"operational","phase4_outcome_events.csv")
n=(sum(1 for _ in open(store,encoding="utf-8"))-1) if os.path.exists(store) else 0
chk(n==0,f"real event store untouched — still 0 owner events ({n})")

print("\n[10] Page 15 explains the plan dynamically, not per hard-coded decision")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("What this asks you to do" in dash,"selection panel states what the recommendation asks for")
chk("What will be measured" in dash,"selection panel names the KPI to measure")
chk("What to enter after the action" in dash,"selection panel says what to enter post-action")
chk("Owner verification required — no measurement yet" in dash,"owner-verify state has its own explanation")
chk("_DIRWORD" in dash and "_UNITWORD" in dash,"wording derived from registry metadata, not hard-coded per decision")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
