"""
Phase-2A Step-3 DETERMINISTIC decision-effectiveness reducer.
Consumes (read-only): locked baselines (phase3_decision_execution_analytics, phase4_ai_opportunities),
registries (phase4_kpi_direction_registry, phase4_measurement_window_registry), and the append-only operational
event store (operational/phase4_outcome_events.csv). Produces before→after→outcome→attribution PER recommendation.

Outputs are DERIVED from mutable owner events, so they are written to operational/ (NOT outputs/) and are
therefore EXCLUDED from the byte-identical locked --verify set. The reducer NEVER writes to the event store.
No LLM. Deterministic for identical (baselines + events).
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
OPDIR=os.path.join(HERE,"operational")
EVENTS=os.path.join(OPDIR,"phase4_outcome_events.csv")
EFF=os.path.join(OPDIR,"phase4_decision_effectiveness.csv")
EFF_SUM=os.path.join(OPDIR,"phase4_decision_effectiveness_summary.csv")
UNAVAIL="Unavailable — required data/linkage does not currently exist"
NOACT="Outcome Unavailable — no action executed"

def _asof():
    try: return str(pd.read_csv(os.path.join(OUT,"phase2_revenue_backtest.csv"))["month"].max())
    except Exception: return "2026-08"

def load_baselines():
    """recommendation universe with baseline reference (source-of-truth). 20 backbone/opp + 14 AIREC."""
    rows=[]
    dea=pd.read_csv(os.path.join(OUT,"phase3_decision_execution_analytics.csv"))
    for _,r in dea.iterrows():
        rows.append(dict(recommendation_id=str(r["decision_id"]),
            recommendation_type=("backbone" if bool(r["is_backbone"]) else "phase3_opportunity"),
            is_backbone=bool(r["is_backbone"]), decision_or_opportunity=str(r["decision_topic"]),
            target_kpi=str(r["kpi_name"]), baseline_value=str(r["baseline_value"]),
            baseline_date=str(r["baseline_period"]), baseline_source="phase3_decision_execution_analytics.csv·baseline_value"))
    ai=pd.read_csv(os.path.join(OUT,"phase4_ai_opportunities.csv"))
    for _,r in ai.iterrows():
        rows.append(dict(recommendation_id=str(r["recommendation_id"]),recommendation_type="phase4_deterministic",
            is_backbone=False, decision_or_opportunity=str(r["opportunity"]),
            target_kpi=str(r["expected_kpi"]), baseline_value=UNAVAIL, baseline_date="",
            baseline_source="phase4_ai_opportunities.csv (no baseline row; baseline via owner event when logged)"))
    return rows

def load_registries():
    d=pd.read_csv(os.path.join(OUT,"phase4_kpi_direction_registry.csv"))
    dirmap={r["kpi_name"]:dict(direction=r["direction"],unit=str(r["unit"]),measurable=r["measurable"],
                               tol=float(r["no_change_tolerance"])) for _,r in d.iterrows()}
    w=pd.read_csv(os.path.join(OUT,"phase4_measurement_window_registry.csv"))
    winrows=[dict(domain=r["domain"],minw=int(r["min_window_days"]),applies=str(r["applies_to"])) for _,r in w.iterrows()]
    return dirmap,winrows

def domain_min_window(rec_id, winrows):
    for wr in winrows:
        for pat in [p.strip() for p in wr["applies"].split(";")]:
            if pat.endswith("*"):
                if rec_id.startswith(pat[:-1]): return wr["domain"],wr["minw"]
            elif rec_id==pat: return wr["domain"],wr["minw"]
    return "unmapped",None

def read_events(path=EVENTS):
    if not os.path.exists(path): return []
    df=pd.read_csv(path,dtype=str,keep_default_na=False)
    return df.to_dict("records") if len(df) else []

def _slot(ev):
    et=ev.get("event_type")
    if et in ("owner_decision","action_taken","note"): return et
    role=ev.get("measurement_role","")
    if et=="measurement": return "baseline" if role=="baseline" else "post_action"
    if et=="correction":  # routed by its own fields
        if role=="baseline": return "baseline"
        if role=="post_action": return "post_action"
        if str(ev.get("action_taken","")).strip(): return "action_taken"
        if str(ev.get("owner_decision","")).strip(): return "owner_decision"
        return "note"
    return "note"

def _latest_per_slot(evs):
    superseded={e.get("supersedes_event_id") for e in evs if e.get("event_type")=="correction"}
    live=[e for e in evs if e.get("event_id") not in superseded]
    slots={}
    for e in sorted(live,key=lambda x:(str(x.get("event_date","")),str(x.get("event_id","")))):
        slots[_slot(e)]=e
    return slots

def _num(x):
    """Plain numeric parse — for values a person entered as a number (owner measurement events)."""
    try: return float(str(x).replace(",","").replace("₹","").replace("Rs",""))
    except Exception: return None

# Analytics baselines are human-readable strings that may carry MORE THAN ONE number, e.g.
#   "₹800,503 across 47 tenants"  → ₹ amount vs tenant count
#   "9 beds / ₹128,700"           → bed count vs monthly ₹ exposure
#   "304 tickets (19.7% of ...)"  → ticket count vs percentage share
# Taking "the first number" would silently pick the wrong component (₹128,700 would become 9).
# The KPI direction registry already declares the unit for every KPI, so the unit selects which
# component is the outcome KPI. Anything not confidently resolvable returns None so the reducer
# reports Outcome Unavailable rather than comparing against an invented number.
_UNIT_PAT={
 "INR":     r"₹\s*(-?[\d,]+(?:\.\d+)?)",                       # the ₹-prefixed amount
 "percent": r"(-?[\d,]+(?:\.\d+)?)\s*%",                        # the figure carrying %
 "tickets": r"(-?[\d,]+(?:\.\d+)?)\s*tickets?\b",
 "tenants": r"(-?[\d,]+(?:\.\d+)?)\s*tenants?\b",
 "beds":    r"(-?[\d,]+(?:\.\d+)?)\s*beds?\b",
 "leads":   r"(-?[\d,]+(?:\.\d+)?)\s*leads?\b",
}
def _kpi_num(x, unit):
    """Numeric KPI component matching the KPI's declared unit. None when not resolvable."""
    s=str(x).strip()
    if not s or s.lower() in ("nan","none",""): return None
    if s.upper().startswith("UNAVAIL") or s.upper().startswith("UNKNOWN"): return None
    v=_num(s)                       # already a clean number (owner-entered, or "116.0")
    if v is not None: return v
    pat=_UNIT_PAT.get(str(unit))
    if pat:
        m=re.search(pat,s,re.I)
        if m:
            try: return float(m.group(1).replace(",",""))
            except Exception: return None
    return None                     # ambiguous / unparseable -> Outcome Unavailable, never a guess

def _days(a,b):
    try: return (pd.to_datetime(b)-pd.to_datetime(a)).days
    except Exception: return None

# ---------------------------------------------------------------------------------------------
# ATTRIBUTION CLUSTERS — the real-world mechanism / population each recommendation acts on.
# Explicit and auditable by design: never inferred from text at runtime. Two recommendations
# share a cluster ONLY where their actions touch the same beds, tenants, tickets or balances —
# not merely because both concern "revenue" or "occupancy".
# A recommendation may belong to MORE THAN ONE cluster where its KPI genuinely spans them
# (AIREC-VAC-RISK is portfolio vacancy exposure, so filling either a Double or a Triple bed
# moves it). Overlap is therefore set intersection, not equality.
# Anything absent from this map gets its own private cluster and can never be judged concurrent.
_CLUSTERS={
 # the same five currently-vacant Double beds, approached from five different angles
 "DEC-VAC-Double":          {"double_inventory_fill"},   # promote the Double inventory
 "AIREC-VAC-DBL":           {"double_inventory_fill"},   # push Double leads at those beds
 "AIREC-INV-PROMOTE-DOUBLE":{"double_inventory_fill"},   # promote those beds in channels
 "DEC-AMEN-AC":             {"double_inventory_fill"},   # market AC on those same beds
 "DEC-LEAD-DEMAND-2SH":     {"double_inventory_fill"},   # fast-track Double leads to those beds
 # portfolio vacancy exposure moves when ANY vacant bed fills -> spans both inventory clusters
 "AIREC-VAC-RISK":          {"double_inventory_fill","triple_inventory_fill"},
 "DEC-VAC-Triple":          {"triple_inventory_fill"},
 # both chase the same overdue tenant population
 "DEC-REVPROTECT-AR90":     {"ar_collection"},
 "AIREC-AR-PRIORITY":       {"ar_collection"},
 # both act on the same recurring apartment x issue hotspots
 "DEC-MAINT-PRIORITISE":    {"maintenance_repeat"},
 "AIREC-MAINT-HOTSPOT":     {"maintenance_repeat"},
 # both inspect the same flagged meters
 "DEC-EB-INVESTIGATE":      {"eb_investigation"},
 "AIREC-EB-INVESTIGATE":    {"eb_investigation"},
 # both engage the same High churn-risk tenant(s)
 "DEC-RETENTION-REVIEW":    {"tenant_retention_individual"},
 "AIREC-CHURN-WATCH":       {"tenant_retention_individual"},
}
def _clusters_overlap(a,b):
    """True when two recommendations act on the same real-world mechanism/population."""
    ca=_CLUSTERS.get(a); cb=_CLUSTERS.get(b)
    if not ca or not cb: return False          # unmapped -> private cluster, never concurrent
    return bool(ca & cb)

def _live_events(evs):
    """Events that have not been superseded by a correction."""
    sup={e.get("supersedes_event_id") for e in evs if e.get("event_type")=="correction"}
    return [e for e in evs if e.get("event_id") not in sup]

def _window_overlap(action_date, post_date, minw, other_action_date):
    """Did another action fall inside this comparison's exposure period?

    Exposure runs from (this action date - the window this KPI needs) through this measurement
    date: an action landing in that span could have contributed to the movement being judged.
    Missing/unparseable dates are treated as overlapping — the cautious reading, since we cannot
    rule the other action out.
    """
    if not other_action_date: return True
    try:
        oa=pd.to_datetime(other_action_date); a=pd.to_datetime(action_date); p=pd.to_datetime(post_date)
    except Exception:
        return True
    if pd.isna(oa) or pd.isna(a) or pd.isna(p): return True
    start=a-pd.Timedelta(days=int(minw)) if minw else a
    return start<=oa<=p

def compute(baselines, events, dirmap, winrows, asof):
    by_rec={}
    for e in events: by_rec.setdefault(str(e.get("recommendation_id")),[]).append(e)
    # concurrent-action detection: actions per KPI within data (for attribution)
    rows=[]
    for b in baselines:
        rid=b["recommendation_id"]; kpi=b["target_kpi"]
        reg=dirmap.get(kpi,{}); direction=reg.get("direction","context_only"); unit=reg.get("unit","")
        measurable=reg.get("measurable","no"); tol=reg.get("tol",0.0)
        dom,minw=domain_min_window(rid,winrows)
        slots=_latest_per_slot(by_rec.get(rid,[]))
        owner=slots.get("owner_decision",{}).get("owner_decision","") or "pending"
        act=slots.get("action_taken"); action_taken=act.get("action_taken","") if act else ""
        action_date=act.get("event_date","") if act else ""
        base_ev=slots.get("baseline"); post_ev=slots.get("post_action")
        # Numeric baseline: an owner-logged baseline event wins (it is already a plain number); otherwise
        # resolve the analytics baseline UNIT-AWARELY so multi-number displays pick the right component.
        num_base=_num(base_ev.get("value")) if base_ev else _kpi_num(b["baseline_value"],unit)
        base_src=("owner baseline event" if base_ev else
                  ("analytics baseline (unit-resolved)" if num_base is not None else "not numerically resolvable"))
        base_disp=(base_ev.get("value") if base_ev else b["baseline_value"])
        base_date=(base_ev.get("event_date") if base_ev else b["baseline_date"])
        post_val=post_ev.get("value") if post_ev else ""
        post_date=post_ev.get("event_date") if post_ev else ""
        # Owner-entered post values are normally plain numbers, but resolve unit-awarely too so a value
        # typed as "₹600,000" or "85%" is still read correctly rather than rejected.
        num_post=_kpi_num(post_val,unit) if post_ev else None
        ev_used="|".join(sorted(str(e.get("event_id")) for e in by_rec.get(rid,[])))

        # ---- outcome (precedence) ----
        win_status="n/a (no action)"; outcome=NOACT; attribution="None / Unavailable"; limitation="none"
        if not act:
            outcome=NOACT; limitation="no owner action recorded (recommendation generation is not execution)"
        elif direction=="context_only":
            outcome="Not Evaluable — direction undefined"; limitation="KPI direction is context_only; not good/bad by itself"
            win_status="n/a (context_only)"
        elif num_base is None or measurable=="no":
            outcome=f"Outcome Unavailable — {UNAVAIL}"; limitation=UNAVAIL
        elif not post_ev:
            outcome="Insufficient Data"; limitation="action recorded but no valid post-action measurement"
            win_status="post measurement missing"
        else:
            dd=_days(action_date,post_date)
            if minw is not None and dd is not None and dd<minw:
                outcome="Insufficient Data"; win_status=f"window not complete ({dd}d < {minw}d)"
                limitation="measurement window not yet complete"
            elif num_post is None:
                outcome="Insufficient Data"; win_status="post value non-numeric/unavailable"; limitation="post value unavailable"
            else:
                win_status=f"window met ({dd}d >= {minw}d)" if (minw is not None and dd is not None) else "window n/a"
                delta=num_post-num_base
                if abs(delta)<=tol: outcome="No Change"
                elif direction=="lower_is_better": outcome="Improved" if delta<0 else "Worsened"
                else: outcome="Improved" if delta>0 else "Worsened"  # higher_is_better
                # ---- attribution (separate from outcome) ----
                # Concurrency is judged on the real-world MECHANISM, not the KPI name. Overlapping
                # recommendations were authored with distinct KPI names, so string equality alone
                # detected nothing and every overlapping action could claim High independently.
                # KPI-string equality is retained as an additional signal, not the only one.
                concurrent=0
                for r2,evs2 in by_rec.items():
                    if r2==rid: continue
                    live2=_live_events(evs2)
                    acts2=[x for x in live2 if _slot(x)=="action_taken"]
                    if not acts2: continue
                    same_kpi=any(str(x.get("target_kpi",""))==kpi for x in live2)
                    if not (same_kpi or _clusters_overlap(rid,r2)): continue
                    # the other action must plausibly fall inside this comparison's exposure period:
                    # from this action's date (less the window it needed) through this measurement date
                    if any(_window_overlap(action_date,post_date,minw,x.get("event_date")) for x in acts2):
                        concurrent+=1
                factors=[bool(act),num_base is not None,num_post is not None,(minw is not None and dd is not None and dd>=minw)]
                if all(factors) and concurrent==0: attribution="High"
                elif all(factors) and concurrent>=1: attribution="Low"
                elif sum(factors)>=3: attribution="Medium"
                else: attribution="Low"
        rows.append(dict(recommendation_id=rid,recommendation_type=b["recommendation_type"],is_backbone=b["is_backbone"],
            decision_or_opportunity=b["decision_or_opportunity"],target_kpi=kpi,kpi_direction=direction,
            baseline_value=base_disp,baseline_numeric=("" if num_base is None else num_base),
            baseline_numeric_source=base_src,baseline_unit=unit,baseline_date=base_date,owner_decision=owner,
            action_taken=action_taken,action_date=action_date,post_value=post_val,post_unit=(unit if post_ev else ""),
            post_date=post_date,min_window_days=(minw if minw is not None else ""),measurement_window_status=win_status,
            outcome_status=outcome,attribution_confidence=attribution,data_limitation=limitation,
            baseline_source=b["baseline_source"],event_ids_used=ev_used,as_of_date=asof))
    E=pd.DataFrame(rows)
    def c(mask): return int(mask.sum())
    summ=[("recommendations_total",len(E)),("backbone_total",c(E["is_backbone"]==True)),
        ("deterministic_opportunities_total",c(E["recommendation_type"]=="phase4_deterministic")),
        ("phase3_opportunities_total",c(E["recommendation_type"]=="phase3_opportunity")),
        ("approved",c(E["owner_decision"]=="approved")),("rejected",c(E["owner_decision"]=="rejected")),
        ("deferred",c(E["owner_decision"]=="deferred")),("pending",c(E["owner_decision"]=="pending")),
        ("actions_recorded",c(E["action_taken"].astype(str).str.len()>0)),
        ("measurable_outcomes",c(E["outcome_status"].isin(["Improved","No Change","Worsened"]))),
        ("improved",c(E["outcome_status"]=="Improved")),("no_change",c(E["outcome_status"]=="No Change")),
        ("worsened",c(E["outcome_status"]=="Worsened")),
        ("insufficient_data",c(E["outcome_status"]=="Insufficient Data")),
        ("not_evaluable_context_only",c(E["outcome_status"].str.startswith("Not Evaluable"))),
        ("outcome_unavailable",c(E["outcome_status"].str.startswith("Outcome Unavailable"))),
        ("attribution_high",c(E["attribution_confidence"]=="High")),("attribution_medium",c(E["attribution_confidence"]=="Medium")),
        ("attribution_low",c(E["attribution_confidence"]=="Low")),
        ("attribution_unavailable",c(E["attribution_confidence"]=="None / Unavailable"))]
    S=pd.DataFrame(summ,columns=["metric","value"])
    return E,S

def main():
    os.makedirs(OPDIR,exist_ok=True)
    baselines=load_baselines(); dirmap,winrows=load_registries(); events=read_events(); asof=_asof()
    E,S=compute(baselines,events,dirmap,winrows,asof)
    E.to_csv(EFF,index=False); S.to_csv(EFF_SUM,index=False)
    print(f"DECISION EFFECTIVENESS: {len(E)} recommendations (backbone {int((E['is_backbone']==True).sum())}, "
          f"AIREC {int((E['recommendation_type']=='phase4_deterministic').sum())}); events read {len(events)}")
    print(S.to_string(index=False))

if __name__=="__main__": main()
