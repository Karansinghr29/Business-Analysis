"""
Phase-3 MASTER competitor research dataset (isolated). Merges 5 evidence sources:
 1 dashboard screenshot (phase3_screenshot_full_verify.csv)  -> provenance 'dashboard'
 2 existing first-party PG research (phase3_pg_research_candidates.csv) -> 'first_party_web'
 3 Groq PG discovery (phase3_groq_pg_candidates.csv)          -> 'groq_discovery'
 4 Groq apartment discovery (phase3_groq_apartments_candidates.csv) -> 'groq_discovery'
 5 independently verified additions (Diyaa/Sumathi/Feel At Home + Sree Siddhi/Ojas) -> 'independent_web_verification'

Rules: keep EVERY dashboard candidate; add only genuinely verified non-screenshot competitors;
dedup ONLY known same-property variants (never merge different props by similar name);
preserve provenance; pricing first-party ONLY, never aggregator/inferred/converted; missing=unknown.

Writes ONLY phase3_competitor_master.csv + _summary.csv. Does not modify dashboard / locked
outputs / existing phase3 modules (reads their outputs read-only).
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
def rd(f):
    p=os.path.join(OUT,f)
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()

SS=rd("phase3_screenshot_full_verify.csv")
PP=rd("phase3_pg_research_candidates.csv")
GP=rd("phase3_groq_pg_candidates.csv")
GA=rd("phase3_groq_apartments_candidates.csv")

TYPES={"mens_pg","womens_pg","pg_unknown_gender","co_living","serviced_apartment","hotel",
       "residential_apartment","hostel","unknown"}
def norm(s): return re.sub(r"[^a-z0-9 ]","",re.sub(r"\s+"," ",str(s).strip().lower())).strip()

# Collapse ONLY known same-property cross-source variants. Order matters (mahalakshmi before 'sri maha').
def canon(name):
    n=norm(name)
    rules=[("sri mahalakshmi","sri_mahalakshmi_pg"),("mahalakshmi pg","sri_mahalakshmi_pg"),
           ("tsp","tsp_pg"),("kripa","kripa_homes"),("emy","emy_pg"),("sumathi","sumathi_illam"),
           ("feel at home","feel_at_home"),("diyaa","diyaa_pg"),("tidel","tidel_hostel"),
           ("sri maha ","sri_maha_hostels"),("star men","star_mens_pg"),("svh","svh_gents_pg"),
           ("triples","triples_mens_pg"),("kolam","kolam_serviced"),("olive serviced","olive_serviced"),
           ("season 4","season4"),("season4","season4"),("olympia jayanthi","olympia_jayanthi"),
           ("lancor sonnet","lancor_sonnet"),("sree siddhi vinayaka","sree_siddhi_vinayaka"),
           ("ojas grand","ojas_grand")]
    for k,c in rules:
        if k in n: return c
    return n  # default: exact normalized name -> distinct branches stay separate

def ptype_norm(t):
    t=str(t).lower()
    if "pg_likely" in t or t=="pg" or t=="pg_unknown_gender": return "pg_unknown_gender"
    if t in TYPES: return t
    if "co_living" in t or "co-living" in t: return "co_living"
    if "serviced" in t: return "serviced_apartment"
    if "hotel" in t: return "hotel"
    if "residential" in t or "apartment" in t: return "residential_apartment"
    if "mens" in t: return "mens_pg"
    if "women" in t: return "womens_pg"
    return "unknown"

# First-party price facts (ONLY from verified first-party pages). Diyaa = sole per-bed grain.
PRICE={
 "diyaa_pg":       dict(has=True, grain="full_by_sharing", perbed=True,  url="https://menspg.in/",
                        ev="own site full per-bed x sharing x AC grid (verified)"),
 "sumathi_illam":  dict(has=True, grain="by_room_class",  perbed=False, url="https://mypgatchennai.com/",
                        ev="own site ROOM-CLASS prices only (dorm/nonAC/AC) — NOT per-bed; not converted"),
}
# Verified first-party OWN sites (existence) even where no price.
FP_SITE={"tsp_pg":"https://tsppgaccommodation.com/","kripa_homes":"https://kripahomes.com/pg-thiruvanmiyur/",
 "sri_mahalakshmi_pg":"https://mahalakshmipgaccommodation.com/","emy_pg":"https://emypgaccommodation.in/",
 "sri_maha_hostels":"https://www.srimahahostels.com/","tidel_hostel":"https://tidelhostel.com/",
 "diyaa_pg":"https://menspg.in/","sumathi_illam":"https://mypgatchennai.com/",
 "feel_at_home":"https://www.hostelforladies.com/","season4":"https://season4.in/season-4-rentals-thiruvanmiyur/",
 "kolam_serviced":"https://kolamapartments.com/","olive_serviced":"https://oliveservicedapartments.com/chennai",
 "olympia_jayanthi":"https://www.olympiagroup.in/olympia-jayanthi-residence/index.html",
 "lancor_sonnet":"https://lancor.in/completed-projects-chennai/"}

OPERATOR=("stanza","zolo","truliv","yube1","nestora")

master={}
def add(name, provenance, ptype, gender, locality, pincode, dkm, prec, url, site_ver,
        is_dashboard, status, evidence, is_op):
    cid=canon(name)
    if cid not in master:
        master[cid]=dict(canonical_id=cid, competitor_name=name, all_names=set([name]),
            provenance=set(), property_type=ptype, gender=gender, locality=locality, pincode=pincode,
            distance_km=dkm, distance_precision=prec, official_url=url, official_site_verified=bool(site_ver),
            is_dashboard_candidate=is_dashboard, verification_status=status, evidence=evidence,
            is_operator_or_aggregator=is_op)
    m=master[cid]
    m["all_names"].add(name); m["provenance"].add(provenance)
    if is_dashboard: m["is_dashboard_candidate"]=True
    # prefer a real first-party url + verified site if any source supplies it
    if (not m["official_url"]) and url: m["official_url"]=url; m["official_site_verified"]=bool(site_ver)
    if cid in FP_SITE and not m["official_url"]: m["official_url"]=FP_SITE[cid]; m["official_site_verified"]=True
    if pincode and not m["pincode"]: m["pincode"]=pincode
    if (m["distance_km"] is None) and (dkm is not None): m["distance_km"]=dkm; m["distance_precision"]=prec
    if is_op: m["is_operator_or_aggregator"]=True

# 1) dashboard screenshot base (keep all 99)
for _,r in SS.iterrows():
    add(r["candidate_name"],"dashboard",ptype_norm(r["property_type"]),r.get("gender","unknown"),
        r.get("dashboard_locality"),r.get("pincode"),
        (None if pd.isna(r.get("distance_km")) else r.get("distance_km")),r.get("distance_precision"),
        (None if pd.isna(r.get("official_url")) else r.get("official_url")),bool(r.get("official_site_verified")),
        True,r.get("verification_status"),r.get("evidence"),bool(r.get("is_operator_or_aggregator")))
# 2) first-party PG research (+ independent verification for these real props)
for _,r in PP.iterrows():
    nm=r["property_name"]
    add(nm,"first_party_web","pg_unknown_gender" if "PG" in str(r.get("property_kind","")) else ptype_norm(r.get("property_kind","")),
        r.get("segment","unknown"),r.get("locality"),(None if pd.isna(r.get("pincode")) else r.get("pincode")),
        (None if pd.isna(r.get("dist_km_from_vishful")) else r.get("dist_km_from_vishful")),r.get("distance_precision"),
        (None if pd.isna(r.get("source_url")) else r.get("source_url")),bool(r.get("is_first_party")),
        False,"verified_real_first_party_site",r.get("note"),False)
    master[canon(nm)]["provenance"].add("independent_web_verification")
# 3) Groq PG discovery
for _,r in GP.iterrows():
    add(r["pg_name"],"groq_discovery",ptype_norm(r.get("property_kind","")),r.get("segment","unknown"),
        r.get("area"),(None if pd.isna(r.get("pincode")) else r.get("pincode")),
        (None if pd.isna(r.get("dist_km_from_vishful")) else r.get("dist_km_from_vishful")),r.get("distance_precision"),
        (None if pd.isna(r.get("official_url")) else r.get("official_url")),False,
        False,"groq_discovered",None,bool(r.get("is_aggregator")))
# 4) Groq apartment discovery
for _,r in GA.iterrows():
    add(r["name"],"groq_discovery",ptype_norm(r.get("property_type","")),"unknown",
        r.get("area"),(None if pd.isna(r.get("pincode")) else r.get("pincode")),
        (None if pd.isna(r.get("dist_km_from_vishful")) else r.get("dist_km_from_vishful")),r.get("distance_precision"),
        (None if pd.isna(r.get("official_url")) else r.get("official_url")),bool(r.get("verified_first_party")),
        False,"groq_discovered",r.get("evidence"),bool(r.get("is_aggregator")))

# finalize rows
rows=[]
for cid,m in master.items():
    pr=PRICE.get(cid)
    op=m["is_operator_or_aggregator"]
    reject = op or m["property_type"] in ("hotel","serviced_apartment")
    perbed = bool(pr and pr["perbed"]) and not reject
    rows.append(dict(
        canonical_id=cid, competitor_name=m["competitor_name"],
        all_names=" || ".join(sorted(m["all_names"])),
        provenance=",".join(sorted(m["provenance"])),
        property_type=m["property_type"], gender=m["gender"],
        evidence_class=("operator_aggregator" if op else
                        "out_of_area" if str(m["verification_status"]).startswith("identity_ambiguous_possible_out") else
                        "verified_real" if str(m["verification_status"]).startswith(("verified_real","verified_operator","exists_described","groq_discovered")) and m["official_site_verified"] else
                        "verified_real" if str(m["verification_status"]).startswith(("verified_real","exists_described")) else
                        "identity_unconfirmed"),
        locality=m["locality"], pincode=m["pincode"],
        distance_km=m["distance_km"], distance_precision=m["distance_precision"],
        within_1km=(m["distance_km"] is not None and m["distance_km"]<=1),
        within_2km=(m["distance_km"] is not None and m["distance_km"]<=2),
        within_3km=(m["distance_km"] is not None and m["distance_km"]<=3),
        within_5km=(m["distance_km"] is not None and m["distance_km"]<=5),
        official_url=m["official_url"], official_site_verified=m["official_site_verified"],
        is_operator_or_aggregator=op, reject_as_pricing_source=reject,
        has_first_party_price=bool(pr and pr["has"] and not reject),
        comparable_perbed_sharing_ac=perbed,
        price_grain=(pr["grain"] if pr else "unknown"),
        monthly_rent_per_bed=None,  # numeric grid lives in phase3_pg_price_evidence.csv (not duplicated here)
        price_source_url=(pr["url"] if (pr and not reject) else None),
        price_confidence=("first_party_published" if perbed else "first_party_room_class" if (pr and pr["has"] and not pr["perbed"]) else "unknown"),
        price_evidence=(pr["ev"] if pr else None),
        is_dashboard_candidate=m["is_dashboard_candidate"],
        verification_status=m["verification_status"]))
df=pd.DataFrame(rows)
df.to_csv(os.path.join(OUT,"phase3_competitor_master.csv"),index=False)

dash=int(df["is_dashboard_candidate"].sum())
tc=lambda t:int((df["property_type"]==t).sum())
summary=[
 ("total_dashboard_candidates",dash),
 ("total_web_discovered_added",len(df)-dash),
 ("total_unique_competitors",len(df)),
 ("verified_real",int((df["evidence_class"]=="verified_real").sum())),
 ("identity_unconfirmed",int((df["evidence_class"]=="identity_unconfirmed").sum())),
 ("out_of_area",int((df["evidence_class"]=="out_of_area").sum())),
 ("operator_aggregator",int((df["evidence_class"]=="operator_aggregator").sum())),
 ("mens_pg",tc("mens_pg")),("womens_pg",tc("womens_pg")),("pg_coed_or_unclear",tc("pg_unknown_gender")),
 ("co_living",tc("co_living")),("serviced_apartment",tc("serviced_apartment")),
 ("hotel",tc("hotel")),("residential_apartment",tc("residential_apartment")),("unknown_type",tc("unknown")),
 ("first_party_websites",int(df["official_site_verified"].sum())),
 ("first_party_price_sources",int(df["has_first_party_price"].sum())),
 ("comparable_perbed_sharing_ac_sources",int(df["comparable_perbed_sharing_ac"].sum())),
 ("unknown_price",int((df["price_confidence"]=="unknown").sum())),
 ("within_1km",int(df["within_1km"].sum())),("within_2km",int(df["within_2km"].sum())),
 ("within_3km",int(df["within_3km"].sum())),("within_5km",int(df["within_5km"].sum())),
 ("duplicate_canonical_ids",int(df["canonical_id"].duplicated().sum())),
]
pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_competitor_master_summary.csv"),index=False)
print("PHASE-3 COMPETITOR MASTER:")
for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": pass
