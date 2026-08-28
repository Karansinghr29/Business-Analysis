"""
Phase-3 EXPERIMENTAL — candidate list transcribed from Vishful's Market AI dashboard SCREENSHOT.
Screenshot = NAME SOURCE ONLY. Names copied verbatim; nothing invented/normalized/added.

This module: (a) records every visible competitor name + its dashboard-shown locality,
(b) rule-classifies property_type, (c) flags hotels/serviced-apts/operators/aggregators as
NOT first-party pricing sources, (d) dedupes vs the existing phase3 PG pool (existing vs new),
(e) attaches COARSE suburb-centroid distance (real Nominatim run; far/downtown = >5km band, no
fabricated street coords), (f) carries in ONLY the first-party facts already verified this
session (price still unknown), (g) leaves price unknown everywhere else — NO fabricated price.

It does NOT run per-candidate first-party pricing for all ~100 names (prior 3 passes established
first-party PG price availability ≈ 0 in this cluster). Prices here are unknown by default and
must be filled only from a verified first-party page.

Writes ONLY: outputs/phase3_screenshot_candidates.csv, outputs/phase3_screenshot_summary.csv.
Does NOT touch dashboard / locked outputs / other phase3 outputs.
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
CAND=os.path.join(OUT,"phase3_screenshot_candidates.csv")
SUMM=os.path.join(OUT,"phase3_screenshot_summary.csv")

# (name VERBATIM from screenshot, dashboard-shown locality VERBATIM)
NAMES=[
 ("kalyani homestay","Perungudi"),("K S MENS P G HOSTAL","Chennai"),
 ("Sasikala Paying Guest","Thiruvanmiyur"),("VIJAY PAYING GUEST LUXURY HOSTEL","Adyar"),
 ("Zara co-living Space - Men's PG / Valasarvakkam","Chennai"),("SAHITHYAN MEN'S PG","Thiruvanmiyur"),
 ("SRI LAKSHMI SRI LADIES PG","Perungudi"),("Mens PG","Adyar"),
 ("Yube1 Emerald League - PG in Perungudi | Coliving PG","Perungudi"),
 ("Ganapathi PG for Women - LB Road","Thiruvanmiyur"),("WowLife Coliving PFLG (Perungudi)","Perungudi"),
 ("Zara Co-Living Space - Men's PG/ Thoraipakkam","Chennai"),("Vishful Vista Heights","Thiruvanmiyur"),
 ("Eden Coliving Space","Chennai"),("Green Apple Residency","Perungudi"),
 ("Skylinn Stays OMR Perungudi | Best Hotel Rooms Chennai","Thiruvanmiyur"),
 ("WHITES INN VANDALUR","Kattankulathur"),("Sri Venkata Vishnu Priya Gents Hostel","Kattankulathur"),
 ("Sri Mahalakshmi PG Accommodation","Perungudi"),("Aostel - Men's PG/ Hostel in Anna Salai","Chennai"),
 ("EXCELLENT MEN'S PG ACCOMODATION | MENS HOSTEL IN THIRUVANMIYUR | BOYS HOSTEL IN THIRUVANMIYUR","Thiruvanmiyur"),
 ("Stay N Tour Home | Best Rooms In Adyar","Adyar"),("SRK Hostel","Kattankulathur"),
 ("SPS Men's PG | Boys Hostel | Mens hostel In Thousand lights | Nungambakkam | Mountroad","Chennai"),
 ("Riya Ladies PG","Perungudi"),("Venkat Ramana PG hostel for Gents","Kattankulathur"),
 ("Bhavani pg","Thiruvanmiyur"),("TSP PG ACCOMADTION","Thiruvanmiyur"),
 ("NESTORA ELITE PG in PERUNGUDI ( Mens PG NEW building)","Thiruvanmiyur"),
 ("Sri Sai Balaji Ladies PG","Perungudi"),("Oragadam Rooms","Kattankulathur"),
 ("Yube1 Premier League - PG in Thiruvanmiyur | Coliving PG","Thiruvanmiyur"),
 ("The Royal Inn Gents PG","Kattankulathur"),("The Royal Inn Ladies Pg (Maple Nest)","Kattankulathur"),
 ("Sri Sai Grn Men's Pg & Hostel","Chennai"),("MR Regency PG Hostel","Adyar"),
 ("TSP MENS PG","Chennai"),("Venkat Ramana PG Hostel for Ladies","Kattankulathur"),
 ("MG Park","Thiruvanmiyur"),("Sree sai pg","Perungudi"),
 ("Yube1 Capital League - PG in Porur | Coliving PG","Chennai"),
 ("Swarna Sudarshan Serviced Apartments, Adyar, Chennai | Hotel rooms in Adyar","Thiruvanmiyur"),
 ("Wowlife Coliving - HerNest","Chennai"),("SNEHA PG","Thiruvanmiyur"),
 ("Oester Hostel for Boys","Kattankulathur"),("THE SHIVAM LIVING PG FOR MEN'S","Chennai"),
 ("STAY GREEN PG","Perungudi"),("Chippy Inn Tharamani","Thiruvanmiyur"),
 ("MCity Elite Suites","Kattankulathur"),("Sree Siddhi Vinayaka Mens PG","Perungudi"),
 ("SMS LADIES HOSTEL","Kattankulathur"),("SV PG Accommodation","Chennai"),
 ("Staylite Suites Thiruvanmiyur Chennai | Hotels in OMR","Thiruvanmiyur"),
 ("WHITES INN Nearby Kilambakkam New Bus Terminal","Kattankulathur"),
 ("The Royal Inn Ladies PG","Kattankulathur"),
 ("Sri Venkateswara mens kR hostel/PG","Chennai"),("SRI LAXMI BALAJI PG FOR LADIES","Perungudi"),
 ("Dreams Neelankarai","Perungudi"),("NAVEENS HIFI PG FLAT AND HOSTEL ONLY FOR GIRLS","Thiruvanmiyur"),
 ("Best Men's PG","Chennai"),("VSTAY INN PG FOR LADIES","Kattankulathur"),
 ("KPA MEN'S PG & HOSTEL","Chennai"),("NESTORA CO-LIVING PG","Chennai"),
 ("Sai Balaji pg hostel for ladies","Kattankulathur"),("Blue Shell","Adyar"),
 ("Yali Service Apartment","Thiruvanmiyur"),("Amman Men's PG Hostel","Chennai"),
 ("Truliv Hercules - Co-living space & PG in Navalur","Chennai"),
 ("Star Men's Pg Accommodation","Thiruvanmiyur"),("Sabari Residency","Kattankulathur"),
 ("Subodhaya Paying Guest Accommodation (for Ladies)","Thiruvanmiyur"),
 ("PG in Perungudi - Sampoorna Nilayam","Perungudi"),("StayBro Co-Living Spaces","Chennai"),
 ("Season 4 Rentals","Thiruvanmiyur"),
 ("Yube1 Continental League - PG in Perungudi | Coliving PG","Thiruvanmiyur"),
 ("Yube1 Zen League - PG in Thoraipakkam | Coliving PG","Chennai"),
 ("Maayaas Stay Ladies Hostel","Kattankulathur"),
 ("Stay Easy Tiruvanmiyur Chennai | Hotels Near Apollo Proton","Thiruvanmiyur"),
 ("Yube1 Millennial Campus - PG in Nungambakkam | Coliving PG","Chennai"),
 ("Yube1 Alpha League - PG in Thiruvanmiyur | Coliving PG","Thiruvanmiyur"),
 ("Chippy Inn","Thiruvanmiyur"),("SRP The Pavilion","Kattankulathur"),
 ("Ojas Grand PG for Men","Perungudi"),
 ("Truliv Sofia - Co-living space & PG in Siruseri","Thiruvanmiyur"),
 ("Kripa Homes pg thiruvanmiyur","Thiruvanmiyur"),("OLive Inn PG for Men","Chennai"),
 ("D and A BOUTIQUE HOTEL","Thiruvanmiyur"),
 ("Yube1 Madras League - PG in Chetpet | Coliving PG","Chennai"),
 ("VJB APARTMENT (PG Sholinganallur / AC PG for Men )","Chennai"),("Yube1 Sarmani","Chennai"),
 ("Kolam Gandhi Serviced Apartments","Thiruvanmiyur"),
 ("Raga's PG (Paying Guest) Boy's Hostel","Chennai"),("VJB House PG","Chennai"),
 ("The Adyar House Boutique Homestays","Adyar"),("The K11 Golden Gate - Chennai","Adyar"),
 ("Stanza Living Fernley House | Coliving PG in Urapakkam","Kattankulathur"),
 ("Stanza Living Conway House | Coliving PG in Navalur","Chennai"),
 ("Olive Serviced Apartments","Thiruvanmiyur"),
 ("Hotel O Guduvancheri Railway Station","Kattankulathur"),("SMS Gents Hostel","Kattankulathur"),
]

# Coarse suburb-centroid km from Vishful anchor (Nominatim). Only the near coastal cluster is
# trusted; downtown/GST-belt geocodes were unreliable -> treated as >5km (no km asserted).
LOCALITY_KM={"thiruvanmiyur":0.0,"tiruvanmiyur":0.0,"adyar":1.3,"tharamani":1.2,
             "perungudi":3.5,"thoraipakkam":4.6,"neelankarai":4.9}
FAR={"kattankulathur","vandalur","guduvancheri","urapakkam","kilambakkam","oragadam",
     "navalur","siruseri","porur","nungambakkam","valasaravakkam","chetpet","sholinganallur"}

# Operator/aggregator brands (NOT first-party independent pricing sources)
OPERATOR_TOKENS=["stanza","zolo","truliv","yube1","nestora"]

# Already in the existing phase3 PG pool / dashboard-existing set (mark existing vs new)
EXISTING_TOKENS=["tsp","sumathi","feel at home","kripa","emy","sri maha","tidel",
 "sri mahalakshmi","diyaa","skylinn","zara","eden","green apple","whites inn",
 "sri venkata vishnu priya","aostel","vista heights","vishful"]

# First-party sites VERIFIED this session (real WebFetch/WebSearch). Price still unknown.
VERIFIED={
 "tsp pg":("https://tsppgaccommodation.com/",True,"own site verified; no public price"),
 "tsp mens":("https://tsppgaccommodation.com/",True,"own site verified; no public price"),
 "kripa homes":("https://kripahomes.com/pg-thiruvanmiyur/",True,"own site verified; no price"),
 "sri mahalakshmi":("https://mahalakshmipgaccommodation.com/",True,"own site verified; no price"),
 "season 4":("https://season4.in/season-4-rentals-thiruvanmiyur/",True,"own serviced-apt site verified; no on-page price"),
 "star men":(None,False,"prior URL-resolution: NO first-party site found -> unknown"),
}

def norm(s): return re.sub(r"\s+"," ",s.strip().lower())

def classify(name):
    n=norm(name)
    op=any(t in n for t in OPERATOR_TOKENS)
    women=any(t in n for t in ["ladies","women","girls","her nest","hernest","women's","womens","for women","for ladies"])
    men=any(t in n for t in ["men","mens","men's","gents","boys","boy's","for men","kr hostel"])
    if any(t in n for t in ["hotel","boutique hotel","best hotel","hotel rooms"]) and "pg" not in n:
        t="hotel"
    elif any(t in n for t in ["serviced apart","service apartment","serviced apartments","suites","rentals","homestay","home |","best rooms","inn "]) and "pg" not in n and "hostel" not in n:
        t="serviced_apartment"
    elif "co-living" in n or "coliving" in n or "co living" in n:
        t="co_living"
    elif any(t in n for t in ["pg","paying guest","hostel","hostal"]):
        t=("womens_pg" if women else "mens_pg" if men else "pg_unknown_gender")
    elif any(t in n for t in ["apartment","residency","residences","flat"]):
        t="residential_apartment"
    else:
        t="unknown"
    return t, op, ("women" if women else "men" if men else "unknown")

def dist(locality):
    l=norm(locality)
    for k,km in LOCALITY_KM.items():
        if k in l: return km, f"suburb_centroid_{k}", km<=1,km<=2,km<=3,km<=5
    if any(f in l for f in FAR): return None,"coarse_far_>5km",False,False,False,False
    return None,"unknown_locality",False,False,False,False   # generic 'Chennai'

def main():
    rows=[]; seen=set()
    for name,loc in NAMES:
        n=norm(name)
        if n in seen: continue
        seen.add(n)
        is_self = "vista heights" in n or ("vishful" in n)
        ptype,is_op,seg=classify(name)
        km,prec,w1,w2,w3,w5=dist(loc)
        is_existing=any(t in n for t in EXISTING_TOKENS)
        # first-party pricing eligibility
        reject_pricing = is_op or ptype in ("hotel","serviced_apartment")
        vf=None; vurl=None; vnote=None
        for key,(url,verified,note) in VERIFIED.items():
            if key in n: vf=verified; vurl=url; vnote=note; break
        rows.append(dict(name=name, dashboard_locality=loc, property_type=ptype, segment=seg,
            is_operator_or_aggregator=is_op, reject_as_pricing_source=reject_pricing,
            is_self=is_self, is_existing_in_pool=is_existing, is_new=(not is_existing and not is_self),
            dist_km_from_vishful=km, distance_precision=prec,
            within_1km=w1, within_2km=w2, within_3km=w3, within_5km=w5,
            verified_first_party=(bool(vf) if vf is not None else False),
            official_url=vurl, monthly_price=None, price_confidence="unknown",
            source_url=vurl, evidence=(vnote or "transcribed from Vishful dashboard screenshot; no first-party price verified this pass"),
            name_source="vishful_dashboard_screenshot", collection_date="2026-08-14"))
    df=pd.DataFrame(rows)
    df.to_csv(CAND,index=False)

    comp=df[~df["is_self"]]
    def c(col,val=True): return int((comp[col]==val).sum())
    types={t:int((comp["property_type"]==t).sum()) for t in sorted(comp["property_type"].unique())}
    summary=[("total_names_transcribed",len(df)),("self_excluded",int(df["is_self"].sum())),
     ("competitor_candidates",len(comp)),
     ("existing_in_pool",c("is_existing_in_pool")),("new",c("is_new")),
     ("operators_or_aggregators",c("is_operator_or_aggregator")),
     ("reject_as_pricing_source",c("reject_as_pricing_source")),
     ("verified_first_party_sites",c("verified_first_party")),
     ("first_party_prices_found",int((comp["monthly_price"].notna()).sum())),
     ("unknown_price",int((comp["price_confidence"]=="unknown").sum())),
     ("within_1km",c("within_1km")),("within_2km",c("within_2km")),
     ("within_3km",c("within_3km")),("within_5km",c("within_5km")),
     ("type_breakdown",str(types))]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(SUMM,index=False)
    print("PHASE-3 SCREENSHOT CANDIDATES:")
    for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": main()
