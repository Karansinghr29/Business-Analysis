"""
Phase-3 nearby-PG discovery via OpenStreetMap (FREE — Overpass + Nominatim). No key, no billing.
No Google, no aggregator scraping, no HTML scraping. Respects OSM usage policy (User-Agent,
minimal requests). Fields OSM cannot provide (rating/review_count/maps_uri) are left null.
Writes outputs/phase3_places_candidates.csv. Read-only on locked outputs. NO pricing.
"""
from __future__ import annotations
import os, sys, math, time, json, urllib.request, urllib.parse
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)
UA={"User-Agent":"VishfulMarketAI/1.0 (contact: wecare@vishful.co.in) nearby-PG-discovery"}
ADDR_CANDIDATES=["West Avenue, Tiruvanmiyur, Chennai, Tamil Nadu 600041",
                 "Tiruvanmiyur, Chennai, Tamil Nadu 600041"]
EXISTING={"skylinn","zara co-living","eden coliving","green apple residency","whites inn",
          "sri venkata vishnu priya","sri mahalakshmi","aostel","vishful","vista heights"}
RADII_M=[1000,2000,3000,5000]

def geocode():
    for a in ADDR_CANDIDATES:
        u="https://nominatim.openstreetmap.org/search?"+urllib.parse.urlencode({"q":a,"format":"json","limit":1})
        try:
            j=json.load(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=30))
            if j: return float(j[0]["lat"]),float(j[0]["lon"]),a
        except Exception as e: print("geocode fail:",a,e)
        time.sleep(1.1)  # Nominatim policy: <=1 req/sec
    return None

OVERPASS_EPS=["https://overpass-api.de/api/interpreter",
              "https://overpass.kumi.systems/api/interpreter",
              "https://overpass.openstreetmap.fr/api/interpreter"]
def overpass(lat,lng):
    # Tag-based (indexed, fast). Name-regex over 5km times out the free servers.
    # OSM has no "PG" tag; PGs map as guest_house/hostel/dormitory (hotels included, flagged by primary_type).
    q=f"""[out:json][timeout:50];
(
  nwr(around:5000,{lat},{lng})["tourism"~"^(hostel|guest_house|hotel|apartment|motel)$"];
  nwr(around:5000,{lat},{lng})["building"="dormitory"];
  nwr(around:5000,{lat},{lng})["amenity"="social_facility"]["social_facility"~"group_home|shelter"];
);
out center tags;"""
    last=None; empty=None
    for ep in OVERPASS_EPS:
        try:
            req=urllib.request.Request(ep,data=urllib.parse.urlencode({"data":q}).encode(),headers=UA)
            j=json.load(urllib.request.urlopen(req,timeout=90))
            n=len(j.get("elements",[])); print(f"  overpass {ep} -> {n} elements")
            if n>0: return j
            empty=j                      # keep empty but try another mirror in case of load
        except Exception as e:
            last=f"{ep}: {e}"; print("  overpass fail:",last)
        time.sleep(2)
    if empty is not None: return empty    # genuinely empty (poor OSM coverage)
    raise RuntimeError(f"all overpass endpoints failed. last={last}")

def haversine(a,b,c,d):
    R=6371000; p1,p2=math.radians(a),math.radians(c); dp=math.radians(c-a); dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R*2*math.asin(math.sqrt(x))

def main():
    g=geocode()
    if not g: sys.exit("Nominatim geocoding failed for all address candidates.")
    lat,lng,used=g; print(f"center via Nominatim ({used}): {lat},{lng}")
    try: data=overpass(lat,lng)
    except Exception as e: sys.exit(f"Overpass query failed: {e}")
    els=data.get("elements",[]); print(f"Overpass returned {len(els)} raw elements")
    rows=[]; seen=set()
    for el in els:
        t=el.get("tags",{}); name=t.get("name")
        if not name: continue                      # skip unnamed
        oid=f"osm:{el['type']}/{el['id']}"
        if oid in seen: continue
        seen.add(oid)
        la=el.get("lat") or el.get("center",{}).get("lat")
        lo=el.get("lon") or el.get("center",{}).get("lon")
        if la is None: continue
        if any(k in name.lower() for k in ["vishful","vista heights"]): continue   # exclude self
        dm=haversine(lat,lng,la,lo); dkm=round(dm/1000,3)
        if dm>5000: continue
        band=next((f"<= {r//1000}km" for r in RADII_M if dm<=r),">5km")
        is_exist=any(k in name.lower() for k in EXISTING)
        ptype=t.get("tourism") or t.get("amenity") or t.get("building") or "unknown"
        addr=", ".join(x for x in [t.get("addr:housenumber"),t.get("addr:street"),
              t.get("addr:suburb"),t.get("addr:city"),t.get("addr:postcode")] if x) or None
        rows.append(dict(place_id=oid,name=name,formatted_address=addr,
            locality=t.get("addr:suburb") or t.get("addr:city_district") or t.get("addr:city"),
            pincode=t.get("addr:postcode"),lat=la,lng=lo,
            phone=t.get("phone") or t.get("contact:phone"),
            website=t.get("website") or t.get("contact:website"),
            rating=None,review_count=None,primary_type=ptype,
            maps_uri=f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            distance_km=dkm,radius_band=band,is_existing=is_exist,is_new_candidate=(not is_exist),
            source="openstreetmap"))
    SCHEMA=["place_id","name","formatted_address","locality","pincode","lat","lng","phone","website",
            "rating","review_count","primary_type","maps_uri","distance_km","radius_band","is_existing",
            "is_new_candidate","source"]
    df=pd.DataFrame(rows).reindex(columns=SCHEMA).sort_values("distance_km",na_position="last")
    df.to_csv(os.path.join(OUT,"phase3_places_candidates.csv"),index=False)

    print(f"\nunique named PG/hostel/co-living candidates (<=5km): {len(df)}  existing={int(df['is_existing'].sum())}  NEW={int(df['is_new_candidate'].sum())}")
    print("per radius (unique):")
    for r in RADII_M:
        n=int((df['distance_km']<=r/1000).sum()); nn=int(((df['distance_km']<=r/1000)&df['is_new_candidate']).sum())
        print(f"  <= {r//1000}km: total={n}  new={nn}")
    print("\nby locality:", {k:int(v) for k,v in df.groupby(df['locality'].fillna('(unknown)')).size().items()})
    print("\nby primary_type:", {k:int(v) for k,v in df.groupby('primary_type').size().items()})
    print("field availability (non-null %):",
          {c:f"{df[c].notna().mean():.0%}" for c in ['formatted_address','locality','pincode','phone','website']})
    print("\nNEW candidates:")
    for _,r in df[df['is_new_candidate']].iterrows():
        print(f"  {r['distance_km']:>5} km | {r['name']} | {r['primary_type']} | {r['locality'] or ''} | {r['website'] or ''}")
    print("\nWrote outputs/phase3_places_candidates.csv  (OSM; rating/review_count/maps_uri from Google unavailable -> null; NO pricing)")

if __name__=="__main__": main()
