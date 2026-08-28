"""
Phase-3 NEARBY-PG DISCOVERY RESEARCH (isolated). FREE + LEGAL only.

Source of every record = my own WebSearch + first-party WebFetch of the PG's OWN website.
NO Google Places API, NO Gemini, NO aggregators, NO paid scraping. Aggregator/operator
prices are NEVER recorded (only the property's own site counts as price evidence).

This module does NOT compute competitor pricing / benchmarks. It only STRUCTURES and
CLASSIFIES the discovered evidence and preserves `unknown` wherever a first-party public
price is not shown. No fabricated prices, no invented sharing-grain.

Isolation contract:
  * writes ONLY new files: outputs/phase3_pg_research_candidates.csv,
    outputs/phase3_pg_price_evidence.csv, outputs/phase3_pg_research_summary.csv
  * does NOT touch/read/modify any locked output, dashboard, run_all ORDER, or source CSV.

Every price row carries a verbatim quote + source_url so it is auditable and reproducible.
To add a candidate: fetch its OWN site, paste verbatim numbers into EVIDENCE below with the
source_url. Never type a price you did not read on a first-party page.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUT, exist_ok=True)

# Aggregator / operator / directory / OTA hosts whose prices are NOT usable evidence.
AGGREGATOR_HOSTS = {
    "nobroker.in","olx.in","99acres.com","magicbricks.com","housing.com","justdial.com",
    "sulekha.com","rentmystay.com","squareyards.com","makaan.com","quikr.com","zolostays.com",
    "stanzaliving.com","cofynd.com","booking.com","tripadvisor.com","makemytrip.com","yube1.in",
    "commonfloor.com","nestaway.com","gopgo.in","chennaiproperties.com","colive.com","flatmate.in",
    "myroomie.in","hexahome.in","pgchoice.com","omrflats.com","studentcosy.com","rentok.com",
    "broklet.com","pg2let.com","scribd.com","blogspot.com",
}

# PG vs HOTEL classifier signal vocabularies (rule-based, reproducible).
PG_SIGNALS    = ("paying guest","pg accommodation","mens pg","men's pg","womens pg","women's pg",
                 "ladies hostel","boys hostel","gents hostel","working women","working men",
                 "sharing","per bed","monthly rent","mess","food included","co-living","coliving")
HOTEL_SIGNALS = ("per night","nightly","check-in","check out","book a room","suite","room service",
                 "star hotel","banquet","tariff per night","reception 24")

# --- Distance from Vishful Vista Heights (Tiruvanmiyur 600041) -------------------
# Anchor + candidate distances are SUBURB-CENTROID approximations from a real Nominatim
# (OpenStreetMap) geocode run — street-level addresses did NOT resolve on OSM, so no
# street-precision coordinates are claimed. Values below are the measured centroid
# haversine km; 600041 candidates share Vishful's suburb (<=~2km, distance not pinned).
VISHFUL_ANCHOR = "Tiruvanmiyur, Chennai 600041 (OSM node 12.98898,80.25159)"
CENTROID_KM = {"600020": 2.05, "600096": 2.26, "600097": 4.58}   # measured vs anchor

def compute_distance(locality, pincode):
    loc = (locality or "").lower(); pin = (pincode or "").split("/")[0].strip()
    if pin == "600041" or "thiruvanmiyur" in loc or "kamaraj nagar" in loc:
        return (None, "same_suburb_600041 (<=~2km; street geocode unavailable on OSM)", True)
    if pin in CENTROID_KM:
        km = CENTROID_KM[pin]
        return (km, f"suburb_centroid_{pin}", km <= 2.0)
    if "adyar" in loc:     return (CENTROID_KM["600020"], "suburb_centroid_600020", False)
    if "perungudi" in loc: return (CENTROID_KM["600096"], "suburb_centroid_600096", False)
    if "thoraipakkam" in loc or "omr" in loc: return (CENTROID_KM["600097"], "suburb_centroid_600097", False)
    return (None, "unknown_locality", False)

def classify(signals_text: str):
    t = (signals_text or "").lower()
    pg    = [s for s in PG_SIGNALS    if s in t]
    hotel = [s for s in HOTEL_SIGNALS if s in t]
    if pg and not hotel:   return "PG", f"PG signals={pg}; no hotel signal"
    if hotel and not pg:   return "HOTEL", f"hotel signals={hotel}; no PG signal"
    if pg and hotel:       return "PG_LIKELY", f"mixed (pg={pg} hotel={hotel}); PG signals dominate PG use"
    return "UNKNOWN", "no decisive PG/hotel signal in fetched text"

# ---------------------------------------------------------------------------
# EVIDENCE — each entry is a REAL first-party fetch (WebSearch discovery -> WebFetch own site).
# prices: list of dict{sharing, ac, room_class, monthly_rent, quote}. monthly_rent=None => unknown.
# grain: full_by_sharing | by_room_class | floor_only | none
# ---------------------------------------------------------------------------
EVIDENCE = [
 dict(property_name="Diyaa Paying Guest", source_url="https://menspg.in/", is_first_party=True,
      segment="men", locality="Indira Nagar, Adyar", pincode="600020",
      signals_text="paying guest men only sharing AC non-AC monthly rent all inclusive WiFi RO housekeeping",
      inclusions="WiFi, R.O water, housekeeping", extra_charges="Electricity per TN Commercial Tariff",
      rent_basis="all-inclusive per bed/month, rate for stay >3 months (1mo=2x, 2mo=1.5x)",
      grain="full_by_sharing", note="Fetched 2026: full per-bed x sharing x AC grid published on own site.",
      prices=[
        dict(sharing="single", ac=True,  room_class=None, monthly_rent=16000, quote="AC Single Sharing (1 person): Rs. 16,000"),
        dict(sharing="two",    ac=True,  room_class=None, monthly_rent=8000,  quote="AC Two Sharing (2 persons): Rs. 8,000"),
        dict(sharing="three",  ac=True,  room_class=None, monthly_rent=6500,  quote="AC Three Sharing (3 persons): Rs. 6,500"),
        dict(sharing="four",   ac=True,  room_class=None, monthly_rent=6000,  quote="AC Four Sharing (4 persons): Rs. 6,000"),
        dict(sharing="single", ac=False, room_class=None, monthly_rent=11000, quote="Non-AC Single Sharing: Rs. 11,000"),
        dict(sharing="two",    ac=False, room_class=None, monthly_rent=6500,  quote="Non-AC Two Sharing: Rs. 6,500"),
        dict(sharing="three",  ac=False, room_class=None, monthly_rent=5500,  quote="Non-AC Three Sharing: Rs. 5,500"),
        dict(sharing="four",   ac=False, room_class=None, monthly_rent=5000,  quote="Non-AC Four Sharing: Rs. 5,000"),
      ]),
 dict(property_name="Sumathi Illam", source_url="https://mypgatchennai.com/", is_first_party=True,
      segment="men", locality=None, pincode=None,
      signals_text="pg accommodation for men dormitory non-ac ac room attached bathroom sharing occupancy",
      inclusions="attached toilet & bathroom", extra_charges="food optional extra (B 1000/L 1100/D 1000)",
      rent_basis="per bed/month by ROOM CLASS (not by sharing count)",
      grain="by_room_class", note="Price grain is room-class only; sharing-count NOT stated. Locality/pincode not on page.",
      prices=[
        dict(sharing=None, ac=None,  room_class="dormitory", monthly_rent=3500, quote="Dormitory: Rs.3,500/-"),
        dict(sharing=None, ac=False, room_class="non_ac",    monthly_rent=4500, quote="Non-AC Room: Rs.4,500/-"),
        dict(sharing=None, ac=True,  room_class="ac",        monthly_rent=5000, quote="AC Room: Rs.5,000/-"),
      ]),
 dict(property_name="Feel At Home Ladies Hostel", source_url="https://www.hostelforladies.com/", is_first_party=True,
      segment="women", locality="Perungudi / Thoraipakkam OMR", pincode="600096/600097",
      signals_text="ladies hostel womens pg sharing single to six separate EB meter working women",
      inclusions="AC, WiFi, locker, separate EB meter, kitchen", extra_charges="EB separate meter",
      rent_basis="floor only",
      grain="floor_only", note='Only "Rent Starts from Rs.6200" published; no per-sharing/AC breakdown -> price UNKNOWN at grain.',
      prices=[
        dict(sharing=None, ac=None, room_class=None, monthly_rent=None,
             quote='Rent Starts from Rs.6200 (floor only, not grain-specific)'),
      ]),
 dict(property_name="TSP PG Accommodation (Boys)", source_url="https://tsppgaccommodation.com/", is_first_party=True,
      segment="men", locality="Thiruvanmiyur", pincode=None,
      signals_text="boys hostel paying guest AC non-AC single & sharing rooms working professionals students",
      inclusions="AC/Non-AC, WiFi", extra_charges=None,
      rent_basis="none published",
      grain="none", note="Own site shows only 'Enquiry Now & Get Quote' + phone; NO public price -> UNKNOWN.",
      prices=[
        dict(sharing=None, ac=None, room_class=None, monthly_rent=None,
             quote='No price on site; "Enquiry Now & Get Quote" (9841108085 / 24483085)'),
      ]),
 dict(property_name="Kripa Homes PG (Men)", source_url="https://kripahomes.com/pg-thiruvanmiyur/", is_first_party=True,
      segment="men", locality="Kamaraj Nagar, Thiruvanmiyur", pincode="600041",
      signals_text="mens pg hostel thiruvanmiyur one two three four sharing attached bathroom",
      inclusions="attached bathroom", extra_charges=None,
      rent_basis="none published",
      grain="none", note="Own site lists One/Two/Three/Four sharing but NO price displayed -> UNKNOWN. Same pincode 600041 as Vishful.",
      prices=[
        dict(sharing=None, ac=None, room_class=None, monthly_rent=None,
             quote="Sharing tiers shown, no price; contact 8015113713 / sales@kripahomes.com"),
      ]),
 dict(property_name="Emy PG Accommodation (Men)", source_url="https://emypgaccommodation.in/", is_first_party=True,
      segment="men", locality="Thiruvanmiyur (14 units), Adyar (3), Besant Nagar (1), Semmancheri (1)", pincode=None,
      signals_text="men's hostel pg accommodation multiple units 24x7 wifi view units",
      inclusions="24x7 WiFi", extra_charges=None,
      rent_basis="none on homepage",
      grain="none", note="Homepage fetch shows NO price (a search snippet implied a grid; the actual page does not display it) -> UNKNOWN pending unit-page fetch.",
      prices=[
        dict(sharing=None, ac=None, room_class=None, monthly_rent=None,
             quote="No price displayed on homepage; 'View Units' links only (98402 28776 / 93812 74173)"),
      ]),
 dict(property_name="Sri Maha Hostels (Ladies)", source_url="https://www.srimahahostels.com/our-branches.php", is_first_party=True,
      segment="women", locality="Kamaraj Nagar, Thiruvanmiyur", pincode="600041",
      signals_text="ladies hostel kamaraj nagar thiruvanmiyur cctv organic meals sharing",
      inclusions="24/7 CCTV, organic meals", extra_charges=None,
      rent_basis="none published",
      grain="none", note="Ladies hostel (out of men's segment). Own site: address 50/1 Valmiki St, Kamaraj Nagar 600041; NO price -> UNKNOWN.",
      prices=[
        dict(sharing=None, ac=None, room_class=None, monthly_rent=None,
             quote="No price on branches page; contact 9080600914"),
      ]),
 dict(property_name="Tidel Hostel (Co-ed)", source_url="https://tidelhostel.com/", is_first_party=True,
      segment="co-ed", locality="Kamaraj Nagar West, Thiruvanmiyur", pincode="600041",
      signals_text="gents ladies hostel thiruvanmiyur single ac non-ac double sharing four sharing food",
      inclusions="veg/non-veg food", extra_charges=None,
      rent_basis="none published",
      grain="none", note="Boys & girls. Own site: E57A 7th West St, Kamaraj Nagar West 600041; sharing tiers shown, NO price -> UNKNOWN.",
      prices=[
        dict(sharing=None, ac=None, room_class=None, monthly_rent=None,
             quote="Single AC/non-AC, double, four-sharing referenced; no rates shown"),
      ]),
 dict(property_name="Sri Mahalakshmi PG (Men)", source_url="https://mahalakshmipgaccommodation.com/", is_first_party=True,
      segment="men", locality="Perungudi", pincode="600096",
      signals_text="pg accommodation males gents perungudi omr 2 3 4 5 sharing ac non-ac meals",
      inclusions="WiFi, meals, laundry, 24/7 security, parking", extra_charges=None,
      rent_basis="none published",
      grain="none", note="Men's PG Perungudi (near OMR), 3 branches ~800 residents; 2-5 sharing AC/non-AC referenced but NO price -> UNKNOWN.",
      prices=[
        dict(sharing=None, ac=None, room_class=None, monthly_rent=None,
             quote="Sharing 2/3/4/5 + AC/non-AC referenced; no rates shown; contact 7838889393"),
      ]),
]

def host_of(url: str) -> str:
    h = url.split("//",1)[-1].split("/",1)[0].lower()
    return h[4:] if h.startswith("www.") else h

def main():
    cand_rows, price_rows = [], []
    for i, e in enumerate(EVIDENCE, 1):
        pid = f"pg{i:02d}"
        host = host_of(e["source_url"])
        is_agg = any(host == a or host.endswith("."+a) for a in AGGREGATOR_HOSTS)
        kind, reason = classify(e["signals_text"])
        priced = [p for p in e["prices"] if p["monthly_rent"] is not None]
        dist_km, dist_prec, within2 = compute_distance(e["locality"], e["pincode"])
        in_600041 = (str(e["pincode"] or "").split("/")[0].strip()=="600041")
        cand_rows.append(dict(
            property_id=pid, property_name=e["property_name"], segment=e["segment"],
            locality=e["locality"], pincode=e["pincode"], source_url=e["source_url"],
            source_host=host, is_first_party=bool(e["is_first_party"]), is_aggregator_source=is_agg,
            property_kind=kind, classify_reason=reason,
            dist_km_from_vishful=dist_km, distance_precision=dist_prec,
            within_2km_of_vishful=within2, in_600041=in_600041,
            price_grain_quality=e["grain"], has_first_party_price=bool(priced),
            n_price_points=len(priced), rent_basis=e["rent_basis"],
            inclusions=e["inclusions"], extra_charges=e["extra_charges"],
            evidence_method="WebSearch discovery + first-party WebFetch of own site (no API, no aggregator)",
            note=e["note"]))
        for p in e["prices"]:
            price_rows.append(dict(
                property_id=pid, property_name=e["property_name"], source_url=e["source_url"],
                is_first_party=bool(e["is_first_party"]), segment=e["segment"],
                locality=e["locality"], pincode=e["pincode"],
                sharing_type=p["sharing"] if p["sharing"] else "unknown",
                ac=("ac" if p["ac"] is True else "non_ac" if p["ac"] is False else "unknown"),
                room_class=p["room_class"] if p["room_class"] else "unknown",
                monthly_rent_inr=p["monthly_rent"],                          # None => unknown, preserved
                price_status=("published" if p["monthly_rent"] is not None else "unknown"),
                price_grain_quality=e["grain"], rent_basis=e["rent_basis"],
                inclusions=e["inclusions"], extra_charges=e["extra_charges"],
                verbatim_quote=p["quote"]))

    cand = pd.DataFrame(cand_rows)
    price = pd.DataFrame(price_rows)
    cand.to_csv(os.path.join(OUT,"phase3_pg_research_candidates.csv"), index=False)
    price.to_csv(os.path.join(OUT,"phase3_pg_price_evidence.csv"), index=False)

    npub = int((price["price_status"]=="published").sum())
    nunk = int((price["price_status"]=="unknown").sum())
    full = int((cand["price_grain_quality"]=="full_by_sharing").sum())
    men = cand[cand["segment"]=="men"]
    men_full = men[men["price_grain_quality"]=="full_by_sharing"]
    summary = [
        ("candidates_total", len(cand)),
        ("candidates_first_party", int(cand["is_first_party"].sum())),
        ("candidates_aggregator_source", int(cand["is_aggregator_source"].sum())),
        ("candidates_men_segment", len(men)),
        ("in_600041", int(cand["in_600041"].sum())),
        ("within_2km_of_vishful", int(cand["within_2km_of_vishful"].sum())),
        ("men_with_full_sharing_grain", len(men_full)),
        ("classified_PG", int(cand["property_kind"].isin(["PG","PG_LIKELY"]).sum())),
        ("classified_HOTEL", int((cand["property_kind"]=="HOTEL").sum())),
        ("classified_UNKNOWN", int((cand["property_kind"]=="UNKNOWN").sum())),
        ("with_first_party_price", int(cand["has_first_party_price"].sum())),
        ("grain_full_by_sharing", full),
        ("grain_by_room_class", int((cand["price_grain_quality"]=="by_room_class").sum())),
        ("grain_floor_only", int((cand["price_grain_quality"]=="floor_only").sum())),
        ("grain_none", int((cand["price_grain_quality"]=="none").sum())),
        ("price_rows_published", npub),
        ("price_rows_unknown", nunk),
        ("verdict", "insufficient comparable data" if full < 2 else "some comparable grain available"),
    ]
    pd.DataFrame(summary, columns=["metric","value"]).to_csv(
        os.path.join(OUT,"phase3_pg_research_summary.csv"), index=False)

    print("PHASE-3 PG RESEARCH (first-party evidence only) written:")
    for m,v in summary: print(f"  {m}: {v}")
    print("\ncandidates:")
    for _,r in cand.iterrows():
        d = f"{r['dist_km_from_vishful']}km" if pd.notna(r['dist_km_from_vishful']) else r['distance_precision']
        print(f"  {r['property_id']} | {r['property_name']} | {r['property_kind']} | {r['segment']} | "
              f"{r['locality'] or 'locality?'} {r['pincode'] or ''} | dist={d} within2km={r['within_2km_of_vishful']} | "
              f"grain={r['price_grain_quality']} | price={'YES' if r['has_first_party_price'] else 'unknown'} | {r['source_host']}")
    print("\nNo competitor benchmark computed. unknown preserved. No aggregator/API/fabricated price.")

if __name__=="__main__": main()
