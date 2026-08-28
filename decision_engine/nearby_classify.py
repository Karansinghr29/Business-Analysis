"""
NEARBY EVIDENCE CLASSIFICATION + WORDING (Groq; network; run by hand; OUTSIDE run_all --verify).

Reuses the grounded-extraction pattern of phase3_review_theme_extract.py verbatim: temperature=0,
fixed vocabulary, code-side filtering of the model's answer, and an honest "(extraction_missing)"
marker where the model does not return an id — never a fabricated default.

Groq does exactly two things here, both judgement, neither factual:
  1. usefulness — is this OSM-tagged place genuinely useful to a prospective PG tenant? OSM contains
     mis-tags ("Alchemy Media Marketing" tagged as a greengrocer) and institutional entries that are
     not consumer services. That call needs judgement; the tag alone cannot make it.
  2. wording   — the section name and one sentence per category, chosen from a fixed allow-list.

Groq NEVER supplies a place, a coordinate, a distance, a source or a number. Model output containing
any digit is rejected in code before it is written. Every number in the final recommendation is
injected deterministically downstream from phase3_nearby_places.csv.

Reads  outputs/phase3_nearby_places.csv (frozen evidence) READ-ONLY.
Writes ONLY outputs/phase3_nearby_classification.csv + phase3_nearby_wording.csv + _summary.csv.
"""
from __future__ import annotations
import os, sys, json, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from groq import Groq

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
PLACES = pd.read_csv(os.path.join(OUT, "phase3_nearby_places.csv"))

MODEL = "openai/gpt-oss-120b"
BATCH = 8
RETRIEVAL_DATE = "2026-08-27"

# ---- fixed vocabularies. Anything outside these is discarded in code, never coerced. -------------
USEFULNESS_VOCAB = ["useful", "not_useful", "unclear"]
SECTION_NAME_VOCAB = {
    "TRANSPORT":  "Nearby Transportation",
    "HEALTHCARE": "Nearby Healthcare",
    "ESSENTIALS": "Nearby Essentials",
    "EDUCATION":  "Nearby Education",
    "FINANCIAL":  "Nearby Banking",
}
DIGIT_RX = re.compile(r"\d")


def _client():
    key = os.environ.get("GROQ_API_KEY")
    if not key: sys.exit("GROQ_API_KEY not in env.")
    return Groq(api_key=key.strip())


def classify_batch(client, batch):
    payload = [{"id": r["evidence_id"], "name": str(r["place_name"])[:120],
                "osm_kind": str(r["place_kind"]), "osm_tag": str(r["matched_tag"])}
               for _, r in batch.iterrows()]
    prompt = (
        "You judge whether each place would be USEFUL to mention to someone deciding whether to rent "
        "a room in a shared paying-guest accommodation nearby.\n"
        f"Answer with one label from exactly this list: {USEFULNESS_VOCAB}.\n"
        "  useful      = any consumer-accessible service a resident would actually use — railway or "
        "metro station, bus stop or terminus, hospital, clinic, dental or eye clinic, dispensary, "
        "pharmacy or medical store, supermarket, grocery or vegetable shop, market, bank, ATM, "
        "school, college or university. A small or specialised clinic still counts as useful.\n"
        "  not_useful  = the NAME contradicts the TAG, or the place is not that kind of service at "
        "all. Apply this test strictly and independently of the list above:\n"
        "                (a) name describes a different trade or an office — e.g. a name containing "
        "'Media', 'Marketing', 'Consultancy', 'Solutions', 'Realty' tagged as a shop;\n"
        "                (b) name is a charity, trust, society, association, welfare body, research "
        "foundation or government department rather than a consumer service;\n"
        "                (c) name makes clear a resident could not walk in and use it as that "
        "service.\n"
        "                A place matching (a), (b) or (c) is not_useful EVEN IF its tag appears in "
        "the useful list.\n"
        "  unclear     = you cannot tell from the name and tag.\n"
        "Judge ONLY from the name and tag given. Do NOT invent places. Do NOT output numbers, "
        "distances, addresses or explanations of distance.\n"
        'Return ONLY a JSON array, one object per input id: [{"id":"","label":"","reason":""}]. '
        "Keep reason under 12 words and free of digits.\nPlaces:\n"
        + json.dumps(payload, ensure_ascii=False))
    r = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}],
                                       temperature=0, max_tokens=2000)
    t = r.choices[0].message.content or ""
    m = re.search(r"\[.*\]", t, re.S)
    try: return json.loads(m.group(0)) if m else []
    except Exception: return []


def word_categories(client, cats):
    payload = [{"category": c, "section_name": SECTION_NAME_VOCAB[c]} for c in cats]
    prompt = (
        "For each category, write ONE short sentence a property owner could act on: it should say "
        "that the property page can show verified nearby places of that category, with their names "
        "and straight-line distances.\n"
        "HARD RULES:\n"
        "  - Do NOT include any digit, number, count, distance or quantity. Numbers are added later.\n"
        "  - Do NOT mention walking time, travel time, minutes, or 'walking distance'.\n"
        "  - Do NOT name any specific place.\n"
        "  - Do NOT compare with any other property or use words like better, best, cheaper.\n"
        "  - Keep each sentence under 25 words.\n"
        'Return ONLY a JSON array: [{"category":"","sentence":""}].\nCategories:\n'
        + json.dumps(payload, ensure_ascii=False))
    r = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}],
                                       temperature=0, max_tokens=900)
    t = r.choices[0].message.content or ""
    m = re.search(r"\[.*\]", t, re.S)
    try: return json.loads(m.group(0)) if m else []
    except Exception: return []


def main():
    client = _client()

    # ---------------- 1. per-place usefulness ----------------
    rows = []; errs = 0
    for i in range(0, len(PLACES), BATCH):
        batch = PLACES.iloc[i:i + BATCH]
        try: res = classify_batch(client, batch)
        except Exception as e:
            errs += 1; res = []; print(f"  batch {i//BATCH} error: {type(e).__name__}")
        got = {str(o.get("id")): o for o in res if isinstance(o, dict)}
        for _, r in batch.iterrows():
            eid = r["evidence_id"]; o = got.get(eid)
            if o is None:
                # model did not return this id -> honest marker, never a fabricated 'useful'
                rows.append(dict(evidence_id=eid, place_name=r["place_name"], category=r["category"],
                                 place_kind=r["place_kind"], usefulness="(extraction_missing)",
                                 model_reason=None, reason_rejected="model omitted this id",
                                 extractor="groq", model=MODEL, retrieval_date=RETRIEVAL_DATE))
                continue
            lab = o.get("label")
            rej = None
            if lab not in USEFULNESS_VOCAB:
                rej = f"label '{lab}' outside fixed vocabulary"; lab = "(extraction_missing)"
            reason = str(o.get("reason") or "").strip()
            if DIGIT_RX.search(reason):
                reason = None
                rej = (rej + "; " if rej else "") + "reason contained a digit -> discarded"
            rows.append(dict(evidence_id=eid, place_name=r["place_name"], category=r["category"],
                             place_kind=r["place_kind"], usefulness=lab, model_reason=reason,
                             reason_rejected=rej, extractor="groq", model=MODEL,
                             retrieval_date=RETRIEVAL_DATE))
    C = pd.DataFrame(rows)
    C.to_csv(os.path.join(OUT, "phase3_nearby_classification.csv"), index=False)

    # ---------------- 2. per-category wording ----------------
    cats = [c for c in SECTION_NAME_VOCAB if (C[(C["category"] == c) & (C["usefulness"] == "useful")].shape[0] > 0)]
    wrows = []
    try: wres = word_categories(client, cats) if cats else []
    except Exception as e:
        wres = []; print(f"  wording error: {type(e).__name__}")
    wgot = {str(o.get("category")): o for o in wres if isinstance(o, dict)}
    for c in cats:
        o = wgot.get(c); sent = None; rej = None
        if o is None:
            rej = "model omitted this category"
        else:
            s = str(o.get("sentence") or "").strip()
            if not s:
                rej = "empty sentence"
            elif DIGIT_RX.search(s):
                rej = "sentence contained a digit -> discarded"
            elif re.search(r"\b(min|mins|minute|minutes|walk|walking|drive|driving|commute)\b", s, re.I):
                rej = "sentence contained a travel-time/walking claim -> discarded"
            elif re.search(r"\b(better|best|worse|worst|cheaper|cheapest|benchmark|compared)\b", s, re.I):
                rej = "sentence contained comparison language -> discarded"
            else:
                sent = s
        wrows.append(dict(category=c, section_name=SECTION_NAME_VOCAB[c],
                          model_sentence=(sent if sent else "(extraction_missing)"),
                          reason_rejected=rej, extractor="groq", model=MODEL,
                          temperature=0, retrieval_date=RETRIEVAL_DATE))
    W = pd.DataFrame(wrows)
    W.to_csv(os.path.join(OUT, "phase3_nearby_wording.csv"), index=False)

    counts = {k: int(v) for k, v in C["usefulness"].value_counts().items()}
    summary = [("model", MODEL), ("temperature", 0), ("batch_size", BATCH),
               ("places_in", len(PLACES)), ("classified_rows", len(C)),
               ("usefulness_counts", str(counts)),
               ("batches_errored", errs),
               ("rejected_model_reasons", int(C["reason_rejected"].notna().sum())),
               ("categories_worded", len(W)),
               ("wording_rejected", int(W["reason_rejected"].notna().sum())),
               ("vocabulary", str(USEFULNESS_VOCAB)),
               ("section_names", str(SECTION_NAME_VOCAB)),
               ("numeric_policy", "model output containing any digit is discarded in code; all numbers injected deterministically downstream"),
               ("walking_time_policy", "sentences containing walk/minute/travel-time vocabulary are discarded"),
               ("retrieval_date", RETRIEVAL_DATE)]
    pd.DataFrame(summary, columns=["metric", "value"]).to_csv(
        os.path.join(OUT, "phase3_nearby_classification_summary.csv"), index=False)

    print("NEARBY CLASSIFICATION (Groq, grounded):")
    for k, v in summary: print(f"  {k}: {v}")
    print("\n  not_useful / unclear / missing:")
    for _, r in C[C["usefulness"] != "useful"].iterrows():
        print(f"    {r['evidence_id']}  {r['category']:11} {str(r['place_name'])[:40]:40} -> {r['usefulness']}  ({r['model_reason']})")
    print("\n  wording:")
    for _, r in W.iterrows():
        print(f"    {r['category']:11} [{r['section_name']}] {r['model_sentence']}")


if __name__ == "__main__":
    main()
