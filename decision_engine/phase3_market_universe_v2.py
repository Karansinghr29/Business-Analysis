"""
Phase-3 MARKET UNIVERSE v2 (isolated, deterministic, read-only).

Versioned property universe for the target-market locations. Does NOT modify the 115-property baseline
(phase3_competitor_master) or any existing calculation/denominator — it is a NEW isolated dataset.

  v1 (baseline, IMMUTABLE) = the original 115 competitors (phase3_competitor_master).
  v2 (verified)            = 115 v1 + 44 verified high-confidence NEW independents + 9 verified in-target Zolo
                             properties (operator:Zolo)  -> 168 verified rows.
  HOLDOUT (outside v2 calc) = 78 medium-confidence (unverified) + 2 possible_duplicate + 5 low-review.

Additions are frozen in phase3_universe_v2_additions.json (identity-verified during the target-locality
platform sweep + browser-rendered Zolo pages). Zolo rows are tagged operator:Zolo and NOT merged into any
existing property. Writes ONLY phase3_market_universe_v2.csv + phase3_market_universe_v2_holdout.csv (+ _summary).
"""
from __future__ import annotations
import os, sys, json
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
M=pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv"))
ADD=json.load(open(os.path.join(HERE,"phase3_universe_v2_additions.json"),encoding="utf-8"))
COLS=["property_name","locality","address","pincode","operator","operator_source_type","identity_confidence",
      "universe_version","source_platform","source_url","sharing_type","published_rent","amenities","provenance","status"]
OPERATOR_TOKENS={"yube1":"Yube1","stanza":"Stanza Living","truliv":"Truliv","zolo":"Zolo","bag2bag":"Bag2Bag",
                 "wowlife":"WowLife","olympia":"Olympia","lancor":"Lancor","prohotel":"Prohotel"}
def baseline_row(r):
    nm=str(r["competitor_name"]); low=nm.lower()
    op="independent"; ost="independent"
    if str(r.get("evidence_class"))=="operator_aggregator" or any(k in low for k in OPERATOR_TOKENS):
        brand=next((v for k,v in OPERATOR_TOKENS.items() if k in low),"operator")
        op=brand; ost=f"operator:{brand}"
    return dict(property_name=nm,locality=str(r.get("locality") or ""),address="",pincode=str(r.get("pincode") or ""),
        operator=op,operator_source_type=ost,identity_confidence="baseline",universe_version="v1",
        source_platform="master (phase1 discovery)",source_url=str(r.get("official_url") or ""),
        sharing_type="",published_rent="",amenities="",
        provenance=str(r.get("provenance") or "phase3_competitor_master baseline"),status="baseline")

def main():
    base=[baseline_row(r) for _,r in M.iterrows()]
    verified_add=[{k:a.get(k,"") for k in COLS} for a in ADD if a["status"]=="verified"]
    holdout=[{k:a.get(k,"") for k in COLS} for a in ADD if a["status"]!="verified"]

    v2=pd.DataFrame(base+verified_add)[COLS]
    hold=pd.DataFrame(holdout)[COLS]
    # guardrails
    assert len(base)==115, "baseline must be 115"
    assert set(M["competitor_name"]).issubset(set(v2["property_name"])), "all 115 baseline names must survive in v2"
    assert v2["property_name"].is_unique, "duplicate property in v2 (fuzzy-dedup should have caught it)"
    assert not (hold["status"]=="verified").any(), "holdout must contain no verified rows"
    v2.to_csv(os.path.join(OUT,"phase3_market_universe_v2.csv"),index=False)
    hold.to_csv(os.path.join(OUT,"phase3_market_universe_v2_holdout.csv"),index=False)

    n_ind=sum(1 for a in verified_add if a["operator_source_type"]=="independent")
    n_zolo=sum(1 for a in verified_add if a["operator"]=="Zolo")
    summary=[("v1_baseline_immutable",115),("v2_verified_total",len(v2)),
     ("new_independents_verified",n_ind),("new_zolo_verified",n_zolo),
     ("holdout_medium_unverified",int((hold['status']=='unverified').sum())),
     ("holdout_possible_duplicate",int((hold['status']=='possible_duplicate').sum())),
     ("holdout_low_review",int((hold['status']=='low_review').sum())),
     ("note","v1 immutable; v2 is isolated and NOT used by any existing denominator/score; holdout excluded from all calculations; Zolo tagged operator:Zolo, never merged into an existing property")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_market_universe_v2_summary.csv"),index=False)
    print("PHASE-3 MARKET UNIVERSE v2:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nv2 by version:",dict(v2["universe_version"].value_counts()))
    print("v2 operator_source_type (verified additions):", {k:v for k,v in pd.Series([a['operator_source_type'] for a in verified_add]).value_counts().items()})

if __name__=="__main__": main()
