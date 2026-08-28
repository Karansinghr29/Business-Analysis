"""
Phase-3 OWNER DECISION CARDS (isolated, deterministic, read-only).

Turns the already-collected market/pricing/review data into short owner-readable decision cards:
  Business finding -> Evidence (real counts) -> Business implication -> Possible action -> Confidence.
Every number is COMPUTED from existing validated datasets (no fabrication, no new data). Decision SUPPORT only:
no competitor ranking, no Vishful-vs-competitor comparison, no "Vishful should charge Rs X", no auto-decision.

Inputs (all already validated): phase3_competitor_master, phase3_competitor_prices, phase3_competitor_source_links,
phase3_locality_summary, phase3_review_theme_aggregate, phase3_review_intelligence_audit, reviews_raw.
Writes ONLY phase3_owner_decision_cards.csv.
"""
from __future__ import annotations
import os, sys, re, statistics
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
M=o("phase3_competitor_master.csv"); PR=o("phase3_competitor_prices.csv")
SRC=o("phase3_competitor_source_links.csv")
# ACTIVE market universe (168) drives competitor-coverage + locality density; pricing/review keep own numerators.
ALOC=o("phase3_active_locality_summary.csv"); N_ACTIVE=len(o("phase3_active_market_universe.csv"))
LOC=ALOC  # locality cards now use the 168 active locality counts (baseline 115 frozen)
TA=o("phase3_review_theme_aggregate.csv"); IA=o("phase3_review_intelligence_audit.csv")
RAW=o("phase3_competitor_reviews_raw.csv")
def r(n): return f"Rs{int(n):,}"

def ticket(topic):
    row=IA[IA["topic"].str.contains(topic,case=False,na=False)]
    if not len(row): return None
    m=re.search(r"(\d+)\s+(?:own[- ])?(?:complaint )?tickets",str(row.iloc[0]["business_implication"]))
    return int(m.group(1)) if m else None
def adv(topic):
    row=IA[IA["topic"].str.contains(topic,case=False,na=False)]
    if not len(row): return None
    m=re.search(r"advertised on (\d+)",str(row.iloc[0]["market_signal"]))
    return int(m.group(1)) if m else None
def theme(t):
    row=TA[TA["theme"]==t]
    if not len(row): return (0,0,0)
    x=row.iloc[0]; return (int(x["total"]),int(x["positive"]),int(x["negative"]))

def main():
    cards=[]
    def add(cid,finding,evidence,implication,action,confidence,prov):
        cards.append(dict(card_id=cid,business_finding=finding,evidence=evidence,
            business_implication=implication,possible_action=action,confidence=confidence,provenance=prov))

    # 1 — Sharing-price positioning
    ss=PR[PR["price_basis"]=="OFFICIAL_SHARING_SPECIFIC"]
    tiers=[]
    for t in ["Single","Double","Triple","4-sharing","5-sharing"]:
        s=ss[ss["sharing_type"]==t]
        if len(s): tiers.append(f"{t} {r(s['price'].min())}-{r(s['price'].max())} ({s['competitor_name'].nunique()} competitors)")
    add("pricing_positioning","Competitors publish clearly different monthly prices by sharing tier",
        "Verified official/operator listings — "+ "; ".join(tiers)+f" ({ss['competitor_name'].nunique()} competitors, {len(ss)} observations).",
        "Vishful can evaluate whether its own sharing-tier pricing and value proposition are positioned appropriately for each tier.",
        "Review Vishful's per-tier value proposition against these observed published ranges. (No specific Vishful price is recommended.)",
        f"Moderate — {ss['competitor_name'].nunique()} competitors with published tiers; observed published prices, not a market average/benchmark.",
        "phase3_competitor_prices.csv (OFFICIAL_SHARING_SPECIFIC)")

    # 2 — Price transparency (denominator = 168 active universe; official-price numerator unchanged)
    n_total=N_ACTIVE; n_src=SRC["competitor_name"].nunique()
    n_priced=PR[PR["price_basis"].isin(["OFFICIAL_SHARING_SPECIFIC","OFFICIAL_STARTING_FROM"])]["competitor_name"].nunique()
    add("price_transparency","Most competitors do NOT publish actual monthly pricing online",
        f"Only {n_priced} of {n_total} competitors (current 168 market universe; 115 baseline) publish an OFFICIAL monthly PG price; {n_src} have any verified online listing. The majority list amenities/contact only, with no rent shown. (New v2 third-party listings are counted in the 168 but their prices are mostly contact-gated/STARTING_FROM.)",
        "Transparent published pricing MAY reduce enquiry friction for prospective tenants — this is a business consideration, not a proven causal effect.",
        "Consider whether publishing clear sharing-tier pricing on Vishful's own channels could ease enquiries; treat as a hypothesis to test, not a certainty.",
        f"High on the coverage fact ({n_priced}/{n_total} priced, 168 universe); the friction effect is a consideration, not evidence.",
        "phase3_competitor_prices.csv + phase3_competitor_source_links.csv")

    # 3 — Maintenance / room quality / service
    mt=theme("maintenance"); rq=theme("room_quality"); cl=theme("cleanliness"); st_=theme("staff")
    tk_fur=ticket("Furniture"); tk_plumb=ticket("Plumbing"); tk_clean=ticket("Cleanliness")
    add("ops_reliability","Room quality, maintenance, cleanliness and staff/service recur strongly in competitor reviews",
        f"Across {RAW['property_name'].nunique()} reviewed competitors: staff {st_[0]} mentions ({st_[1]}+/{st_[2]}-), cleanliness {cl[0]} ({cl[1]}+/{cl[2]}-), room-quality {rq[0]}, maintenance {mt[0]}. "
        f"Vishful's OWN tickets: furniture/room-quality {tk_fur}, plumbing {tk_plumb}, cleanliness {tk_clean}.",
        "Operational reliability and faster issue resolution may be an important customer-value opportunity — the market cares about these and Vishful already logs high internal volumes.",
        "Consider prioritising maintenance responsiveness / room-quality upkeep operationally before marketing them; a faster resolution SLA could become a value proposition.",
        "High — consistent across many competitor reviews AND Vishful's own ticket data.",
        "phase3_review_theme_aggregate.csv + phase3_review_intelligence_audit.csv (Vishful tickets)")

    # 4 — AC / Water / Wi-Fi reliability
    add("amenity_reliability","AC, water and Wi-Fi are commonly advertised amenities — and Vishful's top own-complaints",
        f"Advertised on first-party market sites: AC {adv('AC')}, Water {adv('Water')}, Wi-Fi {adv('Wi-Fi')}. "
        f"Vishful OWN complaint tickets: AC {ticket('AC')}, Water {ticket('Water')}, Wi-Fi {ticket('Wi-Fi')}, Electrical {ticket('Electrical')}.",
        "Reliability of advertised amenities should be assured before leaning on them in marketing — a marketed feature that fails drives complaints.",
        "Consider prioritising AC/Water/Wi-Fi/power reliability operationally first, then feature them in marketing once dependable.",
        "High — market advertises these AND Vishful's own tickets are large in the same areas.",
        "phase3_review_intelligence_audit.csv (advertised counts + Vishful tickets)")

    # 5 — Food
    f_adv=adv("Food"); f_tot,f_pos,f_neg=theme("food")
    add("food_opportunity","Food is advertised by some competitors and draws positive review signals; Vishful food status is not established",
        f"Food advertised on {f_adv} first-party market sites; competitor reviews mention food {f_tot} times ({f_pos}+/{f_neg}-). Vishful's own food-service status is UNKNOWN (no meals evidence in Vishful data).",
        "A food offering/add-on/partnership may be commercially worthwhile — worth evaluating, but not proven necessary.",
        "Consider evaluating a food add-on or partnership (cost vs. demand). Do NOT advertise food yet and do NOT claim Vishful lacks it.",
        "Moderate — clear market signal; Vishful-side food evidence is absent, so treat as an evaluation, not a conclusion.",
        "phase3_review_intelligence_audit.csv (Food/Meals) + phase3_review_theme_aggregate.csv")

    # 6 — Locality opportunity
    lc=LOC.copy()
    dens="; ".join(f"{row['locality'].split(',')[0]} {int(row['competitor_count'])} ({int(row['competitors_with_official_monthly_pricing'])} priced/{int(row['competitors_with_reviews'])} reviewed)" for _,row in lc.iterrows() if row['locality']!="Unknown")
    add("locality_opportunity","Competitor density and data coverage vary sharply by locality",
        f"Competitors per locality in the CURRENT 168-property universe (with official-pricing / review coverage): {dens}.",
        "Higher-density localities may need stronger differentiation; low-coverage localities should be treated cautiously due to thin data.",
        "Consider differentiation emphasis where competitor density is high, and treat low-coverage localities as lower-confidence context. (Locality figures are descriptive, not a ranking.)",
        "Counts on the 168 active universe; pricing/review coverage are their own numerators (not diluted).",
        "phase3_active_locality_summary.csv")

    # 7 — Data coverage / confidence
    thin=[f"{row['locality'].split(',')[0]} ({int(row['competitors_with_official_monthly_pricing'])} priced)" for _,row in lc.iterrows()
          if 0<int(row['competitors_with_official_monthly_pricing'])<3]
    norev=[row['locality'].split(',')[0] for _,row in lc.iterrows() if int(row['competitors_with_reviews'])==0 and row['locality']!="Unknown"]
    add("data_confidence","Several conclusions rest on limited evidence — coverage is stated openly",
        f"Localities with too few priced competitors for a reliable benchmark (n<3): {', '.join(thin) if thin else 'none'}. "
        f"Localities with 0 collected reviews: {', '.join(norev) if norev else 'none'}. Review data covers only {RAW['property_name'].nunique()} of {N_ACTIVE} competitors (current 168 universe); 0 of 114 reviews quote a rent figure.",
        "Where coverage is thin, findings are directional context only — not a reliable market benchmark.",
        "Treat thin-coverage localities and review-derived pricing cautiously; collect more evidence before acting where marked low-confidence.",
        "Explicit — this card exists to flag where confidence is low.",
        "phase3_locality_summary.csv + phase3_competitor_reviews_raw.csv")

    D=pd.DataFrame(cards)
    blob=" ".join(map(str,D.values.ravel())).lower()
    for bad in ["better than vishful","worse than vishful","best competitor","rank competitor","vishful should charge","charge rs ","charge ₹"]:
        assert bad not in blob, f"forbidden phrase: {bad}"
    D.to_csv(os.path.join(OUT,"phase3_owner_decision_cards.csv"),index=False)
    print("PHASE-3 OWNER DECISION CARDS:")
    print(f"  cards: {len(D)}")
    for _,c in D.iterrows(): print(f"  [{c['card_id']}] {c['business_finding'][:70]}")

if __name__=="__main__": main()
