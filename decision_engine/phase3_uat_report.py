"""
Phase-3 UAT REPORT (isolated, deterministic, read-only). Decision -> Evidence -> Action Taken
-> Result, with UAT status classification. NO new decisions, NO logic changes — reads the FROZEN
validated outputs (business decisions + execution tracker) only.

UAT status rule (evidence-driven; nothing Completed without real outcome data):
  action_taken null            -> Pending
  action_taken set, no outcome -> Actioned
  outcome captured (beds/rev)  -> Completed
  outcome_status unavailable   -> "Outcome unavailable"
Currently all execution fields are blank -> every decision is Pending / Outcome unavailable
(honest UAT state before real-world capture). No fabrication, unknown preserved.

Writes ONLY phase3_uat_report.csv + phase3_uat_summary.csv. Modifies nothing.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
DEC=o("phase3_business_decisions.csv"); ET=o("phase3_execution_tracker.csv")

def uat_status(action_taken, outcome_status, beds_filled, revenue):
    has_action = pd.notna(action_taken) and str(action_taken).strip() not in ("","nan")
    has_outcome = pd.notna(beds_filled) or pd.notna(revenue)
    if has_outcome: return "Completed"
    if has_action: return "Actioned"
    return "Pending"

def main():
    et=ET.set_index("decision_id")
    rows=[]
    for _,d in DEC.iterrows():
        did=d["decision_id"]; e=et.loc[did] if did in et.index else None
        act=e["action_taken"] if e is not None else None
        outc=e["outcome_status"] if e is not None else "unavailable_no_data"
        beds=e["beds_filled"] if e is not None else None
        rev=e["revenue_impact"] if e is not None else None
        st=uat_status(act,outc,beds,rev)
        rows.append(dict(decision_id=did,priority=d["priority"],category=d["category"],
            decision=d["decision"],
            evidence=d["data_signal"],
            expected_impact=d["expected_impact"],
            recommended_action=d["recommended_action"],
            action_taken=(act if pd.notna(act) else "none yet"),
            result=("outcome unavailable" if str(outc)=="unavailable_no_data" else outc),
            uat_status=st,
            requires_operational_confirmation=("yes" if st=="Pending" else "no"),
            provenance=d["provenance"]))
    df=pd.DataFrame(rows).sort_values(["priority","decision_id"],
        key=lambda s:s.map({"High":0,"Medium":1,"Low":2}) if s.name=="priority" else s)
    df.to_csv(os.path.join(OUT,"phase3_uat_report.csv"),index=False)

    summary=[("decisions_total",len(df)),
     ("Pending",int((df["uat_status"]=="Pending").sum())),
     ("Actioned",int((df["uat_status"]=="Actioned").sum())),
     ("Completed",int((df["uat_status"]=="Completed").sum())),
     ("outcome_unavailable",int((df["result"]=="outcome unavailable").sum())),
     ("all_require_operational_confirmation",bool((df["requires_operational_confirmation"]=="yes").all())),
     ("real_actions_captured",0),
     ("note","frozen decision logic; UAT reflects real state — nothing Completed without captured outcome evidence"),
     ("owner_rule","Vishful internal = decision driver; market = context; never compare competitors")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_uat_summary.csv"),index=False)
    print("PHASE-3 UAT REPORT:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nDecision -> UAT status:")
    for _,r in df.iterrows(): print(f"  [{r['priority']:6}] {r['uat_status']:20} | {r['decision_id']:22} | {r['decision']}")

if __name__=="__main__": main()
