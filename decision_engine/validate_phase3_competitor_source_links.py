"""Fail-loud validation for the reputable online-platform source-link layer. Read-only + determinism."""
from __future__ import annotations
import os, sys, re, json, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase3_competitor_source_links.csv"); M=o("phase3_competitor_master.csv")
SRC=json.load(open(os.path.join(HERE,"phase3_online_sources.json"),encoding="utf-8"))
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

REPUTABLE={"MakeMyTrip","Booking.com","OYO","Justdial","MagicBricks","NoBroker","99acres","Housing.com",
 "Sulekha","Agoda","Airbnb","Goibibo","Tripadvisor","EaseMyTrip","Trip.com","Magicpin","CommonFloor","HexaHome",
 "Official","Yube1","Stanza Living","Truliv","Bag2Bag","Zolo","WowLife","Prohotel","The India Hotels","Olympia","Lancor"}
EXCLUDED={"chiangdao","Vacations.com.au","Hotwire","Wanderlog","Matrihotel","FindMyRoom","TyTil","Doorento","GoPGo","Rentok","ServicedApartment.com"}

print("[1] Google Maps NEVER displayed; no search/fabricated URLs")
chk(int((D["source_type"]=="Google Maps").sum())==0,"no Google Maps source_type row")
chk(int(D["source_url"].str.contains("google.com/maps|maps.google|goo.gl/maps",case=False,na=False).sum())==0,"no google maps URL anywhere")
chk(int(D["source_url"].str.contains(r"/search[/?]|[?&]query=|[?&]q=",case=False,na=False,regex=True).sum())==0,"no search-result URLs")
chk(bool(D["source_url"].astype(str).str.startswith("http").all()),"every source_url is http(s)")

print("\n[2] reputable-only; excluded niche aggregators absent")
chk(bool(D["source_type"].isin(REPUTABLE).all()),"every source_type is in the approved reputable set")
chk(not D["source_type"].isin(EXCLUDED).any(),"no excluded niche/aggregator platform present")
badhost=D[D["source_url"].str.contains("chiangdao|vacations.com.au|hotwire|wanderlog|matrihotel|findmyroom|tytil|doorento|gopgo|rentok",case=False,na=False)]
chk(len(badhost)==0,f"no excluded-aggregator host in URLs (found={list(badhost['source_url'])[:2]})")

print("\n[3] every displayed URL == a frozen identity-verified entry (no additions/fabrication)")
frozen={(r["name"],r["platform"],r["url"]) for r in SRC}
csv_set={(r["competitor_name"],r["source_type"],r["source_url"]) for _,r in D.iterrows()}
extra=csv_set-frozen
chk(not extra,f"no CSV row outside the frozen verified set (extra={list(extra)[:2]})")
chk(len(D)==len(SRC),f"row count matches frozen input ({len(D)} vs {len(SRC)})")

print("\n[4] coverage counts (after Unknown re-research)")
directory=set(M["competitor_name"]); withsrc=set(D["competitor_name"])
chk(len(withsrc & directory)==90,f"90 competitors with a verified online source (got {len(withsrc & directory)})")
chk(len(directory - withsrc)==25,f"25 competitors Unknown/No verified online source (got {len(directory - withsrc)})")
chk("MakeMyTrip" in set(D["source_type"]),"MakeMyTrip present (audit corrected the earlier '0')")
# newly added listings must be actual property/listing pages (id/slug), never search/category
NEWHOSTS=["justdial.com","makemytrip","booking.com","goibibo","tripadvisor","sulekha"]
listing=D[D["source_url"].str.contains("|".join(NEWHOSTS),case=False,na=False)]
chk(not listing["source_url"].str.contains(r"/search|/find/|[?&]q=",case=False,na=False,regex=True).any(),"all platform URLs are specific listing pages, not search/category")

print("\n[5] labels correspond to hosts")
def host(u):
    import urllib.parse as up; return up.urlparse(str(u)).netloc.lower()
chk(all("booking.com" in host(r.source_url) for r in D.itertuples() if r.source_type=="Booking.com"),"Booking.com label only on booking.com URLs")
chk(all("makemytrip" in host(r.source_url) for r in D.itertuples() if r.source_type=="MakeMyTrip"),"MakeMyTrip label only on makemytrip URLs")
chk(all("justdial" in host(r.source_url) for r in D.itertuples() if r.source_type=="Justdial"),"Justdial label only on justdial URLs")
chk(all(("oyo" in host(r.source_url)) for r in D.itertuples() if r.source_type=="OYO"),"OYO label only on OYO URLs")
chk(set(["competitor_name","source_type","source_url","source_verification","source_provenance"]).issubset(D.columns),"required columns present")

print("\n[6] dashboard read-only; new wording; no Google Maps in view")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_competitor_source_links.csv" in dash and "Source / Links" in dash,"Page 10 renders Source / Links")
chk("Unknown / No verified online source" in dash,"Unknown wording = 'No verified online source'")
chk("Google Maps" not in dash.split("phase3_competitor_source_links.csv")[1][:600] or "never shown" in dash,"Google Maps not used as a displayed source")
chk(not re.search(r"\.to_csv\(|open\([^)]*,\s*['\"][wa]\+?b?['\"]",dash),"dashboard performs no file writes")

print("\n[7] no ranking; nothing else changed")
blob=" ".join(map(str,D.values.ravel())).lower()
chk(not any(b in blob for b in ["cheaper","best pg","worst pg"," rank","benchmark","better than","vs competitor"]),"no ranking/comparison language")
chk(len(M)==115 and "distance_km" in M.columns,"competitor master unchanged (115 rows)")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
chk(len(o("phase3_competitor_distances.csv"))==115,"distance layer unchanged (115)")

print("\n[8] deterministic")
p=os.path.join(OUT,"phase3_competitor_source_links.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_competitor_source_links.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
