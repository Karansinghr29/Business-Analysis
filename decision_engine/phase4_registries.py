"""
Phase-2A Step-1 REGISTRIES (deterministic config, read-only inputs). Generates two reviewable registries from the
REAL KPI names in phase3_decision_execution_analytics + phase4_ai_opportunities. Directions are explicit and
hand-reviewed (never inferred). Writes ONLY phase4_kpi_direction_registry.csv + phase4_measurement_window_registry.csv.
Existing outputs untouched. No LLM, no now()/random.

direction ∈ {higher_is_better, lower_is_better, context_only}.  measurable ∈ {yes, no} (no => KPI has no reliable
baseline linkage; the exact 'Unavailable' sentence is preserved; NEVER treated as zero).
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
UNAVAIL="Unavailable — required data/linkage does not currently exist"
BASE="phase3_decision_execution_analytics.csv·baseline_value"

# (kpi_name, direction, unit, measurable, baseline_source, no_change_tolerance, note)
DIRECTION=[
 ("AR 90+ outstanding (₹) & tenant count","lower_is_better","INR","yes",BASE,0,"ledger-derived receivable; lower outstanding is better"),
 ("open leads (in_progress)","context_only","leads","yes",BASE,0,"volume signal; not good/bad by itself"),
 ("AC-Issue tickets (cumulative) & share of maintenance","lower_is_better","tickets","yes",BASE,0,"cumulative reliable; monthly trend unreliable (created_at ~34% null)"),
 ("Double-requested leads","context_only","leads","yes",BASE,0,"demand signal; direction not intrinsically good/bad"),
 ("high-consumption apartments flagged","lower_is_better","count","yes",BASE,0,"anomaly flag, NOT a confirmed issue"),
 ("Triple occupancy %","higher_is_better","percent","yes",BASE,1,"higher occupancy is better"),
 ("maintenance tickets / month","lower_is_better","tickets","yes",BASE,0,"low-medium confidence (created_at null)"),
 ("tenant exits / month","lower_is_better","tenants","yes",BASE,0,"fewer exits is better"),
 ("leads by locality","context_only","leads","no",UNAVAIL,0,UNAVAIL+" (no locality on leads)"),
 ("vacant 2-sharing beds & ₹/mo at risk","lower_is_better","INR","yes",BASE,0,"lower vacancy exposure is better"),
 ("vacant 3-sharing beds & ₹/mo at risk","lower_is_better","INR","yes",BASE,0,"lower vacancy exposure is better"),
 ("Single occupancy %","higher_is_better","percent","yes",BASE,1,"higher occupancy is better"),
 ("vacant single beds & ₹/mo at risk","lower_is_better","INR","yes",BASE,0,"lower vacancy exposure is better"),
 ("cost per lead / cost per fill","lower_is_better","INR","no",UNAVAIL,0,UNAVAIL+" (no spend<->lead attribution)"),
 ("laundry-related engagement (marketing)","context_only","engagement","no",UNAVAIL,0,"owner-verify; no engagement metric captured"),
 ("common-area marketing engagement","context_only","engagement","no",UNAVAIL,0,"owner-verify; no engagement metric captured"),
 ("food-service availability","context_only","flag","no",UNAVAIL,0,"Owner Verification Required — Vishful own status unknown"),
 ("CCTV/security availability","context_only","flag","no",UNAVAIL,0,"Owner Verification Required — Vishful own status unknown"),
 ("safety availability","context_only","flag","no",UNAVAIL,0,"Owner Verification Required — Vishful own status unknown"),
 ("parking availability","context_only","flag","no",UNAVAIL,0,"Owner Verification Required — Vishful own status unknown"),
 # AIREC expected_kpi strings (Phase-4 deterministic recommendations)
 ("Double occupied beds / Double monthly revenue-at-risk","higher_is_better","beds","yes",BASE,0,"primary = occupied beds (higher better); rev-at-risk is the inverse mirror"),
 ("Monthly vacancy revenue-at-risk","lower_is_better","INR","yes",BASE,0,"lower exposure is better"),
 ("Lead enquiries / campaign conversions","context_only","leads","no",UNAVAIL,0,"no causal conversion evidence exists"),
 ("Collectable AR recovered","higher_is_better","INR","yes",BASE,0,"recovered amount (higher better); mirror of AR outstanding"),
 ("Retained tenants / exits","lower_is_better","tenants","yes",BASE,0,"measured via exits/month (lower better)"),
 ("Confirmed-leak resolutions / EB loss","lower_is_better","count","yes",BASE,0,"primary = EB high-consumption/loss (lower better); anomaly not confirmed"),
 ("Repeat-ticket rate on hotspot apartments","lower_is_better","rate","yes",BASE,0,"fewer repeats is better"),
 ("Occupied beds of the promoted sharing type","higher_is_better","beds","yes",BASE,0,"higher occupied is better"),
 (UNAVAIL,"context_only","none","no",UNAVAIL,0,"Unavailable KPI (owner-verify recommendations); no measurable direction"),
]

# (domain, min_window_days, typical_window_days, rationale, applies_to)
WINDOWS=[
 ("collections_ar",14,30,"AR recovery visible within a billing/follow-up cycle","DEC-REVPROTECT-AR90; AIREC-AR-PRIORITY"),
 ("vacancy_fill",30,60,"bed fill + onboarding cycle","DEC-VAC-*; AIREC-VAC-*; AIREC-INV-PROMOTE-*"),
 ("churn_retention",60,90,"notice-to-exit horizon","DEC-RETENTION-REVIEW; AIREC-CHURN-WATCH"),
 ("maintenance_repeat",30,90,"before/after recurrence observation window","DEC-MAINT-PRIORITISE; DEC-AMEN-AC; AIREC-MAINT-HOTSPOT"),
 ("eb_investigation",30,60,"one EB billing cycle to reflect a change","DEC-EB-INVESTIGATE; AIREC-EB-INVESTIGATE"),
 ("marketing_amenity",45,90,"campaign + demand-response period","AIREC-AMEN-*; OPP-laundry; OPP-common_area"),
 ("pricing_occupancy",30,60,"occupancy response to pricing/positioning","DEC-PRICEREV-Single; DEC-PRICEREV-Triple"),
 ("demand_leads",14,30,"lead follow-up cycle","DEC-LEAD-FOLLOWUP; DEC-LEAD-DEMAND-2SH; AIREC-VAC-DBL"),
 ("owner_verify",0,0,"NO measurement window — owner must verify own status first; KPI unavailable","OPP-food; OPP-security; OPP-safety; OPP-parking; AIREC-VERIFY-*"),
]

def build():
    d=pd.DataFrame(DIRECTION,columns=["kpi_name","direction","unit","measurable","baseline_source","no_change_tolerance","note"])
    assert d["kpi_name"].is_unique,"duplicate kpi_name"
    assert d["direction"].isin(["higher_is_better","lower_is_better","context_only"]).all(),"invalid direction"
    assert d["measurable"].isin(["yes","no"]).all(),"invalid measurable"
    d.to_csv(os.path.join(OUT,"phase4_kpi_direction_registry.csv"),index=False)
    w=pd.DataFrame(WINDOWS,columns=["domain","min_window_days","typical_window_days","rationale","applies_to"])
    assert w["domain"].is_unique,"duplicate domain"
    assert (w["min_window_days"]<=w["typical_window_days"]).all(),"min>typical window"
    w.to_csv(os.path.join(OUT,"phase4_measurement_window_registry.csv"),index=False)
    return d,w

if __name__=="__main__":
    d,w=build()
    print(f"KPI direction registry: {len(d)} KPIs ({d['direction'].value_counts().to_dict()}); measurable={d['measurable'].value_counts().to_dict()}")
    print(f"Measurement-window registry: {len(w)} domains")
