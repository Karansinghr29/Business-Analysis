"""
Phase-3 EXPERIMENTAL — Groq-assisted men's-PG discovery near Vishful Vista Heights
(Thiruvanmiyur 600041). Groq used ONLY as an LLM/web-research helper (web-capable
'compound' models: built-in web search + visit-website). NO Gemini, NO Google Places,
NO Apify, NO Firecrawl, NO paid scraping.

Credential: reads GROQ_API_KEY from env ONLY. Never printed, never written to any
CSV/log/source. If absent -> writes header-only outputs + status=KEY_ABSENT and exits 0
(no fabricated candidates).

Hard guards enforced in CODE (not trusted to the LLM):
  * aggregator/operator hosts dropped (reuses phase3_pg_research.AGGREGATOR_HOSTS)
  * a price is kept ONLY if its source_url host == the PG's own official host (first-party)
  * room-class price is NEVER converted to per-bed (kept unknown at per-bed grain)
  * 'starting from' -> price_confidence='starting_from' (never 'published_exact')
  * dedupe by host; flag is_in_existing_pool vs the existing 9-property pool
  * hotels/service-apartments/colleges/institutional excluded by classifier + LLM instruction

Writes ONLY: outputs/phase3_groq_pg_candidates.csv, phase3_groq_pg_price_evidence.csv,
phase3_groq_pg_summary.csv. Does NOT touch dashboard / locked outputs / run_all /
phase3_pg_research outputs. Read-only on everything else.
"""
from __future__ import annotations
import os, sys, json, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from phase3_pg_research import AGGREGATOR_HOSTS, classify, compute_distance, host_of

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUT, exist_ok=True)
CAND = os.path.join(OUT,"phase3_groq_pg_candidates.csv")
PRICE= os.path.join(OUT,"phase3_groq_pg_price_evidence.csv")
SUMM = os.path.join(OUT,"phase3_groq_pg_summary.csv")

# Own-site hosts already in the existing (non-Groq) 9-property evidence pool -> prefer NEW.
EXISTING_POOL = {"menspg.in","mypgatchennai.com","hostelforladies.com","tsppgaccommodation.com",
    "kripahomes.com","emypgaccommodation.in","srimahahostels.com","tidelhostel.com",
    "mahalakshmipgaccommodation.com"}
MODELS = ["groq/compound-mini", "groq/compound"]   # mini first: fits free-tier per-request token cap
MAX_VISITS = 8                                       # cap Groq calls (quota-friendly)

CAND_COLS = ["pg_name","official_url","host","area","pincode","segment","property_kind",
             "is_aggregator","is_in_existing_pool","dist_km_from_vishful","distance_precision",
             "within_2km","within_3km","groq_grounded","n_groq_tools"]
PRICE_COLS = ["pg_name","official_url","area","pincode","sharing_type","room_ac",
              "monthly_rent_per_bed","price_confidence","source_url","evidence"]

def write_empty(status, model=None, errors=""):
    pd.DataFrame(columns=CAND_COLS).to_csv(CAND, index=False)
    pd.DataFrame(columns=PRICE_COLS).to_csv(PRICE, index=False)
    pd.DataFrame([("groq_status",status),("groq_model",model or ""),("pgs_discovered",0),
        ("mens_pgs",0),("within_2km",0),("within_3km",0),("with_first_party_price",0),
        ("unknown_prices",0),("errors",errors)],
        columns=["metric","value"]).to_csv(SUMM, index=False)
    print(f"GROQ STATUS: {status}. {errors}")

def get_client():
    if not os.environ.get("GROQ_API_KEY"):
        return None, "KEY_ABSENT"
    try:
        from groq import Groq
        return Groq(), None            # reads GROQ_API_KEY from env; key never touched by us
    except Exception as e:
        return None, f"CLIENT_INIT_FAIL: {type(e).__name__}"

def _json_blob(text):
    """Extract the first JSON array/object from possibly-prose LLM output."""
    if not text: return None
    m = re.search(r"\[.*\]", text, re.S) or re.search(r"\{.*\}", text, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None

def call(client, model, prompt, max_tokens=700):
    """Return (text, n_executed_tools, error_str). max_tokens bounds output to stay under free-tier caps."""
    try:
        r = client.chat.completions.create(model=model,
            messages=[{"role":"user","content":prompt}], temperature=0, max_tokens=max_tokens)
        msg = r.choices[0].message
        tools = getattr(msg, "executed_tools", None) or []
        return (msg.content or ""), len(tools), None
    except Exception as e:
        return "", 0, f"{type(e).__name__}: {str(e)[:180]}"

DISCOVERY_PROMPT = (
 "Web search for MEN'S PG / men's hostel / men's co-living within ~3km of Thiruvanmiyur Chennai 600041. "
 "Give each property's OWN official website (its own domain, NOT an aggregator/listing/operator). "
 "Exclude hotels, service apartments, colleges/institutional hostels, women-only, and aggregators "
 "(nobroker/magicbricks/housing/sulekha/justdial/zolo/stanza/colive/nestaway/gopgo). "
 "Return ONLY a compact JSON array (max 5), each: "
 '{"pg_name":"","official_url":"","area":"","pincode":"","is_mens_pg":true}. '
 "official_url=null if unsure it is the property's own site. No prose, no markdown.")

def visit_prompt(name, url):
    return (f"Visit ONLY this URL and read it: {url} (PG '{name}'). "
     "Extract ONLY monthly rent THIS page explicitly publishes, by sharing type and AC/non-AC. "
     "Do NOT infer; do NOT use any other site. Room-level price that is not clearly per-bed: "
     "monthly_rent_per_bed=null, note in evidence. 'starting from'=>price_confidence='starting_from'. "
     "Exact published per-bed=>'published_exact'. No price on page=>'unknown', rent=null. "
     "Return ONLY a compact JSON array, each: "
     '{"sharing_type":"","room_ac":"ac|non_ac|unknown","monthly_rent_per_bed":null,'
     '"price_confidence":"published_exact|starting_from|unknown","source_url":"","evidence":""}. '
     "source_url MUST be this page URL. No prose, no markdown.")

def main():
    client, status = get_client()
    if client is None:
        write_empty(status, errors="GROQ_API_KEY not visible to this process. "
            "Set it (setx GROQ_API_KEY \"...\") and run in a NEW shell; do not paste the key in chat.")
        return

    model = None; errors = []
    # pick first model that responds
    for m in MODELS:
        _, _, err = call(client, m, "Reply OK.")
        if err is None: model = m; break
        errors.append(f"{m} probe: {err}")
    if model is None:
        write_empty("MODEL_UNAVAILABLE", errors=" | ".join(errors)); return

    dtext, dtools, derr = call(client, model, DISCOVERY_PROMPT, max_tokens=350)
    if derr: errors.append(f"discovery: {derr}")
    disc = _json_blob(dtext) or []
    if isinstance(disc, dict): disc = [disc]

    # de-dup + guard candidates
    cand_rows, seen = [], set()
    for d in disc:
        if not isinstance(d, dict): continue
        url = (d.get("official_url") or "").strip()
        name = (d.get("pg_name") or "").strip()
        if not name: continue
        host = host_of(url) if url.startswith("http") else ""
        if host in seen: continue
        seen.add(host or name.lower())
        is_agg = bool(host) and any(host==a or host.endswith("."+a) for a in AGGREGATOR_HOSTS)
        kind, _ = classify(name + " " + ("mens pg paying guest" if d.get("is_mens_pg") else ""))
        area, pin = d.get("area"), (str(d.get("pincode")) if d.get("pincode") else None)
        dist_km, prec, within2 = compute_distance(area, pin)
        within3 = bool(within2 or (dist_km is not None and dist_km<=3.0) or prec.startswith("same_suburb_600041"))
        cand_rows.append(dict(pg_name=name, official_url=url or None, host=host or None, area=area, pincode=pin,
            segment=("men" if d.get("is_mens_pg") else "unknown"), property_kind=kind,
            is_aggregator=is_agg, is_in_existing_pool=(host in EXISTING_POOL),
            dist_km_from_vishful=dist_km, distance_precision=prec, within_2km=within2, within_3km=within3,
            groq_grounded=(dtools>0), n_groq_tools=dtools))

    # visit only NEW, non-aggregator, men's candidates that have a first-party URL
    price_rows = []
    visit_targets = [c for c in cand_rows if c["official_url"] and not c["is_aggregator"]
                     and not c["is_in_existing_pool"] and c["segment"]=="men"][:MAX_VISITS]
    for c in visit_targets:
        vtext, vtools, verr = call(client, model, visit_prompt(c["pg_name"], c["official_url"]), max_tokens=350)
        if verr: errors.append(f"visit {c['host']}: {verr}"); continue
        items = _json_blob(vtext) or []
        if isinstance(items, dict): items = [items]
        own_host = c["host"]
        kept_any = False
        for it in items:
            if not isinstance(it, dict): continue
            src = (it.get("source_url") or c["official_url"] or "").strip()
            src_host = host_of(src) if src.startswith("http") else ""
            # GUARD: price only trusted if source is the PG's OWN first-party host
            first_party = (src_host == own_host and own_host != "")
            conf = it.get("price_confidence") or "unknown"
            rent = it.get("monthly_rent_per_bed")
            if conf not in ("published_exact","starting_from","unknown"): conf = "unknown"
            # GUARD: never keep a number without first-party source; force unknown otherwise
            if rent is not None and not first_party:
                rent, conf = None, "unknown"
            # GUARD: only 'published_exact' + first-party may carry a numeric per-bed price
            if conf != "published_exact":
                if conf == "unknown": rent = None
                # 'starting_from' stays flagged; keep number only if first-party, else null
                if conf == "starting_from" and not first_party: rent = None
            price_rows.append(dict(pg_name=c["pg_name"], official_url=c["official_url"],
                area=c["area"], pincode=c["pincode"],
                sharing_type=it.get("sharing_type") or "unknown",
                room_ac=it.get("room_ac") or "unknown",
                monthly_rent_per_bed=rent, price_confidence=conf, source_url=src or None,
                evidence=(it.get("evidence") or "")[:300]))
            kept_any = True
        if not kept_any:
            price_rows.append(dict(pg_name=c["pg_name"], official_url=c["official_url"], area=c["area"],
                pincode=c["pincode"], sharing_type="unknown", room_ac="unknown",
                monthly_rent_per_bed=None, price_confidence="unknown", source_url=c["official_url"],
                evidence="Groq visited own site; no publicly published price found"))

    cand = pd.DataFrame(cand_rows, columns=CAND_COLS)
    price = pd.DataFrame(price_rows, columns=PRICE_COLS)
    cand.to_csv(CAND, index=False); price.to_csv(PRICE, index=False)

    mens = cand[cand["segment"]=="men"]
    priced = price[price["monthly_rent_per_bed"].notna() & (price["price_confidence"]=="published_exact")]
    summary = [("groq_status","OK"),("groq_model",model),
        ("pgs_discovered",len(cand)),("mens_pgs",len(mens)),
        ("aggregator_dropped_from_visits",int(cand["is_aggregator"].sum())),
        ("new_vs_existing_pool",int((~cand["is_in_existing_pool"]).sum())),
        ("within_2km",int(cand["within_2km"].sum())),("within_3km",int(cand["within_3km"].sum())),
        ("with_first_party_perbed_price",int(priced.shape[0])),
        ("unknown_prices",int((price["price_confidence"]=="unknown").sum())),
        ("starting_from_flags",int((price["price_confidence"]=="starting_from").sum())),
        ("groq_grounded_discovery",bool(dtools>0)),("discovery_tools",dtools),
        ("errors"," | ".join(errors) if errors else "none")]
    pd.DataFrame(summary, columns=["metric","value"]).to_csv(SUMM, index=False)

    print("PHASE-3 GROQ PG RESEARCH:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\ndiscovered candidates:")
    for _,r in cand.iterrows():
        print(f"  {r['pg_name']} | {r['host'] or 'no-site'} | {r['segment']} | {r['property_kind']} | "
              f"agg={r['is_aggregator']} existing={r['is_in_existing_pool']} within3km={r['within_3km']}")
    print("\nfirst-party per-bed prices found by Groq:")
    if priced.empty: print("  NONE")
    for _,r in priced.iterrows():
        print(f"  {r['pg_name']} | {r['sharing_type']}/{r['room_ac']} | ₹{r['monthly_rent_per_bed']} | {r['source_url']}")

if __name__=="__main__": main()
