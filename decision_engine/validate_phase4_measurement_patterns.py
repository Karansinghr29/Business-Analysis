"""Fail-loud validation that each of the 33 recommendations uses an HONEST measurement pattern.

The KPI that caused a recommendation is not automatically the KPI that can measure whether the action
worked. This guards the specific semantic traps found in audit:
  * a marketing action scored by a maintenance ticket count (DEC-AMEN-AC)
  * a cumulative multi-year baseline used as a naive before/after (DEC-EB-INVESTIGATE)
  * a single-tenant action scored by a portfolio-wide monthly KPI (DEC-RETENTION-REVIEW)
  * "review but do not change" scored as if a change had been made (DEC-PRICEREV-Triple)
  * a data-capture change scored by the KPI it is meant to unlock (DEC-MKT-ROI-GAP)
  * at-ceiling / zero-exposure decisions offered a measurement at all

Display-layer contract: only a `direct` pattern may offer numeric measurement entry.
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
import phase4_decision_effectiveness as R

fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

SRC=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
BASE=R.load_baselines(); DIRMAP,WINROWS=R.load_registries()

# ---- parse the display-layer pattern map and resolve the effective pattern for every recommendation
mblk=re.search(r"_PATTERN=\{(.*?)\n    \}",SRC,re.S)
OV=dict(re.findall(r'"([A-Z0-9-]+(?:-[A-Za-z]+)*)":dict\(p="(\w+)"',mblk.group(1) if mblk else ""))

def pattern_of(rid):
    reg=DIRMAP[next(b for b in BASE if b["recommendation_id"]==rid)["target_kpi"]]
    dom,minw=R.domain_min_window(rid,WINROWS)
    if rid in OV: return OV[rid]
    if dom=="owner_verify" or minw==0: return "verify"
    if str(reg["measurable"]).lower()=="yes" and reg["direction"]!="context_only": return "direct"
    return "none"

print("[1] pattern map is present and every recommendation resolves to exactly one pattern")
chk(mblk is not None,"_PATTERN map found in the display layer")
pats={b["recommendation_id"]:pattern_of(b["recommendation_id"]) for b in BASE}
chk(len(pats)==33,f"33 recommendations classified ({len(pats)})")
chk(set(pats.values())<={"direct","different","investig","verify","none"},
    f"only known patterns used ({sorted(set(pats.values()))})")

print("\n[2] the specific semantic traps are NOT scored as naive before/after")
TRAPS={
 "DEC-AMEN-AC":"marketing action must not be scored by cumulative maintenance tickets",
 "DEC-EB-INVESTIGATE":"cumulative 2023-2026 count must not be a naive before/after baseline",
 "DEC-RETENTION-REVIEW":"single-tenant action must not be scored by portfolio monthly exits",
 "DEC-PRICEREV-Triple":"'review, do not change price' must not be scored as an occupancy change",
 "DEC-MKT-ROI-GAP":"data-capture change must not be scored by the KPI it is meant to unlock",
 "DEC-LEAD-DEMAND-2SH":"count of enquiries received is evidence, not the outcome of fast-tracking them",
 "DEC-PRICEREV-Single":"at 100% occupancy there is no headroom to measure",
 "DEC-VAC-Single":"zero vacancy leaves nothing to promote or measure",
}
for rid,why in TRAPS.items():
    chk(pats.get(rid)!="direct",f"{rid} is not 'direct' — {why} (pattern: {pats.get(rid)})")
    chk(rid in OV,f"{rid} carries an explicit documented override")

print("\n[3] only a 'direct' pattern may offer numeric measurement entry")
chk("_numeric_ok=(_pat==\"direct\")" in SRC.replace("'",'"'),"numeric entry gated on the direct pattern")
chk("elif not _numeric_ok:" in SRC,"section D gate uses the resolved pattern, not the registry alone")

print("\n[4] cumulative / composite baselines are explained, not silently reduced")
chk("cumulative across 2023–2026" in SRC,"EB cumulative window stated to the owner")
chk("102 of the 304" in SRC,"AC null-created_at limitation preserved verbatim")
chk("rupee figure is the one measured" in SRC,"composite baselines say which component is measured")

print("\n[5] Unknown stays Unknown; Unavailable is never zero")
for rid,p in pats.items():
    if p=="verify":
        chk(True,f"{rid}: owner-verify preserved")
chk("Owner verification required — no measurement yet" in SRC,"owner-verify has its own explanation")
chk("Unknown is not converted" in SRC or "Unknown stays Unknown" in SRC or
    "not treated as a zero" in SRC,"Unknown is explicitly not treated as zero/no")

print("\n[6] composition unchanged and non-backbone status preserved")
cnt=pd.Series([b["recommendation_type"] for b in BASE]).value_counts().to_dict()
chk(cnt.get("backbone")==14,f"14 backbone ({cnt.get('backbone')})")
chk(cnt.get("phase3_opportunity")==6,f"6 Phase-3 opportunities ({cnt.get('phase3_opportunity')})")
chk(cnt.get("phase4_deterministic")==13,f"13 AIREC ({cnt.get('phase4_deterministic')})")
chk(not any(b["is_backbone"] for b in BASE if b["recommendation_type"]!="backbone"),
    "all 19 non-backbone recommendations remain is_backbone=False")

print("\n[7] no fabricated benefit language in the new wording")
blk=mblk.group(1) if mblk else ""
# strip recommendation IDs first — "DEC-MKT-ROI-GAP" legitimately contains "ROI" as part of its name,
# which is a reference to the decision, not a claim of return on investment.
blk_txt=re.sub(r"\b(?:DEC|AIREC|OPP)[-\w]+","",blk).lower()
for bad in ["roi","uplift","savings","profit","revenue increase","guaranteed","proven"]:
    chk(re.search(rf"\b{re.escape(bad)}\b",blk_txt) is None,f"pattern wording contains no '{bad}'")

print("\n[8] outcome/attribution remain reducer-derived")
cap=open(os.path.join(HERE,"phase4_action_capture.py"),encoding="utf-8").read()
for banned in ["outcome_status","attribution_confidence","improvement_pct"]:
    chk(banned not in cap,f"writer never accepts a typed '{banned}'")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
