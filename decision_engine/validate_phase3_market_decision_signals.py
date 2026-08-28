"""Fail-loud validation for phase3_market_decision_signals. Isolated, read-only + determinism."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase3_market_decision_signals.csv"); SV=o("phase3_market_scraping_value.csv")
fails=[]; blob=" ".join(map(str,D.values.ravel())).lower()
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[no competitor comparison/ranking/benchmark/price-diff]")
BAD=["cheaper","more expensive","competitor price","vs competitor","competitor ranking","market average",
     "market min","market max","competitor benchmark","beats competitor","outperform","better than competitor",
     "worse than competitor","reduce price because","competitor is"]
chk(not any(b in blob for b in BAD),"no competitor comparison/benchmark language")
# per-cell: a competitor price = 'competitor' (as a word, not the provenance filename) + ₹digit in same cell
def _comp_price(cell):
    c=str(cell).lower().replace("competitor_master","").replace("competitor master","")
    return "competitor" in c and bool(re.search(r"₹\s*\d",c))
chk(not any(_comp_price(D.at[i,col]) for i in D.index for col in D.columns),"no competitor price figure in any cell")

print("[no fabricated price / no conversions]")
chk(not re.search(r"per bed.*per room|room price.*per bed|/day|per day|per night|starting from|starts from|package",blob),
    "no room->bed / day->month / starts-from / package conversion")
# pricing signal must stay internal (no benchmark/average built)
pr=D[D["signal_type"]=="published_price"]
chk(bool((pr["candidate_action"].str.contains("INTERNAL",case=False)).all()) if len(pr) else True,
    "price signal keeps pricing INTERNAL (no benchmark)")
chk(bool((pr["would_new_scraping_change_decision"]=="no").all()) if len(pr) else True,"price signal: no new scraping")

print("[unknown preserved: Vishful-unknown amenity -> do NOT advertise]")
unk=D[D["vishful_internal_fact"].str.contains("UNKNOWN",na=False)]
chk(bool((unk["candidate_action"].str.contains("Do NOT advertise|verify internally",case=False)).all()) if len(unk) else True,
    "Vishful-unknown amenities -> do NOT advertise / verify internally")
chk(bool((unk["decision_link"]=="owner_input_gate").all()) if len(unk) else True,"unknown amenities routed to owner gate")

print("[market->Vishful inference blocked]")
# no row asserts a Vishful amenity as present unless fact says VERIFIED (own data), never from market count
act=D[D["candidate_action"].str.startswith(("Highlight","Promote"),na=False)]
chk(bool((act["vishful_internal_fact"].str.contains("VERIFIED|vacant",na=False)).all()) if len(act) else True,
    "every 'highlight/promote' action backed by a VERIFIED/own-vacancy Vishful fact (not market)")

print("[provenance schema complete]")
for col in ["property","location","signal_type","signal_value","first_party_url","evidence","retrieval_date","provenance","confidence_status"]:
    chk(col in D.columns and bool(D[col].astype(str).str.len().gt(0).all()),f"provenance field present+filled: {col}")

print("[scraping-value assessment says NO new scraping]")
chk(bool((SV["new_scraping_has_value"]=="NO").all()),"scraping-value: every candidate signal = NO new scraping")
chk(bool((D["would_new_scraping_change_decision"]=="no").all()),"no linked signal claims new scraping would change a decision")

print("[determinism]")
p=os.path.join(OUT,"phase3_market_decision_signals.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_market_decision_signals.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")

print("[no network/creds + existing files]")
code=open(os.path.join(HERE,"phase3_market_decision_signals.py"),encoding="utf-8").read()
# detect ACTUAL network/scrape CALLS, not the words in filename strings/comments
chk(not re.search(r"import\s+requests|import\s+urllib|from\s+groq|from\s+apify|requests\.(get|post)|"
                  r"urllib\.request|sync_playwright|\.chat\.completions|call-actor",code),
    "module makes no real network/scrape/API call")
chk(re.search(r"gsk_[A-Za-z0-9]{20,}|apify_api_[A-Za-z0-9]{20,}",blob) is None,"no key leak")
chk(len(o("phase3_competitor_master.csv"))==115,"master still 115 rows")
chk(len(o("phase3_business_decisions.csv"))==14,"business decisions unchanged (14)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
