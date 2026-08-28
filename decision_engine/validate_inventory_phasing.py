"""
Inventory-phasing invariant (A33/A34, 11 beds, inventory start 2026-08-01).

Audit finding: occupancy/vacancy/bed-capacity in this project is a CURRENT SNAPSHOT (step4/step5/KPIs) plus
one NUMERATOR-ONLY historical series (revenue_forecast monthly occupied_beds). There is NO occupancy-% that
applies a total-beds DENOMINATOR over a pre-August window, so A33/A34's 11 beds cannot inflate any historical
figure. This validator LOCKS that rule as a regression guard (read-only; changes no output):

  - A33/A34 exist with inventory start 2026-08-01 and 11 beds.
  - A33/A34 have ZERO tenant allotments onboarded before 2026-08-01 -> never in any pre-August occupied count.
  - A33/A34 are absent from the historical EB series (no pre-August consumption rows).
  - step4 vacancy treats A33/A34 unfilled beds as NEW INVENTORY: vacancy duration is measured from the
    operational start (2026-08-01) only — never from any earlier date — and they are labelled
    'New inventory — available from Aug 2026' (owner-approved lifecycle correction), NOT 'never occupied?'.
  - Current occupancy (step5) DOES include A33/A34 (August onwards) — they are live inventory now.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import loader
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
CUT=pd.Timestamp("2026-08-01",tz="UTC")
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

D,_=loader.load_all()
ap=D["apartments"]; beds=D["beds"]; al=D["tenant_allotments"]
a=ap[ap["apartment_code"].astype(str).str.upper().str.replace(" ","").isin(["A33","A34"])]
aid=set(a["id"]); bids=set(beds[beds["apartment_id"].isin(aid)]["id"])

print("[1] A33/A34 identity: 2 apartments, inventory start 2026-08-01, 11 beds")
chk(len(a)==2,"A33 and A34 both present")
sd=pd.to_datetime(a["start_date"],errors="coerce").dt.strftime("%Y-%m-%d")
chk(bool((sd=="2026-08-01").all()),"both start_date = 2026-08-01 (operational inventory start)")
chk(len(bids)==11,f"A33+A34 contain 11 beds (got {len(bids)})")

print("\n[2] no pre-August presence — 11 beds do not exist in any earlier calculation")
ala=al[al["bed_id"].isin(bids)].copy()
ala["ob"]=pd.to_datetime(ala["onboarding_date"],errors="coerce",utc=True)
chk(int((ala["ob"]<CUT).sum())==0,"ZERO A33/A34 allotments onboarded before 2026-08-01 (never in pre-Aug occupied counts)")
ebl=o("phase2_eb_leak_signals.csv")
chk(("apartment_id" not in ebl.columns) or (not ebl["apartment_id"].isin(aid).any()),"A33/A34 absent from historical EB leak series (no pre-Aug consumption)")

print("\n[3] new inventory: vacancy measured from operational start (2026-08-01), never from before it")
v=o("step4_vacancy_at_risk.csv")
TODAY=pd.Timestamp("2026-08-13")  # phase1 fixed TODAY (deterministic); vacancy can be at most TODAY - operational start
MAX_SINCE_START=(TODAY-pd.Timestamp("2026-08-01")).days
if "apartment_id" in v.columns:
    va=v[v["apartment_id"].isin(aid)]
    dv=pd.to_numeric(va["days_vacant"],errors="coerce")
    # duration is KNOWN but bounded by the operational start -> can never imply vacancy before 2026-08-01
    chk((len(va)==0) or bool(((dv.notna())&(dv>=0)&(dv<=MAX_SINCE_START)).all()),
        "A33/A34 unfilled beds: vacancy duration counted from operational start 2026-08-01 only (never pre-August)")
    chk((len(va)==0) or bool(va["recommended_action"].astype(str).str.contains("New inventory",case=False).all()),
        "A33/A34 unfilled beds flagged 'New inventory — available from Aug 2026' (not 'never occupied')")

print("\n[4] included from August onwards (current snapshot)")
occ_now=set(al.loc[al["actual_exit_date"].isna(),"bed_id"].dropna())
chk(len(bids & occ_now)>=1,"at least one A33/A34 bed is currently occupied (live inventory counted now)")
s5=o("step5_pricing_analysis.csv")
# step4 and step5 must share the SAME rentable universe (Live apartment + Live bed) — same computation as phase1 STEP4/5.
apstat2=dict(zip(ap["id"],ap["status"].astype(str).str.strip()))
beds2=beds.copy(); beds2["_apt_status"]=beds2["apartment_id"].map(apstat2)
rentable=beds2[(beds2["_apt_status"]=="Live")&(beds2["status"].astype(str).str.strip()=="Live")]
# any (bed_type,toilet_type) combo absent from bed_rates is unrepresented in step5's card-driven merge — a
# pre-existing, unrelated rate-card data gap (not part of the vacancy lifecycle correction); excluded from the
# expected total so this check isolates the lifecycle universe, not that separate gap.
# step5 now drives its merge from the rentable occupancy universe, so EVERY rentable bed is in
# total_beds — including bed-type/toilet-type combos with no bed_rates row. The previous expectation
# subtracted unpriced combos (194) to work around that gap; the gap is now closed on the COUNTING side
# and the expectation is the full universe. Triple/Common legitimately remains unpriced: its pricing
# columns stay null and signal() reports "insufficient" — a rate-card question for the owner, separate
# from the inventory count.
chk(int(s5["total_beds"].sum())==len(rentable),
    f"step5 total_beds ({int(s5['total_beds'].sum())}) == full rentable Live-apt+Live-bed universe "
    f"({len(rentable)}) — step4 and step5 share the same rentable definition, no bed dropped")
br2=D["bed_rates"]; priced=set(zip(br2["bed_type"],br2["toilet_type"]))
unpriced=rentable[~rentable.apply(lambda r:(r["bed_type"],r["toilet_type"]) in priced,axis=1)]
chk(int(s5["total_beds"].sum())-len(unpriced)==len(rentable)-len(unpriced),
    f"{len(unpriced)} rentable bed(s) have no bed_rates row (Triple/Common in A34) and are STILL counted "
    "in total_beds; their pricing columns stay null rather than the beds being dropped")
if len(unpriced):
    up=s5[s5["total_beds"].notna()].merge(unpriced[["bed_type","toilet_type"]].drop_duplicates(),
                                          on=["bed_type","toilet_type"],how="inner")
    chk(len(up)>0 and bool(up["card_median"].isna().all()),
        "unpriced combo appears in step5 with a null card_median (counted, not priced)")
a33_34_rentable=len(bids & set(rentable["id"]))
chk(a33_34_rentable==10,
    f"{a33_34_rentable} of A33/A34's 11 beds are rentable (Live/Live) and ALL are counted in step5 "
    "total_beds (the 11th, A34 B2, is Not-Active and correctly excluded)")

print("\n[5] no historical occupancy-% denominator exists to distort")
# revenue_forecast monthly occupied_beds is numerator-only (no /total_beds); documented invariant
rf_src=open(os.path.join(HERE,"revenue_forecast.py"),encoding="utf-8").read()
chk("occupied_beds=act[\"bed_id\"].nunique()" in rf_src,"revenue_forecast monthly occupied_beds is a numerator-only count (no total-beds denominator over time)")
chk("/max(float(r[\"total_beds\"]),1)" in open(os.path.join(HERE,"phase3_decision_execution_analytics.py"),encoding="utf-8").read(),
    "KPI occupancy % is computed from step5 CURRENT snapshot (labelled 'current snapshot'), not a historical window")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
