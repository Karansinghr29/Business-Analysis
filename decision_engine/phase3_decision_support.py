"""
Phase-3 DECISION SUPPORT (isolated, deterministic, read-only).

Consolidates the EXISTING review-derived intelligence into one owner-readable
Observation -> Evidence -> Business implication -> Possible Vishful action table.
Decision SUPPORT only — never an automatic decision, never a competitor ranking, never "Vishful should charge Rs X".

Sources (already built in earlier phases; not modified):
  phase3_review_intelligence_audit.csv     (9 amenity/service topics vs Vishful's own tickets)
  phase3_review_decision_candidates.csv    (16 review-signal candidates with evidence strength)

Writes ONLY phase3_decision_support.csv.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
IA=o("phase3_review_intelligence_audit.csv"); RC=o("phase3_review_decision_candidates.csv")
DISCLAIMER="Decision support — not an automatic business decision. Market context only; no competitor ranking."

def main():
    rows=[]
    for _,r in IA.iterrows():
        rows.append(dict(source="review_intelligence_audit", topic=str(r["topic"]),
            observation=str(r["market_signal"]),
            evidence=str(r.get("evidence") or r.get("own_complaint_tickets") or ""),
            business_implication=str(r["business_implication"]),
            possible_vishful_action=str(r["candidate_action"]), disclaimer=DISCLAIMER))
    for _,r in RC.iterrows():
        rows.append(dict(source="review_decision_candidate", topic=str(r["theme"]),
            observation=str(r["market_signal"]),
            evidence=str(r["evidence_strength"])+" | "+str(r.get("vishful_internal_fact") or ""),
            business_implication=str(r["business_relevance"]),
            possible_vishful_action=str(r["recommended_decision"]), disclaimer=DISCLAIMER))
    D=pd.DataFrame(rows)[["source","topic","observation","evidence","business_implication","possible_vishful_action","disclaimer"]]
    D=D.drop_duplicates().reset_index(drop=True)
    # guardrail: no competitor ranking / no explicit Vishful rent recommendation
    blob=" ".join(map(str,D.values.ravel())).lower()
    for bad in ["better than vishful","worse than vishful","rank ","best competitor","vishful should charge","set vishful price","charge rs","charge ₹"]:
        assert bad not in blob, f"forbidden phrase in decision support: {bad}"
    D.to_csv(os.path.join(OUT,"phase3_decision_support.csv"),index=False)
    print("PHASE-3 DECISION SUPPORT:")
    print(f"  rows: {len(D)} (from {len(IA)} audit topics + {len(RC)} review candidates)")
    print(f"  sources: {dict(D['source'].value_counts())}")
    print("  every row carries the decision-support disclaimer; no ranking; no explicit Vishful price recommendation.")

if __name__=="__main__": main()
