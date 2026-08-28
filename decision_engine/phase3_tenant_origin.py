"""
TENANT-ORIGIN COMPOSITION (deterministic, offline, read-only on sources).

Resolves each tenant's HOME/ORIGIN state across the full 1,026-tenant history using a conservative
evidence hierarchy. Never guesses. Ambiguous evidence stays Unknown.

    1  explicit tenants.state          (normalised; invalid values rejected, not coerced)
    2  explicit state name inside permanent_address
    3  pincode -> India Post circle    (ambiguous prefixes excluded)
    4  unambiguous city gazetteer      (multi-state city names excluded)
    5  city column
    6  Unknown

Deliberately NOT used:
  - company_state / company_city — an employer's address is not the tenant's origin.
  - invoice presence — used nowhere; billing cannot imply geography.
  - Vishful's own property state — a tenant staying in Chennai is not thereby from Tamil Nadu.

Identity: tenants.id is the key. Multiple allotments are room/bed movement by the SAME tenant and
never create a duplicate.

Writes ONLY phase3_tenant_origin.csv, _summary.csv, _unresolved_reasons.csv. This is a composition
table, NOT a recommendation and NOT a demand signal — no recommendation is generated from it.
"""
from __future__ import annotations
import os, sys, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import loader

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "outputs")

STATES = ["Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh","Goa","Gujarat","Haryana",
"Himachal Pradesh","Jharkhand","Karnataka","Kerala","Madhya Pradesh","Maharashtra","Manipur","Meghalaya",
"Mizoram","Nagaland","Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana","Tripura",
"Uttar Pradesh","Uttarakhand","West Bengal","Delhi","Jammu and Kashmir","Ladakh","Puducherry","Chandigarh"]
ALIAS = {"tamilnadu":"Tamil Nadu","tamil nadu":"Tamil Nadu","uttarpradesh":"Uttar Pradesh",
"uttar pradesh":"Uttar Pradesh","andhrapradesh":"Andhra Pradesh","andhra pradesh":"Andhra Pradesh",
"madhyapradesh":"Madhya Pradesh","westbengal":"West Bengal","new delhi":"Delhi","delhi":"Delhi",
"orissa":"Odisha","pondicherry":"Puducherry"}

# India Post: first TWO digits identify the postal circle. Prefixes spanning more than one state are
# omitted so they resolve to Unknown rather than to a confidently wrong state.
PIN2 = {"11":"Delhi","12":"Haryana","13":"Haryana","14":"Punjab","15":"Punjab","16":"Punjab",
"17":"Himachal Pradesh","18":"Jammu and Kashmir","19":"Jammu and Kashmir",
"20":"Uttar Pradesh","21":"Uttar Pradesh","22":"Uttar Pradesh","23":"Uttar Pradesh",
"25":"Uttar Pradesh","27":"Uttar Pradesh","28":"Uttar Pradesh",
"30":"Rajasthan","31":"Rajasthan","32":"Rajasthan","33":"Rajasthan","34":"Rajasthan",
"36":"Gujarat","37":"Gujarat","38":"Gujarat","39":"Gujarat",
"40":"Maharashtra","41":"Maharashtra","42":"Maharashtra","43":"Maharashtra","44":"Maharashtra",
"45":"Madhya Pradesh","46":"Madhya Pradesh","47":"Madhya Pradesh","48":"Madhya Pradesh",
"49":"Chhattisgarh","50":"Telangana","51":"Andhra Pradesh","52":"Andhra Pradesh","53":"Andhra Pradesh",
"56":"Karnataka","57":"Karnataka","58":"Karnataka","59":"Karnataka",
"60":"Tamil Nadu","61":"Tamil Nadu","62":"Tamil Nadu","63":"Tamil Nadu","64":"Tamil Nadu","66":"Tamil Nadu",
"67":"Kerala","68":"Kerala","69":"Kerala",
"70":"West Bengal","71":"West Bengal","72":"West Bengal","73":"West Bengal","74":"West Bengal",
"75":"Odisha","76":"Odisha","77":"Odisha","78":"Assam",
"80":"Bihar","81":"Bihar","82":"Bihar","83":"Jharkhand","84":"Bihar","85":"Bihar"}
# Boundary cases the 2-digit circle rule cannot express — established by disagreement with the declared
# state during the audit. Left Unknown rather than resolved wrongly:
#   605xxx  Puducherry town inside the Tamil Nadu circle
#   673xxx  Mahe (Puducherry) inside the Kerala circle
#   24xxxx / 26xxxx  Uttarakhand kept UP-series prefixes after separation
AMBIG_PIN3 = {"605", "673"}
AMBIG_PIN2 = {"24","26","29","35","55","65","79","86","87","88","89"}

CITY = {
 "kolkata":"West Bengal","howrah":"West Bengal","siliguri":"West Bengal","kharagpur":"West Bengal","durgapur":"West Bengal","haldia":"West Bengal",
 "hyderabad":"Telangana","secunderabad":"Telangana","warangal":"Telangana","karimnagar":"Telangana",
 "bengaluru":"Karnataka","bangalore":"Karnataka","mysuru":"Karnataka","mysore":"Karnataka","mangaluru":"Karnataka","mangalore":"Karnataka","hubli":"Karnataka","udupi":"Karnataka","belgaum":"Karnataka",
 "chennai":"Tamil Nadu","coimbatore":"Tamil Nadu","madurai":"Tamil Nadu","tiruchirappalli":"Tamil Nadu","trichy":"Tamil Nadu","salem":"Tamil Nadu","erode":"Tamil Nadu","vellore":"Tamil Nadu","thanjavur":"Tamil Nadu","tirunelveli":"Tamil Nadu","tuticorin":"Tamil Nadu","dindigul":"Tamil Nadu","karur":"Tamil Nadu","namakkal":"Tamil Nadu","cuddalore":"Tamil Nadu","kanchipuram":"Tamil Nadu","tirupattur":"Tamil Nadu","uthiramerur":"Tamil Nadu","marakkanam":"Tamil Nadu","sivakasi":"Tamil Nadu","rajapalayam":"Tamil Nadu","nagercoil":"Tamil Nadu","hosur":"Tamil Nadu","tiruppur":"Tamil Nadu","tambaram":"Tamil Nadu",
 "mumbai":"Maharashtra","pune":"Maharashtra","nagpur":"Maharashtra","nashik":"Maharashtra","thane":"Maharashtra","kolhapur":"Maharashtra","solapur":"Maharashtra","amravati":"Maharashtra",
 "ahmedabad":"Gujarat","surat":"Gujarat","vadodara":"Gujarat","rajkot":"Gujarat","jamnagar":"Gujarat","bharuch":"Gujarat","gandhinagar":"Gujarat",
 "jaipur":"Rajasthan","jodhpur":"Rajasthan","udaipur":"Rajasthan","kota":"Rajasthan","ajmer":"Rajasthan","banswara":"Rajasthan","bikaner":"Rajasthan",
 "lucknow":"Uttar Pradesh","kanpur":"Uttar Pradesh","varanasi":"Uttar Pradesh","agra":"Uttar Pradesh","meerut":"Uttar Pradesh","ghaziabad":"Uttar Pradesh","noida":"Uttar Pradesh","prayagraj":"Uttar Pradesh","allahabad":"Uttar Pradesh","aligarh":"Uttar Pradesh","unnao":"Uttar Pradesh","gorakhpur":"Uttar Pradesh","bareilly":"Uttar Pradesh",
 "patna":"Bihar","gaya":"Bihar","madhubani":"Bihar","muzaffarpur":"Bihar","bhagalpur":"Bihar","darbhanga":"Bihar",
 "bhopal":"Madhya Pradesh","indore":"Madhya Pradesh","gwalior":"Madhya Pradesh","jabalpur":"Madhya Pradesh","ujjain":"Madhya Pradesh","khandwa":"Madhya Pradesh","burhanpur":"Madhya Pradesh","gadarwara":"Madhya Pradesh",
 "raipur":"Chhattisgarh","bhilai":"Chhattisgarh","durg":"Chhattisgarh",
 "bhubaneswar":"Odisha","cuttack":"Odisha","rourkela":"Odisha","puri":"Odisha",
 "ranchi":"Jharkhand","jamshedpur":"Jharkhand","dhanbad":"Jharkhand","adityapur":"Jharkhand","bokaro":"Jharkhand",
 "guwahati":"Assam","dibrugarh":"Assam","silchar":"Assam","jorhat":"Assam",
 "thiruvananthapuram":"Kerala","trivandrum":"Kerala","kochi":"Kerala","ernakulam":"Kerala","thrissur":"Kerala","kozhikode":"Kerala","calicut":"Kerala","kollam":"Kerala","kottayam":"Kerala","alappuzha":"Kerala","palakkad":"Kerala","kannur":"Kerala","malappuram":"Kerala",
 "visakhapatnam":"Andhra Pradesh","vijayawada":"Andhra Pradesh","guntur":"Andhra Pradesh","nellore":"Andhra Pradesh","tirupati":"Andhra Pradesh","rajahmundry":"Andhra Pradesh","kakinada":"Andhra Pradesh","kurnool":"Andhra Pradesh","anantapur":"Andhra Pradesh",
 "chandigarh":"Chandigarh","ludhiana":"Punjab","amritsar":"Punjab","jalandhar":"Punjab","patiala":"Punjab",
 "dehradun":"Uttarakhand","haridwar":"Uttarakhand","roorkee":"Uttarakhand","nainital":"Uttarakhand",
 "gurgaon":"Haryana","gurugram":"Haryana","faridabad":"Haryana","panipat":"Haryana","hisar":"Haryana","bhiwani":"Haryana","karnal":"Haryana",
 "shimla":"Himachal Pradesh","manali":"Himachal Pradesh","panaji":"Goa","margao":"Goa",
 "imphal":"Manipur","shillong":"Meghalaya","aizawl":"Mizoram","agartala":"Tripura","itanagar":"Arunachal Pradesh","kohima":"Nagaland","gangtok":"Sikkim",
 "puducherry":"Puducherry","pondicherry":"Puducherry"}

STATE_RX = {st: re.compile(r"\b" + r"\s*".join(map(re.escape, st.lower().split())) + r"\b") for st in STATES}
STATE_RX["Tamil Nadu"] = re.compile(r"\btamil\s*nadu\b|\btamilnadu\b")
STATE_RX["Uttar Pradesh"] = re.compile(r"\buttar\s*pradesh\b|\buttarpradesh\b")
STATE_RX["Andhra Pradesh"] = re.compile(r"\bandhra\s*pradesh\b|\bandhrapradesh\b")
STATE_RX["West Bengal"] = re.compile(r"\bwest\s*bengal\b")
STATE_RX["Delhi"] = re.compile(r"\bnew\s*delhi\b|\bdelhi\b")
CITY_RX = {c: re.compile(r"\b" + re.escape(c) + r"\b") for c in CITY}
PIN_RX = re.compile(r"\b([1-9]\d{5})\b")


def norm_state(v):
    if not isinstance(v, str): return None
    s = re.sub(r"[^a-z ]", " ", v.strip().lower()); s = re.sub(r"\s+", " ", s).strip()
    if s in ALIAS: return ALIAS[s]
    for st in STATES:
        if s == st.lower(): return st
    return None

def state_in_text(s):
    f = sorted({st for st, rx in STATE_RX.items() if rx.search(s)})
    return (f[0] if len(f) == 1 else ("AMBIGUOUS" if f else None))

def city_in_text(s):
    f = sorted({CITY[c] for c, rx in CITY_RX.items() if rx.search(s)})
    return (f[0] if len(f) == 1 else ("AMBIGUOUS" if f else None))

def pin_state(p):
    if not isinstance(p, str) or not re.fullmatch(r"[1-9]\d{5}", p): return None
    if p[:3] in AMBIG_PIN3 or p[:2] in AMBIG_PIN2: return None
    return PIN2.get(p[:2])


def _confirmed_map():
    """tenant_id -> (state, city, pincode) from the append-only tenant-confirmed evidence store.
    Direct tenant confirmation is the STRONGEST evidence tier — stronger than any field or address
    inference — because it is current, tenant-supplied, and collected for exactly this purpose.
    Returns {} if the store does not exist yet (no confirmations recorded) or is empty."""
    try:
        import phase3_tenant_location_confirm as TLC
    except Exception:
        return {}
    try:
        latest = TLC.latest_confirmations()
    except Exception:
        return {}
    if latest is None or len(latest) == 0:
        return {}
    return {str(r["tenant_id"]): (r["confirmed_state"], r["confirmed_city"], r["confirmed_pincode"])
            for _, r in latest.iterrows()}


def main():
    D, _ = loader.load_all()
    t = D["tenants"].copy()
    al = D["tenant_allotments"]
    confirmed = _confirmed_map()

    addr = t["permanent_address"].fillna("").astype(str).str.lower()
    t["src_declared"] = t["state"].map(norm_state)
    raw_state = t["state"].dropna().astype(str).str.strip()
    invalid_states = sorted({v for v in raw_state if norm_state(v) is None})

    _sa = addr.map(state_in_text)
    amb_state = int((_sa == "AMBIGUOUS").sum())
    t["src_address"] = _sa.where(_sa != "AMBIGUOUS")

    pc = t["pincode"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    t["pin_col"] = pc.where(pc.str.fullmatch(r"[1-9]\d{5}", na=False))
    t["pin_addr"] = t["permanent_address"].map(
        lambda s: (PIN_RX.findall(s)[-1] if isinstance(s, str) and PIN_RX.findall(s) else None))
    t["pin_used"] = t["pin_col"].fillna(t["pin_addr"])
    t["src_pincode"] = t["pin_used"].map(pin_state)
    amb_pin = int((t["pin_used"].notna() & t["src_pincode"].isna()).sum())

    _ca = addr.map(city_in_text)
    amb_city = int((_ca == "AMBIGUOUS").sum())
    t["src_city_addr"] = _ca.where(_ca != "AMBIGUOUS")
    t["src_city_col"] = t["city"].fillna("").astype(str).str.lower().str.strip().map(lambda s: CITY.get(s))

    TIERS = [("explicit_state_field", "src_declared"), ("state_in_address", "src_address"),
             ("pincode_circle", "src_pincode"), ("city_gazetteer_address", "src_city_addr"),
             ("city_column", "src_city_col")]

    # cross-source agreement — a resolution is only accepted when no other populated source contradicts it
    conflicts = []
    states, sources, agree_n, conf_city, conf_pin = [], [], [], [], []
    for _, r in t.iterrows():
        tid = str(r["id"])
        if tid in confirmed:
            # Tier 0 — direct tenant confirmation. Short-circuits every derived tier below: a tenant
            # stating their own state is stronger evidence than any inference from a stale/incorrect
            # stored field, and it OVERRIDES even a property-address record (the confirmation is the
            # correction). Never re-evaluated against the weaker tiers for "conflict".
            cs, cc, cp = confirmed[tid]
            states.append(cs); sources.append("tenant_confirmed"); agree_n.append(1)
            conf_city.append(cc); conf_pin.append(cp)
            continue
        vals = {lbl: r[col] for lbl, col in TIERS if isinstance(r[col], str) and r[col]}
        distinct = set(vals.values())
        conf_city.append(None); conf_pin.append(None)
        if not vals:
            states.append(None); sources.append("unknown"); agree_n.append(0); continue
        if len(distinct) > 1:
            conflicts.append(dict(tenant_id=r["id"], full_name=r["full_name"], **vals))
            states.append(None); sources.append("conflicting_evidence"); agree_n.append(len(vals))
            continue
        chosen_src = next(lbl for lbl, col in TIERS if isinstance(r[col], str) and r[col])
        states.append(next(iter(distinct))); sources.append(chosen_src); agree_n.append(len(vals))
    t["origin_state"] = states
    t["resolution_source"] = sources
    t["agreeing_sources"] = agree_n
    t["confirmed_city"] = conf_city
    t["confirmed_pincode"] = conf_pin

    t["has_created_at"] = pd.to_datetime(t["created_at"], errors="coerce", utc=True).notna()
    t["kyc_completed_flag"] = t["kyc_completed"].astype(str).str.lower().isin(["true", "1"])
    t["allotment_count"] = t["id"].map(al.groupby("tenant_id").size()).fillna(0).astype(int)

    # ---- cohort dating -------------------------------------------------------------------------
    # tenants.created_at is a MIGRATION timestamp (every row postdates the March-2026 data load) and
    # must never be used as a business date. tenant_allotments.onboarding_date is the real onboarding
    # date and is populated for every allotment. First onboarding per tenant defines the cohort.
    alx = al.copy()
    alx["_onb"] = pd.to_datetime(alx["onboarding_date"], errors="coerce", utc=True)
    first_onb = alx.dropna(subset=["_onb"]).groupby("tenant_id")["_onb"].min()
    t["first_onboarding"] = t["id"].map(first_onb)
    t["cohort_year"] = t["first_onboarding"].dt.year
    # CURRENT = holds at least one allotment with no recorded exit. A strict SUBSET of the historical
    # population, never a separate group — the two views are reported separately, never summed.
    active_ids = set(al.loc[al["actual_exit_date"].isna(), "tenant_id"].dropna().astype(str))
    t["is_current"] = t["id"].astype(str).isin(active_ids)
    t["in_historical_population"] = t["first_onboarding"].notna()

    COLS = ["id", "full_name", "origin_state", "resolution_source", "agreeing_sources",
            "src_declared", "src_address", "src_pincode", "src_city_addr", "src_city_col",
            "pin_used", "city", "confirmed_city", "confirmed_pincode",
            "has_created_at", "kyc_completed_flag", "allotment_count",
            "staying_status", "first_onboarding", "cohort_year", "is_current",
            "in_historical_population"]
    out = t[COLS].rename(columns={"id": "tenant_id"})
    out.to_csv(os.path.join(OUT, "phase3_tenant_origin.csv"), index=False)

    # ---- cohort views: historical (2019 onward) and current, reported SEPARATELY ----------------
    HIST = out[out["in_historical_population"]]
    CURR = out[out["is_current"]]

    def _view(df, label, fname):
        r = df[df["origin_state"].notna()]
        n_all, n_res = len(df), len(r)
        vc = r["origin_state"].value_counts()
        rws = []
        for rank, (st, n) in enumerate(vc.items(), 1):
            rws.append(dict(rank=rank, state=st, tenants=int(n),
                            pct_of_resolved=round(100 * n / n_res, 1) if n_res else 0.0,
                            pct_of_population=round(100 * n / n_all, 1) if n_all else 0.0,
                            denominator_resolved=n_res, denominator_population=n_all,
                            population=label))
        # Unknown is a visible row, never dropped and never treated as zero
        rws.append(dict(rank=None, state="Unknown", tenants=int(n_all - n_res),
                        pct_of_resolved=None,
                        pct_of_population=round(100 * (n_all - n_res) / n_all, 1) if n_all else 0.0,
                        denominator_resolved=n_res, denominator_population=n_all, population=label))
        pd.DataFrame(rws).to_csv(os.path.join(OUT, fname), index=False)
        return n_all, n_res

    h_all, h_res = _view(HIST, "historical_2019_onward", "phase3_tenant_origin_historical.csv")
    c_all, c_res = _view(CURR, "current_active", "phase3_tenant_origin_current.csv")

    # ---- year-wise view, with per-year coverage so thin years cannot be read as a trend ---------
    yr_rows = []
    for y in sorted(HIST["cohort_year"].dropna().unique()):
        sub = HIST[HIST["cohort_year"] == y]
        rsub = sub[sub["origin_state"].notna()]
        top = rsub["origin_state"].value_counts()
        yr_rows.append(dict(cohort_year=int(y), tenants_onboarded=len(sub),
                            resolved=len(rsub), unknown=len(sub) - len(rsub),
                            coverage_pct=round(100 * len(rsub) / len(sub), 1) if len(sub) else 0.0,
                            top_state=(top.index[0] if len(top) else None),
                            top_state_tenants=(int(top.iloc[0]) if len(top) else 0),
                            top_state_pct_of_resolved=(round(100 * top.iloc[0] / len(rsub), 1) if len(rsub) else None),
                            coverage_caveat=("sufficient" if len(rsub) >= 50 else
                                             "thin — per-year share not interpretable")))
    pd.DataFrame(yr_rows).to_csv(os.path.join(OUT, "phase3_tenant_origin_by_year.csv"), index=False)

    res = out[out["origin_state"].notna()]
    N, R = len(out), len(res)
    dist = res["origin_state"].value_counts()
    rows = []
    for st, n in dist.items():
        sub = res[res["origin_state"] == st]
        rows.append(dict(state=st, resolved_tenants=int(n),
                         pct_of_resolved=round(100 * n / R, 1),
                         pct_of_all_tenants=round(100 * n / N, 1),
                         kyc_cohort=int(sub["kyc_completed_flag"].sum()),
                         non_kyc=int((~sub["kyc_completed_flag"]).sum()),
                         sources=";".join(f"{k}:{v}" for k, v in
                                          sub["resolution_source"].value_counts().items())))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "phase3_tenant_origin_distribution.csv"), index=False)

    unres = out[out["origin_state"].isna()]["resolution_source"].value_counts().to_dict()
    pd.DataFrame([dict(reason=k, tenants=int(v)) for k, v in unres.items()]
                 ).to_csv(os.path.join(OUT, "phase3_tenant_origin_unresolved_reasons.csv"), index=False)

    south = ["Tamil Nadu","Kerala","Karnataka","Andhra Pradesh","Telangana","Puducherry"]
    summary = [
        ("total_tenants", N),
        ("distinct_tenant_ids", int(out["tenant_id"].nunique())),
        ("resolved_tenants", R),
        ("unknown_tenants", N - R),
        ("pct_resolved_of_all", round(100 * R / N, 1)),
        ("denominator_note", "all percentages in the distribution are of RESOLVED tenants; "
                             f"{N-R} of {N} tenants ({round(100*(N-R)/N,1)}%) remain Unknown"),
        ("by_source", str(res["resolution_source"].value_counts().to_dict())),
        ("conflicting_evidence_left_unknown", len(conflicts)),
        ("ambiguous_state_text_left_unknown", amb_state),
        ("ambiguous_city_left_unknown", amb_city),
        ("pincode_present_but_prefix_ambiguous", amb_pin),
        ("invalid_state_values_rejected", str(invalid_states)),
        ("south_india_pct_of_resolved", round(100 * dist.reindex(south).fillna(0).sum() / R, 1)),
        # ---- historical (2019 onward) and current views, kept strictly separate ----
        ("historical_population", h_all),
        ("historical_resolved", h_res),
        ("historical_unknown", h_all - h_res),
        ("historical_pct_resolved", round(100 * h_res / h_all, 1) if h_all else 0.0),
        ("historical_date_range", (f"{HIST['first_onboarding'].min():%Y-%m-%d} .. "
                                   f"{HIST['first_onboarding'].max():%Y-%m-%d}") if h_all else "n/a"),
        ("historical_south_pct_of_resolved",
         round(100 * HIST[HIST["origin_state"].isin(south)].shape[0] / h_res, 1) if h_res else 0.0),
        ("current_population", c_all),
        ("current_resolved", c_res),
        ("current_unknown", c_all - c_res),
        ("current_pct_resolved", round(100 * c_res / c_all, 1) if c_all else 0.0),
        ("current_south_pct_of_resolved",
         round(100 * CURR[CURR["origin_state"].isin(south)].shape[0] / c_res, 1) if c_res else 0.0),
        ("current_is_subset_of_historical", bool(set(CURR["tenant_id"]).issubset(set(HIST["tenant_id"])))),
        ("view_separation_note", "historical and current are reported as SEPARATE views over the same "
                                 "tenant base; current is a strict SUBSET of historical and the two "
                                 "must never be summed or mixed into one figure"),
        ("excluded_no_onboarding_date", N - h_all),
        ("date_field_used", "tenant_allotments.onboarding_date (business date). tenants.created_at is a "
                            "migration timestamp — every row postdates the data load — and is NEVER used "
                            "as a cohort date"),
        ("year_trend_claim", "NOT SUPPORTED — per-year coverage varies widely; year-wise counts are "
                             "published with a coverage column so thin years cannot be read as a trend"),
        ("kyc_cohort_resolved", int(res["kyc_completed_flag"].sum())),
        ("non_kyc_resolved", int((~res["kyc_completed_flag"]).sum())),
        ("tenants_with_created_at", int(out["has_created_at"].sum())),
        ("time_series_possible", "NO — created_at exists for only "
                                 f"{int(out['has_created_at'].sum())} tenants, all in a single year; "
                                 "historical state composition by year cannot be established"),
        ("tenants_with_multiple_allotments", int((out["allotment_count"] > 1).sum())),
        ("identity_note", "tenant_id is the identity key; multiple allotments are room/bed movement "
                          "by the same tenant and never create a duplicate"),
        ("company_address_used", "NO — an employer address is not the tenant's origin"),
        ("invoice_used_for_geography", "NO — billing presence cannot imply geography"),
        ("interpretation", "tenant-origin composition only; NOT demand, NOT a feeder-market claim, "
                           "NOT a forecast. Supports language/content decisions; the resolved sample "
                           "does not justify city or campus targeting."),
    ]
    pd.DataFrame(summary, columns=["metric", "value"]).to_csv(
        os.path.join(OUT, "phase3_tenant_origin_summary.csv"), index=False)

    print("PHASE-3 TENANT ORIGIN COMPOSITION:")
    for k, v in summary: print(f"  {k}: {v}")

    def _show(df, label, n_all, n_res):
        r = df[df["origin_state"].notna()]
        print(f"\n  === {label} ===  population {n_all} | resolved {n_res} "
              f"({100*n_res/n_all:.1f}%) | Unknown {n_all-n_res}")
        print(f"  {'#':>2} {'state':22}{'n':>5}{'%resolved':>11}{'%population':>13}")
        for i, (st, n) in enumerate(r["origin_state"].value_counts().items(), 1):
            print(f"  {i:2} {st:22}{n:5}{100*n/n_res:10.1f}%{100*n/n_all:12.1f}%")
        print(f"  {'--':>2} {'Unknown':22}{n_all-n_res:5}{'—':>11}{100*(n_all-n_res)/n_all:12.1f}%")

    _show(HIST, "HISTORICAL 2019 onward (all tenants ever onboarded)", h_all, h_res)
    _show(CURR, "CURRENT active tenants (subset of historical)", c_all, c_res)
    print("\n  === BY COHORT YEAR (coverage shown; thin years are not interpretable) ===")
    print(f"  {'year':>6}{'onboarded':>11}{'resolved':>10}{'coverage':>10}  top state")
    for r in yr_rows:
        print(f"  {r['cohort_year']:6}{r['tenants_onboarded']:11}{r['resolved']:10}"
              f"{r['coverage_pct']:9.1f}%  {r['top_state'] or '—'} "
              f"({r['top_state_pct_of_resolved'] or 0:.1f}% of resolved) [{r['coverage_caveat']}]")


if __name__ == "__main__":
    main()
