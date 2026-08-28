"""
ACTIVE TENANT LOCATION DATA-CAPTURE QUEUE (deterministic, offline, read-only on sources).

A DATA-QUALITY / BUSINESS-ENABLEMENT action, NOT a geographic marketing recommendation.

Identifies the currently-active tenants whose profile does not carry reliable origin/location
evidence, so State + City + Pincode can be collected or confirmed from the tenant directly.

NOTHING is inferred. A tenant is never assigned a state from the Vishful property address, the
current apartment or bed, the Chennai stay location, a building name, or an ambiguous locality.
The tenant must supply or confirm the genuine residential/origin information.

Reads  tenants + tenant_allotments + apartments + beds (via loader) and the validated
       phase3_tenant_origin.csv resolution, READ-ONLY.
Writes ONLY phase3_active_location_capture.csv + _summary.csv.

Creates no decision, opportunity, AIREC item or recommendation.
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import loader
import phase3_tenant_origin as G

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "outputs")

# The PG's own address. A tenant who recorded this as their permanent address has NOT told us their
# origin — the record must be corrected, never read as Tamil Nadu.
SELF_ADDR = re.compile(r"vista\s*heights|vishful|west\s*avenue|cosmopolitian|cosmopolitan\s*colony", re.I)
PIN_OK = re.compile(r"[1-9]\d{5}")

CLASS_LABEL = {
    "1_complete": "Complete — reliable State + City/Pincode",
    "2_state_only": "State available, City/Pincode missing",
    "3_state_resolved_city_pincode_missing": "State safely resolved from existing evidence; City/Pincode still to confirm",
    "4_address_insufficient": "Address present but location cannot be reliably resolved",
    "5_no_usable_location": "No usable address/location information",
    "6_property_address_recorded": "Vishful/property address recorded as permanent address — correction required",
    "7_conflicting": "Conflicting evidence",
}
ACTION = {
    "1_complete": "None — profile complete",
    "2_state_only": "Collect City + Pincode",
    "3_state_resolved_city_pincode_missing": "Confirm State; collect City + Pincode",
    "4_address_insufficient": "Collect and confirm State + City + Pincode",
    "5_no_usable_location": "Collect and confirm State + City + Pincode",
    "6_property_address_recorded": "Correct existing address + collect genuine permanent/origin location",
    "7_conflicting": "Confirm State + City + Pincode directly with the tenant",
}


def _blank(v):
    return (v is None) or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "" or str(v).lower() == "nan"


def main():
    D, _ = loader.load_all()
    t, al, ap, bd = D["tenants"], D["tenant_allotments"], D["apartments"], D["beds"]
    origin = pd.read_csv(os.path.join(OUT, "phase3_tenant_origin.csv"),
                         low_memory=False)[["tenant_id", "origin_state", "resolution_source"]]

    # ---- currently-active tenants: at least one allotment with no recorded exit ----
    act = al[al["actual_exit_date"].isna()].copy()
    act["apartment"] = act["apartment_id"].map(dict(zip(ap["id"], ap["apartment_code"])))
    act["bed"] = act["bed_id"].map(dict(zip(bd["id"], bd["bed_code"])))
    cur = (act.sort_values(["onboarding_date", "id"], kind="mergesort").groupby("tenant_id")
              .agg(apartment=("apartment", "last"), bed=("bed", "last"),
                   allotment_status=("staying_status", "last")))

    A = origin.merge(cur, left_on="tenant_id", right_index=True, how="inner")
    A = A.merge(t[["id", "full_name", "state", "city", "pincode", "permanent_address", "address"]],
                left_on="tenant_id", right_on="id", how="left").drop(columns=["id"])

    A["existing_address"] = A["permanent_address"].fillna(A["address"])
    A["is_property_address"] = (A["existing_address"].astype(str).str.contains(SELF_ADDR, na=False)
                                & ~A["existing_address"].map(_blank))
    # The property address is never origin evidence — EXCEPT where a tenant has since directly
    # confirmed their real State/City/Pincode. A confirmation is the correction for exactly this
    # case (dq_class 6): the STORED address field stays the stale Vishful text (source CSVs are
    # never edited), but the confirmed value is authoritative and must not be wiped by this rule.
    A["is_confirmed"] = A["resolution_source"] == "tenant_confirmed"
    A["resolved_state"] = A["origin_state"].where(~A["is_property_address"] | A["is_confirmed"])
    A["resolution_source"] = A["resolution_source"].where(
        ~A["is_property_address"] | A["is_confirmed"], "property_address_excluded")

    A["has_state"] = [(not _blank(v)) and (G.norm_state(v) is not None) for v in A["state"]]
    A["has_city"] = [not _blank(v) for v in A["city"]]
    A["has_pincode"] = [bool(PIN_OK.fullmatch(str(v).strip().replace(".0", ""))) for v in A["pincode"]]
    A["has_address"] = [not _blank(v) for v in A["existing_address"]]

    def classify(r):
        # A direct tenant confirmation is complete by definition — it supersedes even the
        # property-address flag, which exists precisely to catch the case a confirmation corrects.
        if r["is_confirmed"]: return "1_complete"
        if r["is_property_address"]: return "6_property_address_recorded"
        if r["resolution_source"] == "conflicting_evidence": return "7_conflicting"
        if r["has_state"] and (r["has_city"] or r["has_pincode"]): return "1_complete"
        if r["has_state"]: return "2_state_only"
        if pd.notna(r["resolved_state"]): return "3_state_resolved_city_pincode_missing"
        if r["has_address"]: return "4_address_insufficient"
        return "5_no_usable_location"

    A["dq_class"] = A.apply(classify, axis=1)
    A["dq_status"] = A["dq_class"].map(CLASS_LABEL)
    A["required_action"] = A["dq_class"].map(ACTION)
    A["missing_fields"] = ["|".join([f for f, ok in
                                     (("state", r["has_state"]), ("city", r["has_city"]),
                                      ("pincode", r["has_pincode"]), ("address", r["has_address"]))
                                     if not ok]) or "none" for _, r in A.iterrows()]
    # capture queue = every active tenant whose origin is NOT reliably known
    A["in_capture_queue"] = A["resolved_state"].isna()

    COLS = ["tenant_id", "full_name", "apartment", "bed", "allotment_status",
            "existing_address", "resolved_state", "resolution_source",
            "dq_class", "dq_status", "missing_fields", "required_action"]
    Q = A[A["in_capture_queue"]][COLS].sort_values(["dq_class", "apartment", "bed"], kind="mergesort")
    Q.to_csv(os.path.join(OUT, "phase3_active_location_capture.csv"), index=False)

    n = len(A); res = int(A["resolved_state"].notna().sum()); q = len(Q)
    c = A["dq_class"].value_counts()
    summary = [
        ("active_tenants", n),
        ("state_resolved", res),
        ("require_confirmation", q),
        ("pct_lacking_reliable_origin", round(100 * q / n, 1)),
        ("class_1_complete", int(c.get("1_complete", 0))),
        ("class_2_state_only", int(c.get("2_state_only", 0))),
        ("class_3_state_resolved_city_pincode_missing", int(c.get("3_state_resolved_city_pincode_missing", 0))),
        ("class_4_address_insufficient", int(c.get("4_address_insufficient", 0))),
        ("class_5_no_usable_location", int(c.get("5_no_usable_location", 0))),
        ("class_6_property_address_recorded", int(c.get("6_property_address_recorded", 0))),
        ("class_7_conflicting", int(c.get("7_conflicting", 0))),
        ("apartments_affected", int(Q["apartment"].nunique())),
        ("action", "Collect and confirm State + City + Pincode for the active tenants in the capture queue"),
        ("action_type", "data quality / business enablement — NOT a geographic marketing recommendation"),
        ("inference_policy", "no state is inferred from the property address, current apartment/bed, "
                             "the Chennai stay location, building names or ambiguous localities; the "
                             "tenant must supply or confirm the genuine residential/origin information"),
        ("historical_note", "historical origin remains partially unresolved and is NOT filled by guessing; "
                            "only current active tenant data can be improved through direct collection"),
        ("onboarding_requirement", "new tenant onboarding should require State, City and Pincode; existing "
                                   "active tenants should be prompted to confirm the same fields "
                                   "(business requirement only — no application code changed)"),
        ("creates_recommendation", "NO — this action creates no decision, opportunity or AIREC item"),
    ]
    pd.DataFrame(summary, columns=["metric", "value"]).to_csv(
        os.path.join(OUT, "phase3_active_location_capture_summary.csv"), index=False)

    print("PHASE-3 ACTIVE TENANT LOCATION DATA CAPTURE:")
    for k, v in summary: print(f"  {k}: {v}")
    print(f"\n  capture queue by class:")
    for k, v in Q["dq_class"].value_counts().sort_index().items():
        print(f"    {CLASS_LABEL[k]:70} {int(v):4}")


if __name__ == "__main__":
    main()
