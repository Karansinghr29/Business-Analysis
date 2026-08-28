"""
Fail-loud validation for the Before / After / Outcome / AI layer.

Guards: baseline immutability, AFTER measured from live data, deterministic outcome classification
reusing the existing registries, AI grounded in measured facts only, no fabricated ROI/causal claims,
no parallel decision system, and no fabricated owner action.
"""
from __future__ import annotations
import os, sys, csv, shutil, tempfile
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs"); OPDIR = os.path.join(HERE, "operational")
sys.path.insert(0, HERE)
import phase4_kpi_measure as KM
import phase4_outcome_ai as OAI
import phase4_action_capture as CAP
import phase4_decision_effectiveness as RED

fails = []
def chk(c, m):
    print(("  PASS " if c else "  FAIL ") + m)
    if not c: fails.append(m)
def o(f): return pd.read_csv(os.path.join(OUT, f), low_memory=False)

print("[1] reuses the existing architecture — no parallel decision system")
chk(KM.RED is RED, "measure layer imports the existing reducer rather than re-implementing it")
for fn in ("_num", "_days", "domain_min_window", "load_registries", "load_baselines"):
    chk(hasattr(RED, fn), f"reducer helper reused: {fn}")
src = open(os.path.join(HERE, "phase4_kpi_measure.py"), encoding="utf-8").read()
chk("RED.load_registries()" in src, "KPI direction/tolerance come from the existing registry")
chk("RED.domain_min_window" in src, "measurement windows come from the existing registry")
chk(len(o("phase3_business_decisions.csv")) == 14, "14 backbone decisions unchanged")
dr = o("phase3_decision_reconciliation.csv")
chk(int((dr["reconciliation_status"] == "NEW").sum()) == 6, "6 Phase-3 opportunities unchanged")
chk(len(o("phase4_ai_opportunities.csv")) == 13, "13 AIREC unchanged")
chk(CAP.STORE.endswith("phase4_outcome_events.csv"), "the existing append-only event store is reused")

print("\n[2] no fabricated owner action exists")
store = CAP.STORE
n = (sum(1 for _ in open(store, encoding="utf-8")) - 1) if os.path.exists(store) else 0
chk(n == 0, f"real event store holds no fabricated action ({n} events)")
ba_p = os.path.join(OPDIR, "phase4_before_after.csv")
if os.path.exists(ba_p):
    chk(len(pd.read_csv(ba_p)) == 0, "before/after store is empty while no action exists")

print("\n[3] AFTER is measured from live data, never hard-coded")
chk("SOURCE_MODE" in src and "def measure(" in src, "a swappable source mode and measure() exist")
chk("reader=None" in src, "measure() accepts an injected reader so the source can be swapped")
measurable = 0
for rid in ["DEC-REVPROTECT-AR90", "DEC-VAC-Triple", "DEC-PRICEREV-Triple", "DEC-EB-INVESTIGATE"]:
    r = KM.measure(rid)
    chk(r["available"] and r["value"] is not None, f"{rid}: current value measured ({r.get('value')})")
    measurable += 1 if r["available"] else 0
chk(measurable == 4, "all four spot-checked KPIs resolve to a real current value")
un = KM.measure("DEC-MKT-ROI-GAP")
chk(not un["available"] and un["value"] is None and un["reason"],
    "an unmeasurable KPI reports unavailable with a reason, never a fabricated number")

print("\n[4] end-to-end on an ISOLATED store: action -> frozen baseline -> after -> outcome")
real_before = open(store, encoding="utf-8").read() if os.path.exists(store) else None
tmp = tempfile.mkdtemp(); TS = os.path.join(tmp, "t.csv"); CAP.ensure_store(TS)
RID = "DEC-REVPROTECT-AR90"
pre = KM.measure(RID)
CAP.append_event(dict(recommendation_id=RID, event_type="owner_decision",
                      event_date="2026-06-01", owner_decision="approved"), store=TS)
CAP.append_event(dict(recommendation_id=RID, event_type="action_taken", event_date="2026-06-01",
                      action_taken="test action"), store=TS)
CAP.append_event(dict(recommendation_id=RID, event_type="measurement", event_date="2026-06-01",
                      target_kpi="AR 90+ outstanding (₹) & tenant count", unit="INR",
                      value=str(pre["value"]), measurement_role="baseline",
                      source="system_measured", confidence="High"), store=TS)
ba = KM.build(events_store=TS, ba_store=os.path.join(tmp,"ba1.csv"), summary_store=os.path.join(tmp,"s1.csv"))
chk(len(ba) == 1, "exactly one executed action produces exactly one Before/After row")
r0 = ba.iloc[0]
chk(abs(float(r0["before_value"]) - pre["value"]) < 1e-6, "BEFORE equals the value measured at action time")
chk(str(r0["before_source"]).startswith("frozen"), "BEFORE is sourced from the frozen baseline event")

print("\n[5] BASELINE IMMUTABILITY under data movement")
def moved(name):
    d = KM._csv_reader(name)
    if name == "phase3_ar_recovery_queue.csv" and d is not None:
        d = d.copy(); d["ar_90_plus"] = d["ar_90_plus"] * 0.5
    return d
ba2 = KM.build(reader=moved, events_store=TS, ba_store=os.path.join(tmp,"ba2.csv"), summary_store=os.path.join(tmp,"s2.csv")); r1 = ba2.iloc[0]
chk(float(r1["before_value"]) == float(r0["before_value"]), "BEFORE unchanged after the data moved")
chk(float(r1["after_value"]) < float(r0["after_value"]), "AFTER moved with the data")
chk(float(r1["change"]) < 0, "change recomputed from the moved data")
chk(str(r1["outcome"]) == "Positive", "lower_is_better KPI falling classifies as Positive")

print("\n[6] outcome classification is direction-aware and deterministic")
def moved_up(name):
    d = KM._csv_reader(name)
    if name == "phase3_ar_recovery_queue.csv" and d is not None:
        d = d.copy(); d["ar_90_plus"] = d["ar_90_plus"] * 1.5
    return d
r2 = KM.build(reader=moved_up, events_store=TS, ba_store=os.path.join(tmp,"ba3.csv"), summary_store=os.path.join(tmp,"s3.csv")).iloc[0]
chk(str(r2["outcome"]) == "Negative", "the same KPI rising classifies as Negative (not assumed good)")
r3 = KM.build(events_store=TS, ba_store=os.path.join(tmp,"ba4.csv"), summary_store=os.path.join(tmp,"s4.csv")).iloc[0]
chk(str(r3["outcome"]) == "No measurable change", "unchanged data within tolerance = No measurable change")
chk(KM.build(events_store=TS, ba_store=os.path.join(tmp,"ba5.csv"), summary_store=os.path.join(tmp,"s5.csv")).iloc[0]["outcome"] == r3["outcome"], "classification is repeatable")

print("\n[7] insufficient data is reported, never invented")
TS2 = os.path.join(tmp, "t2.csv"); CAP.ensure_store(TS2)
CAP.append_event(dict(recommendation_id="DEC-MKT-ROI-GAP", event_type="owner_decision",
                      event_date="2026-06-01", owner_decision="approved"), store=TS2)
CAP.append_event(dict(recommendation_id="DEC-MKT-ROI-GAP", event_type="action_taken",
                      event_date="2026-06-01", action_taken="test"), store=TS2)
b2 = KM.build(events_store=TS2, ba_store=os.path.join(tmp,"ba6.csv"), summary_store=os.path.join(tmp,"s6.csv"))
# Two distinct honest answers, and the precedence matters:
#   registry says measurable=no          -> "Outcome Unavailable"        (structural, never measurable)
#   measurable but no post-action data   -> "Insufficient post-action data"
chk(len(b2) == 1 and str(b2.iloc[0]["outcome"]) in
    ("Outcome Unavailable", "Insufficient post-action data"),
    f"KPI with no measurable source -> {b2.iloc[0]['outcome']!r} (never a fabricated result)")
chk(pd.isna(b2.iloc[0]["after_value"]), "no after value is invented when none can be measured")
# a MEASURABLE KPI whose current value cannot be read must say "Insufficient post-action data"
TS3 = os.path.join(tmp, "t3.csv"); CAP.ensure_store(TS3)
CAP.append_event(dict(recommendation_id="DEC-VAC-Triple", event_type="action_taken",
                      event_date="2026-06-01", action_taken="test"), store=TS3)
CAP.append_event(dict(recommendation_id="DEC-VAC-Triple", event_type="measurement",
                      event_date="2026-06-01", target_kpi="vacant 3-sharing beds & ₹/mo at risk",
                      unit="INR", value="128700", measurement_role="baseline",
                      source="system_measured", confidence="High"), store=TS3)
b3 = KM.build(reader=lambda n: None, events_store=TS3, ba_store=os.path.join(tmp,"ba7.csv"), summary_store=os.path.join(tmp,"s7.csv"))
chk(str(b3.iloc[0]["outcome"]) == "Insufficient post-action data",
    f"measurable KPI with unreadable current data -> {b3.iloc[0]['outcome']!r}")
chk(float(b3.iloc[0]["before_value"]) == 128700.0, "its frozen BEFORE survives even when AFTER cannot be read")

print("\n[7b] every registered measurer reproduces its own baseline quantity and unit")
_reg = o("phase4_kpi_direction_registry.csv")[["kpi_name", "unit"]]
_dea = o("phase3_decision_execution_analytics.csv")[["decision_id", "kpi_name", "baseline_value"]]
_m = _dea.merge(_reg, on="kpi_name", how="left")
_bad = 0
for _, x in _m.iterrows():
    if x["decision_id"] not in KM.MEASURERS: continue
    rn = RED._kpi_num(x["baseline_value"], str(x["unit"])); mv = KM.measure(x["decision_id"])["value"]
    if rn is None or mv is None: continue
    ok = abs(rn - mv) <= max(1.0, abs(rn) * 0.001)
    if not ok: _bad += 1
    chk(ok, f"{x['decision_id']}: measured {mv} matches its baseline {rn} in unit {x['unit']}")
chk(_bad == 0, "no registered measurer measures a different quantity than its KPI baseline")

print("\n[8] AI receives measured facts only, and fabrication is blocked")
f = OAI._facts(r1)
ALLOWED = {"decision","action_taken","action_date","kpi","kpi_direction","before_value","before_date",
           "after_value","after_date","change","change_pct","days_since_action","min_window_days",
           "window_complete","outcome","outcome_basis","data_confidence","known_limitation"}
chk(set(f) == ALLOWED, "the fact payload is exactly the measured facts — no raw data reaches the model")
for lbl, bad in [("ROI", "The action delivered an ROI of 3.2x."),
                 ("revenue uplift", "This produced a revenue uplift."),
                 ("conversion", "The conversion rate improved."),
                 ("causal", "The collections drive caused the outstanding to fall."),
                 ("causal-2", "The fall resulted in better cash."),
                 ("customer motive", "Customers preferred the new follow-up."),
                 ("ungrounded number", "Outstanding fell to 123456 after the action.")]:
    chk(bool(OAI._violations(bad, f)), f"blocked: {lbl}")
det = OAI.deterministic_analysis(f, "INR")
chk(not OAI._violations(det, f), "the deterministic fallback passes its own guard")
for phrase in ["1.", "2.", "3.", "4.", "5."]:
    chk(phrase in det, f"analysis contains section {phrase}")
chk("not proof that the action produced it" in det, "the analysis states movement is not proof of causation")
a = OAI.analyse(r1, unit="INR", use_ai=True)
chk(not OAI._violations(a["analysis"], f), "the displayed analysis passes the guard whatever its source")
chk(a["outcome"] == str(r1["outcome"]), "the AI does not change the deterministic outcome")

print("\n[9] timeline")
marks, days = KM.timeline("2026-06-01", "2026-08")
chk([m["mark"] for m in marks] == ["Day 1", "Day 7", "Day 14", "Day 30"], "Day 1/7/14/30 checkpoints")
chk(all(m["reached"] for m in marks) and days == 61, f"checkpoints reached for a {days}-day gap")
m2, d2 = KM.timeline("2026-08-01", "2026-08")
chk(not any(m["reached"] for m in m2), "future/short gaps report checkpoints as not reached")

print("\n[10] cleanup — the real store is untouched")
shutil.rmtree(tmp, ignore_errors=True)
KM.build()   # restore the real (empty) before/after store
real_after = open(store, encoding="utf-8").read() if os.path.exists(store) else None
chk(real_before == real_after, "real event store byte-identical after all tests")
n2 = (sum(1 for _ in open(store, encoding="utf-8")) - 1) if os.path.exists(store) else 0
chk(n2 == 0, f"no test event leaked into the real store ({n2} events)")
chk(len(pd.read_csv(ba_p)) == 0, "before/after store restored to empty")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails:
    for x in fails: print("   -", x)
    sys.exit(1)
