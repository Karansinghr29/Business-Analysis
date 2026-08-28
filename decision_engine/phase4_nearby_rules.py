"""
PHASE-4 NEARBY CUSTOMER-FACING RECOMMENDATION RULES (deterministic, offline, no model, no network).

Option A: writes ONLY outputs/phase4_nearby_recommendations.csv (+ _evidence.csv, _summary.csv).
This is a SEPARATE customer-facing layer. It does not touch, extend or renumber the 14 backbone
decisions, the 6 Phase-3 opportunities, the 13 AIREC recommendations, the 33-recommendation
lifecycle, Page 15, the reducer or any registry.

Reads four FROZEN CSVs and nothing else:
    phase3_nearby_places.csv               (OSM evidence: name, coordinates, distance)
    phase3_nearby_classification.csv       (Groq usefulness judgement)
    phase3_nearby_wording.csv              (Groq sentence, digit-free)
    phase3_vishful_site_location_facts.csv (Playwright: what the site already shows)

Every number that reaches a recommendation is recomputed here from stored coordinates. The model's
sentence is used for phrasing only and is re-checked for digits and travel-time vocabulary before
use. No now(), no random, no network — safe to re-run and reproduce byte-identically.

DISTANCE FORMATTING RULE (documented, enforced by the validator):
    displayed = f"{round(stored_distance_km, 2):.2f} km"
    i.e. the stored 3-decimal value rounded half-even to exactly 2 decimals, suffixed " km".
    The validator asserts abs(float(displayed) - stored) <= 0.005 for every displayed distance.
"""
from __future__ import annotations
import os, sys, math, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")


def o(f): return pd.read_csv(os.path.join(OUT, f))


# ---- policy constants -----------------------------------------------------------------------------
MIN_USEFUL_PLACES = 2          # a category with fewer verified useful places produces no recommendation
MAX_CITED_PLACES = 5           # places named in the recommendation text (nearest first)
CATEGORY_ORDER = ["TRANSPORT", "HEALTHCARE", "ESSENTIALS", "EDUCATION", "FINANCIAL"]

# Fallback phrasing used when the model sentence was rejected. Deterministic, digit-free.
FALLBACK_SENTENCE = ("The property page can show verified nearby places of this category, "
                     "with their names and straight-line distances.")

# Blocked in any produced text. Travel time is not derivable from straight-line distance.
WALKING_RX = re.compile(r"\b(min|mins|minute|minutes|hour|hours|walk|walking|walkable|drive|driving|"
                        r"commute|travel time|on foot)\b", re.I)
COMPARISON_RX = re.compile(r"\b(better|best|worse|worst|cheaper|cheapest|expensive|benchmark|"
                           r"compared|versus|vs\.?|outperform|rank(?:ing|ed)?)\b", re.I)


def haversine_km(lat1, lng1, lat2, lng2):
    """Identical formulation to nearby_places_collect.haversine_km / phase3_competitor_distances.hav."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lng2 - lng1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(x))


def fmt_km(stored_km):
    """THE documented formatting rule. Single source of truth, reused by the validator."""
    return f"{round(float(stored_km), 2):.2f} km"


def main():
    P = o("phase3_nearby_places.csv")
    C = o("phase3_nearby_classification.csv")
    W = o("phase3_nearby_wording.csv")
    V = o("phase3_vishful_site_location_facts.csv")

    # ---- recompute every distance from stored coordinates; never trust the collected value --------
    recomputed = []
    for _, r in P.iterrows():
        d = haversine_km(float(r["property_lat"]), float(r["property_lng"]),
                         float(r["lat"]), float(r["lng"]))
        recomputed.append(round(d, 3))
    P = P.copy(); P["distance_km_recomputed"] = recomputed
    P["distance_delta"] = (P["distance_km_recomputed"] - P["distance_km"]).abs()
    drift = P[P["distance_delta"] > 0.001]
    if len(drift):
        sys.exit(f"FAIL: {len(drift)} stored distance(s) disagree with recomputation from coordinates:\n"
                 + drift[["evidence_id", "place_name", "distance_km", "distance_km_recomputed"]].to_string())

    # ---- join usefulness; keep only places the classifier confirmed useful ------------------------
    use = C[C["usefulness"] == "useful"]["evidence_id"].tolist()
    E = P[P["evidence_id"].isin(use)].copy()
    E = E.sort_values(["category", "distance_km_recomputed", "place_id"], kind="mergesort")

    # ---- dedup guards ----------------------------------------------------------------------------
    dup_osm = E[E.duplicated(subset=["place_id"], keep=False)]
    if len(dup_osm):
        sys.exit(f"FAIL: duplicate OSM identity in evidence:\n{dup_osm[['evidence_id','place_id']].to_string()}")
    dup_ev = E[E.duplicated(subset=["evidence_id"], keep=False)]
    if len(dup_ev):
        sys.exit(f"FAIL: duplicate evidence_id:\n{dup_ev['evidence_id'].tolist()}")

    # ---- collapse same-named places within a category --------------------------------------------
    # OSM maps one bus stop as several nodes (separate platforms/directions), all carrying the same
    # name. They are distinct OSM identities, so the dedup above cannot see them — but to a reader
    # "Jayanti (0.05 km), Jayanti (0.10 km), Jayanti (0.11 km)" is one place printed three times.
    # Keep the nearest of each (category, normalised name); record how many were folded away.
    E["_name_key"] = E["place_name"].astype(str).str.lower().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
    before = len(E)
    E = E.sort_values(["category", "distance_km_recomputed", "place_id"], kind="mergesort")
    folded = E.groupby(["category", "_name_key"]).size().rename("n").reset_index()
    E = E.drop_duplicates(subset=["category", "_name_key"], keep="first").copy()
    same_name_folded = before - len(E)

    site = {r["category"]: r for _, r in V.iterrows()}
    words = {r["category"]: r for _, r in W.iterrows()}

    recs = []; ev_rows = []; skipped = []
    for cat in CATEGORY_ORDER:
        sub = E[E["category"] == cat]
        if len(sub) < MIN_USEFUL_PLACES:
            skipped.append(dict(category=cat, reason=f"only {len(sub)} verified useful place(s); "
                                                     f"minimum is {MIN_USEFUL_PLACES}"))
            continue

        sv = site.get(cat)
        spec = str(sv["visibility_specificity"]) if sv is not None else "unknown"
        vis = str(sv["already_visible"]) if sv is not None else "Unknown"

        if spec == "specific":
            skipped.append(dict(category=cat, reason="Vishful site already shows named places with "
                                                     "distances for this category — equivalent "
                                                     "information already provided"))
            continue

        # ---- cite with kind diversity ------------------------------------------------------------
        # Taking the N nearest would fill a category with one kind (all bus stops, no station).
        # Round-robin across place_kind by ascending distance, so every real service type in the
        # category is represented before any kind takes a second slot.
        by_kind = {}
        for _, r in sub.iterrows():
            by_kind.setdefault(r["place_kind"], []).append(r)
        kind_order = sorted(by_kind, key=lambda k: (by_kind[k][0]["distance_km_recomputed"], k))
        picked = []
        depth = 0
        while len(picked) < MAX_CITED_PLACES and any(len(by_kind[k]) > depth for k in kind_order):
            for k in kind_order:
                if len(picked) >= MAX_CITED_PLACES: break
                if len(by_kind[k]) > depth: picked.append(by_kind[k][depth])
            depth += 1
        cited = (pd.DataFrame(picked).sort_values(["distance_km_recomputed", "place_id"], kind="mergesort")
                 if picked else sub.head(MAX_CITED_PLACES))
        # ---- deterministic number injection ------------------------------------------------------
        nearest = cited.iloc[0]
        nearest_disp = fmt_km(nearest["distance_km_recomputed"])
        farthest_disp = fmt_km(cited.iloc[-1]["distance_km_recomputed"])
        place_bits = [f"{r['place_name']} ({fmt_km(r['distance_km_recomputed'])})" for _, r in cited.iterrows()]

        # ---- wording: model sentence, re-checked here before use ---------------------------------
        wrow = words.get(cat)
        sentence = FALLBACK_SENTENCE; wording_prov = "deterministic_fallback"
        if wrow is not None:
            s = str(wrow["model_sentence"])
            if (s and s != "(extraction_missing)" and not re.search(r"\d", s)
                    and not WALKING_RX.search(s) and not COMPARISON_RX.search(s)):
                sentence = s; wording_prov = f"groq:{wrow['model']} temp=0 (digit-free, re-checked)"
        section = str(wrow["section_name"]) if wrow is not None else f"Nearby {cat.title()}"

        if spec == "generic":
            gap = ("Site mentions this category in prose but names no place and gives no distance. "
                   "Missing piece: named places with verified straight-line distances.")
            ask = (f"Upgrade the existing general mention into a '{section}' section listing the "
                   f"verified nearby places below with their straight-line distances.")
        else:
            gap = "No equivalent information found on the rendered Vishful pages."
            ask = f"Add a '{section}' section to the Vishful property page listing the verified nearby places below."

        rid = f"AIREC-NEARBY-{cat}"
        eids = cited["evidence_id"].tolist()
        rec_text = f"{ask} {sentence}"
        customer_change = (f"A prospective tenant viewing the Vishful property page can see a "
                           f"'{section}' section naming verified nearby places and how far each is "
                           f"in straight-line distance (nearest {nearest_disp}).")

        # ---- self-guard before writing -----------------------------------------------------------
        blob = " ".join([rec_text, customer_change, ask, sentence])
        if WALKING_RX.search(blob):
            sys.exit(f"FAIL: walking/travel-time language produced for {rid}")
        if COMPARISON_RX.search(blob):
            sys.exit(f"FAIL: comparison language produced for {rid}")
        allowed_numbers = {fmt_km(r["distance_km_recomputed"]).replace(" km", "") for _, r in cited.iterrows()}
        for tok in re.findall(r"\d+(?:\.\d+)?", blob):
            if tok not in allowed_numbers:
                sys.exit(f"FAIL: untraceable number '{tok}' in {rid} text (allowed: {sorted(allowed_numbers)})")

        recs.append(dict(
            recommendation_id=rid,
            category=cat,
            section_name=section,
            recommendation=rec_text,
            customer_facing_change=customer_change,
            property_id=str(nearest["property_id"]),
            property_name=str(nearest["property_name"]),
            property_lat=float(nearest["property_lat"]),
            property_lng=float(nearest["property_lng"]),
            evidence_ids="|".join(eids),
            evidence_count=len(eids),
            evidence_available_in_category=int(len(sub)),
            place_names="|".join(cited["place_name"].astype(str).tolist()),
            place_kinds="|".join(sorted(set(cited["place_kind"].astype(str).tolist()))),
            distance_summary=f"nearest {nearest_disp}, farthest cited {farthest_disp}",
            nearest_place=str(nearest["place_name"]),
            nearest_distance_km=float(nearest["distance_km_recomputed"]),
            nearest_distance_display=nearest_disp,
            place_distance_display="|".join(place_bits),
            source_provider=str(nearest["provider"]),
            source_urls="|".join(cited["source_url"].astype(str).tolist()),
            source_type=str(nearest["source_type"]),
            evidence_retrieval_date=str(nearest["retrieval_date"]),
            website_visibility_status=vis,
            website_visibility_specificity=spec,
            website_visibility_evidence=(str(sv["evidence_text"]) if sv is not None and pd.notna(sv["evidence_text"]) else None),
            website_visibility_url=(str(sv["evidence_url"]) if sv is not None and pd.notna(sv["evidence_url"]) else None),
            material_gap=gap,
            distance_method="haversine R=6371km recomputed from stored coordinates (offline)",
            distance_format_rule='f"{round(stored_distance_km, 2):.2f} km"',
            walking_time_claimed="False",
            owner_verify_required=True,
            confidence="Medium",
            data_limitation=("OpenStreetMap is volunteer-maintained: a place may be stale and an "
                             "absent place is not evidence of absence. Straight-line distance is not "
                             "travel distance. Owner must confirm each place before publishing."),
            wording_provenance=wording_prov,
            layer="customer_facing_nearby",
            as_of_date=str(nearest["retrieval_date"]),
        ))
        for _, r in cited.iterrows():
            ev_rows.append(dict(recommendation_id=rid, evidence_id=r["evidence_id"],
                                place_id=r["place_id"], place_name=r["place_name"],
                                category=r["category"], place_kind=r["place_kind"],
                                matched_tag=r["matched_tag"], lat=r["lat"], lng=r["lng"],
                                distance_km=r["distance_km_recomputed"],
                                distance_display=fmt_km(r["distance_km_recomputed"]),
                                source_url=r["source_url"], provider=r["provider"],
                                retrieval_date=r["retrieval_date"],
                                source_confidence=r["source_confidence"]))

    R = pd.DataFrame(recs)
    EV = pd.DataFrame(ev_rows)

    # ---- cross-layer id collision guard ----------------------------------------------------------
    existing = set()
    for f, col in [("phase3_business_decisions.csv", "decision_id"),
                   ("phase3_decision_reconciliation.csv", "decision_ref"),
                   ("phase4_ai_opportunities.csv", "recommendation_id")]:
        try: existing |= set(o(f)[col].astype(str))
        except Exception: pass
    clash = set(R["recommendation_id"]) & existing if len(R) else set()
    if clash:
        sys.exit(f"FAIL: new recommendation_id collides with an existing layer: {sorted(clash)}")

    R.to_csv(os.path.join(OUT, "phase4_nearby_recommendations.csv"), index=False)
    EV.to_csv(os.path.join(OUT, "phase4_nearby_recommendations_evidence.csv"), index=False)

    summary = [("layer", "customer_facing_nearby (Option A — separate output)"),
               ("recommendations_generated", len(R)),
               ("categories_evaluated", len(CATEGORY_ORDER)),
               ("categories_skipped", len(skipped)),
               ("skip_reasons", str({s["category"]: s["reason"] for s in skipped})),
               ("evidence_places_total", len(P)),
               ("evidence_places_useful", len(E)),
               ("same_name_places_folded", same_name_folded),
               ("evidence_places_cited", len(EV)),
               ("min_useful_places_per_category", MIN_USEFUL_PLACES),
               ("max_cited_places", MAX_CITED_PLACES),
               ("distance_method", "haversine R=6371km recomputed offline from stored coordinates"),
               ("max_distance_drift_vs_collected_km", float(P["distance_delta"].max()) if len(P) else 0.0),
               ("distance_format_rule", 'f"{round(stored_distance_km, 2):.2f} km"'),
               ("walking_time_claims", 0),
               ("comparison_language", 0),
               ("owner_verify_required_all", bool(R["owner_verify_required"].all()) if len(R) else True),
               ("id_collision_with_existing_layers", 0),
               ("existing_33_lifecycle_touched", "NO"),
               ("page15_touched", "NO"), ("reducer_touched", "NO"), ("registries_touched", "NO"),
               ("inside_run_all_verify", "NO — this layer is intentionally outside the locked verification set")]
    pd.DataFrame(summary, columns=["metric", "value"]).to_csv(
        os.path.join(OUT, "phase4_nearby_recommendations_summary.csv"), index=False)

    print("PHASE-4 NEARBY CUSTOMER-FACING RECOMMENDATIONS:")
    for k, v in summary: print(f"  {k}: {v}")
    print()
    for _, r in R.iterrows():
        print(f"  [{r['recommendation_id']}]  ({r['evidence_count']} of {r['evidence_available_in_category']} verified places cited)")
        print(f"     visibility : {r['website_visibility_status']} / {r['website_visibility_specificity']}")
        print(f"     ask        : {r['recommendation']}")
        print(f"     customer   : {r['customer_facing_change']}")
        print(f"     places     : {r['place_distance_display']}")
        print()


if __name__ == "__main__":
    main()
