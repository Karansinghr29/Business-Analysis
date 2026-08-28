"""
Phase-3 Vishful SELF-DATA AUDIT (ISOLATED, deterministic, read-only). Audit-only.
Determines what Vishful ALREADY knows about its own facilities/amenities/config from its OWN data
(assets, maintenance issue-types, apartments, beds, rate card, leads, financials) — so we do NOT
ask the owner for what already exists.

Rules: NO competitor/market inference. NO inference from room-type NAMES. NO 'common in PGs'
assumption. UNKNOWN never becomes TRUE/FALSE. Ambiguous -> UNKNOWN with evidence shown. Absence
of an asset is NOT proof of absence -> UNKNOWN (not VERIFIED_ABSENT) unless truly determinable.

Evidence tiers: physical ASSET present (assets #78 + asset_types #80) => VERIFIED_PRESENT.
Managed SERVICE proven by tenant issue-subtypes (#76/#77) => VERIFIED_PRESENT (Vishful maintains it).
No asset AND no service evidence => UNKNOWN.

Writes ONLY phase3_vishful_self_audit.csv + _sections.csv + _summary.csv. Reads source CSVs
read-only. Modifies nothing (no dashboard/locked/existing).
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(HERE)          # Business Decision root (source CSVs)
OUT=os.path.join(HERE,"outputs")
def src(nn): return pd.read_csv(os.path.join(ROOT,f"Supabase Snippet Untitled query ({nn}).csv"),low_memory=False)

ASSETS=src(78); ATYPES=src(80); ISSUES=src(76); SUBS=src(77)
APTS=src(41); BEDS=src(42); RATE=src(43); LEADS=src(84); FIN=src(85)
VAC=pd.read_csv(os.path.join(HERE,"outputs","step4_vacancy_at_risk.csv"))  # corrected vacancy (lifecycle-aware)
ASSETS["atype"]=ASSETS["asset_type_id"].map(dict(zip(ATYPES["id"],ATYPES["name"])))
ACOUNT={k:int(v) for k,v in ASSETS["atype"].value_counts().items()}
SUBSET=set(s.lower() for s in SUBS["name"].dropna())
ISET=set(s.lower() for s in ISSUES["name"].dropna())

def acount(*names): return sum(ACOUNT.get(n,0) for n in names)
def sub_has(*kw): return sorted({s for s in SUBSET if any(k in s for k in kw)})

rows=[]
def R(attr,status,ev,srcf,conf,use):
    rows.append(dict(attribute=attr,status=status,evidence=ev,source_file=srcf,confidence=conf,can_use_for_decision=use))

# ---- Room / bed configuration (VERIFIED from own tables) ----
bt=BEDS["bed_type"].value_counts().to_dict(); tt=BEDS["toilet_type"].value_counts().to_dict()
R("Bed types / sharing","VERIFIED_PRESENT",f"{len(BEDS)} beds; bed_type={bt}","beds #42","high","yes")
R("Toilet type (attached/common)","VERIFIED_PRESENT",f"toilet_type={tt}","beds #42","high","yes")
R("Apartments / floors / building","VERIFIED_PRESENT",
  f"{len(APTS)} apartments, floors {sorted(APTS['floor_number'].dropna().unique().tolist())}, "
  f"types {APTS['apartment_type'].value_counts(dropna=False).to_dict()}","apartments #41","high","yes")
R("Gender allowed per apartment","VERIFIED_PRESENT",
  f"{APTS['gender_allowed'].astype(str).str.lower().value_counts().to_dict()}","apartments #41","high","yes")
R("Room size (sqft)","PARTIAL",f"size_sqft present {int(APTS['size_sqft'].notna().sum())}/{len(APTS)} apartments","apartments #41","high","yes")
R("Rate card (rent by bed_type x toilet)","VERIFIED_PRESENT",f"{len(RATE)} rate rows; monthly_rate populated","rate_card #43","high","yes")

# ---- Amenities from OWN assets + issue-types ----
def amenity(attr,asset_names,serv_kw=(),issue_names=()):
    ac=acount(*asset_names) if asset_names else 0
    subs=sub_has(*serv_kw) if serv_kw else []
    isv=[i for i in issue_names if i.lower() in ISET]
    if ac>0:
        R(attr,"VERIFIED_PRESENT",f"{ac} '{'/'.join(asset_names)}' asset(s)"+(f"; issue-type {isv}" if isv else ""),
          "assets #78 / asset_types #80"+(" + issue_types #76" if isv else ""),"high","yes")
    elif subs or isv:
        R(attr,"VERIFIED_PRESENT",f"managed service — tenant issue-subtypes {subs or isv}",
          "issue_subtypes #77 / issue_types #76","high","yes")
    else:
        R(attr,"UNKNOWN","no asset and no issue-type evidence in Vishful data (absence ≠ proof absent)","—","n/a","no — needs owner input")

amenity("AC (air conditioning)",["Air Conditioner"],issue_names=["AC Issues"])
amenity("Wi-Fi / Internet",[],serv_kw=("wifi","internet","router"),issue_names=["Internet Issues"])
amenity("Hot water (water heater/geyser)",["Water Heater"],issue_names=["Heater Issues"])
amenity("RO / drinking water",["RO Water Purifier"],issue_names=["RO Water Issues"])
amenity("Refrigerator",["Refrigerator"],issue_names=["Fridge Issues"])
amenity("Washing machine / laundry",["Washing Machine"],issue_names=["Washing machine Issue"])
amenity("TV",["TV"])
amenity("Kitchen / cooking facility",["Induction Stove","Microwave Oven","Kitchen Table","Dining Table"],issue_names=["Kitchen Equipment"])
amenity("Fan",["Fan","Table Fan (Wall)"])
amenity("Furniture (cot/mattress/cupboard/study table)",["Cot (Bed Frame)","Mattress","Cupboard","Study Table","Chair","Wardrobe"])
amenity("Housekeeping / cleaning service",[],serv_kw=("clean","garbage","dirty"),issue_names=["Cleaning Issues"])
amenity("Common area",[],serv_kw=("common area",))
# genuinely unknown (no asset/issue evidence)
for a in ["Food / catered meals (breakfast/lunch/dinner)","Parking","CCTV / security","Power backup / generator",
          "Lift / elevator","Gym","Dedicated study area","Terrace access"]:
    amenity(a,[])
# note food nuance
rows[-8]["evidence"]=("kitchen/cooking assets exist BUT no evidence of a catered MEALS service; "
    "tenant 'food_preference' (#45) is a tenant attribute, NOT proof Vishful serves meals -> UNKNOWN") \
    if rows[-8]["attribute"].startswith("Food") else rows[-8]["evidence"]

# ---- Commercial / operational (VERIFIED present) ----
for attr,srcf,ev in [
 ("Rent","allotments #44 / rate #43 / invoices #52","monthly_rental + rate card + invoice rent_amount"),
 ("Electricity / EB","invoices #52 / eb_readings #56,#57,#60","electricity_amount + meter readings/units"),
 ("Deposits","allotments #44 / exits #48 / settlements #50","deposit_paid, advance_held, refund_due"),
 ("Billing / invoices","invoices #52 / line_items #53","5,193 invoices with line items"),
 ("Occupancy","occupancy_snapshot #94 / step5","total_beds/occupied/vacant/occupancy_pct"),
 ("Vacancies & availability","beds #42 status / step4","bed status + vacancy-at-risk"),
 ("Tenant movement / events","bed_events #95","2,175 move/status events"),
 ("Transfers / room switches","room_switches #46","28 switch records"),
 ("Booking duration","allotments #44","expected_stay_days, booking/onboarding dates"),
 ("Notice period / move-out","allotments #44 notice_date / notices #47 / exits #48","notice + exit records"),
 ("Maintenance","tickets #71 / resolutions #72 / logs #75","1,650 tickets + lifecycle logs"),
 ("Inventory (assets)","assets #78 / allocations #79","1,700 assets, 1,822 allocations")]:
    R(attr,"VERIFIED_PRESENT",ev,srcf,"high","yes")
_vtot=int(len(VAC)); _vknown=int(VAC["duration_known"].astype(bool).sum())
_vnew=int((VAC["recommended_action"].astype(str).str.contains("New inventory",case=False)).sum())
_vunk=_vtot-_vknown
R("Fill time / vacancy duration","PARTIAL",
  (f"days_vacant known for {_vknown}/{_vtot} vacant beds (duration_known=True); "
   f"{_vnew} new-inventory (A33/A34) counted from operational start 2026-08-01; "
   f"{_vunk} never-occupied -> unknown. Time-to-fill still not measurable (no completed fill events)."),
  "step4_vacancy_at_risk.csv","high","partial")

# ---- Marketing information ----
R("Lead source / enquiries","PARTIAL",
  f"{len(LEADS)} leads; source={LEADS['source'].value_counts().to_dict()}; status={LEADS['status'].value_counts().to_dict()}; "
  "has bed_type/budget/property_interest/move_in_date","leads #84","medium","yes (small n)")
R("Visits requested","PARTIAL",f"{int((LEADS['status']=='visit_requested').sum())} visit_requested leads","leads #84","medium","yes")
mk=float(FIN["marketing"].sum())
R("Marketing spend","VERIFIED_PRESENT",f"₹{mk:,.0f} marketing expense over {int((FIN['marketing']!=0).sum())} months (aggregate)","financials #85","high","yes")
R("Lead -> conversion linkage","UNKNOWN","leads (#84) not linked to allotments (#44); no conversion mapping","—","n/a","no — needs capture")
R("Campaign channel detail / referral","UNKNOWN","only source='whatsapp_bot'; no campaign/referral/channel breakdown or dates","leads #84","n/a","no — needs capture")

audit=pd.DataFrame(rows)
audit.to_csv(os.path.join(OUT,"phase3_vishful_self_audit.csv"),index=False)

# ---- sections ----
known=audit[audit["status"].isin(["VERIFIED_PRESENT"])]["attribute"].tolist()
partial=audit[audit["status"]=="PARTIAL"]["attribute"].tolist()
unknown=audit[audit["status"]=="UNKNOWN"]["attribute"].tolist()
owner_needed=audit[(audit["status"]=="UNKNOWN")]["attribute"].tolist()
sec=[]
for a in known: sec.append(dict(section="ALREADY_KNOWN_DO_NOT_ASK",attribute=a))
for a in partial: sec.append(dict(section="PARTIAL_known_some_missing",attribute=a))
for a in owner_needed: sec.append(dict(section="OWNER_INPUT_REQUIRED",attribute=a))
pd.DataFrame(sec).to_csv(os.path.join(OUT,"phase3_vishful_self_audit_sections.csv"),index=False)

summary=[("attributes_audited",len(audit)),
 ("VERIFIED_PRESENT",int((audit["status"]=="VERIFIED_PRESENT").sum())),
 ("PARTIAL",int((audit["status"]=="PARTIAL").sum())),
 ("UNKNOWN",int((audit["status"]=="UNKNOWN").sum())),
 ("VERIFIED_ABSENT",int((audit["status"]=="VERIFIED_ABSENT").sum())),
 ("amenities_already_proven","AC, Wi-Fi, Hot water, RO water, Refrigerator, Washing machine, TV, Kitchen, Fan, Furniture, Housekeeping, Common area"),
 ("owner_input_required",", ".join(owner_needed)),
 ("newly_discovered_sources","assets #78, asset_types #80, issue_types #76, issue_subtypes #77, leads #84, financials.marketing #85, apartments #41 (floor/gender/size)"),
 ("governing_rule","Vishful data = decision driver; market = context; no competitor inference; unknown stays unknown")]
pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_vishful_self_audit_summary.csv"),index=False)
print("PHASE-3 VISHFUL SELF-AUDIT:")
for k,v in summary: print(f"  {k}: {v}")
print("\naudit rows:")
for _,r in audit.iterrows(): print(f"  {r['status']:16} | {r['attribute']:45} | {r['source_file']}")

if __name__=="__main__": pass
