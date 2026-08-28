"""
Phase-3 EXPERIMENTAL — nearby APARTMENT / co-living / serviced-apartment discovery around
Vishful Vista Heights, West Avenue, Thiruvanmiyur, Chennai 600041 (0-5km, focus 0-3km).
Broader than PGs: residential apartments, rental apartments, co-living, serviced apartments,
apartment-based men's/women's accommodation.

Groq compound-mini = web-search DISCOVERY only. Small requests (free-tier 413-safe).
Guards (code-side): aggregator hosts dropped from pricing; a price is kept ONLY if its
source host == the property's own first-party host AND published_exact; 'starting from' kept
as starting_from; room-level NOT converted to per-bed; dedupe by host/name; property_type
normalized (residential_apartment / co_living / serviced_apartment / pg / hostel / unknown);
distance via existing suburb-centroid logic; price unknown preserved.

Reads GROQ_API_KEY from env only — never printed/written. Writes ONLY:
outputs/phase3_groq_apartments_candidates.csv, outputs/phase3_groq_apartments_summary.csv.
Does NOT touch dashboard / locked outputs / phase3_pg_research / phase3_groq_pg_* outputs.
"""
from __future__ import annotations
import os, sys, json, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from phase3_pg_research import AGGREGATOR_HOSTS, compute_distance, host_of

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUT, exist_ok=True)
CAND = os.path.join(OUT,"phase3_groq_apartments_candidates.csv")
SUMM = os.path.join(OUT,"phase3_groq_apartments_summary.csv")
MODELS = ["groq/compound-mini", "groq/compound"]
MAX_VISITS = 6

CAND_COLS = ["name","official_url","host","area","pincode","property_type","is_business",
             "is_aggregator","verified_first_party","dist_km_from_vishful","distance_precision",
             "within_1km","within_2km","within_3km","within_5km",
             "monthly_price","price_confidence","source_url","evidence","groq_grounded"]

def write_empty(status, model=None, errors=""):
    pd.DataFrame(columns=CAND_COLS).to_csv(CAND, index=False)
    pd.DataFrame([("groq_status",status),("groq_model",model or ""),("candidates",0),("errors",errors)],
        columns=["metric","value"]).to_csv(SUMM, index=False)
    print(f"GROQ STATUS: {status}. {errors}")

def get_client():
    if not os.environ.get("GROQ_API_KEY"): return None,"KEY_ABSENT"
    try:
        from groq import Groq; return Groq(), None
    except Exception as e: return None, f"CLIENT_INIT_FAIL: {type(e).__name__}"

def call(client, model, prompt, max_tokens=350):
    try:
        r=client.chat.completions.create(model=model,messages=[{"role":"user","content":prompt}],
            temperature=0,max_tokens=max_tokens)
        m=r.choices[0].message
        return (m.content or ""), len(getattr(m,"executed_tools",None) or []), None
    except Exception as e:
        return "",0,f"{type(e).__name__}: {str(e)[:180]}"

def json_blob(t):
    if not t: return None
    m=re.search(r"\[.*\]",t,re.S) or re.search(r"\{.*\}",t,re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None

TYPE_MAP=[("serviced","serviced_apartment"),("service apart","serviced_apartment"),
          ("co-living","co_living"),("coliving","co_living"),("co living","co_living"),
          ("pg","pg"),("paying guest","pg"),("hostel","hostel"),
          ("apartment","residential_apartment"),("flat","residential_apartment"),
          ("residenc","residential_apartment"),("residency","residential_apartment")]
def norm_type(s):
    t=(s or "").lower()
    for k,v in TYPE_MAP:
        if k in t: return v
    return "unknown"

DISC_PROMPTS=[
 ("residential/rental apartments",
  "Web search: residential or rental APARTMENT buildings/complexes within ~3km of West Avenue, "
  "Thiruvanmiyur, Chennai 600041. Return ONLY compact JSON array (max 5), each "
  '{"name":"","official_url":"","area":"","pincode":"","property_type":"apartment","is_business":true}. '
  "official_url=null if unsure it's the property's own site. No prose."),
 ("co-living & serviced apartments",
  "Web search: CO-LIVING or SERVICED-APARTMENT or apartment-based men's/women's accommodation within "
  "~5km of Thiruvanmiyur Chennai 600041. Return ONLY compact JSON array (max 5), each "
  '{"name":"","official_url":"","area":"","pincode":"","property_type":"co-living|serviced apartment","is_business":true}. '
  "Exclude aggregators (nobroker/magicbricks/housing/sulekha/nestaway/colive). official_url=null if unsure. No prose."),
]

# Independently verified this session via WebSearch + WebFetch (NOT trusting Groq's URL).
# Each is a confirmed first-party own-domain site; price still UNKNOWN (none published on-site).
INDEPENDENT_VERIFIED = {
 "lancor sonnet square": dict(
    url="https://lancor.in/completed-projects-chennai/", host="lancor.in", ptype="residential_apartment",
    pin="600041", evidence="Lancor Holdings official site (verified). 3BHK FOR SALE — no monthly rent published."),
 "olympia jayanthi": dict(
    url="https://www.olympiagroup.in/olympia-jayanthi-residence/index.html", host="olympiagroup.in",
    ptype="residential_apartment", pin="600041",
    evidence="Olympia Group official site (verified). 2.5/3BHK sale, sold out; LB Rd 600041; no monthly rent published."),
 "season 4 residences": dict(
    url="https://season4.in/season-4-rentals-thiruvanmiyur/", host="season4.in", ptype="serviced_apartment",
    pin="600041", evidence="Season4 official serviced-apt site (verified via WebFetch). Kamaraj Nagar 600041; daily/monthly basis but NO price on page (booking via easeroom.co) -> unknown."),
}

def visit_prompt(name,url):
    return (f"Visit ONLY this URL: {url} (property '{name}'). Extract ONLY a monthly price THIS page "
     "explicitly publishes (rent per unit or per bed). Do NOT infer; no other site. 'starting from'=>"
     "'starting_from'; exact published=>'published_exact'; none=>'unknown' and price=null. "
     'Return ONLY JSON: {"monthly_price":null,"price_confidence":"published_exact|starting_from|unknown",'
     '"source_url":"","evidence":""}. source_url MUST be this page. No prose.')

def main():
    client,status=get_client()
    if client is None:
        write_empty(status, errors="GROQ_API_KEY not visible; set it and run in a new shell."); return
    model=None; errors=[]
    for m in MODELS:
        _,_,e=call(client,m,"Reply OK.")
        if e is None: model=m; break
        errors.append(f"{m} probe: {e}")
    if model is None: write_empty("MODEL_UNAVAILABLE",errors=" | ".join(errors)); return

    raw=[]; grounded=False
    for label,p in DISC_PROMPTS:
        t,tools,err=call(client,model,p,max_tokens=350)
        if err: errors.append(f"discovery[{label}]: {err}"); continue
        grounded = grounded or tools>0
        arr=json_blob(t) or []
        if isinstance(arr,dict): arr=[arr]
        raw.extend([x for x in arr if isinstance(x,dict)])

    rows=[]; seen=set()
    for d in raw:
        name=(d.get("name") or "").strip()
        if not name: continue
        url=(d.get("official_url") or "").strip()
        host=host_of(url) if url.startswith("http") else ""
        key=host or name.lower()
        if key in seen: continue
        seen.add(key)
        is_agg=bool(host) and any(host==a or host.endswith("."+a) for a in AGGREGATOR_HOSTS)
        ptype=norm_type((d.get("property_type") or "")+" "+name)
        area,pin=d.get("area"),(str(d.get("pincode")) if d.get("pincode") else None)
        dk,prec,w2=compute_distance(area,pin)
        w1=bool(dk is not None and dk<=1.0)
        w3=bool(w2 or (dk is not None and dk<=3.0) or prec.startswith("same_suburb_600041"))
        w5=bool(w3 or (dk is not None and dk<=5.0))
        rows.append(dict(name=name,official_url=url or None,host=host or None,area=area,pincode=pin,
            property_type=ptype,is_business=bool(d.get("is_business",True)),is_aggregator=is_agg,
            verified_first_party=False, dist_km_from_vishful=dk,distance_precision=prec,
            within_1km=w1,within_2km=w2,within_3km=w3,within_5km=w5,
            monthly_price=None,price_confidence="unknown",source_url=None,evidence=None,
            groq_grounded=grounded))

    # apply INDEPENDENT (WebSearch/WebFetch) verification — real first-party URLs, price still unknown
    for r in rows:
        nl=r["name"].lower()
        for key,v in INDEPENDENT_VERIFIED.items():
            if key in nl:
                dk,prec,w2=compute_distance(r["area"], v["pin"])
                r.update(official_url=v["url"], host=v["host"], verified_first_party=True,
                    property_type=v["ptype"], pincode=v["pin"], is_aggregator=False,
                    dist_km_from_vishful=dk, distance_precision=prec,
                    within_1km=bool(dk is not None and dk<=1.0), within_2km=w2,
                    within_3km=bool(w2 or (dk is not None and dk<=3.0) or prec.startswith("same_suburb_600041")),
                    within_5km=True, price_confidence="unknown", monthly_price=None,
                    source_url=v["url"], evidence=v["evidence"])
                break

    # price visits: only non-aggregator candidates with a first-party URL not already verified above
    targets=[r for r in rows if r["official_url"] and not r["is_aggregator"] and not r["verified_first_party"]][:MAX_VISITS]
    for r in targets:
        t,tools,err=call(client,model,visit_prompt(r["name"],r["official_url"]),max_tokens=300)
        if err: errors.append(f"visit {r['host']}: {err}"); continue
        obj=json_blob(t) or {}
        if isinstance(obj,list): obj=obj[0] if obj else {}
        src=(obj.get("source_url") or r["official_url"] or "").strip()
        sh=host_of(src) if src.startswith("http") else ""
        first_party=(sh==r["host"] and r["host"]!="")
        r["verified_first_party"]=first_party
        conf=obj.get("price_confidence") or "unknown"
        if conf not in ("published_exact","starting_from","unknown"): conf="unknown"
        price=obj.get("monthly_price")
        # GUARD: number kept only if first-party + published_exact
        if price is not None and not (first_party and conf=="published_exact"): price=None
        if conf=="unknown": price=None
        r.update(price_confidence=conf, monthly_price=price, source_url=(src or None),
                 evidence=(obj.get("evidence") or "")[:300])

    cand=pd.DataFrame(rows,columns=CAND_COLS)
    cand.to_csv(CAND,index=False)
    def cnt(col): return int(cand[col].sum()) if len(cand) else 0
    priced=cand[(cand["monthly_price"].notna()) & (cand["price_confidence"]=="published_exact") & (cand["verified_first_party"])]
    types={t:int((cand["property_type"]==t).sum()) for t in
           ["residential_apartment","co_living","serviced_apartment","pg","hostel","unknown"]}
    summary=[("groq_status","OK"),("groq_model",model),("candidates",len(cand)),
        ("verified_first_party",cnt("verified_first_party")),
        ("aggregator_flagged",cnt("is_aggregator")),
        ("type_residential_apartment",types["residential_apartment"]),
        ("type_co_living",types["co_living"]),("type_serviced_apartment",types["serviced_apartment"]),
        ("type_pg",types["pg"]),("type_hostel",types["hostel"]),("type_unknown",types["unknown"]),
        ("within_1km",cnt("within_1km")),("within_2km",cnt("within_2km")),
        ("within_3km",cnt("within_3km")),("within_5km",cnt("within_5km")),
        ("first_party_priced",len(priced)),
        ("unknown_price",int((cand["price_confidence"]=="unknown").sum())),
        ("groq_grounded",grounded),("errors"," | ".join(errors) if errors else "none")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(SUMM,index=False)

    print("PHASE-3 GROQ APARTMENT DISCOVERY:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\ncandidates:")
    for _,r in cand.iterrows():
        print(f"  {r['name']} | {r['property_type']} | {r['host'] or 'no-site'} | agg={r['is_aggregator']} "
              f"fp={r['verified_first_party']} within3km={r['within_3km']} | price={r['price_confidence']}")
    print("\nfirst-party prices:", "NONE" if priced.empty else "")
    for _,r in priced.iterrows():
        print(f"  {r['name']} | {r['monthly_price']} | {r['source_url']}")

if __name__=="__main__": main()
