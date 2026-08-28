"""
Phase-3 LOCALITY MARKET-CONTEXT (isolated, deterministic, read-only).

Owner-readable market geography of the ACTUAL 115-competitor directory, with spelling variants normalized so
one locality is one card. Contextual only — NOT a ranking of competitors and NOT a Vishful-vs-competitor
comparison. No fabricated values; median shown only when coverage is sufficient (n>=3). Monthly PG price data
(official sharing-specific + starting-from) is kept separate from hotel-nightly/USD (excluded here).

Reads: phase3_competitor_master (locality), phase3_competitor_distances (Vishful km), phase3_competitor_source_links
(verified online source), phase3_competitor_prices (monthly PG prices), phase3_review_intelligence + reviews_raw
(recurring themes). Writes ONLY phase3_locality_summary.csv.
"""
from __future__ import annotations
import os, sys, statistics
from collections import Counter, defaultdict
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd, numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
M=o("phase3_competitor_master.csv"); DIST=o("phase3_competitor_distances.csv")
SRC=o("phase3_competitor_source_links.csv"); PRICE=o("phase3_competitor_prices.csv")
RI=o("phase3_review_intelligence.csv")

def norm_locality(s):
    s=str(s).strip().lower()
    if s in ("","nan","none"): return "Unknown"
    if "tiruvanmiyur" in s or "thiruvanmiyur" in s: return "Thiruvanmiyur, Chennai"
    if "perungudi" in s or "thoraipakkam" in s or "omr" in s: return "Perungudi, Chennai"
    if "adyar" in s or "indira nagar" in s: return "Adyar, Chennai"
    if "kattankulathur" in s or "potheri" in s or "srm" in s: return "Kattankulathur, Chennai"
    if s=="chennai": return "Chennai (area unspecified)"
    return s.title()+", Chennai"

# reviewed property_name -> master competitor (by distinctive token) -> normalized locality
REV2KEY={"Diyaa Paying Guest":"Diyaa","Feel At Home Ladies Hostel":"Feel At Home",
 "Kolam Gandhi Serviced Apartments":"Kolam Gandhi","Kripa Homes PG":"Kripa Homes",
 "Olive Serviced Apartments":"Olive Serviced","Sahithyan Men's PG":"Sahithyan",
 "Season 4 Rentals":"Season 4","Subodhaya Paying Guest (Ladies)":"Subodhaya",
 "TSP PG Accommodation":"TSP","Yali Service Apartment":"Yali"}
def review_locality(prop):
    key=REV2KEY.get(prop)
    if not key: return None
    m=M[M["competitor_name"].str.contains(key,case=False,na=False)]
    return norm_locality(m.iloc[0]["locality"]) if len(m) else None

def main():
    m=M.copy(); m["loc"]=m["locality"].map(norm_locality)
    comp_loc=dict(zip(m["competitor_name"],m["loc"]))
    src_comps=set(SRC["competitor_name"])
    monthly=PRICE[PRICE["price_basis"].isin(["OFFICIAL_SHARING_SPECIFIC","OFFICIAL_STARTING_FROM"])].copy()
    monthly["loc"]=monthly["competitor_name"].map(comp_loc)
    # review themes by locality
    ri=RI.copy(); ri["loc"]=ri["property_name"].map(review_locality)
    pos_theme=defaultdict(Counter); neg_theme=defaultdict(Counter); rev_props=defaultdict(set)
    for _,r in ri.iterrows():
        if not r["loc"]: continue
        rev_props[r["loc"]].add(r["property_name"])
        themes=[t for t in str(r.get("themes") or "").split("|") if t and t!="nan"]
        sent=str(r.get("sentiment"))
        for t in themes:
            if sent=="positive": pos_theme[r["loc"]][t]+=1
            elif sent=="negative": neg_theme[r["loc"]][t]+=1

    rows=[]
    for g,gr in m.groupby("loc"):
        cnt=len(gr)
        with_src=len(set(gr["competitor_name"]) & src_comps)
        lm=monthly[monthly["loc"]==g]
        priced_comps=sorted(set(lm["competitor_name"]))
        n_priced=len(priced_comps)
        prices=pd.to_numeric(lm["price"],errors="coerce").dropna()
        prange = f"Rs{int(prices.min()):,}-Rs{int(prices.max()):,}" if len(prices) else "Not available"
        # per-competitor minimum monthly tier -> median only when n>=3
        percomp_min=[int(pd.to_numeric(lm[lm['competitor_name']==c]['price'],errors='coerce').min()) for c in priced_comps]
        pmed = f"Rs{int(statistics.median(percomp_min)):,}" if n_priced>=3 else "insufficient (n<3)"
        sharing=sorted(set(str(s) for s in lm[lm["price_basis"]=="OFFICIAL_SHARING_SPECIFIC"]["sharing_type"].dropna() if str(s)!="None"))
        nrev=len(rev_props.get(g,set()))
        topp="; ".join(f"{t}({c})" for t,c in pos_theme.get(g,Counter()).most_common(3)) or ("no reviews collected" if nrev==0 else "none")
        topn="; ".join(f"{t}({c})" for t,c in neg_theme.get(g,Counter()).most_common(3)) or ("no reviews collected" if nrev==0 else "none")
        dvals=pd.to_numeric(gr["competitor_name"].map(dict(zip(DIST["competitor_name"],pd.to_numeric(DIST["distance_km_from_vishful"],errors="coerce")))),errors="coerce").dropna()
        avg_dist=round(float(dvals.mean()),2) if len(dvals) else "Unknown"
        rows.append(dict(locality=g,competitor_count=cnt,competitors_with_source=with_src,
            competitors_with_official_monthly_pricing=n_priced,competitors_with_reviews=nrev,
            monthly_price_range=prange,monthly_starting_price_median=pmed,
            common_sharing_types=(", ".join(sharing) if sharing else "Not available"),
            top_positive_themes=topp,top_negative_themes=topn,
            avg_distance_from_vishful_km=avg_dist,
            coverage=f"{cnt} competitors · {n_priced} priced · {nrev} reviewed"))
    L=pd.DataFrame(rows)
    # contextual locality_score (density + proximity). Descriptive only; NOT a ranking.
    cnt=L["competitor_count"].astype(float); dens=cnt/cnt.max() if cnt.max()>0 else cnt*0
    dnum=pd.to_numeric(L["avg_distance_from_vishful_km"],errors="coerce")
    dmax=dnum.max(); prox=(1-(dnum/dmax)) if (dmax and dmax>0) else pd.Series([np.nan]*len(L))
    L["locality_score_context"]=[int(round(100*d)) if pd.isna(p) else int(round(100*(0.6*d+0.4*p))) for d,p in zip(dens,prox)]
    L=L.sort_values("competitor_count",ascending=False).reset_index(drop=True)
    L.to_csv(os.path.join(OUT,"phase3_locality_summary.csv"),index=False)

    print("PHASE-3 LOCALITY MARKET-CONTEXT:")
    print(f"  total competitors: {int(L['competitor_count'].sum())} (expect 115) | localities: {len(L)}")
    print(L[["locality","competitor_count","competitors_with_official_monthly_pricing","competitors_with_reviews",
             "monthly_price_range","monthly_starting_price_median"]].to_string(index=False))

if __name__=="__main__": main()
