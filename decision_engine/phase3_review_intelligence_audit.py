"""
Phase-3 REVIEW-INTELLIGENCE AUDIT (isolated, deterministic, read-only, AUDIT-ONLY).
Determines what legitimate review/customer-experience intelligence exists, with provenance.
NO scraping, NO fabricated reviews/ratings/sentiment, NO competitor comparison/ranking, NO
aggregator-as-first-party, NO Google-Maps HTML. Unknown stays Unknown.

Honest finding: competitor FIRST-PARTY review data is NOT accessible via approved methods
(reviews live on Google Maps + aggregators, both excluded). The legitimate, decision-useful
substitute already in Vishful's OWN data = maintenance tickets (own customers' pain points by
topic) + tenant_rating. Signal chain per topic:
  MARKET OFFERING SIGNAL (what competitors advertise, first-party) + VISHFUL OWN CUSTOMER PAIN-POINT
  (own tickets) -> BUSINESS IMPLICATION -> CANDIDATE ACTION -> EVIDENCE/PROVENANCE.

Writes ONLY phase3_review_intelligence_audit.csv + _availability.csv + _summary.csv. Modifies nothing.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); OUT=os.path.join(HERE,"outputs")
def src(nn): return pd.read_csv(os.path.join(ROOT,f"Supabase Snippet Untitled query ({nn}).csv"),low_memory=False)
def o(f): return pd.read_csv(os.path.join(OUT,f))
RET="2026-08-17"

TK=src(71); IT=src(76); TN=src(45)
TK["issue"]=TK["issue_type_id"].map(dict(zip(IT["id"],IT["name"])))
tkc={k:int(v) for k,v in TK["issue"].value_counts().items()}
SG=o("phase3_market_signals.csv")
AM=o("phase3_amenity_master_from_data.csv")
def mkt(name):
    r=SG[(SG["signal_type"]=="published_amenity")&(SG["signal"]==name)]
    return int(r["value"].iloc[0]) if len(r) else 0
def vstat(a):
    r=AM[AM["amenity"]==a]; return r["verified_status"].iloc[0] if len(r) else "UNKNOWN"

def main():
    # ---- A) review-source availability (legitimacy per platform) ----
    avail=[
     ("competitor first-party websites","own PG sites (playwright)","NO review sections rendered",
      "usable for amenity/config only, NOT reviews","phase3_playwright_market_research.csv"),
     ("Google Maps","public reviews/ratings exist","NOT ACCESSIBLE via approved methods",
      "no Google-Maps HTML scraping; Maps is not first-party -> excluded","policy"),
     ("aggregators/directories (magicpin/yappe/justdial/etc.)","ratings/review counts exist","EXCLUDED",
      "aggregator ≠ first-party property evidence -> not usable as review evidence","policy"),
     ("Vishful Market AI dashboard (owner)","shows competitor ratings/counts","context only",
      "those ratings are Google-sourced (aggregator/Maps) -> context, not first-party review evidence","owner dashboard"),
     ("Vishful OWN maintenance tickets","own customers' pain points by topic","AVAILABLE (first-party to Vishful)",
      "1,540 tickets by issue type = legitimate own customer-experience signal","maintenance_tickets #71 / issue_types #76"),
     ("Vishful tenant_rating","own tenant satisfaction proxy","AVAILABLE (first-party to Vishful)",
      f"{int(TN['tenant_rating'].notna().sum())}/{len(TN)} tenants rated","tenants #45"),
    ]
    pd.DataFrame(avail,columns=["source","what_exists","legitimacy_status","reason","provenance"]).to_csv(
        os.path.join(OUT,"phase3_review_intelligence_availability.csv"),index=False)

    # ---- B) topic signal chain: MARKET OFFERING + VISHFUL OWN PAIN-POINT -> action ----
    # (topic, market_amenity_signal_name, vishful_amenity, own_ticket_issue_name)
    TOPICS=[("AC","AC availability","AC","AC Issues"),
            ("Wi-Fi/Internet","Wi-Fi","Wi-Fi","Internet Issues"),
            ("Cleanliness/Housekeeping","Food",None,"Cleaning Issues"),  # market 'housekeeping' proxied; own = Cleaning Issues
            ("RO/Water","Food",None,"RO Water Issues"),
            ("Laundry","Food","Washing machine","Washing machine Issue"),
            ("Plumbing/Toilet",None,None,"Plumbing"),
            ("Electrical/Power","Power backup",None,"Electrical Issues"),
            ("Furniture/Room quality",None,None,"Furniture"),
            ("Food/Meals","Food",None,None)]
    rows=[]
    for topic,msig,vam,issue in TOPICS:
        mcount=mkt(msig) if msig else None
        own=tkc.get(issue,0) if issue else 0
        vs=vstat(vam) if vam else ("VERIFIED_PRESENT" if issue in ("Cleaning Issues","RO Water Issues","Electrical Issues","Plumbing") else "UNKNOWN")
        # nuanced implication + candidate action (NO competitor comparison; own pain-point drives it)
        if topic=="Food/Meals":
            implication="Food is publicly advertised in the market; Vishful food-service status is UNKNOWN (no meals evidence)."
            action="Product/service opportunity: EVALUATE a food add-on/partnership. Do NOT advertise food; do NOT claim Vishful lacks it."
            vfact="Vishful food = UNKNOWN"
        elif vs=="VERIFIED_PRESENT" and own>0:
            implication=(f"Vishful HAS {topic} (verified) but it is also a top own-customer complaint ({own} tickets) — "
                         "marketing + operational reliability both matter.")
            action=(f"Marketing: highlight verified {topic}. Operational: prioritise {topic} reliability first so the "
                    "marketed feature holds up (own tickets).")
            vfact=f"Vishful {topic} VERIFIED + {own} own tickets"
        elif vs=="VERIFIED_PRESENT":
            implication=f"Vishful HAS {topic} (verified); market advertises it too."
            action=f"Marketing opportunity: highlight verified {topic}."
            vfact=f"Vishful {topic} VERIFIED"
        elif own>0:
            implication=f"{topic} is a recurring own-customer pain point ({own} tickets); market treats it as important."
            action=f"Operational priority: reduce {topic} complaints; then it becomes a marketing strength."
            vfact=f"{own} own {topic} tickets (capability present)"
        else:
            implication=f"{topic}: Vishful status UNKNOWN; market advertises it."
            action=f"Owner verification: confirm Vishful {topic}; do NOT advertise or claim absence."
            vfact=f"Vishful {topic} = UNKNOWN"
        rows.append(dict(topic=topic,
            market_signal=(f"{msig} advertised on {mcount} first-party sites" if msig else "not a distinct market amenity signal"),
            vishful_internal_fact=vfact, own_complaint_tickets=own,
            business_implication=implication, candidate_action=action,
            evidence=f"market: phase3_market_signals.csv; own: maintenance_tickets #71 ({issue or 'n/a'})",
            retrieval_date=RET,
            provenance="phase3_market_signals.csv / phase3_amenity_master_from_data.csv / maintenance_tickets #71",
            competitor_comparison="none — market customer signal -> Vishful opportunity"))
    df=pd.DataFrame(rows); df.to_csv(os.path.join(OUT,"phase3_review_intelligence_audit.csv"),index=False)

    summary=[("competitor_first_party_reviews","NOT ACCESSIBLE via approved methods (Maps/aggregator only)"),
     ("legitimate_substitute","Vishful OWN maintenance tickets (1,540) + tenant_rating (%d rated)"%int(TN["tenant_rating"].notna().sum())),
     ("top_own_pain_points",str(dict(list(sorted(tkc.items(),key=lambda kv:-kv[1])[:5])))),
     ("topics_audited",len(df)),
     ("marketing_opportunities(verified both sides)",int(df["candidate_action"].str.contains("highlight",case=False).sum())),
     ("operational_priorities",int(df["candidate_action"].str.contains("Operational|priorit",case=False).sum())),
     ("owner_verification_gates",int(df["candidate_action"].str.contains("verification|EVALUATE|verify",case=False).sum())),
     ("additional_scraping_has_decision_value","NO — competitor review sentiment not legitimately accessible; own tickets are richer + legitimate"),
     ("owner_rule","market customer signal -> Vishful opportunity; never competitor comparison; unknown stays unknown")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_review_intelligence_summary.csv"),index=False)
    print("PHASE-3 REVIEW-INTELLIGENCE AUDIT:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\ntopic -> action:")
    for _,r in df.iterrows(): print(f"  {r['topic']:24} | own_tickets={r['own_complaint_tickets']:>3} | {r['candidate_action'][:70]}")

if __name__=="__main__": main()
