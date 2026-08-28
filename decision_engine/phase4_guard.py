"""
Phase-4 fail-loud RECOMMENDATION GUARD (deterministic). Rejects any recommendation that is not fully evidence-
grounded or that violates the owner constraints. Imported by phase4_opportunity_rules.py (pre-write) and by the
validator (re-check). No LLM.
"""
from __future__ import annotations
import re

# competitor-comparison / benchmark language (owner: NEVER compare with competitors)
BLOCK_PHRASES=["better than","worse than","cheaper","more expensive","cheapest","most expensive",
    "best competitor","worst competitor","rank competitor","vs competitor","versus competitor",
    "market average","benchmark","vishful should charge","outperform","ahead of competitor","behind competitor"]
# fabricated-metric / unsupported-claim patterns
FAB_PATTERNS=[r"\broi\b",r"revenue uplift",r"conversion rate",r"\d+\s*%",r"occupancy increase",
    r"increase occupancy",r"\d+\s*(?:min|minute)s?\b",r"minute walk",r"min walk",r"customer prefer",
    r"guaranteed",r"expected revenue",r"expected leads",r"will increase",r"will improve by"]
CONF={"High","Medium","Low"}
UNAVAILABLE="Unavailable — required data/linkage does not currently exist"

def _nums(text):
    t=str(text).replace("Rs","").replace("₹","").replace(",","")
    return set(int(x) for x in re.findall(r"(?<![\w.])\d+(?![\w.])", t))

def check(rec, pack):
    """rec: dict; pack: {evidence_id: metric_value(numeric or None)}. Returns (ok:bool, reason:str)."""
    text=" ".join(str(rec.get(k,"")) for k in ["opportunity","why_it_matters","suggested_action","expected_kpi"])
    low=text.lower()
    if rec.get("confidence") not in CONF: return False,f"confidence must be High/Medium/Low (got {rec.get('confidence')})"
    if not str(rec.get("data_limitation","")).strip(): return False,"data_limitation missing"
    eids=rec.get("evidence_ids") or []
    if not eids: return False,"no evidence_ids"
    for e in eids:
        if e not in pack: return False,f"evidence_id {e} not in evidence pack"
    for b in BLOCK_PHRASES:
        if b in low: return False,f"competitor-comparison phrase '{b}'"
    for p in FAB_PATTERNS:
        if re.search(p,low): return False,f"fabricated/unsupported claim pattern '{p}'"
    # numeric traceability: every number in text must be a claimed evidence value
    claimed=set()
    for c in (rec.get("numeric_claims") or []):
        e=c.get("evidence_id"); val=c.get("value")
        if e not in pack: return False,f"numeric_claim cites missing evidence {e}"
        if pack[e] is None or int(pack[e])!=int(val): return False,f"numeric_claim {val} != evidence {e} value {pack.get(e)}"
        claimed.add(int(val))
    stray=_nums(text)-claimed
    if stray: return False,f"untraceable number(s) in text {sorted(stray)} (not backed by evidence)"
    if rec.get("owner_verify_required") and "verify" not in low:
        return False,"owner-verify item must instruct internal verification, not assert a claim"
    return True,"passed"
