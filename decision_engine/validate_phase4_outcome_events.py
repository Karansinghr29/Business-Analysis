"""Fail-loud validation of the append-only owner outcome-event layer. Exercises the writer against an ISOLATED
temp store (never pollutes the real operational store). Verifies append-only + reject-invalid + referential rules."""
from __future__ import annotations
import os, sys, csv, tempfile
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import phase4_action_capture as W
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
def rejects(fn,label):
    try: fn(); chk(False,f"should REJECT: {label}")
    except ValueError: chk(True,f"rejected invalid: {label}")
    except Exception as e: chk(False,f"{label}: wrong exception {e}")

print("[1] real store: header correct, no fabricated events")
W.ensure_store()
rows=W._rows(W.STORE)
with open(W.STORE,newline="",encoding="utf-8") as f: hdr=next(csv.reader(f))
chk(hdr==W.COLUMNS,"real store header == schema COLUMNS")
chk(len(rows)==0,f"real operational store has NO fabricated events (rows={len(rows)})")
chk(not W.STORE.startswith(OUT) and "operational" in W.STORE,"store lives OUTSIDE outputs/ (excluded from --verify)")

# ----- isolated temp store for behavioural tests -----
tmp=os.path.join(tempfile.mkdtemp(),"ev.csv")
bb=list(pd.read_csv(os.path.join(OUT,"phase3_decision_execution_analytics.csv"))["decision_id"].astype(str))[0]
airec=list(pd.read_csv(os.path.join(OUT,"phase4_ai_opportunities.csv"))["recommendation_id"].astype(str))[0]
kpi=pd.read_csv(os.path.join(OUT,"phase4_kpi_direction_registry.csv")); k0=kpi.iloc[0]["kpi_name"]; u0=str(kpi.iloc[0]["unit"])

print("\n[2] valid events accepted; ids monotonic; append-only")
e1=W.append_event({"recommendation_id":bb,"event_type":"owner_decision","event_date":"2026-08-20","owner_decision":"approved"},store=tmp,recorded_at="T0")
e2=W.append_event({"recommendation_id":bb,"event_type":"action_taken","event_date":"2026-08-21","action_taken":"Called 90+ tenants"},store=tmp,recorded_at="T0")
e3=W.append_event({"recommendation_id":bb,"event_type":"measurement","event_date":"2026-08-21","target_kpi":k0,"unit":u0,"value":"800503","measurement_role":"baseline","source":"system_measured"},store=tmp,recorded_at="T0")
e4=W.append_event({"recommendation_id":airec,"event_type":"measurement","event_date":"2026-09-20","target_kpi":k0,"unit":u0,"value":"","measurement_role":"post_action","notes":W.UNAVAIL},store=tmp,recorded_at="T0")
e5=W.append_event({"recommendation_id":"AI-FUTURE-01","event_type":"note","event_date":"2026-08-21","notes":"future AI-* id accepted"},store=tmp,recorded_at="T0")
e6=W.append_event({"recommendation_id":bb,"event_type":"correction","event_date":"2026-08-22","supersedes_event_id":e3,"notes":"baseline corrected"},store=tmp,recorded_at="T0")
chk([e1,e2,e3,e4,e5,e6]==["EVT-000001","EVT-000002","EVT-000003","EVT-000004","EVT-000005","EVT-000006"],"event_ids unique + monotonic")
rr=W._rows(tmp); chk(len(rr)==6,"all 6 valid events appended")
chk(len({r["event_id"] for r in rr})==6,"event_id unique in store")
# append-only: re-read; earlier rows unchanged after later appends
chk(rr[0]["owner_decision"]=="approved" and rr[2]["value"]=="800503","earlier events immutable after later appends")
chk(rr[3]["value"]=="" and W.UNAVAIL in rr[3]["notes"],"Unavailable measurement stored empty value (never 0)")

print("\n[3] invalid events REJECTED (no silent fix)")
rejects(lambda:W.append_event({"recommendation_id":bb,"event_type":"BOGUS","event_date":"2026-08-21"},store=tmp),"bad event_type")
rejects(lambda:W.append_event({"recommendation_id":"NOPE-123","event_type":"note","event_date":"2026-08-21","notes":"x"},store=tmp),"unknown recommendation_id")
rejects(lambda:W.append_event({"recommendation_id":bb,"event_type":"measurement","event_date":"2026-08-21","target_kpi":"NOT-A-KPI","value":"1","measurement_role":"baseline"},store=tmp),"target_kpi not in registry")
rejects(lambda:W.append_event({"recommendation_id":bb,"event_type":"measurement","event_date":"2026-08-21","target_kpi":k0,"unit":"WRONG","value":"1","measurement_role":"baseline"},store=tmp),"unit mismatch vs registry")
rejects(lambda:W.append_event({"recommendation_id":bb,"event_type":"owner_decision","event_date":"2026-08-21","owner_decision":"maybe"},store=tmp),"invalid owner_decision value")
rejects(lambda:W.append_event({"recommendation_id":bb,"event_type":"measurement","event_date":"2026-08-21","target_kpi":k0,"unit":u0,"value":"","measurement_role":"baseline"},store=tmp),"empty measurement without Unavailable note")
rejects(lambda:W.append_event({"recommendation_id":bb,"event_type":"measurement","event_date":"2026-08-21","target_kpi":k0,"unit":u0,"value":"abc","measurement_role":"baseline"},store=tmp),"non-numeric value")
rejects(lambda:W.append_event({"recommendation_id":bb,"event_type":"correction","event_date":"2026-08-21","supersedes_event_id":"EVT-999999","notes":"x"},store=tmp),"correction references missing event")
rejects(lambda:W.append_event({"recommendation_id":bb,"event_type":"action_taken","event_date":"2026-08-21"},store=tmp),"action_taken without action text")

print("\n[4] rejections did not append; store still 6 rows; real store untouched")
chk(len(W._rows(tmp))==6,"invalid events were NOT appended (append-only integrity)")
chk(len(W._rows(W.STORE))==0,"REAL operational store still empty (temp used for tests, not polluted)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
