"""
Phase-3 REVIEW-EVIDENCE INVENTORY (isolated, deterministic, read-only, AUDIT-ONLY).
Inventories the review-adjacent evidence ALREADY collected legitimately (Playwright first-party
renders). NO new scraping, NO Google-Maps call, NO aggregator-as-first-party, NO fabrication.

Honest classification (three DISTINCT datasets, never interchangeable):
  1. Vishful maintenance tickets = first-party OWN operational/customer-pain data (separate module).
  2. Competitor Google-Maps reviews = external independent review corpus -> NOT collected (Maps/aggregator).
  3. What we DO have here = competitor SELF-PUBLISHED testimonials + one self-displayed rating on their
     OWN sites -> curated marketing content (positive-biased), NOT independent review sentiment.

Every row carries verbatim short snippet + source_url + caveat. Writes ONLY new files. Modifies nothing.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
RET="2026-08-17"

# Real evidence captured in Playwright first-party renders (verbatim short snippets).
EV=[
 dict(property="Season 4 Rentals", property_type="serviced_apartment",
      source_platform="own first-party website", source_url="https://season4.in/season-4-rentals-thiruvanmiyur/",
      evidence_type="self_displayed_google_rating", rating="3.9/5", review_count=None, review_date=None,
      review_snippet="Google Review 3.9/5 ★★★★★ (displayed on own site)", theme="overall", sentiment="neutral_positive",
      caveat="rating ORIGINATES from Google and is re-displayed by the property on its own page — NOT independently "
             "collected by us; no review text/count/dates; serviced apartment (not a PG)."),
 dict(property="Kolam Serviced Apartments", property_type="serviced_apartment",
      source_platform="own first-party website", source_url="https://kolamapartments.com/",
      evidence_type="self_published_testimonial", rating=None, review_count=None, review_date=None,
      review_snippet="“the staff knew my name from day one” (guest testimonial)", theme="staff/service", sentiment="positive",
      caveat="curated/self-selected testimonial on own marketing site; positive-biased; no rating/count/date; serviced apt."),
 dict(property="Sri Mahalakshmi PG Accommodation", property_type="mens_pg",
      source_platform="own first-party website", source_url="https://mahalakshmipgaccommodation.com/",
      evidence_type="self_published_testimonial", rating=None, review_count=None, review_date=None,
      review_snippet="named testimonials; site highlights “Tasty & Quality Food”, “Caring & Friendly Staff”",
      theme="food, staff, safety", sentiment="positive",
      caveat="curated marketing testimonials (named), positive-biased; NOT independent reviews; no rating/count/date."),
]
# properties scanned with NO usable review evidence (proof of absence on first-party pages)
NO_EV=["TSP PG (tsppgaccommodation.com) — 'star' = marketing copy, no rating/reviews",
       "Kripa Homes (kripahomes.com) — 'star' = 'starts here'/newsletter, no reviews",
       "Olive Serviced Apartments (oliveservicedapartments.com) — thin/booking-gated, no reviews"]

def main():
    df=pd.DataFrame(EV)
    cols=["property","property_type","source_platform","source_url","evidence_type","rating","review_count",
          "review_date","review_snippet","theme","sentiment","retrieval_date","provenance","caveat"]
    df["retrieval_date"]=RET
    df["provenance"]="Playwright first-party render (phase3_playwright_web_evidence.csv run 2026-08-17)"
    df=df.reindex(columns=cols)
    df.to_csv(os.path.join(OUT,"phase3_review_evidence_inventory.csv"),index=False)

    summary=[("properties_with_any_review_evidence",len(df)),
     ("independent_google_maps_review_corpus","NOT collected — on Maps/aggregator, excluded by rules"),
     ("evidence_types_present","self_displayed_google_rating(1) + self_published_testimonial(2)"),
     ("all_collected_testimonials_are","curated + positive-biased (marketing), NOT representative review sentiment"),
     ("competitor_pain_point_signals","NONE — negative/independent reviews are only on Maps (not collected)"),
     ("properties_scanned_no_review_evidence",len(NO_EV)),
     ("distinct_datasets","1) Vishful own tickets (pain) 2) competitor Maps reviews (NOT collected) 3) competitor self-published testimonials (this file)"),
     ("additional_scraping_decision_value","LOW/NONE — Maps reviews not accessible via approved methods; self-testimonials are positive-biased marketing"),
     ("owner_rule","market customer signal -> Vishful opportunity; never competitor comparison; unknown stays unknown")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_review_evidence_inventory_summary.csv"),index=False)
    print("PHASE-3 REVIEW-EVIDENCE INVENTORY:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nrows:")
    for _,r in df.iterrows(): print(f"  {r['property']:34} | {r['evidence_type']:28} | rating={r['rating']} | theme={r['theme']}")
    print("\nno-evidence (proof of absence):")
    for x in NO_EV: print("  -",x)

if __name__=="__main__": main()
