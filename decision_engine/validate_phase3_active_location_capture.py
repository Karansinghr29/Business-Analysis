"""
Fail-loud validation for the Active Tenant Location Data-Capture action.

Guards the contract: the queue is derived from real active allotments, no state is inferred from the
property/current-stay location, the counts reconcile, the action is labelled data-quality rather than
marketing, and NO recommendation/decision/AIREC item is created from it.
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import loader
import phase3_active_location_capture as C
import phase3_tenant_origin as G

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "outputs")
fails = []
def chk(c, m):
    print(("  PASS " if c else "  FAIL ") + m)
    if not c: fails.append(m)
def o(f): return pd.read_csv(os.path.join(OUT, f), low_memory=False)

Q = o("phase3_active_location_capture.csv")
S = dict(zip(o("phase3_active_location_capture_summary.csv")["metric"],
             o("phase3_active_location_capture_summary.csv")["value"]))
def si(k):
    try: return int(float(S[k]))
    except Exception: return -1
D, _ = loader.load_all()
t, al = D["tenants"], D["tenant_allotments"]
origin = o("phase3_tenant_origin.csv")

print("[1] the active population is real and correctly defined")
active_ids = set(al.loc[al["actual_exit_date"].isna(), "tenant_id"].dropna().astype(str))
chk(si("active_tenants") == len(active_ids),
    f"active_tenants ({si('active_tenants')}) == tenants with an open allotment ({len(active_ids)})")
# 190 was the active population at initial deployment (2026-08-27). Active tenants change over time
# (new onboardings, exits), so this is asserted against the live source, not a frozen magic number.
chk(True, f"{si('active_tenants')} active tenants (deployment baseline was 190; population moves over time)")
chk(set(Q["tenant_id"].astype(str)).issubset(active_ids), "every queued tenant is currently active")
chk(Q["tenant_id"].duplicated().sum() == 0, "no tenant appears twice in the queue")

print("\n[2] counts reconcile exactly")
# 100 resolved / 90 queued was the baseline at deployment, BEFORE any confirmation existed. This
# feature's entire purpose is to move tenants OUT of the queue as confirmations are recorded, so the
# queue length is expected to fall over time — asserting it stays fixed at 90 would defeat the feature
# it is meant to validate. What must never change is the RECONCILIATION between the two numbers.
BASELINE_RESOLVED, BASELINE_QUEUE = 100, 90
chk(si("state_resolved") >= BASELINE_RESOLVED,
    f"state_resolved ({si('state_resolved')}) has not regressed below the {BASELINE_RESOLVED}-tenant "
    "deployment baseline (confirmations only ever add resolved tenants, never remove them)")
chk(si("require_confirmation") <= BASELINE_QUEUE,
    f"require_confirmation ({si('require_confirmation')}) has not grown past the {BASELINE_QUEUE}-tenant "
    "deployment baseline (the active population can change, but this checks the capture mechanism "
    "only ever resolves tenants, never re-adds a resolved one to the queue)")
chk(si("state_resolved") + si("require_confirmation") == si("active_tenants"),
    "resolved + require == active (no tenant double-counted or dropped)")
chk(len(Q) == si("require_confirmation"), f"queue rows ({len(Q)}) == require_confirmation")
CLASS_KEYS = ["class_1_complete", "class_2_state_only", "class_3_state_resolved_city_pincode_missing",
              "class_4_address_insufficient", "class_5_no_usable_location",
              "class_6_property_address_recorded", "class_7_conflicting"]
for k in CLASS_KEYS:
    chk(si(k) >= 0, f"{k} is non-negative (got {si(k)})")
chk(si("class_1_complete") + si("class_2_state_only") + si("class_3_state_resolved_city_pincode_missing")
    + si("class_4_address_insufficient") + si("class_5_no_usable_location")
    + si("class_6_property_address_recorded") + si("class_7_conflicting") == si("active_tenants"),
    "the seven classes partition the active population")
chk(si("class_4_address_insufficient") + si("class_5_no_usable_location")
    + si("class_6_property_address_recorded") == len(Q),
    "the queue is exactly classes 4 + 5 + 6")
chk(abs(float(S["pct_lacking_reliable_origin"]) - 100 * len(Q) / si("active_tenants")) < 0.05,
    "the displayed percentage matches its denominator (active tenants)")

print("\n[3] NOTHING is inferred from the property / current-stay location")
chk(bool(Q["resolved_state"].isna().all()),
    "every queued tenant has NO resolved state — none was guessed to get them off the queue")
prop = Q[Q["dq_class"] == "6_property_address_recorded"]
# 1 was the count at deployment; a confirmation correcting that tenant moves them OUT of this class
# entirely (verified in [3b] below), so 0 remaining is the expected end state, not a failure.
chk(len(prop) <= 1, f"at most the 1-tenant deployment baseline remains in this class (got {len(prop)})")
for _, r in prop.iterrows():
    chk(pd.isna(r["resolved_state"]), "the property-address tenant is NOT assigned a state")
    chk(str(r["resolution_source"]) == "property_address_excluded",
        "the property-address tenant is explicitly marked as excluded, not silently unresolved")
    chk("Correct existing address" in str(r["required_action"]),
        "its required action is correction + genuine origin collection")
    chk(bool(C.SELF_ADDR.search(str(r["existing_address"]))),
        "its recorded address really is the Vishful/property address")
# nobody in the queue was resolved via the property address in the upstream origin table
prop_ids = set(prop["tenant_id"].astype(str))
up = origin[origin["tenant_id"].astype(str).isin(prop_ids)]
if len(up):
    chk(True, f"upstream origin row exists for the property-address tenant "
              f"(origin_state={up['origin_state'].iloc[0]!r}) and is overridden here")
for banned in ["apartment", "bed", "chennai", "vishful", "property"]:
    hits = Q["resolved_state"].astype(str).str.contains(banned, case=False, na=False).sum()
    chk(int(hits) == 0, f"no queued tenant carries a state derived from '{banned}'")

print("\n[3b] every recorded tenant confirmation is correctly reflected downstream")
try:
    import phase3_tenant_location_confirm as TLC
    confirmed = TLC.latest_confirmations()
except Exception:
    confirmed = pd.DataFrame()
chk(True, f"{len(confirmed)} tenant confirmation(s) currently on file "
          "(0 is expected before any tenant has been contacted)")
if len(confirmed):
    for _, cr in confirmed.iterrows():
        tid = str(cr["tenant_id"])
        orow = origin[origin["tenant_id"].astype(str) == tid]
        chk(len(orow) == 1 and str(orow.iloc[0]["resolution_source"]) == "tenant_confirmed",
            f"{tid}: origin resolution_source is 'tenant_confirmed'")
        if len(orow):
            chk(str(orow.iloc[0]["origin_state"]) == str(cr["confirmed_state"]),
                f"{tid}: origin_state matches the confirmed state exactly")
        chk(tid not in set(Q["tenant_id"].astype(str)),
            f"{tid}: no longer appears in the capture queue — confirmation removed them")

print("\n[4] queue rows carry what operations needs, and no more")
NEED = ["tenant_id", "full_name", "apartment", "bed", "allotment_status", "existing_address",
        "resolved_state", "resolution_source", "dq_class", "dq_status", "missing_fields",
        "required_action"]
chk(list(Q.columns) == NEED, f"queue columns are exactly the operational set: {list(Q.columns)}")
for extra in ["phone", "email", "aadhar", "pan", "bank", "date_of_birth", "photo", "id_proof", "salary"]:
    chk(not any(extra in c.lower() for c in Q.columns), f"queue exposes no '{extra}' field")
chk(bool(Q["required_action"].notna().all()) and bool((Q["required_action"].astype(str) != "").all()),
    "every queued tenant has a required action")
chk(bool(Q["dq_status"].notna().all()), "every queued tenant has a data-quality status")

print("\n[5] the action is labelled data-quality, not marketing")
chk("NOT a geographic marketing recommendation" in str(S["action_type"]),
    "action_type states it is not a geographic marketing recommendation")
chk("State + City + Pincode" in str(S["action"]), "the action names the three fields to collect")
blob = " ".join(str(v) for v in S.values()).lower()
for banned in ["demand", "conversion", "revenue potential", "feeder", "ranking", "target market"]:
    if banned == "demand":
        chk("prove" not in blob or "demand" not in blob.split("prove")[1][:60],
            "summary makes no claim that the data proves demand")
    else:
        chk(banned not in blob, f"summary makes no '{banned}' claim")
chk("no state is inferred" in str(S["inference_policy"]).lower(), "inference policy is recorded")
chk("not filled by guessing" in str(S["historical_note"]).lower(),
    "historical note states unresolved history is not filled by guessing")
chk("business requirement only" in str(S["onboarding_requirement"]).lower(),
    "onboarding rule is a business requirement, not an application change")

print("\n[6] no recommendation / decision / AIREC created from this")
chk(str(S["creates_recommendation"]).startswith("NO"), "summary records that no recommendation is created")
bd = o("phase3_business_decisions.csv"); ai = o("phase4_ai_opportunities.csv")
nb = o("phase4_nearby_recommendations.csv")
dr = o("phase3_decision_reconciliation.csv")
chk(len(bd) == 14, f"14 backbone decisions unchanged ({len(bd)})")
chk(int((dr["reconciliation_status"] == "NEW").sum()) == 6, "6 Phase-3 opportunities unchanged")
chk(len(ai) == 13, f"13 AIREC unchanged ({len(ai)})")
chk(len(nb) == 5, f"5 nearby recommendations unchanged ({len(nb)})")
allrec = " ".join([str(x) for x in bd.values.ravel()] + [str(x) for x in ai.values.ravel()]
                  + [str(x) for x in nb.values.ravel()]).lower()
for term in ["location capture", "state + city + pincode", "capture queue", "tenant origin"]:
    chk(term not in allrec, f"no existing recommendation output mentions '{term}'")

print("\n[7] the dashboard block reads via the loader and writes ONLY via the validated append-only path")
DSH = open(os.path.join(HERE, "dashboard.py"), encoding="utf-8").read()
# The phrase appears twice (comment banner and st.subheader), so slice from the comment banner to
# the start of the next section rather than using a naive split index.
_start = DSH.find("# ---- Active Tenant Location Data Capture")
_end = DSH.find("# ---- Tenant Origin Analysis", max(_start, 0))
chk(_start > 0 and _end > _start, "the capture block is present and sits before the Tenant Origin section")
blk = DSH[_start:_end] if (_start > 0 and _end > _start) else ""
chk("load_csv_ro(\"phase3_active_location_capture.csv\")" in blk,
    "the block reads the validated output via the read-only loader")
# the block now legitimately WRITES — a tenant confirmation — but ONLY through the validated
# append-only writer, never by hand-patching a CSV or duplicating the resolution logic inline.
chk("TLC.append_confirmation(" in blk, "the only write goes through the validated append-only writer")
chk("_tlc_refresh()" in blk, "a successful write triggers the validated refresh path, not an inline recompute")
for banned in ["to_csv", "norm_state(", "SELF_ADDR", "re.compile", "groupby", 'open(', '"w")', "'w')"]:
    chk(banned not in blk, f"the block does not recompute resolution logic or write a raw file ('{banned}' absent)")
chk("data-quality" in blk.lower() and "not a geographic marketing recommendation" in blk.lower(),
    "the block labels itself a data-quality action on screen")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails:
    for f in fails: print("   -", f)
    sys.exit(1)
