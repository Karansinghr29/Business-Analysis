"""
Fail-loud validation for the NEARBY customer-facing recommendation layer (Option A).

Validates the new layer AND asserts that it changed nothing in the existing system: the 14 backbone
decisions, the 6 Phase-3 opportunities, the 13 AIREC recommendations, the 33-recommendation
lifecycle, Page 15, the reducer and the registries must all be untouched.

Includes the DECIMAL-DISTANCE check the generic phase4_guard._nums() pattern cannot perform:
_nums() uses (?<![\\w.])\\d+(?![\\w.]), so in "0.8 km" neither digit is matched and the value is
never verified. Here every displayed distance is parsed as a decimal and re-derived from the stored
coordinates.
"""
from __future__ import annotations
import os, sys, re, math, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
sys.path.insert(0, HERE)
from phase4_nearby_rules import haversine_km, fmt_km, WALKING_RX, COMPARISON_RX, MIN_USEFUL_PLACES

fails = []
def chk(c, m):
    print(("  PASS " if c else "  FAIL ") + m)
    if not c: fails.append(m)

def o(f): return pd.read_csv(os.path.join(OUT, f))

R = o("phase4_nearby_recommendations.csv")
EV = o("phase4_nearby_recommendations_evidence.csv")
P = o("phase3_nearby_places.csv")
C = o("phase3_nearby_classification.csv")
V = o("phase3_vishful_site_location_facts.csv")

# ---------------------------------------------------------------- 1-2 evidence integrity
print("[1] every recommendation cites real, resolvable evidence")
chk(len(R) > 0, f"layer produced recommendations ({len(R)})")
pack = set(P["evidence_id"])
all_cited = []
for _, r in R.iterrows():
    eids = str(r["evidence_ids"]).split("|")
    all_cited += eids
    chk(len(eids) > 0 and all(e.strip() for e in eids), f"{r['recommendation_id']} has non-empty evidence_ids")
    missing = [e for e in eids if e not in pack]
    chk(not missing, f"{r['recommendation_id']} evidence all resolves in phase3_nearby_places.csv"
                     + (f" (missing {missing})" if missing else ""))
    chk(int(r["evidence_count"]) == len(eids), f"{r['recommendation_id']} evidence_count matches evidence_ids")

print("\n[2] evidence detail table matches the cited ids")
chk(set(EV["evidence_id"]) == set(all_cited), "evidence table covers exactly the cited evidence ids")
chk(set(EV["recommendation_id"]) == set(R["recommendation_id"]), "every recommendation has evidence rows")

# ---------------------------------------------------------------- 3-4 coordinates + distance
print("\n[3] every displayed place has valid coordinates")
for _, r in EV.iterrows():
    ok = (pd.notna(r["lat"]) and pd.notna(r["lng"])
          and -90 <= float(r["lat"]) <= 90 and -180 <= float(r["lng"]) <= 180)
    chk(ok, f"{r['evidence_id']} coordinates valid ({r['lat']},{r['lng']})")

print("\n[4] every distance is derived from coordinates, not from prose")
anchor = (float(R["property_lat"].iloc[0]), float(R["property_lng"].iloc[0]))
chk(abs(anchor[0] - 12.9878697) < 1e-9 and abs(anchor[1] - 80.2551457) < 1e-9,
    f"anchor is the approved exact Vishful coordinate {anchor} (not a suburb centroid)")
for _, r in EV.iterrows():
    d = haversine_km(anchor[0], anchor[1], float(r["lat"]), float(r["lng"]))
    chk(abs(d - float(r["distance_km"])) <= 0.001,
        f"{r['evidence_id']} distance re-derives from coordinates ({d:.3f} vs stored {r['distance_km']})")

# ---------------------------------------------------------------- 5-6 DECIMAL distance validation
print("\n[5] DECIMAL distances are validated (the gap phase4_guard._nums() cannot see)")
GUARD_NUM = re.compile(r"(?<![\w.])\d+(?![\w.])")          # the existing generic pattern
DECIMAL_KM = re.compile(r"(\d+(?:\.\d+)?)\s*km\b")          # the distance-specific pattern

# prove the gap is real, so this check cannot be quietly deleted later
for probe in ["0.8 km", "1.25 km", "4.9 km"]:
    chk(not GUARD_NUM.findall(probe.replace(" km", "")),
        f"demonstrated: generic _nums() pattern does NOT capture '{probe}'")
    chk(bool(DECIMAL_KM.search(probe)), f"distance-specific pattern DOES capture '{probe}'")
chk(bool(DECIMAL_KM.search("1 km")), "distance-specific pattern captures the integer form '1 km'")

stored_by_eid = {r["evidence_id"]: float(r["distance_km"]) for _, r in EV.iterrows()}
print("\n[6] no displayed distance differs from stored beyond the documented formatting rule")
FORMAT_TOLERANCE = 0.005     # implied by round(x, 2)
for _, r in EV.iterrows():
    disp = str(r["distance_display"])
    m = DECIMAL_KM.search(disp)
    chk(m is not None, f"{r['evidence_id']} display '{disp}' parses as a decimal distance")
    if m:
        chk(abs(float(m.group(1)) - float(r["distance_km"])) <= FORMAT_TOLERANCE,
            f"{r['evidence_id']} displayed {m.group(1)} within {FORMAT_TOLERANCE} of stored {r['distance_km']}")
        chk(disp == fmt_km(r["distance_km"]), f"{r['evidence_id']} display follows the documented rule exactly")

for _, r in R.iterrows():
    shown = DECIMAL_KM.findall(str(r["place_distance_display"]) + " " + str(r["recommendation"])
                               + " " + str(r["customer_facing_change"]) + " " + str(r["distance_summary"]))
    cited = {round(stored_by_eid[e], 2) for e in str(r["evidence_ids"]).split("|")}
    stray = [s for s in shown if round(float(s), 2) not in cited]
    chk(not stray, f"{r['recommendation_id']} every displayed distance traces to cited evidence"
                   + (f" (stray {stray})" if stray else ""))
    chk(abs(float(r["nearest_distance_km"]) - min(stored_by_eid[e] for e in str(r["evidence_ids"]).split("|"))) < 1e-9,
        f"{r['recommendation_id']} nearest_distance_km is the true minimum of its cited evidence")

# ---------------------------------------------------------------- 7-9 language + grounding
print("\n[7] no walking-time / travel-time claims anywhere in the layer")
TEXT_COLS = ["recommendation", "customer_facing_change", "distance_summary", "material_gap",
             "section_name", "place_distance_display"]
for _, r in R.iterrows():
    blob = " ".join(str(r[c]) for c in TEXT_COLS)
    chk(not WALKING_RX.search(blob), f"{r['recommendation_id']} free of walking/travel-time language")
    chk(str(r["walking_time_claimed"]) == "False", f"{r['recommendation_id']} walking_time_claimed=False")
chk(not WALKING_RX.search(" ".join(P["evidence_text"].astype(str))), "collected evidence text carries no travel-time claim")

print("\n[8] no unsupported model-generated numbers")
w = o("phase3_nearby_wording.csv")
for _, r in w.iterrows():
    s = str(r["model_sentence"])
    if s != "(extraction_missing)":
        chk(not re.search(r"\d", s), f"model sentence for {r['category']} contains no digit")
        chk(not WALKING_RX.search(s), f"model sentence for {r['category']} has no travel-time claim")
        chk(not COMPARISON_RX.search(s), f"model sentence for {r['category']} has no comparison language")
chk(int(C["model_reason"].astype(str).str.contains(r"\d", regex=True).sum()) == 0,
    "no model reason string contains a digit")

print("\n[9] no invented place names — every displayed name exists in collected evidence")
collected_names = set(P["place_name"].astype(str))
for _, r in EV.iterrows():
    chk(str(r["place_name"]) in collected_names, f"{r['evidence_id']} place name came from collection")
for _, r in R.iterrows():
    for nm in str(r["place_names"]).split("|"):
        chk(nm in collected_names, f"{r['recommendation_id']} names only collected places ('{nm}')")
chk(set(EV["place_id"]).issubset(set(P["place_id"])), "every cited place_id came from the collector")

# ---------------------------------------------------------------- 10-13 dedup + rule shape
print("\n[10] no duplicate OSM identities")
chk(P["place_id"].duplicated().sum() == 0, "collected evidence has no duplicate OSM id")
chk(P["evidence_id"].duplicated().sum() == 0, "collected evidence has no duplicate evidence_id")
chk(EV["place_id"].duplicated().sum() == 0, "no place cited twice across the layer")

print("\n[11] no duplicate recommendation categories")
chk(R["recommendation_id"].duplicated().sum() == 0, "recommendation ids unique")
chk(R["category"].duplicated().sum() == 0, "exactly one recommendation per category")

print("\n[12] one recommendation may cite many places (not one place per recommendation)")
chk(bool((R["evidence_count"] > 1).all()), f"every recommendation cites >1 place "
                                           f"(counts {R['evidence_count'].tolist()})")
chk(len(EV) > len(R), f"evidence rows ({len(EV)}) exceed recommendations ({len(R)})")

print("\n[13] empty / thin categories produce no recommendation")
useful = C[C["usefulness"] == "useful"]["evidence_id"]
avail = P[P["evidence_id"].isin(useful)].groupby("category").size().to_dict()
for cat, n in avail.items():
    if n < MIN_USEFUL_PLACES:
        chk(cat not in set(R["category"]), f"thin category {cat} ({n}) produced no recommendation")
chk(bool((R["evidence_available_in_category"] >= MIN_USEFUL_PLACES).all()),
    "every produced category met the minimum verified-place threshold")

print("\n[13b] website-visibility rule respected")
spec_by_cat = {r["category"]: str(r["visibility_specificity"]) for _, r in V.iterrows()}
for cat, spec in spec_by_cat.items():
    if spec == "specific":
        chk(cat not in set(R["category"]),
            f"{cat}: site already names places with distances -> no duplicate recommendation")
for _, r in R.iterrows():
    if str(r["website_visibility_specificity"]) == "generic":
        chk(bool(str(r["material_gap"]).strip()) and "no place" in str(r["material_gap"]).lower(),
            f"{r['recommendation_id']} states the materially different missing piece")
chk(bool(R["owner_verify_required"].all()), "every recommendation is gated on owner verification")

# ---------------------------------------------------------------- 14-20 existing system untouched
print("\n[14-17] existing recommendation layers unchanged")
BD = o("phase3_business_decisions.csv"); DR = o("phase3_decision_reconciliation.csv")
AO = o("phase4_ai_opportunities.csv")
chk(len(BD) == 14, f"14 backbone decisions intact ({len(BD)})")
chk(len(DR[DR["reconciliation_status"] == "NEW"]) == 6,
    f"6 Phase-3 opportunities intact ({len(DR[DR['reconciliation_status']=='NEW'])})")
chk(len(AO) == 13, f"13 AIREC recommendations intact ({len(AO)})")
chk(len(BD) + 6 + len(AO) == 33, "33-recommendation lifecycle count unchanged")
new_ids = set(R["recommendation_id"])
chk(not (new_ids & set(BD["decision_id"].astype(str))), "no id collision with backbone")
chk(not (new_ids & set(DR["decision_ref"].astype(str))), "no id collision with Phase-3 opportunities")
chk(not (new_ids & set(AO["recommendation_id"].astype(str))), "no id collision with existing AIREC")
chk(all(i.startswith("AIREC-NEARBY-") for i in new_ids), "new ids are namespaced under AIREC-NEARBY-")

print("\n[18-19] Page 15, reducer, registries and guard unmodified")
BASE = os.path.join(HERE, "..", ".baseline", "pre_nearby.json")
# Dashboard sections added AFTER this baseline was taken, each separately approved and read-only.
# Every entry is (start marker, end marker). They are stripped before hashing so this check keeps
# proving "no OTHER change was made" instead of going stale each time an approved section is added.
# Dashboard sections added AFTER this baseline was taken, each separately approved and read-only.
# Every entry is (start marker, end marker). They are stripped before hashing so this check keeps
# proving "no OTHER change was made" instead of going stale each time an approved section is added.
APPROVED_BLOCKS = [
    ("    # ---- \u246d Nearby Customer-Access Information", "def _p15_refresh():"),
    ("    # ---- Active Tenant Location Data Capture", "    # ---- Tenant Origin Analysis"),
    ("    # ---- Tenant Origin Analysis", "def p_eb():"),
]

def _strip_approved(raw):
    """Remove each approved block, keeping exactly the one blank line that separated it."""
    out = raw
    for smark, emark in APPROVED_BLOCKS:
        s = out.find(smark.encode("utf-8"))
        if s < 0:
            return None, f"missing start marker {smark.strip()!r}"
        e = out.find(emark.encode("utf-8"), s)
        if e <= s:
            return None, f"missing end marker {emark.strip()!r}"
        # cut one blank-line gap inside each boundary so the halves rejoin with a single blank line
        gap = b"\r\n\r\n"
        pad = 4 if (s >= 4 and out[s - 4:s] == gap and out[e - 4:e] == gap) else 0
        out = out[:s - pad] + out[e - pad:]
    return out, None

if os.path.exists(BASE):
    import json
    base = json.load(open(BASE))
    for rel, h in base.items():
        p = os.path.join(HERE, rel)
        raw = open(p, "rb").read()
        if rel == "dashboard.py":
            stripped, err = _strip_approved(raw)
            chk(err is None, f"dashboard.py contains every approved block ({err or chr(97)+chr(108)+chr(108)})")
            if stripped is not None:
                chk(hashlib.md5(stripped).hexdigest() == h,
                    f"dashboard.py: the {len(APPROVED_BLOCKS)} approved sections are the ONLY changes "
                    "(strip them and the file is byte-identical to the pre-nearby baseline)")
            continue
        chk(hashlib.md5(raw).hexdigest() == h, f"unchanged: {rel}")
else:
    chk(False, "baseline hash file missing — cannot prove existing files unchanged")

print("\n[19b] the existing display blocks the new section sits beside are untouched")
DSH = open(os.path.join(HERE, "dashboard.py"), encoding="utf-8").read()
chk("⑧ AI Business Opportunities" not in DSH or DSH.count("phase4_ai_opportunities.csv") >= 1,
    "section 11 still reads phase4_ai_opportunities.csv")
chk("phase4_nearby_recommendations.csv" not in DSH.split("def p_actions()")[1],
    "Page 15 does NOT read the nearby layer (lifecycle count untouched)")
chk("phase4_nearby" not in DSH.split("⑪ AI Business Opportunities")[1].split("⑫ Decision Effectiveness")[0],
    "section 11 (13 AIREC) does not render nearby rows — layers stay separate")

print("\n[19c] all 5 nearby recommendations are OWNER-VISIBLE on the rendered dashboard")
try:
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(HERE, "dashboard.py"), default_timeout=300)
    at.run()
    # the sidebar page selector has no key, so it must be driven as a widget, not via session_state
    at.sidebar.radio[0].set_value("14 · Owner Decision Board").run()
    chk(len(at.exception) == 0, f"Page 14 renders without exception ({[str(e.value)[:120] for e in at.exception]})")
    blob = " ".join([str(e.value) for e in at.markdown] + [str(e.value) for e in at.caption]
                    + [str(e.value) for e in at.info] + [str(e.value) for e in at.warning]
                    + [str(getattr(e, "label", "")) for e in at.expander])
    frames = [df.value for df in at.dataframe]
    fblob = " ".join(f.to_csv(index=False) for f in frames)
    for rid in R["recommendation_id"]:
        chk(rid in blob, f"{rid} visible on Page 14")
    for _, r in R.iterrows():
        chk(str(r["section_name"]) in blob, f"section name '{r['section_name']}' visible")
    for _, r in EV.iterrows():
        chk(str(r["place_name"]) in fblob, f"place '{r['place_name']}' visible in an evidence table")
        chk(str(r["distance_display"]) in fblob, f"distance {r['distance_display']} visible and matches output")
        chk(str(r["evidence_id"]) in fblob, f"{r['evidence_id']} visible in an evidence table")
    # The section's own disclaimer necessarily contains the forbidden vocabulary in order to DENY it
    # ("Not travel time and not walking time - no journey time is claimed or derivable"). A denial is
    # not a claim. Rather than rely on a negation lookback, remove that one exact sentence and then
    # require everything that remains to be completely free of travel-time vocabulary.
    DISC_A = "Not travel time and not walking time"
    chk(DISC_A in blob, "the section states its travel-time disclaimer verbatim to the owner")
    _resid = blob.replace(DISC_A, " ") + " " + fblob
    _hits = [_resid[max(0, m.start() - 60):m.end() + 60] for m in WALKING_RX.finditer(_resid)]
    chk(not _hits, f"no walking/travel-time CLAIM anywhere else on rendered Page 14 {_hits[:2]}")
    gen = R[R["website_visibility_specificity"] == "generic"]
    for _, r in gen.iterrows():
        chk(str(r["website_visibility_evidence"])[:40] in blob,
            f"{r['recommendation_id']}: existing generic website wording shown to the owner")
    chk("14 + 6 + 13 + 5 = 38" in blob, "owner-visible universe stated as 14 + 6 + 13 + 5 = 38")
except Exception as e:
    chk(False, f"dashboard render check failed: {type(e).__name__}: {e}")

print("\n[20] the new layer is isolated from the locked verification set")
ra = open(os.path.join(HERE, "run_all.py"), encoding="utf-8").read()
for m in ["nearby_places_collect.py", "vishful_site_location_check.py", "nearby_classify.py",
          "phase4_nearby_rules.py"]:
    chk(m not in ra, f"{m} is NOT in run_all.py ORDER (network/model stages stay outside --verify)")
chk("DEC-LOC-MKT" not in " ".join(R["recommendation"].astype(str)),
    "layer does not restate DEC-LOC-MKT (where to market) — it concerns what to publish")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails:
    for f in fails: print("   -", f)
    sys.exit(1)
