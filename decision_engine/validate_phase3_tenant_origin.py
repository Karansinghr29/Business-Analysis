"""
Fail-loud validation for the tenant-origin composition table.

Guards the conservative-resolution contract: no fabricated state, ambiguous evidence stays Unknown,
overlapping sources must agree, the denominator is labelled, and no demand/forecast claim is made.
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import loader
import phase3_tenant_origin as G

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "outputs")
fails = []
def chk(c, m):
    print(("  PASS " if c else "  FAIL ") + m)
    if not c: fails.append(m)
def o(f): return pd.read_csv(os.path.join(OUT, f))

T = o("phase3_tenant_origin.csv")
DIST = o("phase3_tenant_origin_distribution.csv")
S = dict(zip(o("phase3_tenant_origin_summary.csv")["metric"], o("phase3_tenant_origin_summary.csv")["value"]))
D, _ = loader.load_all()
src = D["tenants"]; al = D["tenant_allotments"]

print("[1] population and identity")
chk(len(T) == len(src), f"one row per tenant record ({len(T)} vs source {len(src)})")
chk(T["tenant_id"].duplicated().sum() == 0, "no duplicate tenant_id — identity key is unique")
chk(set(T["tenant_id"].astype(str)) == set(src["id"].astype(str)), "tenant ids match the source table exactly")
multi = int((T["allotment_count"] > 1).sum())
chk(multi > 0 and len(T) == src["id"].nunique(),
    f"{multi} tenants hold >1 allotment yet appear ONCE — room/bed movement never duplicates a tenant")

print("\n[2] resolution counts reconcile")
R = int(T["origin_state"].notna().sum()); U = int(T["origin_state"].isna().sum())
chk(R + U == len(T), f"resolved {R} + unknown {U} == total {len(T)}")
chk(int(S["resolved_tenants"]) == R and int(S["unknown_tenants"]) == U, "summary counts match the table")
chk(int(DIST["resolved_tenants"].sum()) == R, "distribution rows sum to the resolved count")
chk(abs(DIST["pct_of_resolved"].sum() - 100.0) < 1.0, "percentages are of RESOLVED tenants and sum to ~100")

print("\n[3] no fabricated geography — every resolution traces to real evidence")
for _, r in T[T["origin_state"].notna()].iterrows():
    cols = [r["src_declared"], r["src_address"], r["src_pincode"], r["src_city_addr"], r["src_city_col"]]
    vals = {v for v in cols if isinstance(v, str) and v}
    chk(r["origin_state"] in vals,
        f"{str(r['full_name'])[:20]}: resolved state came from a populated evidence column") if len(vals) == 0 else None
bad = [r for _, r in T[T["origin_state"].notna()].iterrows()
       if r["origin_state"] not in {v for v in [r["src_declared"], r["src_address"], r["src_pincode"],
                                                r["src_city_addr"], r["src_city_col"]] if isinstance(v, str) and v}]
chk(not bad, f"every resolved state appears in at least one evidence column ({len(bad)} violations)")
chk(set(T["origin_state"].dropna()).issubset(set(G.STATES)),
    "every resolved value is a real Indian state/UT from the fixed list")

print("\n[4] overlapping evidence sources agree (conservative acceptance)")
conf = 0
for _, r in T.iterrows():
    vals = {v for v in [r["src_declared"], r["src_address"], r["src_pincode"],
                        r["src_city_addr"], r["src_city_col"]] if isinstance(v, str) and v}
    if len(vals) > 1:
        conf += 1
        chk(pd.isna(r["origin_state"]), f"{str(r['full_name'])[:20]}: contradicting sources left Unknown")
chk(int(S["conflicting_evidence_left_unknown"]) == conf, f"summary records the {conf} conflict case(s)")
agree = T[(T["origin_state"].notna()) & (T["agreeing_sources"] > 1)]
chk(len(agree) > 0, f"{len(agree)} resolutions are corroborated by >1 independent source")

print("\n[5] ambiguity is preserved as Unknown, never guessed")
chk(int(S["ambiguous_city_left_unknown"]) >= 0 and int(S["pincode_present_but_prefix_ambiguous"]) >= 0,
    "ambiguous city / pincode counters are reported")
for p3 in G.AMBIG_PIN3:
    hit = T[T["pin_used"].astype(str).str.startswith(p3) & T["src_pincode"].notna()]
    chk(len(hit) == 0, f"boundary prefix {p3}xxx never resolved by pincode (Puducherry/Mahe enclave)")
for p2 in ["24", "26"]:
    hit = T[T["pin_used"].astype(str).str.startswith(p2) & T["src_pincode"].notna()]
    chk(len(hit) == 0, f"boundary prefix {p2}xxxx never resolved by pincode (Uttarakhand kept UP series)")
chk("Tamil Nafu" in str(S["invalid_state_values_rejected"]),
    "invalid state value 'Tamil Nafu' rejected rather than corrected by inference")
chk("Harris County Health Center" in str(S["invalid_state_values_rejected"]),
    "non-state value 'Harris County Health Center' rejected")
raw_bad = src[src["state"].astype(str).str.strip().isin(["Tamil Nafu", "Harris County Health Center"])]
for _, r in raw_bad.iterrows():
    row = T[T["tenant_id"].astype(str) == str(r["id"])]
    if len(row) and pd.notna(row["origin_state"].iloc[0]):
        chk(row["resolution_source"].iloc[0] != "explicit_state_field",
            "a tenant with an invalid state value was not resolved FROM that invalid value")

print("\n[6] forbidden sources were not used")
SRC = open(os.path.join(HERE, "phase3_tenant_origin.py"), encoding="utf-8").read()
body = SRC.split('"""', 2)[-1]
chk("company_state" not in body and "company_city" not in body,
    "employer address fields are not used to derive origin")
chk("invoice" not in body.lower().replace("invoice_used_for_geography", ""),
    "invoice data is not used to derive geography")
chk(str(S["company_address_used"]).startswith("NO"), "summary states employer address was not used")
chk(str(S["invoice_used_for_geography"]).startswith("NO"), "summary states invoices were not used")

print("\n[7] denominator labelling and honest limitations")
chk("RESOLVED" in str(S["denominator_note"]) and "Unknown" in str(S["denominator_note"]),
    "denominator is explicitly labelled as resolved tenants with the Unknown share stated")
chk(set(["state", "resolved_tenants", "pct_of_resolved", "pct_of_all_tenants"]).issubset(DIST.columns),
    "distribution carries BOTH the resolved-denominator and all-tenant percentages")
chk(str(S["time_series_possible"]).startswith("NO"),
    "time-series limitation recorded (created_at only for a single-year subset)")
chk(int(S["tenants_with_created_at"]) == int(T["has_created_at"].sum()), "created_at coverage matches")

print("\n[8] no demand / forecast / targeting claim")
blob = (str(S["interpretation"]) + " " + SRC).lower()
for banned in ["feeder market", "demand forecast", "will grow", "growing market", "predicted demand"]:
    chk(banned not in str(S["interpretation"]).lower(), f"interpretation makes no '{banned}' claim")
chk("not demand" in str(S["interpretation"]).lower() or "NOT demand" in str(S["interpretation"]),
    "interpretation explicitly states this is composition, not demand")
chk("composition" in str(S["interpretation"]).lower(), "labelled as tenant-origin composition")

print("\n[9] this layer creates NO recommendation")
for f in ["phase4_ai_opportunities.csv", "phase3_business_decisions.csv", "phase4_nearby_recommendations.csv"]:
    try:
        d = o(f)
        blob2 = " ".join(d.astype(str).values.ravel().tolist()).lower()
        chk("origin_state" not in blob2 and "tenant-origin" not in blob2,
            f"{f} contains no tenant-origin recommendation")
    except Exception:
        pass
chk(len(o("phase3_business_decisions.csv")) == 14, "14 backbone decisions unchanged in count")
chk(len(o("phase4_ai_opportunities.csv")) == 13, "13 AIREC unchanged in count")
chk(len(o("phase4_nearby_recommendations.csv")) == 5, "5 nearby recommendations unchanged in count")

print("\n[10] historical (2019-onward) and current views")
H = o("phase3_tenant_origin_historical.csv")
C = o("phase3_tenant_origin_current.csv")
Y = o("phase3_tenant_origin_by_year.csv")
alx = al.copy()
alx["_onb"] = pd.to_datetime(alx["onboarding_date"], errors="coerce", utc=True)
first = alx.dropna(subset=["_onb"]).groupby("tenant_id")["_onb"].min()
active_ids = set(al.loc[al["actual_exit_date"].isna(), "tenant_id"].dropna().astype(str))

chk(int(Y["cohort_year"].min()) == 2019,
    f"historical population starts at 2019 where onboarding data exists (min cohort year {int(Y['cohort_year'].min())})")
chk(int(first.dt.year.min()) == 2019 and int(Y["cohort_year"].min()) == int(first.dt.year.min()),
    "earliest cohort year matches the earliest real onboarding_date in the source")
chk(int(Y["tenants_onboarded"].sum()) == len(first),
    f"year rows sum to the historical population ({int(Y['tenants_onboarded'].sum())} vs {len(first)})")
hist_pop = int(H["denominator_population"].iloc[0]); curr_pop = int(C["denominator_population"].iloc[0])
chk(hist_pop == len(first), f"historical population = tenants with an onboarding_date ({hist_pop})")
chk(curr_pop == len(active_ids), f"current population = tenants with an open allotment ({curr_pop})")
chk(hist_pop != curr_pop, "current and historical are calculated SEPARATELY, not one blended figure")
hist_ids = set(T[T["in_historical_population"] == True]["tenant_id"].astype(str))
curr_ids = set(T[T["is_current"] == True]["tenant_id"].astype(str))
chk(curr_ids.issubset(hist_ids), "current is a strict SUBSET of historical (never summed with it)")
chk(str(S["current_is_subset_of_historical"]).lower() == "true", "summary records the subset relationship")
chk("never be summed" in str(S["view_separation_note"]), "summary warns the two views must not be summed")

print("\n[11] no duplicate tenant counting from invoices or multiple allotments")
chk(len(first) == first.index.nunique(), "one first-onboarding row per tenant_id")
inv_ids = set(D["invoices"]["tenant_id"].dropna().astype(str))
chk(inv_ids.issubset(set(T["tenant_id"].astype(str))),
    f"no invoice tenant_id outside the {len(T)}-tenant population ({len(inv_ids - set(T['tenant_id'].astype(str)))} orphans)")
chk(set(al["tenant_id"].dropna().astype(str)).issubset(set(T["tenant_id"].astype(str))),
    "no allotment tenant_id outside the tenant population")
for name, df in [("historical", H), ("current", C)]:
    d = df[df["state"] != "Unknown"]
    chk(int(d["tenants"].sum()) + int(df[df["state"] == "Unknown"]["tenants"].iloc[0])
        == int(df["denominator_population"].iloc[0]),
        f"{name}: resolved + Unknown == population (no tenant counted twice or dropped)")
    chk(d["state"].duplicated().sum() == 0, f"{name}: each state appears once")
multi_al = int((T["allotment_count"] > 1).sum())
chk(multi_al > 0, f"{multi_al} tenants have >1 allotment and still contribute one row each")

print("\n[12] every displayed percentage uses the correct denominator")
for name, df in [("historical", H), ("current", C)]:
    d = df[df["state"] != "Unknown"]
    nres = int(df["denominator_resolved"].iloc[0]); npop = int(df["denominator_population"].iloc[0])
    chk(int(d["tenants"].sum()) == nres, f"{name}: resolved rows sum to denominator_resolved ({nres})")
    chk(abs(d["pct_of_resolved"].sum() - 100.0) < 1.0, f"{name}: pct_of_resolved sums to ~100")
    chk(abs(d["pct_of_population"].sum() - 100 * nres / npop) < 1.0,
        f"{name}: pct_of_population sums to the resolved share of the population, not to 100")
    for _, r in d.iterrows():
        ok = (abs(r["pct_of_resolved"] - 100 * r["tenants"] / nres) < 0.11
              and abs(r["pct_of_population"] - 100 * r["tenants"] / npop) < 0.11)
        if not ok: chk(False, f"{name}/{r['state']}: percentage does not match its stated denominator")
    chk(True, f"{name}: every row's percentages recompute from the stated denominators")
    unk = df[df["state"] == "Unknown"].iloc[0]
    chk(pd.isna(unk["pct_of_resolved"]),
        f"{name}: Unknown has NO pct_of_resolved (it is not a resolved state)")
    chk(abs(unk["pct_of_population"] - 100 * unk["tenants"] / npop) < 0.11,
        f"{name}: Unknown share of population is correct and visible")
    chk(int(unk["tenants"]) > 0, f"{name}: Unknown is preserved as a visible non-zero row")

print("\n[13] year view publishes coverage so thin years cannot be read as a trend")
chk("coverage_pct" in Y.columns and "coverage_caveat" in Y.columns, "year view carries coverage and a caveat column")
thin = Y[Y["resolved"] < 50]
chk(bool((thin["coverage_caveat"].astype(str).str.contains("thin")).all()),
    f"all {len(thin)} thin year(s) are flagged as not interpretable")
chk(str(S["year_trend_claim"]).startswith("NOT SUPPORTED"), "summary states no year trend is claimed")
for _, r in Y.iterrows():
    chk(int(r["resolved"]) + int(r["unknown"]) == int(r["tenants_onboarded"]),
        f"{int(r['cohort_year'])}: resolved + unknown == onboarded")

print("\n[14] cohort dating never uses the migration timestamp")
# behavioural, not a source-text match: cohort_year must equal the year of first_onboarding for every
# tenant, and must NOT track created_at (whose years are all post-migration).
_fo = pd.to_datetime(T["first_onboarding"], errors="coerce", utc=True)
_have = T["cohort_year"].notna()
chk(bool((T.loc[_have, "cohort_year"].astype(int) == _fo[_have].dt.year).all()),
    "cohort_year == year(first_onboarding) for every dated tenant")
chk(bool(_fo[_have].notna().all()), "every cohort year has a real first_onboarding date behind it")
_ca = pd.to_datetime(src.set_index(src["id"].astype(str))["created_at"], errors="coerce", utc=True)
_ca_years = set(_ca.dropna().dt.year.unique())
_co_years = set(T.loc[_have, "cohort_year"].astype(int).unique())
chk(_co_years - _ca_years, f"cohort years {sorted(_co_years)} span beyond the migration years "
                           f"{sorted(_ca_years)} — proving onboarding_date, not created_at, was used")
chk("migration timestamp" in str(S["date_field_used"]), "summary records why created_at is not used")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails:
    for f in fails: print("   -", f)
    sys.exit(1)
