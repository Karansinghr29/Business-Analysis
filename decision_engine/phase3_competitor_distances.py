"""
Phase-3 Competitor DISTANCE correction (isolated, deterministic, read-only).
Distance = great-circle from Vishful's reference coordinate to each competitor. Fixes the bug where
same-suburb (Thiruvanmiyur) competitors were shown as 0.0 km. Uses ACTUAL geocoded coordinates
(Google Maps via the approved Apify run) where available; otherwise preserves the existing coarse
suburb-centroid distance (labelled coarse) or Unknown. NO fabricated coordinates. Same locality is
NOT treated as same location. Does NOT change discovery/verification/pricing/master/spec logic —
produces a NEW isolated file the Market AI directory joins for display.

Vishful reference: property gps is null in the DB and 'West Avenue' did not geocode, so we use the
Nominatim geocode of Tiruvanmiyur 600041 (suburb-level, labelled). This is the fixed reference point.

Writes ONLY phase3_competitor_distances.csv + _summary.csv.
"""
from __future__ import annotations
import os, sys, math, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
M=pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv"))

# Vishful EXACT mapped property location (Google Maps place, same map methodology as competitors).
# Place: "Vishful Vista Heights", M39/M40 West Avenue, Cosmopolitian Colony, Kamaraj Nagar, Thiruvanmiyur,
# Chennai 600041. Google placeId=ChIJl51FKnxdUjoR6GcIjXDtGGw, cid=7789236623195531240, website vishful.co.in
# (matches owner domain — authoritative). Retrieved via approved Apify compass/crawler-google-places run
# AxGSVtCcgrP1vgevf (dataset siqqC4A0tYfIt2iRn). NOT the suburb centroid; NOT fabricated.
VISHFUL=(12.9878697, 80.2551457)
VISHFUL_PLACE_ID="ChIJl51FKnxdUjoR6GcIjXDtGGw"
VISHFUL_REF_NOTE=("Vishful ref = EXACT mapped property (Vishful Vista Heights, West Avenue, Thiruvanmiyur 600041; "
    "12.9878697,80.2551457; Google placeId ChIJl51FKnxdUjoR6GcIjXDtGGw; Apify google-places run AxGSVtCcgrP1vgevf)")

# Coarse suburb/pincode CENTROIDS (real Nominatim geocodes). Used ONLY for competitors in a DIFFERENT suburb
# than Vishful, whose exact coordinate is unavailable -> approximate Vishful-relative distance. Thiruvanmiyur/
# 600041 is deliberately EXCLUDED: same-suburb competitors without a coordinate stay UNKNOWN (a same-suburb
# centroid is ~1 km from Vishful yet such a competitor could be adjacent — never assign it a centroid distance).
LOCALITY_CENTROID={
 "adyar":(13.006450,80.257779),"600020":(13.006450,80.257779),
 "tharamani":(12.979010,80.243214),
 "perungudi":(12.971024,80.241805),"600096":(12.971024,80.241805),
 "thoraipakkam":(12.949176,80.240688),"600097":(12.949176,80.240688),
 "neelankarai":(12.945495,80.257469),
}
def centroid_key(prec):
    s=str(prec).replace("suburb_centroid_","")
    return s if s in LOCALITY_CENTROID else None

# ACTUAL competitor coordinates from Google Maps (approved Apify run zID57BCmD2hhyLRCb, dataset l4cqWmfaZENy3LdCI)
# keyed by a distinctive name substring -> (lat, lng). Real, retrieved — not fabricated.
COORDS={
 "kolam gandhi":(13.0073394,80.2540198),"kripa homes":(12.9850641,80.2537744),
 "diyaa":(12.9915299,80.2524615),"sahithyan":(12.983111,80.2537158),
 "olive serviced":(12.9676487,80.244729),"feel at home":(12.9528419,80.2422624),
 "tsp":(12.9773709,80.2595081),"subodhaya":(12.9865332,80.2548812),
 "season 4":(12.9839839,80.2585875),"yali service":(12.9641024,80.2490728),
}
def hav(a,b,c,d):
    R=6371.0; p1,p2=math.radians(a),math.radians(c); dp=math.radians(c-a); dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R*2*math.asin(math.sqrt(x))
def match_coord(name):
    n=str(name).lower()
    for k,ll in COORDS.items():
        if k in n: return k,ll
    return None,None

def main():
    rows=[]
    for _,r in M.iterrows():
        name=r["competitor_name"]; prec=str(r.get("distance_precision")); dkm=r.get("distance_km")
        key,ll=match_coord(name)
        ckey=centroid_key(prec)
        if ll is not None:
            # EXACT map coordinate for both endpoints -> exact Vishful-relative great-circle distance
            dist=round(hav(VISHFUL[0],VISHFUL[1],ll[0],ll[1]),2)
            rows.append(dict(competitor_name=name,distance_km_from_vishful=dist,
                distance_precision="geocoded_gmaps",coordinate_source="google_maps (Apify run)",
                is_geocoded=True,distance_provenance=f"EXACT great-circle: Vishful mapped coordinate -> competitor actual Google Maps coordinate; {VISHFUL_REF_NOTE}"))
        elif prec.startswith("same_suburb_600041") or (pd.notna(dkm) and float(dkm)==0.0 and "thiruv" in prec):
            # BUG FIX: same suburb as Vishful but NO coordinate -> exact distance UNKNOWN, never 0.0 or centroid
            rows.append(dict(competitor_name=name,distance_km_from_vishful=None,
                distance_precision="same_suburb_thiruvanmiyur_street_unknown",coordinate_source=None,
                is_geocoded=False,distance_provenance="same suburb as Vishful; no coordinate available; exact street-level distance UNKNOWN (NOT 0 km, NOT suburb centroid)"))
        elif pd.notna(dkm) and ckey is not None:
            # different suburb, no exact competitor coord -> APPROXIMATE distance from exact Vishful to real suburb centroid
            cc=LOCALITY_CENTROID[ckey]
            dist=round(hav(VISHFUL[0],VISHFUL[1],cc[0],cc[1]),2)
            rows.append(dict(competitor_name=name,distance_km_from_vishful=dist,
                distance_precision=prec,coordinate_source="suburb_centroid (Nominatim)",is_geocoded=False,
                distance_provenance=f"APPROXIMATE: exact Vishful mapped coordinate -> {ckey} suburb centroid (coarse, not street-level; no exact competitor coordinate); {VISHFUL_REF_NOTE}"))
        else:
            rows.append(dict(competitor_name=name,distance_km_from_vishful=None,
                distance_precision=(prec if prec not in ("nan","None") else "unknown_locality"),
                coordinate_source=None,is_geocoded=False,
                distance_provenance="insufficient location data — distance UNKNOWN (no coordinate/centroid)"))
    D=pd.DataFrame(rows)
    D.to_csv(os.path.join(OUT,"phase3_competitor_distances.csv"),index=False)

    # audit vs old master distance
    old=M.set_index("competitor_name")["distance_km"].to_dict()
    Dm=D.set_index("competitor_name")
    changed=0; from_zero=0; from_unknown=0
    for n in D["competitor_name"]:
        o=old.get(n); ne=Dm.loc[n,"distance_km_from_vishful"]
        o_nan=pd.isna(o); n_nan=pd.isna(ne)
        if (o_nan!=n_nan) or (not o_nan and not n_nan and round(float(o),2)!=round(float(ne),2)):
            changed+=1
            if (not o_nan) and float(o)==0.0: from_zero+=1
            if o_nan and (not n_nan): from_unknown+=1
    summary=[("vishful_reference",VISHFUL_REF_NOTE),
     ("vishful_lat",VISHFUL[0]),("vishful_lng",VISHFUL[1]),("vishful_place_id",VISHFUL_PLACE_ID),
     ("vishful_source","Google Maps place via Apify compass/crawler-google-places run AxGSVtCcgrP1vgevf (dataset siqqC4A0tYfIt2iRn); website vishful.co.in confirms identity"),
     ("vishful_ref_is_exact_map_place","True (NOT suburb centroid)"),
     ("competitors",len(D)),("geocoded_actual",int(D["is_geocoded"].sum())),
     ("coarse_centroid",int(D["coordinate_source"].astype(str).str.startswith("suburb_centroid").sum())),
     ("unknown_distance",int(D["distance_km_from_vishful"].isna().sum())),
     ("changed_total",changed),("changed_from_0.0",from_zero),("changed_from_unknown",from_unknown),
     ("bug_fixed","no competitor is 0.0 km merely for locality==Thiruvanmiyur"),
     ("note","distances measured from EXACT Vishful mapped coordinate; exact competitor coords where available; else coarse suburb centroid (approximate); unknown kept; no fabricated coords")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_competitor_distances_summary.csv"),index=False)
    print("PHASE-3 COMPETITOR DISTANCES (Vishful-relative):")
    for k,v in summary: print(f"  {k}: {v}")
    print("\ngeocoded (actual Vishful-relative distances):")
    for _,r in D[D["is_geocoded"]].sort_values("distance_km_from_vishful").iterrows():
        print(f"  {r['competitor_name'][:36]:36} {r['distance_km_from_vishful']} km")

if __name__=="__main__": main()
