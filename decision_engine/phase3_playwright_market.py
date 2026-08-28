"""
Phase-3 EXPERIMENTAL — Playwright (headless Chromium) targeted check of already-identified
first-party domains for JS-rendered market info static WebFetch/Apify missed. Bounded + isolated.

Ran: 6 first-party domains, homepage + up to 2 pricing/room subpages each = 14 pages rendered,
all HTTP 200, 0 blocked. No login / CAPTCHA / anti-bot bypass. Public pages only.

Result: 0 valid first-party PRICES (no digit-bearing per-bed/monthly figure on any page —
'GST 12% Extra' and 'Daily & Monthly Rentals' are not prices; Book-Now/enquiry only). BUT
additional publicly-displayed market ATTRIBUTES were rendered (amenities, room/sharing/AC configs)
— genuine non-price market signals. Amenity flags are True only where the rendered page explicitly
showed them; absence => null/unknown (never False-asserted, never fabricated).

Every attribute below is grounded in the actual rendered text (scratchpad/pw_results.json).
Writes ONLY phase3_playwright_market_research.csv + _web_evidence.csv + _summary.csv.
Does not modify master / dashboard / Market AI spec / locked outputs / run_all / existing phase3.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
SHOTS="scratchpad/pw_shots"  # evidence screenshots (scratchpad; not distributed)

T=True; N=None  # T = explicitly rendered on the property's own page; N = unknown (not shown)
# Grounded in rendered text of each first-party domain.
RESEARCH=[
 dict(domain="tsppgaccommodation.com", canonical="tsp_pg", property_name="TSP PG Accommodation",
      property_type="mens_pg", gender="men", pages_rendered=3, blocked=0,
      room_types="single & sharing (single/double)", sharing_config="single, double", ac_available=T, non_ac=N,
      wifi=T, food=T, laundry=N, housekeeping=N, cctv_security=N, parking=N, power_backup=N,
      evidence="Rendered: AC, single/double sharing rooms, WiFi, food. No price figure (enquiry only).",
      price_status="unknown"),
 dict(domain="kripahomes.com", canonical="kripa_homes", property_name="Kripa Homes PG",
      property_type="mens_pg", gender="men", pages_rendered=2, blocked=0,
      room_types="one/two/three/four sharing", sharing_config="sharing (1-4)", ac_available=T, non_ac=N,
      wifi=T, food=N, laundry=N, housekeeping=N, cctv_security=T, parking=T, power_backup=N,
      evidence="Rendered amenities: AC, CCTV, parking, WiFi, sharing rooms. No price figure.",
      price_status="unknown"),
 dict(domain="mahalakshmipgaccommodation.com", canonical="sri_mahalakshmi_pg", property_name="Sri Mahalakshmi PG Accommodation",
      property_type="mens_pg", gender="men", pages_rendered=3, blocked=0,
      room_types="single/double, AC & Non-AC, 2-5 sharing", sharing_config="single, double, 2-5 sharing",
      ac_available=T, non_ac=T, wifi=T, food=T, laundry=N, housekeeping=N, cctv_security=T, parking=T, power_backup=N,
      evidence="Richest render: AC + Non-AC, single/double + 2-5 sharing, WiFi, food, parking, security. No price figure.",
      price_status="unknown"),
 dict(domain="season4.in", canonical="season4", property_name="Season 4 Rentals",
      property_type="serviced_apartment", gender="unknown", pages_rendered=2, blocked=0,
      room_types="1BHK/2BHK suite (serviced apt)", sharing_config=N, ac_available=N, non_ac=N,
      wifi=T, food=T, laundry=T, housekeeping=N, cctv_security=N, parking=T, power_backup=T,
      evidence="Rendered: WiFi, laundry, generator (power backup), food, parking; 'Daily and Monthly Rentals' + 'GST 12% Extra' (NOT a price); Book-Now only.",
      price_status="unknown"),
 dict(domain="kolamapartments.com", canonical="kolam_serviced", property_name="Kolam Serviced Apartments",
      property_type="serviced_apartment", gender="unknown", pages_rendered=1, blocked=0,
      room_types="serviced apartment", sharing_config=N, ac_available=N, non_ac=N,
      wifi=T, food=T, laundry=N, housekeeping=N, cctv_security=N, parking=N, power_backup=N,
      evidence="Rendered: meals, WiFi. No price (OTA/booking-driven serviced apt).",
      price_status="unknown"),
 dict(domain="oliveservicedapartments.com", canonical="olive_serviced", property_name="Olive Serviced Apartments",
      property_type="serviced_apartment", gender="unknown", pages_rendered=2, blocked=0,
      room_types=N, sharing_config=N, ac_available=N, non_ac=N,
      wifi=N, food=N, laundry=N, housekeeping=N, cctv_security=N, parking=N, power_backup=N,
      evidence="Thin render (JS/booking-gated, ~630 chars); no amenities or price surfaced. Not bypassed.",
      price_status="unknown"),
]

# Per-page evidence (14 rendered pages; all 200, 0 blocked; no price found on any).
EVIDENCE=[
 ("season4.in","https://season4.in/","home",200,False,2381),
 ("season4.in","https://season4.in/season-4-rentals-thiruvanmiyur/","sub",200,False,4284),
 ("season4.in","https://season4.in/wp-content/uploads/2024/03/Suite-Room-1.jpg","sub",200,False,0),
 ("kolamapartments.com","https://kolamapartments.com/","home",200,False,3232),
 ("oliveservicedapartments.com","https://oliveservicedapartments.com/chennai","home",200,False,630),
 ("oliveservicedapartments.com","https://oliveservicedapartments.com/lowest-price-guarantee","sub",200,False,1769),
 ("tsppgaccommodation.com","https://tsppgaccommodation.com/","home",200,False,1574),
 ("tsppgaccommodation.com","https://tsppgaccommodation.com/index.html","sub",200,False,1574),
 ("tsppgaccommodation.com","https://tsppgaccommodation.com/about-us.html","sub",200,False,1793),
 ("kripahomes.com","https://kripahomes.com/pg-thiruvanmiyur/","home",200,False,1424),
 ("kripahomes.com","https://kripahomes.com/pg-thiruvanmiyur/#Amenities","sub",200,False,1438),
 ("mahalakshmipgaccommodation.com","https://mahalakshmipgaccommodation.com/","home",200,False,7193),
 ("mahalakshmipgaccommodation.com","https://mahalakshmipgaccommodation.com/index","sub",200,False,7193),
 ("mahalakshmipgaccommodation.com","https://mahalakshmipgaccommodation.com/aboutus","sub",200,False,3436),
]

def main():
    df=pd.DataFrame(RESEARCH)
    df["monthly_rent"]=None; df["sharing_type_priced"]=None; df["ac_priced"]=None
    df["deposit"]=None; df["eb_electricity"]=None; df["food_price"]=None; df["price_unit"]=None
    df["price_source_url"]=None; df["provenance"]="playwright_first_party_render"
    df["official_site_verified"]=True
    df["screenshot_dir"]=SHOTS
    cols=["domain","canonical","property_name","property_type","gender","pages_rendered","blocked",
          "official_site_verified","room_types","sharing_config","ac_available","non_ac",
          "wifi","food","laundry","housekeeping","cctv_security","parking","power_backup",
          "monthly_rent","sharing_type_priced","ac_priced","deposit","eb_electricity","food_price",
          "price_unit","price_status","price_source_url","evidence","provenance","screenshot_dir"]
    df[cols].to_csv(os.path.join(OUT,"phase3_playwright_market_research.csv"),index=False)
    ev=pd.DataFrame(EVIDENCE,columns=["domain","url","kind","http_status","blocked","rendered_text_len"])
    ev["price_found"]=False; ev["provenance"]="playwright_headless_chromium"
    ev.to_csv(os.path.join(OUT,"phase3_playwright_web_evidence.csv"),index=False)

    amen_cols=["wifi","food","laundry","housekeeping","cctv_security","parking","power_backup","ac_available","non_ac"]
    new_attr=int((df[amen_cols]==True).any(axis=1).sum())
    summary=[
     ("domains_attempted",len(df)),
     ("pages_rendered",int(ev.shape[0])),
     ("pages_blocked",int(ev["blocked"].sum())),
     ("js_rendered_info_discovered","YES — amenities/room-config/AC attributes on 5/6 domains"),
     ("first_party_prices_discovered",0),
     ("valid_comparable_perbed_sharing_ac",0),
     ("domains_with_new_market_attributes",new_attr),
     ("richest_attribute_source","mahalakshmipgaccommodation.com (AC+NonAC, single/double+2-5 sharing, WiFi, food, parking, security)"),
     ("screenshots_captured","~12 (scratchpad/pw_shots)"),
     ("browser_access_errors","none — all 200, 0 blocked, no bypass"),
     ("unknown_price_rows",int((df["price_status"]=="unknown").sum())),
     ("conclusion","Playwright rendered pages fine but NO valid first-party price exists -> remaining pricing gap is a DATA-AVAILABILITY limitation, not a scraping-tool limitation"),
    ]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_playwright_summary.csv"),index=False)
    print("PHASE-3 PLAYWRIGHT MARKET RESEARCH:")
    for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": main()
