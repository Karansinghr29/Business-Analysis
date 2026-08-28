"""
Phase-3 Stage-3 THEME EXTRACTION (Groq). Extracts themes + sentiment ONLY from the collected
competitor review text (phase3_competitor_reviews_raw.csv). Groq never invents a review or a theme
absent from the text. temperature=0. Output is a DERIVED layer linked by review_id to the raw
(immutable) evidence — the raw file is not modified. Themes from a fixed vocabulary only.
NO competitor comparison/ranking. Writes only phase3_review_themes.csv + phase3_review_theme_aggregate.csv.
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
MODEL="openai/gpt-oss-120b"; BATCH=6

def extract(client, batch):
    payload=[{"id":str(r["review_id"]),"text":str(r["review_text"])[:600]} for _,r in batch.iterrows()]
    prompt=("Extract ONLY themes explicitly present in each review and an overall sentiment. "
      f"Allowed themes (use only these): {VOCAB}. Sentiment: positive|negative|neutral. "
      "Do NOT invent themes not in the text. Return ONLY a JSON array, one object per input id: "
      '[{"id":"","themes":["..."],"sentiment":"positive|negative|neutral"}]. Reviews:\n'
      +json.dumps(payload,ensure_ascii=False))
    r=client.chat.completions.create(model=MODEL,messages=[{"role":"user","content":prompt}],
        temperature=0,max_tokens=2500)
    t=r.choices[0].message.content or ""
    m=re.search(r"\[.*\]",t,re.S)
    try: return json.loads(m.group(0)) if m else []
    except Exception: return []

def main():
    key=os.environ.get("GROQ_API_KEY")
    if not key: sys.exit("GROQ_API_KEY not in env.")
    client=Groq(api_key=key.strip())
    prop_by_id=dict(zip(RAW["review_id"].astype(str),RAW["property_name"]))
    rows=[]; errs=0
    for i in range(0,len(RAW),BATCH):
        batch=RAW.iloc[i:i+BATCH]
        try: res=extract(client,batch)
        except Exception as e: errs+=1; res=[]
        got={str(o.get("id")):o for o in res if isinstance(o,dict)}
        for _,r in batch.iterrows():
            rid=str(r["review_id"]); o=got.get(rid)
            if o is None:                    # model did not return this id -> honest, not fabricated neutral
                rows.append(dict(property_name=prop_by_id.get(rid), review_id=rid, theme="(extraction_missing)",
                    sentiment="unknown", extractor="groq", model=MODEL, evidence_snippet=str(r["review_text"])[:160]))
                continue
            themes=[t for t in (o.get("themes") or []) if t in VOCAB]  # guard: fixed vocab only
            sent=o.get("sentiment") if o.get("sentiment") in ("positive","negative","neutral") else "neutral"
            for th in (themes or ["(none)"]):
                rows.append(dict(property_name=prop_by_id.get(rid), review_id=rid, theme=th,
                    sentiment=sent, extractor="groq", model=MODEL,
                    evidence_snippet=str(r["review_text"])[:160]))
    th=pd.DataFrame(rows)
    th.to_csv(os.path.join(OUT,"phase3_review_themes.csv"),index=False)

    # aggregate (context only, per property + market) — never a ranking
    real=th[th["theme"]!="(none)"]
    agg=real.groupby(["theme","sentiment"]).size().reset_index(name="mentions")
    agg=agg.pivot_table(index="theme",columns="sentiment",values="mentions",fill_value=0).reset_index()
    for c in ["positive","negative","neutral"]:
        if c not in agg.columns: agg[c]=0
    agg["total"]=agg[["positive","negative","neutral"]].sum(axis=1)
    agg=agg.sort_values("total",ascending=False)
    agg.to_csv(os.path.join(OUT,"phase3_review_theme_aggregate.csv"),index=False)

    print("PHASE-3 REVIEW THEME EXTRACTION:")
    print(f"  reviews_processed: {RAW['review_id'].nunique()}  theme_rows: {len(real)}  batches_errored: {errs}")
    print("  top themes (mentions | +/-/0):")
    for _,r in agg.head(12).iterrows():
        print(f"    {r['theme']:14} {int(r['total']):>3}  (+{int(r['positive'])} / -{int(r['negative'])} / ~{int(r['neutral'])})")

if __name__=="__main__": main()
