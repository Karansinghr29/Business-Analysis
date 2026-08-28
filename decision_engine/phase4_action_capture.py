"""
Phase-2A Step-2 APPEND-ONLY owner outcome-event writer (operational/mutable — NOT a locked deterministic output).
Store lives OUTSIDE outputs/ (decision_engine/operational/phase4_outcome_events.csv) so run_all --verify never
treats it as a locked artifact. Every owner decision/action/measurement/correction/note is a NEW appended event;
existing events are NEVER edited or deleted. Corrections append a new event referencing supersedes_event_id.
Invalid events are REJECTED (ValueError) — never silently fixed. No existing/locked file is touched.
"""
from __future__ import annotations
import os, sys, csv
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
OPDIR=os.path.join(HERE,"operational"); STORE=os.path.join(OPDIR,"phase4_outcome_events.csv")

COLUMNS=["event_id","recommendation_id","recommendation_type","event_type","event_date","owner_decision",
 "action_taken","target_kpi","value","unit","measurement_role","source","confidence","supersedes_event_id",
 "notes","recorded_at","recorded_by"]
EVENT_TYPES={"owner_decision","action_taken","measurement","correction","note"}
OWNER_DECISIONS={"approved","rejected","deferred","pending"}
MEAS_ROLES={"baseline","post_action"}
REC_TYPES={"backbone","phase4_deterministic","phase2_ai"}
UNAVAIL="Unavailable — required data/linkage does not currently exist"

def _reg_kpi():
    r=pd.read_csv(os.path.join(OUT,"phase4_kpi_direction_registry.csv"))
    return dict(zip(r["kpi_name"],r["unit"]))

def _valid_rec_ids():
    ids=set()
    for f,col in [("phase3_business_decisions.csv","decision_id"),
                  ("phase3_decision_execution_analytics.csv","decision_id"),
                  ("phase4_ai_opportunities.csv","recommendation_id")]:
        p=os.path.join(OUT,f)
        if os.path.exists(p): ids|=set(pd.read_csv(p)[col].astype(str))
    return ids

def _rec_type(rid):
    if str(rid).startswith("AIREC-"): return "phase4_deterministic"
    if str(rid).startswith("AI-"):    return "phase2_ai"
    return "backbone"

def ensure_store(store=STORE):
    os.makedirs(os.path.dirname(store),exist_ok=True)
    if not os.path.exists(store):
        with open(store,"w",newline="",encoding="utf-8") as f: csv.writer(f).writerow(COLUMNS)
    return store

def _rows(store):
    if not os.path.exists(store): return []
    with open(store,newline="",encoding="utf-8") as f: return list(csv.DictReader(f))

def _next_id(store):
    rows=_rows(store); n=0
    for r in rows:
        try: n=max(n,int(str(r["event_id"]).split("-")[1]))
        except Exception: pass
    return f"EVT-{n+1:06d}"

def append_event(ev:dict, store=STORE, recorded_at=None, recorded_by="owner"):
    """Validate then append one event. Returns event_id. Raises ValueError on any invalid event (no silent fix)."""
    ensure_store(store)
    et=ev.get("event_type")
    if et not in EVENT_TYPES: raise ValueError(f"invalid event_type {et}")
    rid=str(ev.get("recommendation_id","")).strip()
    if not rid: raise ValueError("recommendation_id required")
    valid=_valid_rec_ids()
    if rid not in valid and not rid.startswith("AI-"):
        raise ValueError(f"unknown recommendation_id {rid} (not a backbone / AIREC-* / AI-* id)")
    rtype=ev.get("recommendation_type") or _rec_type(rid)
    if rtype not in REC_TYPES: raise ValueError(f"invalid recommendation_type {rtype}")
    if rtype!=_rec_type(rid): raise ValueError(f"recommendation_type {rtype} inconsistent with id {rid}")
    if not str(ev.get("event_date","")).strip(): raise ValueError("event_date required")
    kpi_units=_reg_kpi()
    tk=ev.get("target_kpi")
    if tk not in (None,"","nan"):
        if tk not in kpi_units: raise ValueError(f"target_kpi not in direction registry: {tk}")
        u=ev.get("unit")
        if u not in (None,"") and str(u)!=str(kpi_units[tk]):
            raise ValueError(f"unit '{u}' != registry unit '{kpi_units[tk]}' for KPI {tk}")
    val=ev.get("value")
    if val not in (None,"","nan"):
        try: float(val)
        except Exception: raise ValueError(f"value must be numeric or empty (got {val}); Unavailable stays empty, never 0")
    # per-type required fields
    if et=="owner_decision" and ev.get("owner_decision") not in OWNER_DECISIONS:
        raise ValueError(f"owner_decision must be one of {OWNER_DECISIONS}")
    if et=="action_taken" and not str(ev.get("action_taken","")).strip():
        raise ValueError("action_taken text required for action_taken event")
    if et=="measurement":
        if ev.get("measurement_role") not in MEAS_ROLES: raise ValueError(f"measurement_role must be {MEAS_ROLES}")
        if tk in (None,"","nan"): raise ValueError("measurement event requires target_kpi")
        if val in (None,"","nan") and UNAVAIL not in str(ev.get("notes","")):
            raise ValueError("measurement with empty value must state Unavailable in notes (never 0)")
    if et=="correction":
        sup=ev.get("supersedes_event_id")
        existing={r["event_id"] for r in _rows(store)}
        if sup not in existing: raise ValueError(f"correction must reference an existing event_id (got {sup})")
    if et=="note" and not str(ev.get("notes","")).strip():
        raise ValueError("note event requires notes text")
    eid=_next_id(store)
    row={c:"" for c in COLUMNS}
    row.update({k:v for k,v in ev.items() if k in COLUMNS})
    row["event_id"]=eid; row["recommendation_type"]=rtype
    row["recorded_at"]=recorded_at if recorded_at is not None else pd.Timestamp.utcnow().isoformat()
    row["recorded_by"]=ev.get("recorded_by",recorded_by)
    with open(store,"a",newline="",encoding="utf-8") as f:
        csv.DictWriter(f,fieldnames=COLUMNS).writerow(row)
    return eid

if __name__=="__main__":
    ensure_store()
    n=len(_rows(STORE))
    print(f"append-only event store ready: {STORE}")
    print(f"columns: {COLUMNS}")
    print(f"existing events: {n} (no fabricated owner actions written)")
