"""
Phase-3 Review INTELLIGENCE extraction (Groq). Per collected review, extract decision-relevant,
aggregatable signals (not just theme): themes, sentiment, pain_points, positive_drivers,
customer_needs, purchase_signal, retention_signal, evidence_strength. Groq never invents; only
what the review text supports. temperature=0. Derived layer keyed by review_id to the immutable raw.
Fixed theme vocab. NO competitor comparison. Writes only phase3_review_intelligence.csv.
"""
from __future__ import annotations
import os, sys, json, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
from groq import Groq
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
RAW=pd.read_csv(os.path.join(OUT,"phase3_competitor_reviews_raw.csv"))
VOCAB=["food","wifi","laundry","cleanliness","maintenance","staff","security","parking",
       "power_backup","room_quality","sharing","ac","water","common_area","location","value","safety"]
MODEL="openai/gpt-oss-120b"; BATCH=8

def call(client, batch):
    payload=[{"id":str(r["review_id"]),"stars":int(r["rating"]),"text":str(r["review_text"])[:700]} for _,r in batch.iterrows()]
    prompt=("You are a customer-experience analyst. For EACH review extract ONLY what the text supports. "
     f"Allowed themes (use only these): {VOCAB}. "
     "Return ONLY a JSON array, one object per id: "
     '{"id":"","themes":[],"sentiment":"positive|negative|neutral",'
     '"pain_points":[<themes with a NEGATIVE experience>],'
     '"positive_drivers":[<themes with a POSITIVE experience>],'
     '"customer_needs":[<themes the customer expects/needs>],'
     '"purchase_signal":true|false,   (mentions choosing/booking/deciding/recommending for a decision)'
     '"retention_signal":true|false,  (mentions long stay / leaving / would return / deposit / renew)'
     '"evidence_strength":"high|medium|low"}   (high=specific+detailed, low=generic like \"good\"). '
     "Do NOT invent themes not in the text. Reviews:\n"+json.dumps(payload,ensure_ascii=False))
    r=client.chat.completions.create(model=MODEL,messages=[{"role":"user","content":prompt}],temperature=0,max_tokens=3800)
    t=r.choices[0].message.content or ""; m=re.search(r"\[.*\]",t,re.S)
    try: return json.loads(m.group(0)) if m else []
    except Exception: return []

def clean_list(x): return [t for t in (x or []) if t in VOCAB]

def main():
    key=os.environ.get("GROQ_API_KEY")
    if not key: sys.exit("GROQ_API_KEY not in env.")
    client=Groq(api_key=key.strip())
    prop=dict(zip(RAW["review_id"].astype(str),RAW["property_name"]))
    rows=[]; errs=0
    for i in range(0,len(RAW),BATCH):
        b=RAW.iloc[i:i+BATCH]
        try: res=call(client,b)
        except Exception: errs+=1; res=[]
        got={str(o.get("id")):o for o in res if isinstance(o,dict)}
        for _,r in b.iterrows():
            rid=str(r["review_id"]); o=got.get(rid)
            if o is None:
                rows.append(dict(review_id=rid,property_name=prop.get(rid),themes="",sentiment="unknown",
                    pain_points="",positive_drivers="",customer_needs="",purchase_signal=False,
                    retention_signal=False,evidence_strength="unknown",extraction_status="missing",
                    model=MODEL,evidence_snippet=str(r["review_text"])[:160])); continue
            sent=o.get("sentiment") if o.get("sentiment") in ("positive","negative","neutral") else "neutral"
            es=o.get("evidence_strength") if o.get("evidence_strength") in ("high","medium","low") else "low"
            rows.append(dict(review_id=rid,property_name=prop.get(rid),
                themes="|".join(clean_list(o.get("themes"))),sentiment=sent,
                pain_points="|".join(clean_list(o.get("pain_points"))),
                positive_drivers="|".join(clean_list(o.get("positive_drivers"))),
                customer_needs="|".join(clean_list(o.get("customer_needs"))),
                purchase_signal=bool(o.get("purchase_signal")),retention_signal=bool(o.get("retention_signal")),
                evidence_strength=es,extraction_status="ok",model=MODEL,evidence_snippet=str(r["review_text"])[:160]))
    df=pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT,"phase3_review_intelligence.csv"),index=False)
    ok=df[df["extraction_status"]=="ok"]
    print("PHASE-3 REVIEW INTELLIGENCE:")
    print(f"  reviews:{len(df)} ok:{len(ok)} missing:{int((df['extraction_status']=='missing').sum())} batches_errored:{errs}")
    print(f"  pain-point reviews:{int((ok['pain_points'].str.len()>0).sum())}  purchase_signal:{int(ok['purchase_signal'].sum())}  retention_signal:{int(ok['retention_signal'].sum())}")
    print(f"  evidence_strength: {ok['evidence_strength'].value_counts().to_dict()}")

if __name__=="__main__": main()
