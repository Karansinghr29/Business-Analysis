"""
Phase-3 MARKET-SIGNAL -> VISHFUL-DECISION linkage layer (isolated, deterministic, read-only).
Rule: MARKET SIGNAL (context) + VISHFUL INTERNAL DATA (driver) -> VISHFUL-SPECIFIC candidate action.
NEVER a competitor comparison/ranking/benchmark/price-diff. Unknown stays Unknown. No new scraping,
no fabricated price/amenity; uses already-validated evidence only.

Also answers the gating question per signal: "would NEW scraping of this signal change a Vishful
decision?" -> phase3_market_scraping_value.csv. If no signal has decision value, we do NOT scrape.

Provenance per signal: property, location, signal_type, signal_value, first_party_url, evidence,
retrieval_date, provenance, confidence/status. Writes ONLY new files. Modifies nothing.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
SG=o("phase3_market_signals.csv"); AM=o("phase3_amenity_master_from_data.csv")
MX=o("phase3_inventory_amenity_matrix.csv"); VAC=o("step4_vacancy_at_risk.csv")
RET="2026-08-17"  # playwright/market retrieval date (real)

def amcount(name):
    r=SG[(SG["signal_type"]=="published_amenity")&(SG["signal"]==name)]
    return int(r["value"].iloc[0]) if len(r) else 0
def vstatus(name):
    r=AM[AM["amenity"]==name]
    return r["verified_status"].iloc[0] if len(r) else "UNKNOWN"
def vac(bt):
    s=VAC[VAC["bed_type"]==bt]; return len(s), float(s["rev_at_risk_monthly"].sum())

def main():
    rows=[]
    def S(prop,loc,stype,sval,url,ev,conf,vfact,action,declink,change,reason):
        rows.append(dict(property=prop,location=loc,signal_type=stype,signal_value=sval,
            first_party_url=url,evidence=ev,retrieval_date=RET,
            provenance="phase3_market_signals.csv / phase3_playwright_market_research.csv (first-party)",
            confidence_status=conf,vishful_internal_fact=vfact,candidate_action=action,
            decision_link=declink,would_new_scraping_change_decision=change,scraping_reason=reason))

    # --- amenity signals: market context + Vishful own-data status -> action ---
    AMEN=[("AC","AC availability"),("Wi-Fi","Wi-Fi"),("Food","Food"),("Parking","Parking"),
          ("Security/CCTV","Security/CCTV"),("Power backup","Power backup")]
    for vname,sname in AMEN:
        cnt=amcount(sname); vs=vstatus("Wi-Fi" if vname=="Wi-Fi" else vname)
        if vname=="AC":
            acbeds=int((MX["AC"]=="present").sum())
            S("market aggregate (first-party sources)","Thiruvanmiyur/Adyar/Perungudi (coarse)","published_amenity",
              f"{sname} published on {cnt} first-party sources","phase3_playwright_market_research.csv",
              f"{cnt} first-party sites publish {sname}","market_context_medium",
              f"Vishful AC = {vs}; {acbeds} vacant beds in AC-verified apartments",
              f"Highlight verified AC on the {acbeds} AC-associated vacant beds","DEC-AMEN-AC",
              "no","AC already VERIFIED from Vishful assets + market signal already collected")
        elif vs=="VERIFIED_PRESENT":
            S("market aggregate (first-party sources)","coarse","published_amenity",
              f"{sname} published on {cnt} first-party sources","phase3_playwright_market_research.csv",
              f"{cnt} first-party sites publish {sname}","market_context_medium",
              f"Vishful {vname} = VERIFIED_PRESENT (own assets/issue data)",
              f"Highlight verified {vname} in Vishful marketing","DEC-AMEN (marketing)",
              "no","Vishful amenity already proven from own data; signal already collected")
        else:  # UNKNOWN Vishful side -> do NOT advertise; owner verify (NOT scraping)
            S("market aggregate (first-party sources)","coarse","published_amenity",
              f"{sname} published on {cnt} first-party sources","phase3_playwright_market_research.csv",
              f"{cnt} first-party sites publish {sname}","market_context_medium",
              f"Vishful {vname} = UNKNOWN (not in Vishful data)",
              f"Do NOT advertise {vname}; verify internally before any claim","owner_input_gate",
              "no","gap is Vishful's OWN status (owner input), not a market data gap — scraping cannot resolve it")

    # --- sharing configuration signals + Vishful vacancy ---
    for vname,bt in [("2-sharing","Double"),("3-sharing","Triple"),("single","Single")]:
        n,rev=vac(bt)
        present=len(SG[(SG["signal_type"]=="sharing_configuration")&(SG["signal"].str.contains(vname.split("-")[0],case=False))])>0
        if n>0 and present:
            S("market aggregate (first-party sources)","coarse","sharing_configuration",
              f"{vname} is a first-party market-published configuration","phase3_playwright_market_research.csv",
              f"{vname} appears in first-party rendered sources","market_context_medium",
              f"Vishful has {n} vacant {vname} bed(s), ₹{rev:,.0f}/mo at risk",
              f"Promote available Vishful {vname} inventory",
              {"Double":"DEC-VAC-Double","Triple":"DEC-VAC-Triple","Single":"DEC-VAC-Single"}[bt],
              "no","both sides already evidenced; new scraping adds nothing")

    # --- locality concentration + Vishful vacancy ---
    locn=SG[SG["signal_type"]=="locality_concentration"]
    if len(locn):
        top=locn.sort_values("value",ascending=False).iloc[0]
        S("market aggregate","Vishful locality cluster (coarse)","locality_concentration",
          f"{int(top['value'])} competitors in {top['signal']} (coarse)","phase3_competitor_master.csv (aggregate)",
          "PG/co-living supply density in Vishful's own locality","market_context_low",
          f"Vishful has {int(len(VAC))} vacant beds",
          "Locality-targeted marketing for available inventory","DEC-LOC-MKT",
          "no","locality density already known; refine via Vishful's own leads-by-locality, not more scraping")

    # --- pricing signal (explicitly insufficient) ---
    S("market","area","published_price","only 1 first-party comparable per-bed source (Diyaa)",
      "https://menspg.in/","public first-party per-bed x sharing x AC price is not published by the cluster",
      "insufficient_sample","Vishful uses OWN rate card (rate_card #43) for pricing review",
      "Keep pricing INTERNAL (rate card + fill signal); do NOT build a market price benchmark","DEC-PRICEREV-*",
      "no","tested Groq+Apify+static+Playwright -> 1 comparable; more scraping cannot produce a valid benchmark and must never fabricate")

    df=pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT,"phase3_market_decision_signals.csv"),index=False)

    # scraping value assessment (would a NEW scrape change a decision?)
    sv=[("per-bed price at grain","pricing review","NO","exhausted: 1 comparable; would risk fabrication"),
        ("food service published","amenity marketing","NO","gap is Vishful's OWN food status -> owner input, not market"),
        ("parking/CCTV/power published","amenity marketing","NO","same — Vishful own status unknown -> owner input"),
        ("more competitor amenities","amenity marketing","NO","already have enough context; Vishful side is the gap"),
        ("locality demand detail","locality marketing","NO","better from Vishful's own leads-by-locality (leads #84)")]
    pd.DataFrame(sv,columns=["candidate_signal","decision_it_would_affect","new_scraping_has_value","reason"]).to_csv(
        os.path.join(OUT,"phase3_market_scraping_value.csv"),index=False)

    act=df[df["would_new_scraping_change_decision"]=="no"]
    summary=[("signals_linked",len(df)),
     ("actionable_now(verified both sides)",int(df["candidate_action"].str.startswith(("Highlight","Promote")).sum())),
     ("owner_gate(vishful unknown)",int((df["decision_link"]=="owner_input_gate").sum())),
     ("pricing_stays_internal",int((df["signal_type"]=="published_price").sum())),
     ("signals_where_new_scraping_would_change_a_decision",int((df["would_new_scraping_change_decision"]=="yes").sum())),
     ("scraping_recommendation","NO new scraping justified — no missing market signal has identifiable decision value"),
     ("owner_rule","Vishful internal = decision driver; market = context; never compare competitors")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_market_decision_signals_summary.csv"),index=False)
    print("PHASE-3 MARKET-DECISION SIGNALS:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nsignal -> action:")
    for _,r in df.iterrows(): print(f"  {r['signal_type']:24} | {r['vishful_internal_fact'][:48]:48} | {r['candidate_action'][:50]}")

if __name__=="__main__": main()
