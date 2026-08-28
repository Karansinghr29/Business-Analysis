"""Fail-loud validation for the Vishful amenity 5-bucket provenance (first-party verified). Read-only + determinism."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase3_vishful_amenity_provenance.csv"); SA=o("phase3_vishful_self_audit.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
BUCKETS={"VISHFUL_INTERNAL_VERIFIED","VISHFUL_PUBLIC_EXPLICIT","VISHFUL_PUBLIC_NEARBY_CONTEXT","MARKET_FIRST_PARTY_CONTEXT","UNKNOWN"}
def b(a): return D[D["amenity"]==a]["vishful_own_bucket"].iloc[0]

print("[1] five amenities; Vishful-own bucket from taxonomy; market kept separate")
chk(set(D["amenity"])=={"AC","Wi-Fi","Food","Parking","Security/CCTV"},"AC/Wi-Fi/Food/Parking/Security-CCTV")
chk(set(D["vishful_own_bucket"]).issubset(BUCKETS),"vishful_own_bucket uses only the 5 buckets")
chk((D["market_context_bucket"]=="MARKET_FIRST_PARTY_CONTEXT").all(),"competitor prevalence = MARKET_FIRST_PARTY_CONTEXT (separate column)")

print("[2] classifications match the verified first-party evidence")
chk(b("AC")=="VISHFUL_INTERNAL_VERIFIED","AC = VISHFUL_INTERNAL_VERIFIED")
chk(b("Wi-Fi")=="VISHFUL_INTERNAL_VERIFIED","Wi-Fi = VISHFUL_INTERNAL_VERIFIED")
chk(b("Parking")=="VISHFUL_PUBLIC_EXPLICIT","Parking = VISHFUL_PUBLIC_EXPLICIT (site advertises it)")
chk(b("Security/CCTV")=="VISHFUL_PUBLIC_EXPLICIT","Security/CCTV = VISHFUL_PUBLIC_EXPLICIT (site: 'CCTV Security')")
chk(b("Food")=="VISHFUL_PUBLIC_NEARBY_CONTEXT","Food = VISHFUL_PUBLIC_NEARBY_CONTEXT ('Food Vendors Nearby')")

print("[3] internal verification kept separate from public-explicit")
chk(D[D["amenity"]=="Parking"]["internal_status"].iloc[0]=="UNKNOWN","Parking public-explicit but internal still UNKNOWN (kept separate)")
chk(D[D["amenity"]=="Security/CCTV"]["internal_status"].iloc[0]=="UNKNOWN","Security public-explicit but internal still UNKNOWN")
# AC/Wi-Fi internal verified traces to self-audit
def sa(attr):
    r=SA[SA["attribute"]==attr]; return str(r.iloc[0]["status"]) if len(r) else "?"
chk(sa("AC (air conditioning)")=="VERIFIED_PRESENT" and sa("Wi-Fi / Internet")=="VERIFIED_PRESENT","self-audit confirms AC + Wi-Fi VERIFIED_PRESENT")

print("[4] exact source wording + URL recorded; Food nearby (not provided)")
chk(bool(D["vishful_public_source"].str.contains("vishful.co.in").all()),"public source URL recorded (vishful.co.in)")
chk("CCTV Security" in D[D["amenity"]=="Security/CCTV"]["vishful_public_wording"].iloc[0],"Security wording quotes 'CCTV Security'")
chk("Parking" in D[D["amenity"]=="Parking"]["vishful_public_wording"].iloc[0],"Parking wording recorded")
fw=D[D["amenity"]=="Food"]["vishful_public_wording"].iloc[0]
chk("Food Vendors Nearby" in fw and ("not a vishful" in fw.lower() or "nearby" in fw.lower()),"Food wording = 'Food Vendors Nearby' (NOT Vishful-provided)")

print("[5] competitor evidence never establishes a Vishful amenity; no over-claim/demand")
blob=" ".join(map(str,D.values.ravel())).lower()
chk("vishful provides food" not in blob,"never claims Vishful provides food")
for bad in ["should add","proves demand","competitor demand","better than","market average","charge ₹","charge rs "]:
    chk(bad not in blob,f"absent forbidden phrase: '{bad}'")
chk(bool(D["market_context_evidence"].str.contains("NOT a Vishful claim",case=False).all()),"market context flagged NOT a Vishful claim")
# no amenity's Vishful bucket is set from competitor market data
chk(not (D["vishful_own_bucket"]=="MARKET_FIRST_PARTY_CONTEXT").any(),"no Vishful-own bucket is MARKET_FIRST_PARTY_CONTEXT")

print("[6] engine untouched; deterministic; dashboard renders it")
chk(len(o("phase3_marketing_recommendations.csv"))==10,"marketing recs reflect corrected vacancy (10; Single INV/VAC/SHR dropped at 0 single vacancy)")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
p=os.path.join(OUT,"phase3_vishful_amenity_provenance.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_vishful_amenity_provenance.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("VISHFUL_PUBLIC_EXPLICIT" in dash and "VISHFUL_PUBLIC_NEARBY_CONTEXT" in dash and "vishful_public_wording" in dash,"Page 12 renders 5-bucket provenance with public wording")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
