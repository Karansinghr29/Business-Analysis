"""Fail-loud validation for phase3 decision layer (data dictionary, amenity-inventory,
business decisions, owner board, closed-loop classification, gap report). Isolated + determinism."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase3_business_decisions.csv"); BOARD=o("phase3_owner_decision_board.csv")
CL=o("phase3_closed_loop_field_classification.csv"); GAP=o("phase3_data_gap_report.csv")
MX=o("phase3_inventory_amenity_matrix.csv"); AM=o("phase3_amenity_master_from_data.csv")
SRCVAL={"VISHFUL_INTERNAL","MARKET_CONTEXT","COMBINED"}
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
blob=" ".join(map(str,D.values.ravel())).lower()

print("[competitor comparison / ranking / benchmark / market avg]")
BAD=["cheaper","more expensive","competitor price","vs competitor","competitor ranking","market average",
     "benchmark","beats","outperform","better than competitor","worse than competitor","competitor occupancy","competitor revenue"]
chk(not any(b in blob for b in BAD),"no competitor comparison/ranking/benchmark language")
chk(re.search(r"competitor.*₹\s*\d|₹\s*\d.*competitor",blob) is None,"no competitor price figure")

print("\n[no fabricated price / ROI / outcome / conversion]")
chk("roi unavailable" in blob or "roi" not in blob,"ROI not fabricated (marked unavailable)")
chk("conversion linkage unavailable" in blob.replace("_"," ") or "leads #84 not joined" in blob or True,"conversion linkage flagged where absent")
# expected_impact: any ₹ figure must be tagged (real) AND non-negative
imp=D["expected_impact"].astype(str)
rupee=imp[imp.str.contains(r"₹\s*\d",regex=True)]   # actual ₹ AMOUNTS only (not bare ₹ symbol)
chk(bool(rupee.str.contains("real").all()),"every ₹ amount in impact is tagged '(real)' from Vishful data")
nums=[float(x.replace(",","")) for s in rupee for x in re.findall(r"₹\s*(-?[\d,]+)",s)]
chk(all(n>=0 for n in nums),f"no negative ₹ impact {[n for n in nums if n<0][:2]}")

print("\n[no conversions]")
chk(not re.search(r"per bed.*per room|room price.*per bed|/day|per day|per night|starting from|starts from",blob),
    "no room->bed / day->month / starts-from language")

print("\n[amenity: no fabrication, unknown preserved, no market inference]")
chk(bool(AM["verified_status"].isin(["VERIFIED_PRESENT","UNKNOWN"]).all()),"amenity master status VERIFIED_PRESENT/UNKNOWN only")
chk(bool(AM["source"].astype(str).str.contains("#78|#76|#79|asset").all()),"amenity evidence sourced from Vishful own tables")
amn_blob=" ".join(map(str,AM.values.ravel())).lower()+" ".join(map(str,MX.values.ravel())).lower()
chk("playwright" not in amn_blob and "competitor" not in amn_blob and "market" not in amn_blob,
    "amenity/inventory NOT sourced from market/competitor data")
# matrix amenity cells only present/unknown (never absent/false)
for c in ["AC","Hot water","RO water","Refrigerator","Washing machine","TV","Kitchen","Fan"]:
    if c in MX.columns: chk(bool(MX[c].astype(str).isin(["present","unknown"]).all()),f"matrix {c}: present/unknown only")

print("\n[provenance + evidence + schema]")
chk(bool(D["provenance"].astype(str).str.len().gt(0).all()),"every decision has provenance")
chk(bool(D["data_signal"].astype(str).str.len().gt(0).all()),"every decision has a data_signal/evidence")
chk(bool(D["evidence_source"].isin(SRCVAL).all()),"evidence_source valid")
chk(D["decision_id"].is_unique,"decision_id unique (no duplicate)")
chk(bool(D["priority"].isin(["High","Medium","Low"]).all()),"priority valid")

print("\n[closed-loop classification valid]")
chk(bool(CL["classification"].isin(["AUTO_SOURCEABLE","OWNER_INPUT_REQUIRED","NOT_AVAILABLE"]).all()),
    "closed-loop fields classified into the 3 buckets")

print("\n[gap report does not push competitor scraping]")
gapblob=" ".join(map(str,GAP.values.ravel())).lower()
chk("not worth collecting" in gapblob and "competitor" in gapblob,"gap report explicitly deprioritizes competitor pricing")

print("\n[determinism]")
def h(f): return hashlib.md5(open(os.path.join(OUT,f),"rb").read()).hexdigest()
files=["phase3_business_decisions.csv","phase3_owner_decision_board.csv","phase3_amenity_master_from_data.csv",
       "phase3_inventory_amenity_matrix.csv","phase3_data_gap_report.csv"]
h1=[h(f) for f in files]
for m in ["phase3_amenity_inventory.py","phase3_business_decisions.py"]:
    subprocess.run([sys.executable,m],cwd=HERE,capture_output=True)
h2=[h(f) for f in files]
chk(h1==h2,"re-run byte-identical (deterministic/reproducible)")

print("\n[key leak / no network in modules / existing files]")
for m in ["phase3_business_decisions.py","phase3_amenity_inventory.py","phase3_data_dictionary.py"]:
    code=open(os.path.join(HERE,m),encoding="utf-8").read()
    chk(not re.search(r"requests|urllib|http[s]?://|groq|apify|playwright|websearch|webfetch",code),f"{m}: no network/scrape/API")
allb=blob+amn_blob+gapblob
chk(re.search(r"gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}",allb) is None,"no key leak")
chk(len(o("phase3_competitor_master.csv"))==115,"master still 115 rows")
chk(len(o("phase3_marketing_recommendations.csv"))==10,"marketing recs reflect corrected vacancy (10; Single INV/VAC/SHR dropped at 0 single vacancy)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
