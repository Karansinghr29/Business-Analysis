"""
Phase-3 Google Places DISCOVERY (official Places API (New) only — NO HTML scraping, NO pricing).
Center = Vishful property (geocoded from address; gps cols are null in DB).
Discovers PG/hostel/paying-guest businesses, dedups by place_id, tags NEW vs existing list,
computes distance + radius bands. Writes outputs/phase3_places_candidates.csv.

USAGE (PowerShell):
    $env:GOOGLE_MAPS_API_KEY = "<your key>"      # do NOT paste the key into chat
    python places_discovery.py

Requires Places API (New) + Geocoding API enabled on the key. Billed to your Google account.
Field mask keeps only permitted business fields (cost + privacy controlled).
"""
from __future__ import annotations
import os, sys, math, time, json, urllib.request, urllib.parse
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

KEY=os.environ.get("GOOGLE_MAPS_API_KEY")
if not KEY: sys.exit("Set GOOGLE_MAPS_API_KEY env var first (do not paste it into chat).")
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs"); os.makedirs(OUT,exist_ok=True)

ADDRESS="M38, M39 and M40 West Avenue, Tiruvanmiyur, Chennai, Tamil Nadu 600041"
# PGs already shown in the dashboard Market AI list (from prior capture) — for is_new tagging.
EXISTING={"skylinn stays","zara co-living","eden coliving","green apple residency","whites inn",
          "sri venkata vishnu priya","sri mahalakshmi","aostel","vishful vista heights"}
QUERIES=["PG in Tiruvanmiyur Chennai","paying guest Tiruvanmiyur","mens PG near Tiruvanmiyur",
         "womens PG Tiruvanmiyur","ladies hostel Tiruvanmiyur","co-living Tiruvanmiyur",
         "hostel near Tiruvanmiyur","PG Perungudi","PG Adyar Chennai"]
RADII_M=[1000,2000,3000,5000]
FIELD_MASK=("places.id,places.displayName,places.formattedAddress,places.location,places.rating,"
            "places.userRatingCount,places.primaryType,places.nationalPhoneNumber,places.websiteUri,"
            "places.googleMapsUri,places.addressComponents")

def geocode(addr):
    u="https://maps.googleapis.com/maps/api/geocode/json?"+urllib.parse.urlencode({"address":addr,"key":KEY})
    j=json.load(urllib.request.urlopen(u))
    loc=j["results"][0]["geometry"]["location"]; return loc["lat"],loc["lng"]

def post(url, body):
    req=urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type":"application/json","X-Goog-Api-Key":KEY,"X-Goog-FieldMask":FIELD_MASK})
    return json.load(urllib.request.urlopen(req))

def text_search(q, lat, lng, radius):
    return post("https://places.googleapis.com/v1/places:searchText",
        {"textQuery":q,"maxResultCount":20,
         "locationBias":{"circle":{"center":{"latitude":lat,"longitude":lng},"radius":radius}}})

def nearby(lat, lng, radius):
    return post("https://places.googleapis.com/v1/places:searchNearby",
        {"includedTypes":["lodging"],"maxResultCount":20,
         "locationRestriction":{"circle":{"center":{"latitude":lat,"longitude":lng},"radius":radius}}})

def haversine(a,b,c,d):
    R=6371000; p1,p2=math.radians(a),math.radians(c); dp=math.radians(c-a); dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return int(R*2*math.asin(math.sqrt(x)))

def pincode(comps):
    for c in comps or []:
        if "postal_code" in c.get("types",[]): return c.get("longText")
    return None
def locality(comps):
    for want in ("sublocality_level_1","sublocality","locality"):
        for c in comps or []:
            if want in c.get("types",[]): return c.get("longText")
    return None

def main():
    lat,lng=geocode(ADDRESS); print(f"center: {lat},{lng}")
    seen={}
    for q in QUERIES:
        try: r=text_search(q,lat,lng,5000)
        except Exception as e: print("skip",q,e); continue
        for p in r.get("places",[]): seen[p["id"]]=p
        time.sleep(0.3)
    for rad in (2000,5000):
        try: r=nearby(lat,lng,rad)
        except Exception as e: print("nearby skip",e); continue
        for p in r.get("places",[]): seen.setdefault(p["id"],p)
        time.sleep(0.3)
    rows=[]
    for pid,p in seen.items():
        name=p.get("displayName",{}).get("text","")
        loc=p.get("location",{}); dm=haversine(lat,lng,loc.get("latitude"),loc.get("longitude")) if loc else None
        dkm=round(dm/1000,3) if dm is not None else None
        is_exist=any(k in name.lower() for k in EXISTING)
        band=next((f"<= {r//1000}km" for r in RADII_M if dm is not None and dm<=r), ">5km")
        rows.append(dict(place_id=pid,name=name,formatted_address=p.get("formattedAddress"),
            locality=locality(p.get("addressComponents")),pincode=pincode(p.get("addressComponents")),
            lat=loc.get("latitude"),lng=loc.get("longitude"),phone=p.get("nationalPhoneNumber"),
            website=p.get("websiteUri"),rating=p.get("rating"),review_count=p.get("userRatingCount"),
            primary_type=p.get("primaryType"),maps_uri=p.get("googleMapsUri"),
            distance_km=dkm,radius_band=band,is_existing=is_exist,is_new_candidate=(not is_exist)))
    SCHEMA=["place_id","name","formatted_address","locality","pincode","lat","lng","phone","website",
            "rating","review_count","primary_type","maps_uri","distance_km","radius_band","is_existing","is_new_candidate"]
    df=pd.DataFrame(rows).reindex(columns=SCHEMA).sort_values("distance_km",na_position="last")
    df.to_csv(os.path.join(OUT,"phase3_places_candidates.csv"),index=False)
    print(f"\nunique places discovered: {len(df)}  existing: {int(df['is_existing'].sum())}  NEW: {int(df['is_new_candidate'].sum())}")
    print("candidates per radius (unique):")
    for r in RADII_M:
        n=int((df['distance_km']<=r/1000).sum()); nn=int(((df['distance_km']<=r/1000)&df['is_new_candidate']).sum())
        print(f"  <= {r//1000}km: total={n}  new={nn}")
    print("\nby locality:", df.groupby('locality').size().to_dict())
    print("Wrote outputs/phase3_places_candidates.csv  (NO pricing — Places API does not provide PG prices)")

if __name__=="__main__": main()
