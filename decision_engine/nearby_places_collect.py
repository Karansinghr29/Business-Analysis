"""
NEARBY-PLACE COLLECTION (network; run by hand; OUTSIDE run_all --verify).

Extends the category discovery of places_discovery_osm.py from lodging tags to the customer-useful
categories a prospective Vishful tenant cares about (transport / healthcare / essentials / education
/ financial). Reuses that module's proven mechanics verbatim: Nominatim-free fixed anchor, Overpass
3-mirror failover, OSM-policy User-Agent, unnamed-element skip, self-exclusion, haversine, stable
osm:type/id dedup key.

Anchor is NOT re-geocoded. It is the approved exact Vishful mapped coordinate already established in
phase3_competitor_distances.py (Google placeId ChIJl51FKnxdUjoR6GcIjXDtGGw, Apify compass/
crawler-google-places run AxGSVtCcgrP1vgevf). Never a suburb centroid.

Freezes evidence to outputs/phase3_nearby_places.csv. Everything downstream is deterministic over
those stored bytes. Writes ONLY that file + _summary.csv. Touches no existing output.

NO pricing. NO competitor comparison. NO walking time. NO Groq. Distances come only from coordinates.
"""
from __future__ import annotations
import os, sys, math, time, json, urllib.request, urllib.parse
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
UA = {"User-Agent": "VishfulMarketAI/1.0 (contact: wecare@vishful.co.in) nearby-location-evidence"}

# ---- approved Vishful anchor (identical to phase3_competitor_distances.py; not re-derived) --------
VISHFUL_LAT, VISHFUL_LNG = 12.9878697, 80.2551457
VISHFUL_PLACE_ID = "ChIJl51FKnxdUjoR6GcIjXDtGGw"
VISHFUL_NAME = "Vishful Vista Heights"
ANCHOR_NOTE = ("EXACT mapped property coordinate (Vishful Vista Heights, West Avenue, Thiruvanmiyur "
               "600041); Google placeId ChIJl51FKnxdUjoR6GcIjXDtGGw; Apify compass/crawler-google-places "
               "run AxGSVtCcgrP1vgevf. NOT a suburb centroid.")

RETRIEVAL_DATE = "2026-08-27"   # explicit constant — never now(); frozen into the CSV
PROVIDER = "openstreetmap"

# ---- category definitions -------------------------------------------------------------------------
# Only categories whose OSM classification is reliable AND genuinely useful to a prospective tenant.
# Each entry: canonical category -> (radius_m, [(osm_key, osm_value_regex, place_kind), ...])
# place_kind is the honest sub-label carried into evidence; it is the matched tag, never inferred.
CATEGORIES = {
    "TRANSPORT": (3000, [
        ("railway",          "^(station|halt)$",              "railway_station"),
        ("amenity",          "^bus_station$",                 "bus_station"),
        ("highway",          "^bus_stop$",                    "bus_stop"),
    ]),
    "HEALTHCARE": (3000, [
        ("amenity",          "^hospital$",                    "hospital"),
        ("amenity",          "^pharmacy$",                    "pharmacy"),
        ("amenity",          "^(clinic|doctors)$",            "clinic"),
    ]),
    "ESSENTIALS": (2000, [
        ("shop",             "^(supermarket|convenience|greengrocer)$", "grocery"),
        ("amenity",          "^marketplace$",                 "marketplace"),
    ]),
    "EDUCATION": (3000, [
        ("amenity",          "^(school|college|university)$", "education"),
    ]),
    "FINANCIAL": (2000, [
        ("amenity",          "^bank$",                        "bank"),
        ("amenity",          "^atm$",                         "atm"),
    ]),
}
CATEGORY_ORDER = ["TRANSPORT", "HEALTHCARE", "ESSENTIALS", "EDUCATION", "FINANCIAL"]

# Deterministic cap on STORED evidence, applied per (category, place_kind) so that a dense kind
# (bus stops) cannot crowd out a sparser but more useful one (railway stations) inside the same
# category. Nearest first, place_id breaks ties. Nothing is silently dropped: found vs stored is
# reported per category AND per kind in the summary.
MAX_STORED_PER_KIND = 5

OVERPASS_EPS = ["https://overpass-api.de/api/interpreter",
                "https://overpass.kumi.systems/api/interpreter",
                "https://overpass.openstreetmap.fr/api/interpreter"]


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km. Same formulation as phase3_competitor_distances.hav (R=6371)."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lng2 - lng1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(x))


def build_query():
    """One Overpass query for every category (minimises requests, per OSM usage policy)."""
    parts = []
    for cat in CATEGORY_ORDER:
        radius, tags = CATEGORIES[cat]
        for key, val_rx, _kind in tags:
            parts.append(f'  nwr(around:{radius},{VISHFUL_LAT},{VISHFUL_LNG})["{key}"~"{val_rx}"];')
    return "[out:json][timeout:90];\n(\n" + "\n".join(parts) + "\n);\nout center tags;"


def overpass(query):
    last = None; empty = None
    for ep in OVERPASS_EPS:
        try:
            req = urllib.request.Request(ep, data=urllib.parse.urlencode({"data": query}).encode(), headers=UA)
            j = json.load(urllib.request.urlopen(req, timeout=120))
            n = len(j.get("elements", []))
            print(f"  overpass {ep} -> {n} elements")
            if n > 0: return j
            empty = j
        except Exception as e:
            last = f"{ep}: {e}"; print("  overpass fail:", last)
        time.sleep(2)
    if empty is not None: return empty
    raise RuntimeError(f"all overpass endpoints failed. last={last}")


def classify(tags):
    """Deterministic tag -> (category, place_kind, radius). First match in CATEGORY_ORDER wins.
    The category IS the matched tag; nothing is inferred and no model is involved."""
    import re
    for cat in CATEGORY_ORDER:
        radius, tagspecs = CATEGORIES[cat]
        for key, val_rx, kind in tagspecs:
            v = tags.get(key)
            if v and re.match(val_rx, str(v)):
                return cat, kind, radius, f"{key}={v}"
    return None, None, None, None


def main():
    q = build_query()
    print("PHASE-3 NEARBY-PLACE COLLECTION (OSM Overpass)")
    print(f"  anchor: {VISHFUL_LAT},{VISHFUL_LNG}  ({ANCHOR_NOTE[:60]}...)")
    data = overpass(q)
    els = data.get("elements", [])
    print(f"  raw elements returned: {len(els)}")

    seen = set(); rows = []; skipped = {"unnamed": 0, "no_coord": 0, "dup_osm_id": 0,
                                        "self": 0, "out_of_radius": 0, "unclassified": 0}
    for el in els:
        t = el.get("tags", {}) or {}
        name = t.get("name")
        if not name or not str(name).strip():
            skipped["unnamed"] += 1; continue
        oid = f"osm:{el['type']}/{el['id']}"
        if oid in seen:
            skipped["dup_osm_id"] += 1; continue
        la = el.get("lat") or (el.get("center") or {}).get("lat")
        lo = el.get("lon") or (el.get("center") or {}).get("lon")
        if la is None or lo is None:
            skipped["no_coord"] += 1; continue
        try:
            la = float(la); lo = float(lo)
        except Exception:
            skipped["no_coord"] += 1; continue
        if not (-90 <= la <= 90 and -180 <= lo <= 180):
            skipped["no_coord"] += 1; continue
        if any(k in str(name).lower() for k in ["vishful", "vista heights"]):
            skipped["self"] += 1; continue
        cat, kind, radius, matched_tag = classify(t)
        if cat is None:
            skipped["unclassified"] += 1; continue
        dkm = haversine_km(VISHFUL_LAT, VISHFUL_LNG, la, lo)
        if dkm * 1000 > radius:
            skipped["out_of_radius"] += 1; continue
        seen.add(oid)
        addr = ", ".join(x for x in [t.get("addr:housenumber"), t.get("addr:street"),
                                     t.get("addr:suburb"), t.get("addr:city"), t.get("addr:postcode")] if x) or None
        # evidence_text = the raw matched tags, verbatim — the audit trail
        keep = {k: v for k, v in t.items() if k in ("name", "railway", "amenity", "highway", "shop",
                                                    "public_transport", "operator", "brand",
                                                    "addr:street", "addr:suburb", "addr:postcode")}
        rows.append(dict(
            property_id=VISHFUL_PLACE_ID, property_name=VISHFUL_NAME,
            property_lat=VISHFUL_LAT, property_lng=VISHFUL_LNG,
            place_id=oid, place_name=str(name).strip(), category=cat, place_kind=kind,
            matched_tag=matched_tag, lat=la, lng=lo, distance_km=round(dkm, 3),
            search_radius_m=radius, provider=PROVIDER,
            source_url=f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            source_type="structured_map", formatted_address=addr,
            evidence_text="; ".join(f"{k}={v}" for k, v in sorted(keep.items())),
            retrieval_date=RETRIEVAL_DATE,
            source_confidence=("High" if (addr or t.get("operator") or t.get("brand")) else "Medium"),
        ))

    df = pd.DataFrame(rows)
    found_per_cat = {c: int((df["category"] == c).sum()) if len(df) else 0 for c in CATEGORY_ORDER}
    found_per_kind = ({k: int(v) for k, v in df.groupby(["category", "place_kind"]).size().items()}
                      if len(df) else {})

    # deterministic ordering, then per-(category, kind) cap (nearest first; place_id breaks ties)
    if len(df):
        df["_ord"] = df["category"].map({c: i for i, c in enumerate(CATEGORY_ORDER)})
        df = df.sort_values(["_ord", "distance_km", "place_id"], kind="mergesort").reset_index(drop=True)
        df["_rank"] = df.groupby(["category", "place_kind"]).cumcount() + 1
        df = df[df["_rank"] <= MAX_STORED_PER_KIND].reset_index(drop=True)
        df = df.sort_values(["_ord", "distance_km", "place_id"], kind="mergesort").reset_index(drop=True)
        df = df.drop(columns=["_ord", "_rank"])
        df.insert(0, "evidence_id", [f"EV-NEAR-{i+1:03d}" for i in range(len(df))])

    COLS = ["evidence_id", "property_id", "property_name", "property_lat", "property_lng",
            "place_id", "place_name", "category", "place_kind", "matched_tag", "lat", "lng",
            "distance_km", "search_radius_m", "provider", "source_url", "source_type",
            "formatted_address", "evidence_text", "retrieval_date", "source_confidence"]
    df = (df.reindex(columns=COLS) if len(df) else pd.DataFrame(columns=COLS))
    df.to_csv(os.path.join(OUT, "phase3_nearby_places.csv"), index=False)

    stored_per_cat = {c: int((df["category"] == c).sum()) if len(df) else 0 for c in CATEGORY_ORDER}
    stored_per_kind = ({k: int(v) for k, v in df.groupby(["category", "place_kind"]).size().items()}
                       if len(df) else {})
    summary = [("anchor_lat", VISHFUL_LAT), ("anchor_lng", VISHFUL_LNG),
               ("anchor_place_id", VISHFUL_PLACE_ID), ("anchor_provenance", ANCHOR_NOTE),
               ("provider", PROVIDER), ("retrieval_date", RETRIEVAL_DATE),
               ("raw_elements_returned", len(els)),
               ("categories_queried", ",".join(CATEGORY_ORDER)),
               ("radius_m_per_category", str({c: CATEGORIES[c][0] for c in CATEGORY_ORDER})),
               ("found_per_category", str(found_per_cat)),
               ("stored_per_category", str(stored_per_cat)),
               ("found_per_kind", str(found_per_kind)),
               ("stored_per_kind", str(stored_per_kind)),
               ("max_stored_per_kind", MAX_STORED_PER_KIND),
               ("dropped_by_cap", str({c: found_per_cat[c] - stored_per_cat[c] for c in CATEGORY_ORDER})),
               ("skipped_unnamed", skipped["unnamed"]),
               ("skipped_no_or_invalid_coord", skipped["no_coord"]),
               ("skipped_duplicate_osm_id", skipped["dup_osm_id"]),
               ("skipped_self", skipped["self"]),
               ("skipped_out_of_category_radius", skipped["out_of_radius"]),
               ("skipped_unclassified", skipped["unclassified"]),
               ("total_stored_evidence", len(df)),
               ("distance_method", "haversine R=6371km from exact anchor coordinate; coordinates only"),
               ("walking_time_collected", "NO — straight-line km only; travel time is not derivable"),
               ("note", "customer-facing location evidence; no pricing, no competitor comparison, no ranking")]
    pd.DataFrame(summary, columns=["metric", "value"]).to_csv(
        os.path.join(OUT, "phase3_nearby_places_summary.csv"), index=False)

    for k, v in summary: print(f"  {k}: {v}")
    if len(df):
        print("\n  stored evidence (nearest first per category):")
        for _, r in df.iterrows():
            print(f"    {r['evidence_id']}  {r['category']:11} {r['distance_km']:>6} km  {r['place_name'][:44]:44} [{r['place_kind']}]")


if __name__ == "__main__":
    main()
