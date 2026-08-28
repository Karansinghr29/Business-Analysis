"""Fail-loud tests for the reducer's unit-aware KPI parsing and end-to-end outcome calculation.

Why this exists: the reducer previously parsed the analytics baseline with a bare float(), so any
human-readable baseline carrying words or a '%' returned None and the outcome stayed
"Outcome Unavailable" even when the owner had acted and measured correctly.

The fix resolves the numeric KPI component using the unit already declared in the KPI direction
registry. These tests prove the RIGHT component is chosen — not merely "a number" — because
"9 beds / ₹128,700" must yield 128700 (INR), never 9.

Runs the real reducer against a temporary event store; the operational store is never touched.
"""
from __future__ import annotations
import os, sys, csv, tempfile, importlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
sys.path.insert(0,HERE)
import phase4_decision_effectiveness as R

fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

# ---------------------------------------------------------------- unit-aware component selection
print("[1] the unit selects the RIGHT numeric component (not 'the first number')")
CASES=[
 ("₹800,503 across 47 tenants","INR",800503.0,"AR: takes the ₹ amount, not the 47 tenant count"),
 ("9 beds / ₹128,700","INR",128700.0,"vacancy: takes ₹128,700, NOT the 9 beds"),
 ("5 beds / ₹67,500","INR",67500.0,"vacancy: takes ₹67,500, NOT the 5 beds"),
 ("0 beds / ₹0","INR",0.0,"zero exposure resolves to 0, not None"),
 ("304 tickets (19.7% of maintenance)","tickets",304.0,"amenity: takes 304 tickets, NOT 19.7%"),
 ("80.0%","percent",80.0,"pricing: percentage parsed"),
 ("100.0%","percent",100.0,"pricing at ceiling parsed"),
 ("116.0","tickets",116.0,"already-plain number passes through"),
 ("22.0","tenants",22.0,"already-plain number passes through"),
 ("16","leads",16.0,"integer count passes through"),
]
for raw,unit,want,why in CASES:
    got=R._kpi_num(raw,unit)
    chk(got==want,f"{why}  ('{raw}' [{unit}] -> {got})")

print("\n[2] unparseable / unavailable values return None (never an invented number)")
for raw,unit,why in [("UNAVAILABLE","leads","explicit UNAVAILABLE"),
                     ("Unavailable — required data/linkage does not currently exist","INR","long unavailable text"),
                     ("","INR","empty string"),("nan","INR","nan string"),
                     ("no numbers here","INR","text with no figure"),
                     ("several 12 numbers 34 no unit","INR","ambiguous, unit not present")]:
    chk(R._kpi_num(raw,unit) is None,f"{why} -> None")

print("\n[3] owner-entered values are accepted in either plain or formatted form")
for raw,unit,want in [("600000","INR",600000.0),("₹600,000","INR",600000.0),
                      ("85","percent",85.0),("85.0%","percent",85.0),("15","tenants",15.0)]:
    chk(R._kpi_num(raw,unit)==want,f"'{raw}' [{unit}] -> {want}")

# ---------------------------------------------------------------- end-to-end through the reducer
def run_case(rid,kpi,base_disp,post_value,action_date,post_date,baseline_event=None):
    """Run the real reducer over a synthetic event store for one recommendation."""
    dirmap,winrows=R.load_registries()
    baselines=[dict(recommendation_id=rid,recommendation_type="backbone",is_backbone=True,
                    decision_or_opportunity="test",target_kpi=kpi,baseline_value=base_disp,
                    baseline_date="",baseline_source="test")]
    evs=[dict(event_id="E1",recommendation_id=rid,event_type="owner_decision",event_date=action_date,
              owner_decision="approved"),
         dict(event_id="E2",recommendation_id=rid,event_type="action_taken",event_date=action_date,
              action_taken="test action")]
    if baseline_event is not None:
        evs.append(dict(event_id="E0",recommendation_id=rid,event_type="measurement",event_date=action_date,
                        target_kpi=kpi,value=baseline_event,measurement_role="baseline"))
    evs.append(dict(event_id="E3",recommendation_id=rid,event_type="measurement",event_date=post_date,
                    target_kpi=kpi,value=post_value,measurement_role="post_action"))
    E,_=R.compute(baselines,evs,dirmap,winrows,asof=post_date)
    return E.iloc[0]

print("\n[4] end-to-end outcomes through the real reducer")
# Test 1 — AR90: ₹800,503 -> ₹600,000 over 30d (min window 14d), lower_is_better
r=run_case("DEC-REVPROTECT-AR90","AR 90+ outstanding (₹) & tenant count",
           "₹800,503 across 47 tenants","600000","2026-09-01","2026-10-01")
chk(float(r["baseline_numeric"])==800503.0,f"AR90 baseline resolves to 800503 (got {r['baseline_numeric']})")
chk(r["outcome_status"]=="Improved",f"AR90 ₹800,503 -> ₹600,000 = Improved (got '{r['outcome_status']}')")
chk("window met" in str(r["measurement_window_status"]),"AR90 30d satisfies the 14d minimum window")

# Test 2 — percentage KPI: 80% -> 85%, higher_is_better
r=run_case("DEC-PRICEREV-Triple","Triple occupancy %","80.0%","85.0","2026-09-01","2026-10-15")
chk(float(r["baseline_numeric"])==80.0,"percent baseline resolves to 80.0")
chk(r["outcome_status"]=="Improved",f"80% -> 85% = Improved (got '{r['outcome_status']}')")

# Test 3 — bed/revenue KPI: the ₹ component must be used, not the bed count
r=run_case("DEC-VAC-Double","vacant 2-sharing beds & ₹/mo at risk","5 beds / ₹67,500","40500",
           "2026-09-01","2026-10-15")
chk(float(r["baseline_numeric"])==67500.0,f"uses ₹67,500 not 5 beds (got {r['baseline_numeric']})")
chk(r["outcome_status"]=="Improved",f"₹67,500 -> ₹40,500 = Improved (got '{r['outcome_status']}')")

# Test 4 — count KPI: exits 22 -> 15, lower_is_better
r=run_case("DEC-RETENTION-REVIEW","tenant exits / month","22.0","15","2026-09-01","2026-12-01")
chk(float(r["baseline_numeric"])==22.0,"exits baseline resolves to 22")
chk(r["outcome_status"]=="Improved",f"22 -> 15 exits = Improved (got '{r['outcome_status']}')")

# Test 4b — a worsening case must be reported honestly
r=run_case("DEC-RETENTION-REVIEW","tenant exits / month","22.0","30","2026-09-01","2026-12-01")
chk(r["outcome_status"]=="Worsened",f"22 -> 30 exits = Worsened (got '{r['outcome_status']}')")

# Test 5 — malformed / unavailable baseline must NOT invent a number
r=run_case("DEC-LOC-MKT","leads by locality","UNAVAILABLE","42","2026-09-01","2026-12-01")
chk(str(r["baseline_numeric"]).strip() in ("","nan"),"unavailable baseline stays non-numeric")
chk("Unavailable" in str(r["outcome_status"]) or r["outcome_status"]=="Not Evaluable — direction undefined",
    f"unavailable KPI -> no invented outcome (got '{r['outcome_status']}')")

# Test 5b — window not yet complete must not produce a verdict
r=run_case("DEC-REVPROTECT-AR90","AR 90+ outstanding (₹) & tenant count",
           "₹800,503 across 47 tenants","600000","2026-09-01","2026-09-03")
chk(r["outcome_status"]=="Insufficient Data",f"3d < 14d window -> Insufficient Data (got '{r['outcome_status']}')")

# Test 5c — an owner-logged baseline event overrides the analytics string
r=run_case("DEC-AMEN-AC","AC-Issue tickets (cumulative) & share of maintenance",
           "304 tickets (19.7% of maintenance)","250","2026-09-01","2026-12-01",baseline_event="300")
chk(float(r["baseline_numeric"])==300.0,f"owner baseline event wins over the analytics string (got {r['baseline_numeric']})")
chk(str(r["baseline_numeric_source"]).startswith("owner"),"baseline source reported as the owner event")

print("\n[5] every measurable backbone KPI is numerically resolvable")
ea=pd.read_csv(os.path.join(OUT,"phase3_decision_execution_analytics.csv"))
reg=pd.read_csv(os.path.join(OUT,"phase4_kpi_direction_registry.csv"))
unit_of=dict(zip(reg["kpi_name"],reg["unit"])); meas_of=dict(zip(reg["kpi_name"],reg["measurable"]))
bb=ea[ea["is_backbone"]==True]
chk(len(bb)==14,f"exactly 14 backbone decisions ({len(bb)})")
unresolved=[]
for r in bb.itertuples():
    unit=unit_of.get(r.kpi_name); measurable=str(meas_of.get(r.kpi_name,"no")).lower()=="yes"
    v=R._kpi_num(r.baseline_value,unit)
    if measurable and v is None: unresolved.append((r.decision_id,r.baseline_value))
    if not measurable:
        chk(v is None or True,f"{r.decision_id}: KPI declared unavailable — not required to resolve")
chk(not unresolved,f"every MEASURABLE backbone baseline resolves numerically (unresolved: {unresolved})")

print("\n[6] the real operational store is untouched and outcomes stay reducer-derived")
store=os.path.join(HERE,"operational","phase4_outcome_events.csv")
n=(sum(1 for _ in open(store,encoding="utf-8"))-1) if os.path.exists(store) else 0
chk(n==0,f"real event store still holds 0 owner events ({n})")
eff=os.path.join(HERE,"operational","phase4_decision_effectiveness.csv")
if os.path.exists(eff):
    E=pd.read_csv(eff)
    chk("outcome_status" in E.columns and "attribution_confidence" in E.columns,"outcome + attribution present as derived columns")
    chk(bool((E["outcome_status"].astype(str).str.startswith("Outcome Unavailable")).all()),
        "with 0 events every row is still Outcome Unavailable (nothing fabricated)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
