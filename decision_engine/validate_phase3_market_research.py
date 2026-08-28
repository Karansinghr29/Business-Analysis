"""Fail-loud validation for phase3_market_research dataset + signals. Isolated."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
DS=os.path.join(OUT,"phase3_market_research_dataset.csv")
D=pd.read_csv(DS); SG=pd.read_csv(os.path.join(OUT,"phase3_market_signals.csv"))
AGG=("nobroker","magicbricks","housing","sulekha","justdial","zolostays","stanzaliving","nestaway",
     "gopgo","colive","google.com/maps","youtube.com","instagram.com","facebook.com","tripadvisor",
     "booking.com","makemytrip","indiamart","magicpin","yappe","rentmystay","chennaiproperties")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[first-party only + verification]")
chk(bool(D["official_site_verified"].all()),"every dataset row first-party verified")
chk(bool((D["verification_status"]=="first_party_verified").all()),"verification_status = first_party_verified")
bad=[u for u in D["official_url"].astype(str) if any(a in u.lower() for a in AGG)]
chk(not bad,f"no aggregator/social/map/directory as first-party {bad[:2]}")
chk(bool(D["source_url"].astype(str).str.startswith("https://").all()),"all source_url https first-party")

print("\n[strict pricing / unknown preserved]")
chk(D["monthly_price"].isna().all(),"no numeric price (none published first-party) -> all unknown")
chk(D["price_unit"].isna().all() and D["deposit"].isna().all(),"no price_unit/deposit fabricated")
# no conversion artifacts
chk(not D.astype(str).apply(lambda c:c.str.contains("per night|/night|per day|starting from|per room",case=False)).any().any(),
    "no day/room/starts-from price artifacts in dataset")

print("\n[amenity flags True-or-null only]")
for c in ["food","wifi","laundry","parking","security_cctv","power_backup","ac_availability"]:
    if c in D.columns:
        chk(D[c].dropna().isin([True]).all(),f"{c}: True or null only (no False-assert)")

print("\n[signals = market context, no ranking language]")
alltext=" ".join(SG.astype(str).agg(" ".join,axis=1)).lower()
BAD=["cheaper","more expensive","better than","worse than","rank","beats","outperform","vs vishful","competitor price"]
chk(not any(b in alltext for b in BAD),"no ranking/comparison language in signals")
chk(bool((SG["evidence_source"]=="MARKET_CONTEXT").all()),"all signals tagged MARKET_CONTEXT")
chk(bool(SG["provenance"].astype(str).str.len().gt(0).all()),"every signal has provenance")

print("\n[determinism]")
h1=hashlib.md5(open(DS,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_market_research.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(DS,"rb").read()).hexdigest()
chk(h1==h2,"re-run byte-identical (deterministic)")

print("\n[dedup / key leak / existing files]")
chk(D["property_name"].is_unique,"no duplicate property in dataset")
blob=open(DS,encoding="utf-8").read()+open(os.path.join(OUT,"phase3_market_signals.csv"),encoding="utf-8").read()
chk(re.search(r"(gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,})",blob) is None,"no key leak")
chk(len(pd.read_csv(os.path.join(OUT,"phase3_competitor_master.csv")))==115,"master still 115 rows")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
