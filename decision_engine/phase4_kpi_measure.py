"""
KPI MEASUREMENT PROVIDER — the single place that answers "what is this decision's KPI worth RIGHT NOW?"

This is the layer that makes Before/After automatic. It does NOT re-implement outcome logic: direction,
tolerance and measurement windows all come from the existing registries, and the numeric parsing and
window helpers are imported from phase4_decision_effectiveness so there is exactly one definition of
each rule. No parallel decision system is created and the 14 backbone decisions are untouched.

SOURCE SWAP (CSV today -> Supabase later)
    Every KPI is measured by a small function that takes a `read` callable and returns a value.
    `read(name)` resolves a dataset by logical name. Today `_csv_reader` reads decision_engine/outputs.
    To move to a live database, implement a reader with the same signature and set SOURCE_MODE, or pass
    `reader=` into measure(). No measurement function, registry, event or dashboard code changes.

IMMUTABILITY
    This module only ever REPORTS the current value. The frozen "Before" baseline lives in the
    append-only event store as a `measurement`/`baseline` event written once when the owner records the
    action. Later data movement changes the AFTER value and can never change that stored BEFORE.

Writes ONLY operational/phase4_before_after.csv (+ _summary.csv). Never touches outputs/ or locked files.
"""
from __future__ import annotations
import os, sys, math
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

import phase4_decision_effectiveness as RED   # reuse: numeric parsing, windows, registries

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
OPDIR = os.path.join(HERE, "operational")
BA_STORE = os.path.join(OPDIR, "phase4_before_after.csv")

SOURCE_MODE = "csv_outputs"     # future: "supabase"


# ---------------------------------------------------------------- data readers
def _csv_reader(name: str):
    """Resolve a logical dataset name to a DataFrame from the validated outputs."""
    p = os.path.join(OUT, name)
    return pd.read_csv(p, low_memory=False) if os.path.exists(p) else None


def _as_of_csv():
    """The as-of date of the CSV snapshot — the engine's fixed reporting date."""
    try:
        return str(pd.read_csv(os.path.join(OUT, "phase2_revenue_backtest.csv"))["month"].max())
    except Exception:
        return "unknown"


# ---------------------------------------------------------------- KPI measurement functions
# Each returns (value, detail) or (None, reason). Value is the SAME quantity the baseline states,
# in the unit the KPI direction registry declares, so Before and After are always comparable.
def _m_ar90(read):
    d = read("phase3_ar_recovery_queue.csv")
    if d is None or "ar_90_plus" not in d.columns: return None, "ar recovery queue unavailable"
    return float(d["ar_90_plus"].sum()), f"{len(d)} accounts in the 90+ bucket"


def _m_vacancy(read, bed_type):
    # The KPI direction registry declares this KPI's unit as INR, and the baseline states
    # "N beds / ₹X". The comparable quantity is therefore the RUPEE at-risk figure, not the bed
    # count — measuring beds here would compare a count against a rupee baseline.
    d = read("step4_vacancy_at_risk.csv")
    if d is None: return None, "vacancy output unavailable"
    s = d[d["bed_type"] == bed_type]
    return float(s["rev_at_risk_monthly"].sum()), f"{len(s)} vacant {bed_type} bed(s)"


def _m_occupancy(read, bed_type):
    d = read("step5_pricing_analysis.csv")
    if d is None: return None, "pricing analysis unavailable"
    s = d[d["bed_type"] == bed_type]
    tot = float(s["total_beds"].sum())
    if tot <= 0: return None, f"no {bed_type} inventory"
    occ = float(s["occupied_beds"].sum())
    return round(100 * occ / tot, 1), f"{int(occ)} of {int(tot)} beds occupied"


def _m_maint_hotspots(read):
    d = read("phase2_maintenance_repeat_register.csv")
    if d is None: return None, "maintenance register unavailable"
    if "priority" in d.columns and "date_confidence" in d.columns:
        s = d[(d["priority"] == "High") & (d["date_confidence"] == "high")]
        return float(len(s)), "high-confidence High-priority recurring hotspots"
    return float(len(d)), "maintenance register rows"


def _m_eb_flagged(read):
    # Baseline definition: DISTINCT apartments flagged high_consumption in phase2_eb_anomalies.
    d = read("phase2_eb_anomalies.csv")
    if d is None or "anomaly_type" not in d.columns: return None, "EB anomaly output unavailable"
    hi = d[d["anomaly_type"] == "high_consumption"]
    return float(hi["apartment_id"].nunique()), "distinct apartments flagged high_consumption"


def _m_churn_high(read):
    d = read("phase2_churn_risk_scored.csv")
    if d is None or "risk_band" not in d.columns: return None, "churn output unavailable"
    return float((d["risk_band"] == "High").sum()), "tenants in the High churn-risk band"


def _m_open_leads(read):
    d = read("phase3_lead_followup.csv")
    if d is None: return None, "lead follow-up output unavailable"
    return float((d["lead_status"] == "in_progress").sum()), "leads in in_progress"


def _m_double_leads(read):
    d = read("phase3_lead_followup.csv")
    if d is None: return None, "lead follow-up output unavailable"
    return float((d.get("requested_bed_type") == "Double").sum()), "open Double-sharing leads"


def _m_ac_tickets(read):
    d = read("phase3_inventory_amenity_matrix.csv")
    return None, "AC-issue ticket count is not exposed as a standalone current-value output"


# decision_id -> (measure fn, what the number means). Only decisions whose KPI can be measured from
# real data appear here; everything else honestly reports "no current-value source".
MEASURERS = {
    "DEC-REVPROTECT-AR90":  (_m_ar90, "aged 90+ AR outstanding (₹)"),
    "DEC-VAC-Triple":       (lambda r: _m_vacancy(r, "Triple"), "vacant 3-sharing beds"),
    "DEC-VAC-Double":       (lambda r: _m_vacancy(r, "Double"), "vacant 2-sharing beds"),
    "DEC-VAC-Single":       (lambda r: _m_vacancy(r, "Single"), "vacant single beds"),
    "DEC-PRICEREV-Triple":  (lambda r: _m_occupancy(r, "Triple"), "Triple occupancy %"),
    "DEC-PRICEREV-Single":  (lambda r: _m_occupancy(r, "Single"), "Single occupancy %"),
    "DEC-EB-INVESTIGATE":   (_m_eb_flagged, "apartments flagged high-consumption"),
    "DEC-LEAD-FOLLOWUP":    (_m_open_leads, "open leads (in_progress)"),
    "DEC-LEAD-DEMAND-2SH":  (_m_double_leads, "open Double-sharing leads"),
    "DEC-AMEN-AC":          (_m_ac_tickets, "AC-issue tickets"),
    # Deliberately NOT registered — the KPI cannot be reproduced from outputs alone, and measuring a
    # different quantity than the baseline would make Before/After meaningless:
    #   DEC-MAINT-PRIORITISE  tickets/month  -> needs raw maintenance_tickets + rolling 3-month window
    #   DEC-RETENTION-REVIEW  exits/month    -> needs raw tenant_exits + rolling 3-month window
    #   AIREC-MAINT-HOTSPOT   repeat-ticket rate on hotspot apartments
    #   AIREC-CHURN-WATCH     retained tenants / exits
    # They report "no current-value source" until the measurement can be defined exactly.
    "AIREC-AR-PRIORITY":    (_m_ar90, "aged 90+ AR outstanding (₹)"),
    "AIREC-VAC-DBL":        (lambda r: _m_vacancy(r, "Double"), "vacant 2-sharing beds"),
    "AIREC-VAC-RISK":       (lambda r: _m_vacancy(r, "Triple"), "vacant 3-sharing beds"),
    "AIREC-EB-INVESTIGATE": (_m_eb_flagged, "apartments flagged high-consumption"),
}


def measure(recommendation_id: str, reader=None) -> dict:
    """Current real-data value for a decision's KPI. Never fabricates: unmeasurable -> available=False."""
    read = reader or _csv_reader
    ent = MEASURERS.get(str(recommendation_id))
    if ent is None:
        return dict(recommendation_id=recommendation_id, available=False, value=None,
                    as_of=_as_of_csv(), source=SOURCE_MODE, detail=None,
                    reason="no current-value source is defined for this decision's KPI")
    fn, means = ent
    try:
        val, detail = fn(read)
    except Exception as e:
        return dict(recommendation_id=recommendation_id, available=False, value=None,
                    as_of=_as_of_csv(), source=SOURCE_MODE, detail=None,
                    reason=f"measurement failed: {type(e).__name__}")
    if val is None:
        return dict(recommendation_id=recommendation_id, available=False, value=None,
                    as_of=_as_of_csv(), source=SOURCE_MODE, detail=None, reason=detail)
    return dict(recommendation_id=recommendation_id, available=True, value=float(val),
                as_of=_as_of_csv(), source=SOURCE_MODE, detail=detail, means=means, reason=None)


# ---------------------------------------------------------------- before / after / outcome
def _events(store=None):
    p = store or os.path.join(OPDIR, "phase4_outcome_events.csv")
    if not os.path.exists(p): return []
    d = pd.read_csv(p, dtype=str).fillna("")
    return d.to_dict("records")


def _latest(evs, etype, role=None):
    """Latest live event of a type, honouring supersedes (same rule the reducer applies)."""
    superseded = {str(e.get("supersedes_event_id")) for e in evs if str(e.get("supersedes_event_id"))}
    c = [e for e in evs if str(e.get("event_type")) == etype
         and str(e.get("event_id")) not in superseded
         and (role is None or str(e.get("measurement_role")) == role)]
    return sorted(c, key=lambda e: (str(e.get("event_date")), str(e.get("event_id"))))[-1] if c else None


def build(reader=None, events_store=None, ba_store=None, summary_store=None):
    """One row per EXECUTED action. Recommendations with no action are not invented into rows."""
    dirmap, winrows = RED.load_registries()
    baselines = {b["recommendation_id"]: b for b in RED.load_baselines()}
    evs_all = _events(events_store)
    by_rec = {}
    for e in evs_all:
        by_rec.setdefault(str(e.get("recommendation_id")), []).append(e)

    rows = []
    for rid, evs in by_rec.items():
        act = _latest(evs, "action_taken")
        if not act:
            continue                      # only executed actions produce a Before/After row
        b = baselines.get(rid, {})
        kpi = b.get("target_kpi", "")
        reg = dirmap.get(kpi, {})
        direction = reg.get("direction", "context_only")
        unit = str(reg.get("unit", ""))
        tol = float(reg.get("tol", 0.0))
        measurable = str(reg.get("measurable", "no")).lower()
        dom, minw = RED.domain_min_window(rid, winrows)

        # ---- BEFORE: the frozen baseline event written when the action was recorded ----
        be = _latest(evs, "measurement", "baseline")
        before = RED._num(be.get("value")) if be else None
        before_date = be.get("event_date") if be else ""
        before_src = "frozen baseline event (captured at action time)" if be else "no frozen baseline"

        # ---- AFTER: measured live from current data ----
        cur = measure(rid, reader=reader)
        after = cur["value"] if cur["available"] else None
        after_date = cur["as_of"]

        days = RED._days(act.get("event_date", ""), after_date)
        change = pct = None
        if before is not None and after is not None:
            change = after - before
            if before != 0:
                pct = round(100 * change / abs(before), 1)

        # ---- OUTCOME: same precedence and rules the reducer uses; nothing re-invented ----
        if direction == "context_only":
            outcome = "Not Evaluable — direction undefined"
            note = "KPI direction is context_only; movement is not good or bad by itself"
        elif measurable == "no":
            outcome = "Outcome Unavailable"; note = RED.UNAVAIL
        elif before is None:
            outcome = "Insufficient post-action data"; note = "no frozen baseline captured at action time"
        elif after is None:
            outcome = "Insufficient post-action data"; note = cur.get("reason") or "no current value available"
        elif minw is not None and days is not None and days < minw:
            outcome = "Insufficient post-action data"
            note = f"measurement window not complete ({days}d elapsed, {minw}d minimum)"
        elif abs(change) <= tol:
            outcome = "No measurable change"; note = f"movement within the declared tolerance ({tol})"
        elif direction == "lower_is_better":
            outcome = "Positive" if change < 0 else "Negative"; note = "lower is better for this KPI"
        else:
            outcome = "Positive" if change > 0 else "Negative"; note = "higher is better for this KPI"

        rows.append(dict(
            recommendation_id=rid,
            decision=b.get("decision_or_opportunity", ""),
            action_taken=act.get("action_taken", ""),
            action_date=act.get("event_date", ""),
            target_kpi=kpi, kpi_unit=unit, kpi_direction=direction,
            before_value=before, before_date=before_date, before_source=before_src,
            after_value=after, after_date=after_date,
            after_source=f"{cur['source']}:{cur.get('means') or 'n/a'}",
            after_detail=cur.get("detail"),
            change=change, change_pct=pct,
            days_since_action=days,
            measurement_domain=dom, min_window_days=minw,
            window_complete=(None if (days is None or minw is None) else bool(days >= minw)),
            outcome=outcome, outcome_basis=note,
            no_change_tolerance=tol,
            data_confidence=("measured from validated output" if after is not None else "unavailable"),
            limitation=b.get("baseline_source", ""),
        ))

    BA = pd.DataFrame(rows)
    # ba_store lets a test redirect the OUTPUT as well as the input, so a test run can never
    # leave a row behind in the real operational store.
    ba_path = ba_store or BA_STORE
    sum_path = summary_store or os.path.join(OPDIR, "phase4_before_after_summary.csv")
    os.makedirs(os.path.dirname(ba_path), exist_ok=True)
    COLS = ["recommendation_id", "decision", "action_taken", "action_date", "target_kpi", "kpi_unit",
            "kpi_direction", "before_value", "before_date", "before_source", "after_value", "after_date",
            "after_source", "after_detail", "change", "change_pct", "days_since_action",
            "measurement_domain", "min_window_days", "window_complete", "outcome", "outcome_basis",
            "no_change_tolerance", "data_confidence", "limitation"]
    (BA[COLS] if len(BA) else pd.DataFrame(columns=COLS)).to_csv(ba_path, index=False)

    c = BA["outcome"].value_counts().to_dict() if len(BA) else {}
    summary = [("executed_actions", len(BA)), ("source_mode", SOURCE_MODE), ("as_of", _as_of_csv()),
               ("positive", c.get("Positive", 0)), ("negative", c.get("Negative", 0)),
               ("no_measurable_change", c.get("No measurable change", 0)),
               ("insufficient_post_action_data", c.get("Insufficient post-action data", 0)),
               ("not_evaluable_context_only", c.get("Not Evaluable — direction undefined", 0)),
               ("outcome_unavailable", c.get("Outcome Unavailable", 0)),
               ("measurable_decisions_registered", len(MEASURERS)),
               ("baseline_rule", "frozen at action time in the append-only event store; later data "
                                 "movement changes AFTER only and can never alter BEFORE"),
               ("fabrication_policy", "no outcome is invented; missing post-action data reports "
                                      "'Insufficient post-action data'")]
    pd.DataFrame(summary, columns=["metric", "value"]).to_csv(sum_path, index=False)
    return BA


def timeline(action_date: str, after_date: str, marks=(1, 7, 14, 30)):
    """Day-1/7/14/30 checkpoints from the action date, flagged as reached or not yet."""
    days = RED._days(action_date, after_date)
    return [dict(mark=f"Day {m}", days=m, reached=(days is not None and days >= m)) for m in marks], days


def main():
    BA = build()
    print("PHASE-4 BEFORE / AFTER / OUTCOME:")
    s = pd.read_csv(os.path.join(OPDIR, "phase4_before_after_summary.csv"))
    for _, r in s.iterrows(): print(f"  {r['metric']}: {r['value']}")
    if len(BA):
        print()
        for _, r in BA.iterrows():
            print(f"  [{r['recommendation_id']}] {r['target_kpi']}")
            print(f"     before {r['before_value']} ({r['before_date']}) -> after {r['after_value']} "
                  f"({r['after_date']}) | change {r['change']} | {r['outcome']}")
    else:
        print("\n  No executed actions yet — nothing to measure. (Recommendations exist, but "
              "generation is not execution.)")


if __name__ == "__main__":
    main()
