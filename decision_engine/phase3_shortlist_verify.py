"""
Phase-3 EXPERIMENTAL — targeted first-party verification of 9 shortlisted nearby men's PGs
(names from Vishful dashboard SCREENSHOT only). Groq compound-mini used for URL discovery
(rate-limited on some), then EVERY candidate independently verified via WebSearch (aggregators
+ social + maps + youtube blocked). No Groq URL trusted without independent check.

Finding: NONE of the 9 has a genuine first-party website. Only aggregator/directory/maps/
social listings exist -> official_url=null, price=unknown for all. Two are confirmed REAL
properties via independent listings (address+phone): Sree Siddhi Vinayaka, Ojas Grand.
No first-party price recorded anywhere (no fabrication; aggregator prices never used).

Writes ONLY outputs/phase3_shortlist_verify.csv (+ summary). Isolated: does not touch
dashboard / locked outputs / other phase3 outputs.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
CSV=os.path.join(OUT,"phase3_shortlist_verify.csv")
SUMM=os.path.join(OUT,"phase3_shortlist_verify_summary.csv")
LOCALITY_KM={"thiruvanmiyur":0.0,"perungudi":3.5}  # coarse suburb-centroid (Nominatim)

def dist(loc):
    l=(loc or "").lower()
    for k,km in LOCALITY_KM.items():
        if k in l: return km, f"suburb_centroid_{k}"
    return None,"unknown_locality"

# Each row = independently verified evidence (WebSearch, aggregators/social/maps blocked).
# monthly_rent_per_bed/sharing/AC = None unless a FIRST-PARTY page published it (none did).
R=[
 dict(candidate_name="Sasikala Paying Guest", verified_property_name="Sasikala Paying Guest",
   property_type="pg_unknown_gender", gender="unknown", locality="Thiruvanmiyur", pincode="600041",
   official_url=None, official_site_verified=False,
   food_terms=None, deposit=None, electricity_terms=None,
   evidence="Groq: official_url=null,is_aggregator=true (600041). WebSearch (aggregators/social blocked): no own-domain, no authoritative address listing.",
   verification_status="identity_unconfirmed_no_first_party"),
 dict(candidate_name="Sahithyan Men's PG", verified_property_name="Sahithyan Men's PG",
   property_type="mens_pg", gender="men", locality="Thiruvanmiyur", pincode=None,
   official_url=None, official_site_verified=False,
   food_terms="breakfast/lunch/dinner (per directory listing, NOT first-party)", deposit=None, electricity_terms=None,
   evidence="WebSearch: described (3-bed sharing, meals) on directory listings only; NO own site. Earlier Groq 'sahithyanpg.com' was hallucinated -> rejected (unverified).",
   verification_status="exists_described_no_first_party"),
 dict(candidate_name="Excellent Men's PG Accommodation", verified_property_name="Excellent Men's PG Accommodation (unconfirmed)",
   property_type="mens_pg", gender="men", locality="Thiruvanmiyur", pincode="600041",
   official_url=None, official_site_verified=False,
   food_terms=None, deposit=None, electricity_terms=None,
   evidence="Groq wrongly mapped to 'EMY PG' emypgaccommodation.in (different property) -> rejected. WebSearch: no distinct first-party site.",
   verification_status="identity_unconfirmed_no_first_party"),
 dict(candidate_name="Bhavani PG", verified_property_name="Bhavani PG (unconfirmed)",
   property_type="pg_unknown_gender", gender="unknown", locality="Thiruvanmiyur", pincode=None,
   official_url=None, official_site_verified=False, food_terms=None, deposit=None, electricity_terms=None,
   evidence="Groq call rate-limited (429). WebSearch: no distinct first-party site or authoritative listing.",
   verification_status="identity_unconfirmed_no_first_party"),
 dict(candidate_name="SNEHA PG", verified_property_name="Sneha PG Accommodation",
   property_type="pg_unknown_gender", gender="unknown", locality="Thiruvanmiyur", pincode="600041",
   official_url=None, official_site_verified=False, food_terms=None, deposit=None, electricity_terms=None,
   evidence="Groq: official_url=null,is_aggregator=true (600041). WebSearch: no own domain.",
   verification_status="identity_weak_no_first_party"),
 dict(candidate_name="Sree Siddhi Vinayaka Mens PG", verified_property_name="Sree Siddhi Vinayaka Mens PG",
   property_type="mens_pg", gender="men", locality="Perungudi", pincode="600096",
   official_url=None, official_site_verified=False, food_terms=None, deposit=None, electricity_terms=None,
   evidence="VERIFIED REAL: Plot 36, CBI Colony Main Rd, Perungudi 600096; ph 9557795579; 4.8(265). Listings on magicpin/mappls/yappe/rentok only -> NO first-party site.",
   verification_status="verified_real_no_first_party"),
 dict(candidate_name="Ojas Grand PG for Men", verified_property_name="Ojas Grand PG for Men",
   property_type="mens_pg", gender="men", locality="Perungudi", pincode="600096",
   official_url=None, official_site_verified=False,
   food_terms="breakfast/lunch/dinner (per directory listing, NOT first-party)", deposit=None, electricity_terms=None,
   evidence="VERIFIED REAL: 8 Ritish Castle 1st St, Thiruvengadam Nagar, Perungudi 600096; ph 9789833624; single/double/triple; 4.6(118). Listings on homelikepg/typeindia/magicpin/primepgs (aggregators) only -> NO first-party site.",
   verification_status="verified_real_no_first_party"),
 dict(candidate_name="Best Men's PG", verified_property_name="Best Men's PG (unconfirmed / generic name)",
   property_type="mens_pg", gender="men", locality="Chennai", pincode=None,
   official_url=None, official_site_verified=False, food_terms=None, deposit=None, electricity_terms=None,
   evidence="Groq call 413 (request too large). WebSearch: generic name, no distinct first-party site or authoritative listing.",
   verification_status="identity_unconfirmed_generic_name"),
 dict(candidate_name="SV PG Accommodation", verified_property_name="SV PG Accommodation (ambiguous)",
   property_type="pg_unknown_gender", gender="unknown", locality="Chennai", pincode=None,
   official_url=None, official_site_verified=False, food_terms=None, deposit=None, electricity_terms=None,
   evidence="Groq located an 'SV PG' at Arumbakkam 600106 (out of Vishful area) — likely a DIFFERENT property. WebSearch: no first-party site; screenshot locality generic 'Chennai'.",
   verification_status="identity_ambiguous_possible_out_of_area"),
]

EXISTING_POOL={"tsp","sumathi","feel at home","kripa","emy","sri maha","tidel","sri mahalakshmi","diyaa"}

def main():
    rows=[]
    for r in R:
        km,prec=dist(r["locality"])
        n=r["candidate_name"].lower()
        rows.append(dict(**r,
            distance_km=km, distance_precision=prec,
            monthly_rent_per_bed=None, sharing_type=None, AC=None,   # no first-party price -> null grain
            price_confidence="unknown", price_source_url=None,
            existing_or_new=("existing" if any(t in n for t in EXISTING_POOL) else "new"),
            name_source="vishful_dashboard_screenshot", collection_date="2026-08-14"))
    cols=["candidate_name","verified_property_name","property_type","gender","locality","pincode",
          "distance_km","distance_precision","official_url","official_site_verified",
          "monthly_rent_per_bed","sharing_type","AC","deposit","electricity_terms","food_terms",
          "price_confidence","price_source_url","evidence","existing_or_new","verification_status",
          "name_source","collection_date"]
    df=pd.DataFrame(rows)[cols]
    df.to_csv(CSV,index=False)

    real=df["verification_status"].str.startswith("verified_real").sum()
    fp_site=int(df["official_site_verified"].sum())
    fp_price=int(df["monthly_rent_per_bed"].notna().sum())
    usable=int((df["monthly_rent_per_bed"].notna() & df["sharing_type"].notna() & df["AC"].notna()).sum())
    summary=[("candidates",len(df)),("verified_real_properties",int(real)),
      ("with_first_party_website",fp_site),("with_first_party_price",fp_price),
      ("usable_perbed_sharing_ac_prices",usable),
      ("unknown_price",int((df["price_confidence"]=="unknown").sum())),
      ("new",int((df["existing_or_new"]=="new").sum())),("existing",int((df["existing_or_new"]=="existing").sum())),
      ("rejected_aggregator_sources","homelikepg,magicpin,typeindia,primepgs,rentmystay,chennaiproperties,yappe,mappls,addresspage,asklaila,top-rated,wanderboat,scribd,yube1,rentok,sulekha,facebook,instagram,youtube,google maps"),
      ("groq_errors","429 rate-limit (Sahithyan/Bhavani/Ojas); 413 too-large (Best Men's PG); others OK"),
      ("webfetch_errors","none (no first-party page existed to fetch)")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(SUMM,index=False)
    print("PHASE-3 SHORTLIST VERIFY:")
    for k,v in summary: print(f"  {k}: {v}")
    for _,r in df.iterrows():
        print(f"  - {r['candidate_name']} | {r['verification_status']} | site={r['official_site_verified']} | price={r['price_confidence']}")

if __name__=="__main__": main()
