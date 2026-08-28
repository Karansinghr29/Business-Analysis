"""
OUTCOME AI ANALYSIS — a grounded explanation layer that runs AFTER the real Before/After calculation.

The AI never decides the outcome. phase4_kpi_measure.py has already classified it deterministically
from the KPI direction registry, the tolerance and the measurement window. This module only explains
what was measured, and is handed ONLY those measured facts — no raw tables, no tenant records, no
market data, no freedom to look anything up.

HARD CONSTRAINTS, enforced in code after generation (not merely requested in the prompt):
  - no number may appear that is not one of the supplied measured facts
  - no ROI, revenue-uplift, conversion, profit or cost-saving claim
  - no causal claim ("caused", "because of", "due to the action", "drove", "resulted in")
    -> the KPI "improved after the action", never "the action caused the improvement"
  - no customer-behaviour or motive speculation
Any generated text violating these is DISCARDED and replaced by the deterministic template, which is
built purely from the measured facts. The system therefore degrades to something true, never to
something invented.

Reads  operational/phase4_before_after.csv (already-measured facts) READ-ONLY.
Writes ONLY operational/phase4_outcome_ai.csv.
"""
from __future__ import annotations
import os, sys, re, json
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OPDIR = os.path.join(HERE, "operational")
BA = os.path.join(OPDIR, "phase4_before_after.csv")
AI_OUT = os.path.join(OPDIR, "phase4_outcome_ai.csv")

MODEL = "openai/gpt-oss-120b"

# ---- forbidden claim vocabulary -------------------------------------------------------------------
CAUSAL = re.compile(r"\b(caused|causing|because of the action|due to the action|as a result of the "
                    r"action|drove|resulted in|led to|thanks to|attributable to)\b", re.I)
FABRICATED = re.compile(r"\b(roi|return on investment|revenue uplift|uplift|conversion rate|"
                        r"converted|profit|margin|cost saving|savings of|payback|revenue increase|"
                        r"we earned|we saved)\b"
                        # customer-motive speculation, including inflected forms
                        r"|\bcustomers?\s+\w{0,6}\s?(?:prefer|want|feel|felt|respond|react|like|"
                        r"dislike|complain|expect)\w*", re.I)
NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _facts(r) -> dict:
    """Exactly what the model is allowed to know. Nothing else is passed."""
    return {
        "decision": str(r["decision"]),
        "action_taken": str(r["action_taken"]),
        "action_date": str(r["action_date"]),
        "kpi": str(r["target_kpi"]),
        "kpi_direction": str(r["kpi_direction"]),
        "before_value": (None if pd.isna(r["before_value"]) else float(r["before_value"])),
        "before_date": str(r["before_date"]),
        "after_value": (None if pd.isna(r["after_value"]) else float(r["after_value"])),
        "after_date": str(r["after_date"]),
        "change": (None if pd.isna(r["change"]) else float(r["change"])),
        "change_pct": (None if pd.isna(r["change_pct"]) else float(r["change_pct"])),
        "days_since_action": (None if pd.isna(r["days_since_action"]) else int(r["days_since_action"])),
        "min_window_days": (None if pd.isna(r["min_window_days"]) else int(r["min_window_days"])),
        "window_complete": (None if pd.isna(r["window_complete"]) else bool(r["window_complete"])),
        "outcome": str(r["outcome"]),
        "outcome_basis": str(r["outcome_basis"]),
        "data_confidence": str(r["data_confidence"]),
        "known_limitation": str(r["limitation"]),
    }


def _allowed_numbers(f: dict) -> set:
    """Every numeric token the model may legitimately restate."""
    out = set()
    for k in ("before_value", "after_value", "change", "change_pct",
              "days_since_action", "min_window_days"):
        v = f.get(k)
        if v is None: continue
        a = abs(v)
        out.add(re.sub(r"\.0$", "", f"{a:.2f}".rstrip("0").rstrip(".")))
        out.add(re.sub(r"\.0$", "", str(round(a, 1))))
        out.add(str(int(a)))
        # display rounds INR to whole rupees, which can round UP (400251.69 -> "₹400,252").
        # The rounded form is the same measured fact, so it must be allowed or the guard would
        # reject its own truthful output.
        out.add(str(round(a)))
        out.add(f"{a:.1f}"); out.add(f"{a:.2f}")
    # Numbers already present in the supplied fact STRINGS are legitimate to restate — the KPI name
    # itself carries digits (e.g. "AR 90+ outstanding"), as do dates and the outcome basis. Without
    # this the guard would reject its own truthful deterministic text.
    for k in ("action_date", "before_date", "after_date", "kpi", "decision", "action_taken",
              "outcome", "outcome_basis", "data_confidence", "known_limitation"):
        for t in NUM.findall(str(f.get(k) or "")): out.add(t)
    return {t.replace(",", "") for t in out}


def _violations(text: str, f: dict):
    """Reasons the generated text must be rejected. Empty list = acceptable."""
    bad = []
    if CAUSAL.search(text): bad.append(f"causal claim: {CAUSAL.search(text).group(0)!r}")
    if FABRICATED.search(text): bad.append(f"fabricated metric: {FABRICATED.search(text).group(0)!r}")
    allowed = _allowed_numbers(f)
    for tok in NUM.findall(text):
        t = tok.replace(",", "").rstrip(".")
        if t in allowed or t.rstrip("0").rstrip(".") in allowed: continue
        # allow the section numbering 1..5
        if t in {"1", "2", "3", "4", "5"}: continue
        bad.append(f"ungrounded number: {tok!r}")
        break
    return bad


def _fmt(v, unit=""):
    if v is None: return "not available"
    if unit == "INR": return f"₹{v:,.0f}"
    if unit == "percent": return f"{v:.1f}%"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def deterministic_analysis(f: dict, unit: str = "") -> str:
    """Built only from measured facts. Always true; used as the fallback and as the guard's floor."""
    o = f["outcome"]
    b, a, ch = f["before_value"], f["after_value"], f["change"]
    L = []
    if b is not None and a is not None:
        L.append(f"1. What changed: {f['kpi']} was {_fmt(b, unit)} at the action baseline "
                 f"({f['before_date']}) and is {_fmt(a, unit)} as of {f['after_date']}.")
        L.append(f"2. Direction: {o}. {f['outcome_basis']}.")
        L.append(f"3. Evidence: the measured change is {_fmt(ch, unit)}"
                 + (f" ({f['change_pct']}%)" if f["change_pct"] is not None else "")
                 + f", against a KPI where {f['kpi_direction'].replace('_', ' ')}.")
    else:
        L.append(f"1. What changed: {f['kpi']} cannot be compared yet — "
                 + ("no current value is available." if a is None else "no frozen baseline was captured."))
        L.append(f"2. Direction: {o}. {f['outcome_basis']}.")
        L.append("3. Evidence: insufficient measured data to state a movement.")
    win = ("the measurement window is complete" if f["window_complete"]
           else f"the measurement window is not complete"
                + (f" ({f['days_since_action']} of {f['min_window_days']} days)"
                   if f["days_since_action"] is not None and f["min_window_days"] is not None else ""))
    L.append(f"4. Limitations: {win}. Data confidence: {f['data_confidence']}. "
             "Movement after an action is not proof that the action produced it.")
    if o == "Positive":
        nxt = ("The KPI is moving in the intended direction after the action. Continue monitoring "
               "through the defined measurement window before making a final effectiveness judgement.")
    elif o == "Negative":
        nxt = ("The measured KPI has not improved during the current measurement window. Review the "
               "action and consider an alternative intervention.")
    elif o == "No measurable change":
        nxt = ("The KPI has not moved beyond the declared tolerance. Consider whether the action was "
               "applied at sufficient scale, or allow more of the measurement window to elapse.")
    else:
        nxt = ("There is not enough post-action data to determine whether the action produced a "
               "measurable outcome. Re-check once the measurement window has elapsed.")
    L.append(f"5. Next: {nxt}")
    return "\n".join(L)


def _groq(f: dict):
    key = os.environ.get("GROQ_API_KEY")
    if not key: return None, "GROQ_API_KEY not set"
    try:
        from groq import Groq
    except Exception:
        return None, "groq package unavailable"
    prompt = (
        "You explain an ALREADY-MEASURED business outcome. You did not decide it and you must not "
        "change it. Use ONLY the JSON facts given.\n\n"
        "Write exactly five numbered lines:\n"
        "1. What changed?\n2. Was the movement positive, negative, or inconclusive?\n"
        "3. What evidence supports that conclusion?\n4. Are there data-quality limitations?\n"
        "5. What should the owner consider doing next?\n\n"
        "HARD RULES:\n"
        "- Use NO number that is not present in the facts.\n"
        "- Never claim the action CAUSED the movement. Say the KPI improved/worsened AFTER the action.\n"
        "- Never mention ROI, revenue, uplift, profit, conversion, cost saving or customer motives.\n"
        "- If the outcome says data is insufficient, say so plainly; do not speculate.\n"
        "- Under 130 words total.\n\nFACTS:\n" + json.dumps(f, ensure_ascii=False))
    try:
        c = Groq(api_key=key.strip())
        # gpt-oss-120b is a reasoning model: reasoning tokens count against max_tokens, so a small
        # budget returns empty content. Give it room, and keep reasoning short.
        kw = dict(model=MODEL, messages=[{"role": "user", "content": prompt}],
                  temperature=0, max_tokens=1400)
        try:
            r = c.chat.completions.create(reasoning_effort="low", **kw)
        except Exception:
            r = c.chat.completions.create(**kw)
        txt = (r.choices[0].message.content or "").strip()
        return (txt or None), (None if txt else "model returned empty content")
    except Exception as e:
        return None, f"{type(e).__name__}"


def analyse(row, unit: str = "", use_ai: bool = True) -> dict:
    f = _facts(row)
    det = deterministic_analysis(f, unit)
    text, src, rej = det, "deterministic (facts only)", ""
    if use_ai:
        gen, err = _groq(f)
        if gen:
            v = _violations(gen, f)
            if v:
                rej = "; ".join(v[:2])
            else:
                text, src = gen, f"groq:{MODEL} temp=0 (guard-checked)"
        else:
            rej = err or "no generation"
    return dict(recommendation_id=row["recommendation_id"], outcome=f["outcome"],
                analysis=text, analysis_source=src, rejected_reason=rej,
                facts_supplied=json.dumps(f, ensure_ascii=False))


def main(use_ai: bool = True):
    if not os.path.exists(BA):
        print("No before/after store yet — run phase4_kpi_measure.py first."); return
    ba = pd.read_csv(BA)
    if not len(ba):
        pd.DataFrame(columns=["recommendation_id", "outcome", "analysis", "analysis_source",
                              "rejected_reason", "facts_supplied"]).to_csv(AI_OUT, index=False)
        print("PHASE-4 OUTCOME AI: no executed actions — nothing to analyse."); return
    rows = [analyse(r, str(r.get("kpi_unit", "")), use_ai) for _, r in ba.iterrows()]
    pd.DataFrame(rows).to_csv(AI_OUT, index=False)
    print(f"PHASE-4 OUTCOME AI: {len(rows)} analysed")
    for r in rows:
        print(f"\n  [{r['recommendation_id']}] {r['outcome']}  ({r['analysis_source']})")
        if r["rejected_reason"]: print(f"     generation REJECTED -> {r['rejected_reason']}")
        for line in r["analysis"].split("\n"): print("     " + line)


if __name__ == "__main__":
    main()
