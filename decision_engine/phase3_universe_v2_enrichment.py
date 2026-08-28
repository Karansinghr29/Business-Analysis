"""
Phase-3 UNIVERSE v2 ENRICHMENT / BACKFILL (isolated, deterministic, read-only).

Backfills the 53 verified NEW properties (44 independents + 9 operator:Zolo) with what is PUBLICLY available:
coarse Vishful-relative distance, identity/source URL, published rent (basis-classified), sharing-level rent
where explicitly published, review availability, and amenity evidence with strict provenance. NO fabrication:
"starting from" -> STARTING_FROM; contact-gated / not-displayed -> UNKNOWN. Third-party platform evidence stays
separate from first-party; Zolo stays operator:Zolo. Does NOT touch v1/v2 masters or any existing calculation.

Coarse distance uses real Nominatim suburb centroids (same method as the existing coarse-distance layer);
Kattankulathur/SRM uses the median Vishful-distance of the already-geocoded SRM competitors (data-derived).
Writes ONLY phase3_universe_v2_enrichment.csv (+ _summary.csv).
"""
from __future__ import annotations
import os, sys, json, re, math, statistics
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
ADD=[a for a in json.load(open(os.path.join(HERE,"phase3_universe_v2_additions.json"),encoding="utf-8")) if a["status"]=="verified"]
DIST=pd.read_csv(os.path.join(OUT,"phase3_competitor_distances.csv"))
M=pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv"))
VISHFUL=(12.9878697,80.2551457)
CENTROID={"thiruvanmiyur":(12.985895,80.264421),"adyar":(13.006450,80.257779),
 "perungudi":(12.971024,80.241805),"thoraipakkam":(12.949176,80.240688),"kottivakkam":(12.970505,80.261503)}
def hav(a,b,c,d):
    R=6371.0;p1,p2=math.radians(a),math.radians(c);dp=math.radians(c-a);dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return R*2*math.asin(math.sqrt(x))
# Kattankulathur/SRM coarse = median distance of existing geocoded SRM competitors (data-derived, not fabricated)
katt=M[M["locality"].str.contains("kattankulathur|potheri|srm",case=False,na=False)]["competitor_name"]
kd=pd.to_numeric(DIST[DIST["competitor_name"].isin(katt)]["distance_km_from_vishful"],errors="coerce").dropna()
KATT_KM=round(float(statistics.median(kd)),2) if len(kd) else None

def loc_key(s):
    s=str(s).lower()
    for k in CENTROID:
        if k in s: return k
    if "kattankulathur" in s or "potheri" in s or "srm" in s: return "kattankulathur"
    return None

def classify_rent(txt):
    t=str(txt).lower()
    if not t or t in ("nan","none") or "not displayed" in t or "contact" in t: return ("UNKNOWN","")
    if "-" in t and re.search(r"\d[\d,]*\s*-\s*\d",t): return ("RANGE",txt)      # "Rs.3,500 to 6,500" style
    if " to " in t and re.search(r"\d[\d,]*\s*to\s*\d",t): return ("RANGE",txt)
    if re.search(r"\d.*shar",t):                                                 # tier tied to a sharing type
        return ("SHARING_SPECIFIC",txt)
    if "onwards" in t or "starts" in t or "from" in t: return ("STARTING_FROM",txt)
    if re.search(r"₹\s?\d|rs\.?\s?\d",t): return ("FLAT_DISPLAYED",txt)
    return ("UNKNOWN","")

def main():
    rows=[]
    for a in ADD:
        nm=a["property_name"]; lk=loc_key(a.get("locality","")+" "+str(a.get("address","")))
        if lk=="kattankulathur":
            dist=KATT_KM; dbasis="coarse_srm_cluster_median(existing geocoded SRM competitors)"
        elif lk:
            dist=round(hav(VISHFUL[0],VISHFUL[1],*CENTROID[lk]),2); dbasis=f"coarse_suburb_centroid_{lk}(Nominatim)"
        else:
            dist=None; dbasis="unknown_no_locality_centroid"
        pbasis,pev=classify_rent(a.get("published_rent",""))
        is_zolo=(a.get("operator")=="Zolo")
        amen=str(a.get("amenities") or "")
        rows.append(dict(property_name=nm,operator=a.get("operator","independent"),
            operator_source_type=a.get("operator_source_type","independent"),
            locality=a.get("locality",""),pincode=a.get("pincode",""),
            distance_from_vishful_km=(dist if dist is not None else "Unknown"),distance_basis=dbasis,
            source_platform=a.get("source_platform",""),source_url=a.get("source_url",""),
            source_evidence_type=("operator:Zolo (browser-rendered)" if is_zolo else "third_party_platform_listing"),
            sharing_type=a.get("sharing_type",""),published_rent=a.get("published_rent",""),
            price_basis=pbasis,price_evidence=(pev if pev else "unknown/contact-gated"),
            review_evidence=("ratings only (no review text collected)" if not is_zolo else "not collected"),
            amenities=amen,amenity_provenance=("operator:Zolo self-listed" if is_zolo else "third_party_platform_listed") if amen else "none",
            provenance=a.get("provenance","")))
    D=pd.DataFrame(rows)
    D.to_csv(os.path.join(OUT,"phase3_universe_v2_enrichment.csv"),index=False)
    n=len(D)
    def cov(mask): return f"{int(mask.sum())}/{n}"
    summary=[
     ("new_properties",n),("independents",int((D['operator_source_type']=='independent').sum())),("zolo",int((D['operator']=='Zolo').sum())),
     ("distance_coverage(coarse or better)",cov(D['distance_from_vishful_km'].astype(str)!="Unknown")),
     ("source_url_coverage",cov(D['source_url'].astype(str).str.startswith('http'))),
     ("any_published_rent",cov(D['price_basis']!="UNKNOWN")),
     ("SHARING_SPECIFIC_rent",cov(D['price_basis']=="SHARING_SPECIFIC")),
     ("STARTING_FROM_rent",cov(D['price_basis']=="STARTING_FROM")),
     ("RANGE_rent",cov(D['price_basis']=="RANGE")),
     ("price_UNKNOWN(contact-gated)",cov(D['price_basis']=="UNKNOWN")),
     ("review_coverage(review text)","0/%d (Justdial/Sulekha show ratings only; no review intelligence collected for the 53)"%n),
     ("amenity_evidence_coverage",cov(D['amenities'].astype(str).str.len()>2)),
     ("distance_UNKNOWN",cov(D['distance_from_vishful_km'].astype(str)=="Unknown")),
     ("kattankulathur_coarse_km",KATT_KM),
     ("note","third-party kept separate from first-party; Zolo=operator:Zolo; no fabrication; contact-gated=UNKNOWN; distances are COARSE suburb-centroid (not exact per-property coords)"),
    ]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_universe_v2_enrichment_summary.csv"),index=False)
    print("PHASE-3 UNIVERSE v2 ENRICHMENT (53 new properties):")
    for k,v in summary: print(f"  {k}: {v}")

if __name__=="__main__": main()
