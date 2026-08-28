"""
Phase-3 EXPERIMENTAL — Apify + Groq bounded market discovery (isolated). Measures whether
Apify(free rag-web-browser) + Groq(compound-mini) materially improve first-party market coverage
over the existing 115-competitor master. Records ONLY genuinely-returned evidence; no fabrication.

Outcome (this run): 0 NEW first-party properties, 0 new first-party prices. Apify returned only
aggregators/directories/operators; Groq returned operator brands + Diyaa (already in master) and
429'd on 2/4 locations. Fallback rule triggered -> Playwright plan prepared, NOT executed.

Writes ONLY phase3_apify_groq_market_discovery.csv + _web_evidence.csv + _summary.csv.
Reads phase3_competitor_master.csv READ-ONLY for dedup. Does not modify dashboard / locked
outputs / existing phase3 research / run_all / master.
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
M=pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv"))
def norm(s): return re.sub(r"[^a-z0-9 ]","",re.sub(r"\s+"," ",str(s).strip().lower())).strip()
MASTER_NORMS=set()
for a in M["all_names"]: MASTER_NORMS.update(norm(x) for x in str(a).split(" || "))
MASTER_NORMS |= set(M["competitor_name"].map(norm)) | set(M["canonical_id"].map(lambda x:norm(str(x).replace("_"," "))))

TARGET_LOCS={"adyar","thiruvanmiyur","tiruvanmiyur","perungudi","kattankulathur"}
TYPES={"mens_pg","womens_pg","coed_pg","hostel","co_living","serviced_apartment","residential","unknown"}
OPERATOR_AGG={"zolo","stanza","oyo","coho","colive","yube1","helloworld","thehelloworld",
              "rentmystay","chennaiproperties","nobroker","magicbricks","housing","sulekha","justdial"}

# Real evidence gathered this run (Groq compound-mini + Apify rag-web-browser + verification).
# Each candidate: is it a genuine NEW first-party property? None were.
DISCOVERY=[
 dict(candidate_name="Diyaa Paying Guest", locality="Adyar", pincode="600020", property_type="mens_pg",
      gender="men", discovery_source="groq", discovery_url="https://menspg.in",
      official_url="https://menspg.in/", official_site_verified=True, is_aggregator_operator=False,
      verification_status="verified_real_first_party_site",
      note="Already in master (canonical diyaa_pg). No new info; sole per-bed comparable already recorded."),
 dict(candidate_name="Zolostays Coliving", locality="Adyar", pincode="600020", property_type="co_living",
      gender="unknown", discovery_source="groq", discovery_url="https://zolostays.com",
      official_url=None, official_site_verified=False, is_aggregator_operator=True,
      verification_status="operator_discovery_only",
      note="Operator/aggregator brand — discovery only, rejected as first-party pricing."),
 dict(candidate_name="Stanza Living", locality="Adyar", pincode="600020", property_type="co_living",
      gender="unknown", discovery_source="groq", discovery_url="https://stanzaliving.com",
      official_url=None, official_site_verified=False, is_aggregator_operator=True,
      verification_status="operator_discovery_only", note="Operator brand — rejected pricing."),
 dict(candidate_name="OYO Life Kattankulathur", locality="Kattankulathur", pincode="603203", property_type="co_living",
      gender="unknown", discovery_source="groq", discovery_url="https://oyolife.com",
      official_url=None, official_site_verified=False, is_aggregator_operator=True,
      verification_status="operator_discovery_only", note="Operator/booking marketplace — rejected."),
 dict(candidate_name="CoHo Kattankulathur", locality="Kattankulathur", pincode="603203", property_type="co_living",
      gender="unknown", discovery_source="groq", discovery_url="https://coho.in",
      official_url=None, official_site_verified=False, is_aggregator_operator=True,
      verification_status="operator_discovery_only", note="Operator brand — rejected."),
 dict(candidate_name="Colive Kattankulathur", locality="Kattankulathur", pincode="603203", property_type="co_living",
      gender="unknown", discovery_source="groq", discovery_url="https://colive.in",
      official_url=None, official_site_verified=False, is_aggregator_operator=True,
      verification_status="operator_discovery_only", note="Operator brand — rejected."),
 dict(candidate_name="Yube1", locality="Thiruvanmiyur", pincode=None, property_type="co_living",
      gender="unknown", discovery_source="apify", discovery_url="https://yube1.in/",
      official_url=None, official_site_verified=False, is_aggregator_operator=True,
      verification_status="operator_discovery_only", note="Operator (already in master) — rejected."),
 dict(candidate_name="HelloWorld Coliving", locality="Perungudi", pincode=None, property_type="co_living",
      gender="unknown", discovery_source="apify", discovery_url="https://thehelloworld.com/coliving-in-chennai",
      official_url=None, official_site_verified=False, is_aggregator_operator=True,
      verification_status="operator_discovery_only", note="Operator brand — rejected."),
]
# Aggregator/directory RESULT PAGES (not properties) — logged as evidence, NOT candidates:
AGG_PAGES=["https://www.rentmystay.com/co-live-pg/Thiruvanmiyur-Chennai/all",
           "https://www.chennaiproperties.com/rent/pg-hostels/thiruvanmiyur",
           "https://www.chennaiproperties.com/rent/pg-hostels/perungudi"]

WEB_EVIDENCE=[
 dict(tool="apify/rag-web-browser", run_id="XOBhBazJInXdjeZF7", location="Thiruvanmiyur",
      pages=3, compute_units=0.02484, pricing="FREE actor (userTier FREE)",
      discovered="rentmystay.com(agg), yube1.in(operator), chennaiproperties.com(directory)", error=None),
 dict(tool="apify/rag-web-browser", run_id="VHGbQsohpLivZftp7", location="Perungudi",
      pages=3, compute_units=0.02639, pricing="FREE actor (userTier FREE)",
      discovered="yube1.in(operator), chennaiproperties.com(directory), thehelloworld.com(operator)", error=None),
 dict(tool="groq/compound-mini", run_id=None, location="Adyar", pages=None, compute_units=None,
      pricing="Groq free tier", discovered="Zolo, Diyaa(known), Stanza", error=None),
 dict(tool="groq/compound-mini", run_id=None, location="Kattankulathur", pages=None, compute_units=None,
      pricing="Groq free tier", discovered="Stanza, OYO, Zolo, CoHo, Colive (all operators)", error=None),
 dict(tool="groq/compound-mini", run_id=None, location="Thiruvanmiyur", pages=None, compute_units=None,
      pricing="Groq free tier", discovered=None, error="429 RateLimitError (openai/gpt-oss-120b)"),
 dict(tool="groq/compound-mini", run_id=None, location="Perungudi", pages=None, compute_units=None,
      pricing="Groq free tier", discovered=None, error="429 RateLimitError (openai/gpt-oss-120b)"),
]

def main():
    rows=[]
    for d in DISCOVERY:
        n=norm(d["candidate_name"])
        is_existing = n in MASTER_NORMS or any(op in n for op in ["yube1","stanza","zolo","diyaa"] if op in MASTER_NORMS or any(op in mn for mn in MASTER_NORMS))
        # new first-party = not existing AND not operator/aggregator AND verified first-party
        is_new_first_party = (not is_existing) and (not d["is_aggregator_operator"]) and d["official_site_verified"]
        rows.append(dict(
            candidate_name=d["candidate_name"], canonical_name=n.replace(" ","_"),
            locality=d["locality"], pincode=d["pincode"], property_type=d["property_type"], gender=d["gender"],
            discovery_source=d["discovery_source"], discovery_url=d["discovery_url"],
            verification_status=d["verification_status"],
            official_url=d["official_url"], official_site_verified=d["official_site_verified"],
            official_site_source=("first_party" if d["official_site_verified"] else None),
            is_aggregator_operator=d["is_aggregator_operator"],
            monthly_rent=None, sharing_type=None, ac=None, deposit=None, eb=None, food=None,
            price_unit=None, price_status="unknown", price_source_url=None, price_evidence=None,
            wifi=None, laundry=None, housekeeping=None, cctv_security=None, parking=None, power_backup=None,
            dedup_vs_master=("existing" if is_existing else "new"),
            is_new_first_party_property=is_new_first_party,
            note=d["note"]))
    disc=pd.DataFrame(rows)
    disc.to_csv(os.path.join(OUT,"phase3_apify_groq_market_discovery.csv"),index=False)
    pd.DataFrame(WEB_EVIDENCE).to_csv(os.path.join(OUT,"phase3_apify_groq_web_evidence.csv"),index=False)

    by_loc=disc.groupby("locality").size().to_dict()
    by_type=disc.groupby("property_type").size().to_dict()
    summary=[
     ("total_candidates_discovered",len(disc)),
     ("aggregator_directory_result_pages(not_properties)",len(AGG_PAGES)),
     ("new_after_dedup_vs_115",int((disc["dedup_vs_master"]=="new").sum())),
     ("new_FIRST_PARTY_properties",int(disc["is_new_first_party_property"].sum())),
     ("existing_rediscovered",int((disc["dedup_vs_master"]=="existing").sum())),
     ("operators_or_aggregators",int(disc["is_aggregator_operator"].sum())),
     ("first_party_websites_verified",int(disc["official_site_verified"].sum())),
     ("first_party_price_sources",0),
     ("unknown_price",int((disc["price_status"]=="unknown").sum())),
     ("comparable_perbed_sharing_ac_sources_new",0),
     ("by_location",str(by_loc)),("by_type",str(by_type)),
     ("apify_actor","apify/rag-web-browser (FREE)"),
     ("apify_runs",2),("apify_pages_scraped",6),("apify_compute_units",round(0.02484+0.02639,5)),
     ("apify_credit_impact","negligible — FREE actor, ~0.051 compute units total; no paid per-event actor run"),
     ("groq_model","groq/compound-mini"),
     ("groq_errors","429 RateLimitError x2 (Thiruvanmiyur, Perungudi); Adyar+Kattankulathur OK"),
     ("coverage_improvement","NONE — 0 new first-party properties, 0 new first-party prices"),
     ("fallback_triggered","YES — Playwright plan prepared, NOT executed"),
    ]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_apify_groq_summary.csv"),index=False)
    print("PHASE-3 APIFY+GROQ MARKET DISCOVERY:")
    for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": main()
