"""
Phase-3 VISHFUL AMENITY PROVENANCE (isolated, deterministic, read-only).

Classifies EACH amenity into exactly one Vishful-own bucket, plus a separate competitor market-context column:

  1 VISHFUL_INTERNAL_VERIFIED       - Vishful's own validated internal data confirms Vishful provides it.
  2 VISHFUL_PUBLIC_EXPLICIT         - Vishful's own public first-party site EXPLICITLY advertises it as a property amenity.
  3 VISHFUL_PUBLIC_NEARBY_CONTEXT   - Vishful's site mentions a nearby service/vendor (location context ONLY, not a Vishful amenity).
  4 MARKET_FIRST_PARTY_CONTEXT      - competitors' own first-party sites publish it (market context ONLY; separate column).
  5 UNKNOWN                          - none of the above.

Vishful public first-party wording captured from the JS-RENDERED site https://vishful.co.in/ (WHY VISHFUL / AMENITIES
sections) via the in-app browser (SPA — not readable by plain WebFetch). Exact quotes frozen below (deterministic).
Security/CCTV and Parking are advertised as property amenities -> VISHFUL_PUBLIC_EXPLICIT. Food is advertised only as
"Food Vendors Nearby" -> VISHFUL_PUBLIC_NEARBY_CONTEXT (NOT a Vishful Food amenity). AC and Wi-Fi are already
VISHFUL_INTERNAL_VERIFIED (own assets/services), also publicly listed. Competitor prevalence is NEVER used to
establish a Vishful amenity. Writes ONLY phase3_vishful_amenity_provenance.csv.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
SA=pd.read_csv(os.path.join(OUT,"phase3_vishful_self_audit.csv"))
BUCKETS=["VISHFUL_INTERNAL_VERIFIED","VISHFUL_PUBLIC_EXPLICIT","VISHFUL_PUBLIC_NEARBY_CONTEXT",
         "MARKET_FIRST_PARTY_CONTEXT","UNKNOWN"]
INTERNAL_ATTR={"AC":"AC (air conditioning)","Wi-Fi":"Wi-Fi / Internet",
 "Food":"Food / catered meals","Parking":"Parking","Security/CCTV":"CCTV / security"}
MARKET={"AC":"3/6","Wi-Fi":"5/6","Food":"4/6","Parking":"3/6","Security/CCTV":"2/6"}
PUB_URL="https://vishful.co.in/ (first-party, JS-rendered; captured via in-app browser)"
# frozen exact first-party wording from vishful.co.in rendered page
PUBLIC_EXPLICIT={
 "Security/CCTV":'"CCTV Security — Round-the-clock surveillance across all floors and entrances."',
 "Parking":'AMENITIES section lists "Parking" (property amenity, alongside Study Lounge / Gaming Zone / Rooftop Area / Smart TVs).',
 "AC":'"AC Rooms — Stay cool year-round with individual AC controls in every room."',
 "Wi-Fi":'"High-Speed WiFi — Dedicated fiber broadband with uninterrupted connectivity."',
}
PUBLIC_NEARBY={
 "Food":'"Food Vendors Nearby — Multiple trusted vendors serving all cuisines…" = nearby vendors (location convenience), NOT a Vishful-provided food service. FAQ only asks "Is food included in the rent?" (a question, not a claim).',
}
def internal_status(attr):
    r=SA[SA["attribute"]==attr]
    if not len(r): return ("UNKNOWN","attribute not in self-audit")
    x=r.iloc[0]; return (str(x["status"]), str(x["evidence"])[:150])

def main():
    rows=[]
    for amen,attr in INTERNAL_ATTR.items():
        st,ev=internal_status(attr)
        verified=(st=="VERIFIED_PRESENT")
        if verified:
            bucket="VISHFUL_INTERNAL_VERIFIED"
            pub=("also publicly advertised: "+PUBLIC_EXPLICIT[amen]) if amen in PUBLIC_EXPLICIT else "—"
            owner="Vishful provides this — internally verified (own assets/services). Safe to highlight in marketing."
        elif amen in PUBLIC_NEARBY:
            bucket="VISHFUL_PUBLIC_NEARBY_CONTEXT"
            pub=PUBLIC_NEARBY[amen]
            owner=("Vishful's site mentions this only as a NEARBY service (location convenience) — NOT a Vishful-"
                   "provided amenity. Do NOT market it as a Vishful amenity; internal provision evidence is absent.")
        elif amen in PUBLIC_EXPLICIT:
            bucket="VISHFUL_PUBLIC_EXPLICIT"
            pub=PUBLIC_EXPLICIT[amen]
            owner=("Vishful's OWN public first-party site explicitly advertises this as a property amenity (first-party "
                   "public evidence, kept separate from internal validation). Safe to market as advertised; confirm "
                   "internally for operational assurance. Competitor prevalence is NOT the basis for this.")
        else:
            bucket="UNKNOWN"; pub="not found on Vishful first-party site"
            owner="Vishful's own provision not confirmed (no internal evidence, not on Vishful's public site). Verify before marketing."
        rows.append(dict(amenity=amen,vishful_own_bucket=bucket,
            internal_status=("CONFIRMED" if verified else "UNKNOWN"),
            internal_evidence=ev, internal_source="phase3_vishful_self_audit.csv",
            vishful_public_wording=pub, vishful_public_source=PUB_URL,
            market_context_bucket="MARKET_FIRST_PARTY_CONTEXT",
            market_context_evidence=f"{amen} published on {MARKET[amen]} eligible first-party amenity-evidence sources [the '6' = the 6 competitors whose own first-party sites carried renderable amenity evidence; only 6 of the 115-property research universe met that criteria — NOT 6 of 115 PGs] (context only; NOT a Vishful claim, NOT demand proof)",
            owner_decision_status=owner))
    D=pd.DataFrame(rows)
    assert set(D["vishful_own_bucket"]).issubset(set(BUCKETS)),"invalid bucket"
    # guardrails: Food must stay NEARBY_CONTEXT; competitor evidence never sets a Vishful bucket
    assert D[D["amenity"]=="Food"]["vishful_own_bucket"].iloc[0]=="VISHFUL_PUBLIC_NEARBY_CONTEXT","Food must be NEARBY_CONTEXT"
    assert D[D["amenity"]=="Security/CCTV"]["vishful_own_bucket"].iloc[0]=="VISHFUL_PUBLIC_EXPLICIT","Security must be PUBLIC_EXPLICIT"
    assert D[D["amenity"]=="Parking"]["vishful_own_bucket"].iloc[0]=="VISHFUL_PUBLIC_EXPLICIT","Parking must be PUBLIC_EXPLICIT"
    D.to_csv(os.path.join(OUT,"phase3_vishful_amenity_provenance.csv"),index=False)
    print("PHASE-3 VISHFUL AMENITY PROVENANCE (5-bucket, first-party verified):")
    print(D[["amenity","vishful_own_bucket","internal_status"]].to_string(index=False))

if __name__=="__main__": main()
