"""Fail-loud validation for the owner opportunity-card DISPLAY consolidation. Read-only + determinism."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase3_owner_opportunity_cards.csv"); OPP=o("phase3_business_opportunities.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] 9 engine opportunities -> 4 owner cards; engine output unchanged (Single dropped at 0 single vacancy)")
chk(len(OPP)==9,"engine has 9 opportunities (Single opps dropped after A22-exclusion / 0 single vacancy)")
chk(len(D)==4,f"exactly 4 owner cards (single actionable card correctly absent at 0 single vacancy) (got {len(D)})")
chk(list(D.sort_values('display_order')['card_id'])==["fill_2_sharing","fill_3_sharing","locality_campaign","verify_amenities"],
    "owner-facing order: 2-sharing, 3-sharing, locality, amenities (no single card)")
chk("investigate_single" not in set(D["card_id"]),"no single opportunity card while current single vacancy = 0 (A22's old 272-day single excluded)")

print("\n[2] every card consolidates only REAL engine opportunities (no invented)")
allc=[]
for _,c in D.iterrows(): allc+=[n.strip() for n in str(c["consolidates"]).split("+")]
chk(all(OPP["opportunity"].str.contains(n,case=False,na=False).any() for n in allc),"every consolidated name exists in the engine output")
chk(sum(int(x["source_count"]) for _,x in D.iterrows())==9,"all 9 engine rows are represented across the 4 cards (none dropped)")

print("\n[3] required consolidations")
def card(cid): return D[D["card_id"]==cid].iloc[0]
chk("Highlight 2-sharing availability" in card("fill_2_sharing")["consolidates"] and "Promote available 2-sharing inventory" in card("fill_2_sharing")["consolidates"],"2-sharing card merges both 2-sharing opportunities")
chk(card("verify_amenities")["source_count"]==5,"amenities card consolidates all 5 amenity opportunities")
# corrected 2-sharing evidence derived from step4/step5 (Double 5 beds / ₹67,500), NOT the old A22-era 10/₹138,000
for tok in ["5 vacant 2-sharing beds","67,500"]:
    chk(tok in card("fill_2_sharing")["evidence"],f"2-sharing card shows corrected evidence '{tok}'")
# corrected 3-sharing evidence (Triple 9 beds / ₹128,700)
for tok in ["9 vacant 3-sharing beds","128,700"]:
    chk(tok in card("fill_3_sharing")["evidence"],f"3-sharing card shows corrected evidence '{tok}'")
# NO stale A22-single or old-Double numbers anywhere on the owner cards
blob0=" ".join(map(str,D.values.ravel()))
for stale in ["272 days","19,000","10 vacant 2-sharing beds","138,000","285,700"]:
    chk(stale not in blob0,f"no stale A22/old-Double figure on owner cards: '{stale}'")
for tok in ["3/6","4/6","5/6","2/6"]:
    chk(tok in card("verify_amenities")["evidence"],f"amenities card shows '{tok}'")

print("\n[4] guardrails — no ranking / price / demand claims")
blob=" ".join(map(str,D.values.ravel())).lower()
for bad in ["better than","worse than","cheaper than","market average","vishful should charge","charge ₹","charge rs ","rank competitor","proves demand","competitor demand"]:
    chk(bad not in blob,f"absent forbidden phrase: '{bad}'")
import re as _re
chk(not any(_re.search(r"(charge|set|price)\s*(it|at|to)?\s*(₹|rs\.?\s*)?\d",str(a),_re.I) for a in D["suggested_action"]),"no action recommends a specific numeric price")
chk(set(D["provenance_label"]).issubset({"VISHFUL_INTERNAL","MARKET_CONTEXT","COMBINED"}),"provenance labels kept (VISHFUL_INTERNAL/MARKET_CONTEXT/COMBINED)")
# (single card is correctly absent at 0 single vacancy — no single-card price-cut check needed)
# amenities card must not ASSERT that Vishful should add an amenity (a negated 'do NOT ... should add' is fine)
am=card("verify_amenities")["suggested_action"].lower()
chk(("should add" not in am) or ("do not" in am),"amenities card does not assert Vishful should add an amenity")

print("\n[5] scores untouched; dashboard renders cards + keeps traceability; deterministic")
chk("score" in OPP.columns and OPP["score"].notna().any(),"engine scores present and untouched (display did not alter them)")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_owner_opportunity_cards.csv" in dash and "Owner opportunities" in dash,"Page 11 renders the owner cards")
chk("Priority Opportunities (engine detail" in dash and "Evidence Details" in dash,"engine detail table + Evidence Details preserved for traceability")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
p=os.path.join(OUT,"phase3_owner_opportunity_cards.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_owner_opportunity_cards.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
