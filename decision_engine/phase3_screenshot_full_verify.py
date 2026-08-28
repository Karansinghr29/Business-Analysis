"""
Phase-3 EXPERIMENTAL — FINAL per-candidate verification for EVERY Vishful dashboard
screenshot name (no candidate dropped). Screenshot = candidate_name source ONLY.

Groq compound-mini used as discovery assistant (rate-limited on some); EVERY finding below
comes from INDEPENDENT WebSearch/WebFetch (aggregators/social/maps/OTA blocked or excluded as
first-party pricing). No Groq URL trusted without independent check.

Outcome across all passes: first-party per-bed x sharing x AC PG price sources = 0. A handful
of own websites exist (PG own-sites + serviced-apt own-sites + operator portals) but none
publishes per-bed PG rent; serviced/hotel sites show NIGHTLY rates (never converted to monthly).
Every candidate carries a final verification_status; price=unknown unless a first-party per-bed
price was published (none was).

Writes ONLY outputs/phase3_screenshot_full_verify.csv (+ summary). Isolated: does not touch
dashboard / locked outputs / existing phase3 research / OSM outputs.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from phase3_screenshot_candidates import NAMES, classify, dist  # reuse verbatim names + classifier + coarse distance

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
CSV=os.path.join(OUT,"phase3_screenshot_full_verify.csv")
SUMM=os.path.join(OUT,"phase3_screenshot_full_verify_summary.csv")

# key-substring -> verification record. Every value independently confirmed this session.
# fp_url = first-party OWN domain (verified); fp_price_usable always False (no per-bed price published).
V = {
 # PG own-sites (verified real, own domain, NO per-bed price on-site)
 "tsp":            ("verified_real_first_party_site","https://tsppgaccommodation.com/",True,"own PG site; enquiry only, no per-bed price"),
 "kripa":          ("verified_real_first_party_site","https://kripahomes.com/pg-thiruvanmiyur/",True,"own PG site; sharing tiers shown, no price"),
 "sri mahalakshmi":("verified_real_first_party_site","https://mahalakshmipgaccommodation.com/",True,"own PG site; no per-bed price"),
 "season 4":       ("verified_real_first_party_site","https://season4.in/season-4-rentals-thiruvanmiyur/",True,"own serviced-apt site; daily/monthly basis, price behind booking link"),
 # serviced-apt own-sites (verified real, own domain, NIGHTLY only -> not per-bed, rejected)
 "kolam gandhi":   ("verified_real_first_party_site","https://kolamapartments.com/",True,"own serviced-apt site; nightly rate only (not per-bed) -> rejected"),
 "olive serviced": ("verified_real_first_party_site","https://oliveservicedapartments.com/chennai",True,"own serviced-apt site; nightly rate only -> rejected"),
 # operator portals (own site but OPERATOR -> rejected as first-party independent pricing)
 "yube1":          ("verified_operator_site_rejected","https://yube1.in/",True,"operator portal (not independent competitor first-party price)"),
 "stanza":         ("verified_operator_site_rejected","https://www.stanzaliving.com/",True,"operator/aggregator portal -> rejected"),
 "truliv":         ("verified_operator_site_rejected","https://truliv.in/",True,"operator portal -> rejected"),
 # hotels / serviced with OTA presence only (verified real; no independent first-party per-bed)
 "skylinn":        ("verified_real_no_independent_first_party",None,False,"real hotel (Kottivakkam 600041, 'Unit of Prohotel'); OTA listings only; nightly"),
 "staylite":       ("verified_real_no_independent_first_party",None,False,"real hotel OMR; OTA only; nightly"),
 "stay easy":      ("verified_real_no_independent_first_party",None,False,"real budget hotel (Prohotel); OTA only; nightly"),
 "swarna sudarshan":("verified_real_no_independent_first_party",None,False,"serviced apt (Sholinganallur/Adyar); OTA only; nightly"),
 "yali":           ("verified_real_no_independent_first_party",None,False,"serviced apt (Palavakkam 600041); OTA only; ~Rs.1550/night"),
 "mg park":        ("verified_real_no_independent_first_party",None,False,"2-star hotel Thiruvanmiyur; OTA only"),
 # verified-real PGs, listings only, NO own site
 "sree siddhi vinayaka":("verified_real_no_first_party",None,False,"REAL: CBI Colony Perungudi 600096, ph 9557795579; listings only"),
 "ojas grand":     ("verified_real_no_first_party",None,False,"REAL: Thiruvengadam Nagar Perungudi 600096, ph 9789833624; aggregators only"),
 "sahithyan":      ("exists_described_no_first_party",None,False,"described on directories (3-bed, meals); 'sahithyanpg.com' was hallucinated -> rejected"),
 "subodhaya":      ("verified_real_no_first_party",None,False,"REAL ladies PG Thiruvanmiyur; directory listing only"),
 # existing-pool / dashboard-tracked, listings-only
 "zara":           ("verified_real_no_first_party",None,False,"co-living men's PG (existing tracked); listings only"),
 "eden":           ("verified_real_no_first_party",None,False,"co-living (existing tracked); listings only"),
 "green apple":    ("verified_real_no_first_party",None,False,"Perungudi (existing tracked); listings only"),
 "whites inn":     ("verified_real_no_independent_first_party",None,False,"hotel (existing tracked); OTA only"),
 "sri venkata vishnu priya":("verified_real_no_first_party",None,False,"gents hostel Kattankulathur (existing tracked); listings only"),
 "aostel":         ("verified_real_no_first_party",None,False,"men's PG Anna Salai (existing tracked); listings only"),
 # searched, identity NOT independently confirmed / no first-party
 "sasikala":       ("identity_unconfirmed_no_first_party",None,False,"no authoritative listing/own site found"),
 "excellent men":  ("identity_unconfirmed_no_first_party",None,False,"Groq wrongly mapped to Emy PG; no distinct own site"),
 "bhavani":        ("identity_unconfirmed_no_first_party",None,False,"Groq 429; no distinct listing/own site"),
 "sneha":          ("identity_weak_no_first_party",None,False,"no own domain"),
 "best men":       ("identity_unconfirmed_generic_name",None,False,"Groq 413; generic name, no distinct listing"),
 "sv pg":          ("identity_ambiguous_possible_out_of_area",None,False,"an 'SV PG' at Arumbakkam 600106 (out of area); likely different property"),
 "naveens hifi":   ("identity_unconfirmed_no_first_party",None,False,"no own site/authoritative listing found"),
 "ganapathi pg for women":("identity_unconfirmed_no_first_party",None,False,"no own site found"),
}

def lookup(name):
    n=name.lower()
    for k,v in V.items():
        if k in n: return v
    return ("not_independently_web_verified", None, False,
            "transcribed name; not individually web-verified this pass (far >5km / lower priority)")

def main():
    rows=[]; seen=set()
    for name,loc in NAMES:
        key=name.strip().lower()
        if key in seen: continue
        seen.add(key)
        is_self = "vista heights" in key or "vishful" in key
        if is_self:
            continue  # self, excluded from competitor universe
        ptype,is_op,seg = classify(name)
        km,prec,w1,w2,w3,w5 = dist(loc)
        status,fp_url,fp_ver,note = lookup(name)
        reject = is_op or ptype in ("hotel","serviced_apartment") or status=="verified_operator_site_rejected"
        rows.append(dict(
            candidate_name=name, property_type=ptype, gender=seg, dashboard_locality=loc,
            distance_km=km, distance_precision=prec,
            within_1km=w1, within_2km=w2, within_3km=w3, within_5km=w5,
            official_url=fp_url, official_site_verified=bool(fp_ver),
            is_operator_or_aggregator=is_op, reject_as_pricing_source=bool(reject),
            monthly_rent_per_bed=None, sharing_type=None, AC=None,
            price_confidence="unknown", price_source_url=None, evidence=note,
            verification_status=status,
            real_property=("real" if status.startswith(("verified_real","verified_operator","exists_described")) else "unconfirmed"),
            name_source="vishful_dashboard_screenshot", collection_date="2026-08-14"))
    df=pd.DataFrame(rows)
    df.to_csv(CSV,index=False)

    def n(col,val=True): return int((df[col]==val).sum())
    tcount=lambda t:int((df["property_type"]==t).sum())
    summary=[
     ("total_screenshot_candidates",len(df)),
     ("verified_real_properties",int((df["real_property"]=="real").sum())),
     ("unverified_names",int((df["real_property"]=="unconfirmed").sum())),
     ("mens_pg",tcount("mens_pg")),("womens_pg",tcount("womens_pg")),
     ("pg_unknown_gender(co-ed/unclear)",tcount("pg_unknown_gender")),
     ("co_living",tcount("co_living")),("serviced_apartment",tcount("serviced_apartment")),
     ("hotel",tcount("hotel")),("residential_apartment",tcount("residential_apartment")),
     ("unknown_type",tcount("unknown")),
     ("first_party_websites_found",n("official_site_verified")),
     ("first_party_pricing_sources",int(df["monthly_rent_per_bed"].notna().sum())),
     ("usable_perbed_sharing_ac_prices",int((df["monthly_rent_per_bed"].notna()&df["sharing_type"].notna()&df["AC"].notna()).sum())),
     ("unknown_price",int((df["price_confidence"]=="unknown").sum())),
     ("operators_or_aggregators_rejected",n("is_operator_or_aggregator")),
     ("reject_as_pricing_source",n("reject_as_pricing_source")),
     ("within_1km",n("within_1km")),("within_2km",n("within_2km")),
     ("within_3km",n("within_3km")),("within_5km",n("within_5km")),
     ("not_independently_web_verified",int((df["verification_status"]=="not_independently_web_verified").sum())),
     ("errors","Groq 429 rate-limit (several shortlist calls) + 413 too-large (Best Men's PG); WebSearch/WebFetch OK; no first-party page existed to fetch for unknowns"),
    ]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(SUMM,index=False)
    print("PHASE-3 SCREENSHOT FULL VERIFY:")
    for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": main()
