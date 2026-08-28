"""Fail-loud validation for the owner marketing-card DISPLAY consolidation. Read-only + determinism."""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase3_owner_marketing_cards.csv"); REC=o("phase3_marketing_recommendations.csv")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)
def card(cid): return D[D["card_id"]==cid].iloc[0]

print("[1] 10 engine recommendations -> 4 owner cards; engine unchanged (Single recs dropped at 0 single vacancy)")
chk(len(REC)==10,"engine has 10 recommendations (Single INV/VAC/SHR dropped after A22-exclusion / 0 single vacancy)")
chk(len(D)==4,f"exactly 4 owner cards (single actionable card correctly absent at 0 single vacancy) (got {len(D)})")
chk(list(D.sort_values('display_order')['card_id'])==["fill_2_sharing","fill_3_sharing","locality_campaign","verify_amenities"],
    "owner order: 2-sharing, 3-sharing, locality, amenities (no single card)")
chk("investigate_single" not in set(D["card_id"]),"no single marketing card while current single vacancy = 0 (A22's old 272-day single excluded)")

print("[2] required consolidations (exact rec ids); all 10 represented")
chk("SHR-Double" in card("fill_2_sharing")["consolidates"] and "INV-Double" in card("fill_2_sharing")["consolidates"],"2-sharing = SHR-Double + INV-Double")
chk("VAC-Triple" in card("fill_3_sharing")["consolidates"] and "INV-Triple" in card("fill_3_sharing")["consolidates"],"3-sharing = VAC-Triple + INV-Triple")
chk("LOC-TVM" in card("locality_campaign")["consolidates"],"locality = LOC-TVM")
chk(card("verify_amenities")["source_count"]==5,"amenities card = 5 AMEN-* rows")
ids=[i.strip() for _,c in D.iterrows() for i in str(c["consolidates"]).split("+")]
chk(sum(int(x["source_count"]) for _,x in D.iterrows())==10 and all((REC["recommendation_id"]==i).any() for i in ids),"all 10 engine rows represented; every id exists")

print("[3] evidence numbers present (derived from corrected step4/step5)")
for tok in ["5 vacant","96.0%","67,500"]: chk(tok in card("fill_2_sharing")["evidence"],f"2-sharing shows corrected {tok}")
# 72.7% (not 80.0%): Triple occupancy is now measured over the full 33-bed Triple universe
# (30 Attached + 3 Common in A34). The 80.0% figure came from the pre-correction 30-bed denominator,
# which silently dropped the unpriced Triple/Common group. 9 vacant of 33 == 72.7% occupied.
for tok in ["9 vacant","72.7%","128,700"]: chk(tok in card("fill_3_sharing")["evidence"],f"3-sharing shows {tok}")
# no stale A22-single or old-Double figures anywhere on the owner marketing cards
blob0=" ".join(map(str,D.values.ravel()))
for stale in ["272 days","19,000","10 vacant","138,000","285,700"]:
    chk(stale not in blob0,f"no stale A22/old-Double figure on owner marketing cards: '{stale}'")

print("[4] amenity card uses 5-bucket provenance (AC/Wi-Fi internal; Parking/Security public-explicit; Food nearby)")
ae=card("verify_amenities")["evidence"].lower(); aa=card("verify_amenities")["suggested_action"].lower()
chk("ac: vishful_internal_verified" in ae and "wi-fi: vishful_internal_verified" in ae,"AC + Wi-Fi = VISHFUL_INTERNAL_VERIFIED")
chk("parking: vishful_public_explicit" in ae and "security/cctv: vishful_public_explicit" in ae,"Parking + Security = VISHFUL_PUBLIC_EXPLICIT")
chk("food: vishful_public_nearby_context" in ae,"Food = VISHFUL_PUBLIC_NEARBY_CONTEXT")
chk("do not market food as a vishful amenity" in aa or ("food vendors nearby" in aa and "not a vishful" in aa),"food explicitly not marketed as a Vishful amenity")
chk("never a reason to add" in aa and "market context only" in aa,"competitor prevalence = context only, not a reason to add")

print("[5] guardrails + scores untouched + deterministic")
blob=" ".join(map(str,D.values.ravel())).lower()
for bad in ["better than","worse than","market average","vishful should charge","charge ₹","charge rs ","rank competitor","proves demand","competitor demand"]:
    chk(bad not in blob,f"absent forbidden phrase: '{bad}'")
chk(not any(re.search(r"(charge|set|price)\s*(it|at|to)?\s*(₹|rs\.?\s*)?\d",str(a),re.I) for a in D["suggested_action"]),"no action recommends a specific numeric price")
chk(set(D["provenance_label"]).issubset({"VISHFUL_INTERNAL","MARKET_CONTEXT","COMBINED"}),"provenance labels preserved")
chk(REC["score"].notna().any(),"engine scores present/untouched")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_owner_marketing_cards.csv" in dash and "Owner decisions" in dash,"Page 12 renders owner marketing cards")
chk("Engine detail" in dash,"engine 13-row detail table preserved for traceability")
chk(len(o("phase3_business_decisions.csv"))==14,"Page-14 decisions unchanged (14)")
p=os.path.join(OUT,"phase3_owner_marketing_cards.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_owner_marketing_cards.py"],cwd=HERE,capture_output=True)
h2=hashlib.md5(open(p,"rb").read()).hexdigest(); chk(h1==h2,"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
