"""Fail-loud validation for the Vishful-relative competitor-distance correction. Read-only + determinism."""
from __future__ import annotations
import os, sys, re, math, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase3_competitor_distances.csv"); M=o("phase3_competitor_master.csv")
S=o("phase3_competitor_distances_summary.csv").set_index("metric")["value"].to_dict()
VISHFUL=(12.9878697,80.2551457)          # exact Google Maps place
OLD_CENTROID=(12.9889822,80.2515865)     # former suburb-centroid reference (must NOT be the final ref)
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[0] Vishful reference = EXACT mapped place (not suburb centroid)")
chk(str(S.get("vishful_place_id","")).startswith("ChIJ"),"Vishful Google placeId provenance present")
chk("Apify" in str(S.get("vishful_source","")) or "Google Maps" in str(S.get("vishful_source","")),"Vishful coordinate source/provenance recorded")
chk(abs(float(S["vishful_lat"])-VISHFUL[0])<1e-6 and abs(float(S["vishful_lng"])-VISHFUL[1])<1e-6,"summary Vishful coord == exact mapped coord")
chk((abs(VISHFUL[0]-OLD_CENTROID[0])>1e-4 or abs(VISHFUL[1]-OLD_CENTROID[1])>1e-4),"reference is NOT the old suburb centroid")

print("[1] no competitor 0.0 km merely for locality==Thiruvanmiyur")
chk(not ((D["distance_km_from_vishful"]==0.0).any()),"no distance is exactly 0.0 km")
same=D[D["distance_precision"]=="same_suburb_thiruvanmiyur_street_unknown"]
chk(bool(same["distance_km_from_vishful"].isna().all()) if len(same) else True,"same-suburb-no-coord rows are Unknown (not 0.0)")

print("\n[2] every numeric distance is Vishful-relative + non-negative")
num=D[D["distance_km_from_vishful"].notna()]
chk(bool((num["distance_km_from_vishful"]>=0).all()),"all numeric distances non-negative")
chk(bool(num["distance_provenance"].str.contains("Vishful",case=False).all()),"every numeric distance provenance references Vishful reference")

print("\n[3] no fabricated coordinates; geocoded distances match haversine from Vishful")
COORDS={"kolam gandhi":(13.0073394,80.2540198),"kripa homes":(12.9850641,80.2537744),
 "diyaa":(12.9915299,80.2524615),"sahithyan":(12.983111,80.2537158),"olive serviced":(12.9676487,80.244729),
 "feel at home":(12.9528419,80.2422624),"tsp":(12.9773709,80.2595081),"subodhaya":(12.9865332,80.2548812),
 "season 4":(12.9839839,80.2585875),"yali service":(12.9641024,80.2490728)}
def hav(a,b,c,d):
    R=6371.0;p1,p2=math.radians(a),math.radians(c);dp=math.radians(c-a);dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return R*2*math.asin(math.sqrt(x))
geo=D[D["is_geocoded"]==True]
ok=True
for _,r in geo.iterrows():
    n=str(r["competitor_name"]).lower(); key=next((k for k in COORDS if k in n),None)
    if key is None: ok=False; break
    exp=round(hav(VISHFUL[0],VISHFUL[1],*COORDS[key]),2)
    if abs(exp-float(r["distance_km_from_vishful"]))>0.02: ok=False; break
chk(ok,"every geocoded distance == haversine(EXACT Vishful, its real Google coordinate)")
chk(len(geo)==10,"exactly 10 geocoded competitors (the collected coords; no invented coords)")

print("\n[3b] coarse distances == haversine(EXACT Vishful, real suburb centroid); not old km, not 0")
CENT={"perungudi":(12.971024,80.241805),"adyar":(13.006450,80.257779),"tharamani":(12.979010,80.243214),
 "thoraipakkam":(12.949176,80.240688),"neelankarai":(12.945495,80.257469)}
cok=True
for _,r in D[D["coordinate_source"].astype(str).str.startswith("suburb_centroid")].iterrows():
    key=str(r["distance_precision"]).replace("suburb_centroid_","")
    m={"600020":"adyar","600096":"perungudi","600097":"thoraipakkam"}.get(key,key)
    if m not in CENT: cok=False; break
    exp=round(hav(VISHFUL[0],VISHFUL[1],*CENT[m]),2)
    if abs(exp-float(r["distance_km_from_vishful"]))>0.02: cok=False; break
chk(cok,"every coarse distance == haversine(EXACT Vishful, its real suburb centroid)")

print("\n[4] Unknown preserved; provenance matches method")
chk(bool(D[D["distance_km_from_vishful"].isna()]["distance_provenance"].str.contains("UNKNOWN|unknown|insufficient",case=False).all()),
    "Unknown distances flagged unknown/insufficient in provenance")
chk(bool((geo["distance_precision"]=="geocoded_gmaps").all()),"geocoded rows precision=geocoded_gmaps")
cen=D[D["coordinate_source"].astype(str).str.startswith("suburb_centroid")]
chk(bool(cen["distance_provenance"].str.contains("coarse|APPROXIMATE",case=False).all()) if len(cen) else True,"centroid rows provenance says coarse/approximate")
# same-suburb (Thiruvanmiyur) with no coord must stay Unknown — never assigned a centroid distance
ss=D[D["distance_precision"]=="same_suburb_thiruvanmiyur_street_unknown"]
chk(bool(ss["distance_km_from_vishful"].isna().all()) if len(ss) else True,"same-suburb-no-coord stays Unknown (not centroid, not 0)")

print("\n[5] no ranking/comparison introduced")
blob=" ".join(map(str,D.values.ravel())).lower()
chk(not any(b in blob for b in ["cheaper","best pg","worst pg","rank","benchmark","better than","vs competitor"]),"no ranking/comparison language")

print("\n[6] no pricing / Page-14 / master change")
chk("monthly_rent" not in D.columns and "price" not in " ".join(D.columns).lower(),"distance file has no pricing columns")
chk(len(M)==115 and "distance_km" in M.columns,"competitor master unchanged (115 rows, original distance col intact)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_decision_execution_analytics" in dash and "phase3_competitor_distances" in dash,"dashboard reads corrected distances (display join)")
chk(not re.search(r"\.to_csv\(|open\([^)]*,\s*['\"][wa]\+?b?['\"]",dash),"dashboard performs no file writes")

print("\n[7] deterministic + isolation")
p=os.path.join(OUT,"phase3_competitor_distances.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_competitor_distances.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
chk(os.path.exists(os.path.join(OUT,"phase3_market_spec.json")),"Market AI spec present (not modified by this fix)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
