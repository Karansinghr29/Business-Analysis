"""
Phase-4 DETERMINISTIC OPPORTUNITY RULES (read-only). Generates evidence-grounded advisory business opportunities
from the phase4 evidence pack. Every recommendation is checked by phase4_guard.check() BEFORE it is written;
non-compliant recommendations go to _rejected.csv and are never displayed. No LLM, no fabricated metrics, no
competitor comparison. recommendation_id is compatible with phase3_execution_tracker.decision_id (string key).
Writes ONLY phase4_ai_opportunities.csv, _rejected.csv, _summary.csv. Existing outputs untouched.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from phase4_evidence_pack import build as build_pack
import phase4_guard as guard
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")

def _num(v):
    try: return int(float(v))
    except Exception: return None

def main():
    P=build_pack()
    packval={r["evidence_id"]:_num(r["metric_value"]) for _,r in P.iterrows()}
    has=set(P["evidence_id"]); asof=str(P["as_of_date"].iloc[0])
    def g(eid): return _num(P[P["evidence_id"]==eid]["metric_value"].iloc[0]) if eid in has else None

    recs=[]
    def add(rid,opp,eids,why,action,kpi,conf,limit,claims,prov="VISHFUL_INTERNAL",owner_verify=False):
        recs.append(dict(recommendation_id=rid,opportunity=opp,evidence_ids=eids,why_it_matters=why,
            suggested_action=action,expected_kpi=kpi,confidence=conf,data_limitation=limit,
            owner_verify_required=owner_verify,provenance=prov,as_of_date=asof,numeric_claims=claims))

    # Rule 1 — Double-sharing vacancy + demand match
    if g("EV-VAC-DOU") and g("EV-VAC-DOU")>0 and g("EV-DEM-DOU") and g("EV-DEM-DOU")>0:
        vd,rd,ld=g("EV-VAC-DOU"),g("EV-VAC-DOU-RISK"),g("EV-DEM-DOU")
        add("AIREC-VAC-DBL","Prioritize Double-sharing demand against Double vacant inventory",
            ["EV-VAC-DOU","EV-VAC-DOU-RISK","EV-DEM-DOU"],
            f"{vd} vacant Double beds carry Rs{rd:,}/month revenue at risk, and {ld} open Double-sharing leads exist now.",
            f"Prioritize the {ld} open Double-sharing leads for the {vd} vacant Double beds; log outcome per lead.",
            "Double occupied beds / Double monthly revenue-at-risk","High",
            "Lead intent is requested_bed_type only; no conversion probability implied.",
            [{"value":vd,"evidence_id":"EV-VAC-DOU"},{"value":rd,"evidence_id":"EV-VAC-DOU-RISK"},{"value":ld,"evidence_id":"EV-DEM-DOU"}])

    # Rule 2 — Vacancy revenue-at-risk prioritization
    if g("EV-VAC-TOTAL") and g("EV-VAC-TOTAL")>0:
        vt,rt=g("EV-VAC-TOTAL"),g("EV-VAC-RISK")
        add("AIREC-VAC-RISK","Prioritize the highest revenue-at-risk vacant beds",
            ["EV-VAC-TOTAL","EV-VAC-RISK"],
            f"{vt} vacant beds represent Rs{rt:,}/month of revenue exposure.",
            "Rank vacant beds by monthly revenue-at-risk and fill the highest-exposure beds first.",
            "Monthly vacancy revenue-at-risk","High",
            "Vacancy duration is approximate (bed_status_history missing).",
            [{"value":vt,"evidence_id":"EV-VAC-TOTAL"},{"value":rt,"evidence_id":"EV-VAC-RISK"}])

    # Rule 3 — Verified amenity marketing (only where Vishful-verified AND market-published; owner-verify gated ones separate)
    amen_map={"AC":("EV-AMEN-AC","EV-MKT-AMEN-AC"),"Wi-Fi":("EV-AMEN-WIFI","EV-MKT-AMEN-WIFI")}
    for name,(ave,mve) in amen_map.items():
        if ave in has and mve in has:
            n=g(mve)
            add(f"AIREC-AMEN-{name.replace('-','').upper()}",f"Highlight Vishful's verified {name} in marketing content",
                [ave,mve],
                f"{name} is verified present at Vishful and is publicly published on {n} first-party market sources, so it is a relevant market theme Vishful can evidence.",
                f"Consider featuring verified {name} in Vishful marketing material.",
                "Lead enquiries / campaign conversions","Medium",
                "No causal conversion evidence exists; market data is context only, not a comparison.",
                [{"value":n,"evidence_id":mve}],prov="VISHFUL_INTERNAL+MARKET_CONTEXT")
    # owner-verify amenity themes (Vishful own status unknown) -> advisory to verify, never assert
    for mve in ["EV-MKT-AMEN-FOOD","EV-MKT-AMEN-PARKING","EV-MKT-AMEN-SECURITY","EV-MKT-AMEN-POWERBAC"]:
        if mve in has:
            nm=P[P["evidence_id"]==mve]["source_row_ref"].iloc[0]; n=g(mve)
            add(f"AIREC-VERIFY-{mve.split('-')[-1]}",f"Owner-verify Vishful's own {nm} status before any marketing claim",
                [mve],
                f"'{nm}' is publicly published on {n} first-party market sources, but Vishful's own {nm} status is not established in Vishful data.",
                f"Verify Vishful's own {nm} provision internally before making any {nm} marketing claim.",
                "Unavailable — required data/linkage does not currently exist","Low",
                "Vishful own status unknown; do not advertise until verified.",
                [{"value":n,"evidence_id":mve}],prov="MARKET_CONTEXT",owner_verify=True)

    # Rule 4 — Collections priority
    if g("EV-AR-HIGH") and g("EV-AR-HIGH")>0:
        n,amt=g("EV-AR-HIGH"),g("EV-AR-HIGH-AMT")
        add("AIREC-AR-PRIORITY","Prioritize collections on high overdue-risk tenants",
            ["EV-AR-HIGH","EV-AR-HIGH-AMT"],
            f"{n} tenants are at high overdue risk, with Rs{amt:,} of AR exposure.",
            f"Prioritize collection follow-up on the {n} high-risk tenants; log outcome per tenant.",
            "Collectable AR recovered","High",
            "Settlement is UNRECONCILED (receipt_allocations missing); AR is ledger-based exposure, not confirmed loss.",
            [{"value":n,"evidence_id":"EV-AR-HIGH"},{"value":amt,"evidence_id":"EV-AR-HIGH-AMT"}])

    # Rule 5 — Churn watch action
    if g("EV-CHURN-HIGH") and g("EV-CHURN-HIGH")>0:
        n=g("EV-CHURN-HIGH")
        add("AIREC-CHURN-WATCH","Engage High churn-risk tenants",
            ["EV-CHURN-HIGH"],
            f"{n} tenants fall in the High churn-risk band.",
            f"Engage the {n} High-band tenants using the ranked watch-list (ranking, not a fixed cutoff).",
            "Retained tenants / exits","Medium",
            "Ranking-only (ROC-AUC ~0.72); not a yes/no prediction.",
            [{"value":n,"evidence_id":"EV-CHURN-HIGH"}])

    # Rule 6 — EB investigation
    if g("EV-EB-LEAK") and g("EV-EB-LEAK")>0:
        n=g("EV-EB-LEAK")
        add("AIREC-EB-INVESTIGATE","Investigate possible-leak electricity candidates",
            ["EV-EB-LEAK"],
            f"{n} meters show occupancy-aware possible-leak signals.",
            f"Investigate the {n} flagged meters on site.",
            "Confirmed-leak resolutions / EB loss","Medium",
            "Abnormal consumption is NOT a confirmed leak; inspection required.",
            [{"value":n,"evidence_id":"EV-EB-LEAK"}])

    # Rule 7 — Maintenance hotspot action
    if g("EV-MAINT-HOT") and g("EV-MAINT-HOT")>0:
        n=g("EV-MAINT-HOT")
        add("AIREC-MAINT-HOTSPOT","Prioritize high-confidence recurring maintenance hotspots",
            ["EV-MAINT-HOT"],
            f"{n} apartment-issue groups are High-priority recurring hotspots at high date-confidence.",
            f"Prioritize preventive action on the {n} high-confidence hotspots.",
            "Repeat-ticket rate on hotspot apartments","High",
            "Acts on date_confidence=high only; low-confidence recurrences excluded.",
            [{"value":n,"evidence_id":"EV-MAINT-HOT"}])

    # Rule 8 — Available inventory promotion (by sharing type present + market-published config context)
    for name,ve,rve,mve in [("Double","EV-VAC-DOU","EV-VAC-DOU-RISK","EV-MKT-SHARE-2SHARING"),
                            ("Single","EV-VAC-SIN","EV-VAC-SIN-RISK","EV-MKT-SHARE-SINGLE")]:
        if ve in has and g(ve)>0 and mve in has:
            n=g(ve)
            add(f"AIREC-INV-PROMOTE-{name.upper()}",f"Promote available Vishful {name}-sharing inventory",
                [ve,mve],
                f"{n} {name} beds are currently available, and {name}-sharing appears as a published configuration in public market listings.",
                f"Promote the {n} available Vishful {name} beds in relevant channels.",
                "Occupied beds of the promoted sharing type","Medium",
                "Market configuration is context only; no competitor comparison implied.",
                [{"value":n,"evidence_id":ve}],prov="VISHFUL_INTERNAL+MARKET_CONTEXT")

    # ---- guard every recommendation; split passed vs rejected ----
    passed=[]; rejected=[]
    for r in recs:
        ok,reason=guard.check(r,packval)
        if ok:
            rr=dict(r); rr["evidence_ids"]="|".join(r["evidence_ids"]); rr["guard_status"]="passed"; rr.pop("numeric_claims")
            passed.append(rr)
        else:
            rejected.append(dict(recommendation_id=r["recommendation_id"],reason_rejected=reason,
                offending_text=f"{r['opportunity']} :: {r['suggested_action']}"))
    PA=pd.DataFrame(passed); RJ=pd.DataFrame(rejected)
    cols=["recommendation_id","opportunity","evidence_ids","why_it_matters","suggested_action","expected_kpi",
          "confidence","data_limitation","owner_verify_required","provenance","as_of_date","guard_status"]
    (PA[cols] if len(PA) else pd.DataFrame(columns=cols)).to_csv(os.path.join(OUT,"phase4_ai_opportunities.csv"),index=False)
    (RJ if len(RJ) else pd.DataFrame(columns=["recommendation_id","reason_rejected","offending_text"])).to_csv(os.path.join(OUT,"phase4_ai_opportunities_rejected.csv"),index=False)
    pd.DataFrame([dict(metric="recommendations_passed",value=len(passed)),dict(metric="recommendations_rejected",value=len(rejected)),
        dict(metric="evidence_facts",value=len(P)),dict(metric="owner_verify_items",value=int(PA["owner_verify_required"].sum()) if len(PA) else 0)]
        ).to_csv(os.path.join(OUT,"phase4_ai_opportunities_summary.csv"),index=False)

    print(f"PHASE-4 OPPORTUNITIES: passed={len(passed)} rejected={len(rejected)} (from {len(P)} evidence facts)")
    for r in passed: print(f"  [{r['recommendation_id']}] {r['opportunity']} ({r['confidence']})")
    for r in rejected: print(f"  REJECTED [{r['recommendation_id']}] {r['reason_rejected']}")

if __name__=="__main__": main()
