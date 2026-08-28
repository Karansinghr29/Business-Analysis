"""Fail-loud validation for the v2 enrichment/backfill of the 53 new properties. Read-only + determinism."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
E=o("phase3_universe_v2_enrichment.csv"); V2=o("phase3_market_universe_v2.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] covers exactly the 53 verified new properties")
chk(len(E)==53,f"53 enrichment rows (got {len(E)})")
v2new=set(V2[V2["universe_version"]=="v2"]["property_name"])
chk(set(E["property_name"])==v2new,"enrichment rows == the 53 v2 verified additions")
chk(int((E["operator"]=="Zolo").sum())==9 and int((E["operator_source_type"]=="independent").sum())==44,"44 independents + 9 Zolo")

print("\n[2] no fabrication — contact-gated/absent stays UNKNOWN")
chk(bool(E[E["price_basis"]=="UNKNOWN"]["price_evidence"].astype(str).str.contains("unknown|contact",case=False).all()),"UNKNOWN prices carry no fabricated amount")
chk(set(E["price_basis"]).issubset({"SHARING_SPECIFIC","STARTING_FROM","RANGE","FLAT_DISPLAYED","UNKNOWN"}),"price_basis values are valid")
# no invented distance: Unknown allowed; numeric must be coarse-labelled
num=E[E["distance_from_vishful_km"].astype(str)!="Unknown"]
chk(bool(num["distance_basis"].str.contains("coarse",case=False).all()),"every numeric distance is labelled COARSE (no fake exact coord)")

print("\n[3] third-party kept separate from first-party; Zolo tagged")
chk(bool(E[E["operator"]=="Zolo"]["source_evidence_type"].str.contains("Zolo",case=False).all()),"Zolo rows tagged operator:Zolo evidence")
chk(bool(E[E["operator_source_type"]=="independent"]["source_evidence_type"].str.contains("third_party",case=False).all()),"independent listings tagged third_party_platform")
chk(int((E["review_evidence"].astype(str).str.contains("no review text|not collected|ratings only",case=False)).sum())==53,"reviews: no review-text fabricated for any of the 53")

print("\n[4] coverage columns present; source URL for all")
need={"property_name","distance_from_vishful_km","distance_basis","source_url","source_evidence_type","price_basis","sharing_type","published_rent","review_evidence","amenities","amenity_provenance"}
chk(need.issubset(E.columns),"required enrichment columns present")
chk(bool(E["source_url"].astype(str).str.startswith("http").all()),"every new property has a source URL")

print("\n[5] existing calcs untouched; deterministic; not wired downstream")
chk(len(o("phase3_competitor_prices.csv"))==66,"pricing dataset unchanged (66)")
chk(len(o("phase3_competitor_distances.csv"))==115,"distance layer unchanged (115)")
chk(o("phase3_competitor_source_links.csv")["competitor_name"].nunique()==90,"source-links unchanged (90)")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_universe_v2_enrichment" not in dash,"dashboard does NOT consume the enrichment (no downstream change)")
p=os.path.join(OUT,"phase3_universe_v2_enrichment.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_universe_v2_enrichment.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
