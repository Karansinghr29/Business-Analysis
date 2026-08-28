"""
Phase-3 Stage-3 COLLECTION: persist competitor Google Maps reviews from OUR approved Apify run.
Pulls the immutable dataset of run zID57BCmD2hhyLRCb (actor compass/crawler-google-places) via the
official Apify API using APIFY_API_TOKEN (never printed). Keeps ONLY the approved 9 fields; drops
ALL reviewer PII (name, reviewerId, reviewerUrl, reviewerPhotoUrl). Reviews grouped per property.
NO comparison/ranking/benchmark. Raw evidence preserved unchanged. Isolated — writes only new files.
"""
from __future__ import annotations
import os, sys, json, urllib.request, urllib.parse
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
DATASET_ID="l4cqWmfaZENy3LdCI"; RUN_ID="zID57BCmD2hhyLRCb"; RET="2026-08-18"
ACTOR="compass/crawler-google-places"
# searchString -> canonical property name (the approved 10-target list)
TARGET={
 "Sahithyan Men's PG Thiruvanmiyur Chennai":"Sahithyan Men's PG",
 "TSP PG Accommodation Thiruvanmiyur Chennai":"TSP PG Accommodation",
 "Yali Service Apartment Thiruvanmiyur Chennai":"Yali Service Apartment",
 "Subodhaya Paying Guest ladies Thiruvanmiyur Chennai":"Subodhaya Paying Guest (Ladies)",
 "Season 4 Rentals Thiruvanmiyur Chennai":"Season 4 Rentals",
 "Kripa Homes PG Thiruvanmiyur Chennai":"Kripa Homes PG",
 "Kolam Gandhi Serviced Apartments Adyar Chennai":"Kolam Gandhi Serviced Apartments",
 "Olive Serviced Apartments Perungudi Chennai":"Olive Serviced Apartments",
 "Diyaa Paying Guest Adyar Chennai":"Diyaa Paying Guest",
 "Feel At Home Ladies Hostel Perungudi Chennai":"Feel At Home Ladies Hostel"}
KEEP_REVIEW=("stars","text","publishedAtDate","reviewId","reviewOrigin")  # allowed only
DROP_PII=("name","reviewerId","reviewerUrl","reviewerPhotoUrl","reviewerNumberOfReviews","isLocalGuide")

def fetch():
    tok=os.environ.get("APIFY_API_TOKEN")
    if not tok: sys.exit("APIFY_API_TOKEN not in env — cannot fetch our Apify dataset.")
    # project place identity + reviews; PII sub-fields are dropped in code below regardless
    q=urllib.parse.urlencode({"token":tok,"clean":"true",
        "fields":"searchString,title,url,placeId,totalScore,reviewsCount,reviews"})
    url=f"https://api.apify.com/v2/datasets/{DATASET_ID}/items?{q}"
    return json.load(urllib.request.urlopen(url,timeout=60))

def main():
    items=fetch()
    rows=[]; per=[]
    for it in items:
        prop=TARGET.get(it.get("searchString"), it.get("title"))
        src=it.get("url"); revs=it.get("reviews") or []
        collected=0
        for r in revs:
            txt=(r.get("text") or r.get("textTranslated") or "")
            if not str(txt).strip(): continue
            rows.append(dict(property_name=prop, platform="google_maps", source_url=src,
                rating=r.get("stars"), review_text=str(txt).strip(),
                review_date=r.get("publishedAtDate"), retrieval_date=RET,
                apify_run_id=RUN_ID, provenance=f"Apify {ACTOR} dataset {DATASET_ID}",
                review_id=r.get("reviewId"), review_origin=r.get("reviewOrigin")))
            collected+=1
        per.append(dict(property_name=prop, place_title=it.get("title"),
            google_total_score=it.get("totalScore"), google_total_reviews=it.get("reviewsCount"),
            reviews_collected=collected, source_url=src, apify_run_id=RUN_ID, retrieval_date=RET))
    raw=pd.DataFrame(rows,columns=["property_name","platform","source_url","rating","review_text",
        "review_date","retrieval_date","apify_run_id","provenance","review_id","review_origin"])
    raw.to_csv(os.path.join(OUT,"phase3_competitor_reviews_raw.csv"),index=False)
    pd.DataFrame(per).to_csv(os.path.join(OUT,"phase3_competitor_reviews_by_property.csv"),index=False)

    summary=[("target_properties",len(TARGET)),("properties_returned",len(per)),
     ("total_reviews_collected",len(raw)),
     ("per_property",str({p["property_name"]:p["reviews_collected"] for p in per})),
     ("zero_or_few",str({p["property_name"]:p["reviews_collected"] for p in per if p["reviews_collected"]<3})),
     ("apify_run_id",RUN_ID),("apify_dataset_id",DATASET_ID),("actor",ACTOR),
     ("retrieval_date",RET),
     ("pii_stored","NONE — reviewer name/id/url/photo dropped at ingest"),
     ("note","raw Google Maps reviews; context only; never competitor comparison/ranking/benchmark")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_competitor_reviews_summary.csv"),index=False)
    print("PHASE-3 COMPETITOR REVIEWS — COLLECTED:")
    for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": main()
