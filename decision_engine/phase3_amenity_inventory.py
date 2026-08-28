"""
Phase-3 Amenity master from REAL Vishful data + inventory-amenity matrix (Parts 5/6, isolated,
deterministic, read-only). Maps apartment -> asset -> amenity from assets #78 + asset_types #80,
then vacant inventory (step4) -> apartment -> amenities. Unknown stays Unknown; absence of a
record is NOT marked absent. Service-level amenities (WiFi/housekeeping) proven by issue-types
are property-scope. No market inference. Writes ONLY new files. Modifies nothing.
"""
from __future__ import annotations
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); OUT=os.path.join(HERE,"outputs")
def src(nn): return pd.read_csv(os.path.join(ROOT,f"Supabase Snippet Untitled query ({nn}).csv"),low_memory=False)

ASSETS=src(78); ATYPES=src(80); BEDS=src(42); ISSUES=src(76); ALLOC=src(79)
VAC=pd.read_csv(os.path.join(OUT,"step4_vacancy_at_risk.csv"))
ASSETS["atype"]=ASSETS["asset_type_id"].map(dict(zip(ATYPES["id"],ATYPES["name"])))
# authoritative mapping = allocations #79 (assets.apartment_id/bed_id are null); join asset_type name
ALLOC=ALLOC.merge(ASSETS[["id","atype"]],left_on="asset_id",right_on="id",how="left",suffixes=("","_a"))
# amenity -> asset_type name(s)
AMAP={"AC":["Air Conditioner"],"Hot water":["Water Heater"],"RO water":["RO Water Purifier"],
      "Refrigerator":["Refrigerator"],"Washing machine":["Washing Machine"],"TV":["TV"],
      "Kitchen":["Induction Stove","Microwave Oven"],"Fan":["Fan","Table Fan (Wall)"]}
SERVICE={"Wi-Fi":"Internet Issues","Housekeeping":"Cleaning Issues"}  # property-scope services (issue-proven)
ISET=set(s for s in ISSUES["name"].dropna())

def main():
    # apartment-level amenities from allocations #79 (apartment_id present)
    ah=ALLOC.dropna(subset=["apartment_id"])
    apt_am=[]
    for ap in sorted(ah["apartment_id"].dropna().unique()):
        sub=ah[ah["apartment_id"]==ap]; row={"apartment_id":ap}
        for am,types in AMAP.items():
            n=int(sub["atype"].isin(types).sum())
            row[am]=("present" if n>0 else "unknown"); row[am+"_count"]=n
        apt_am.append(row)
    apt=pd.DataFrame(apt_am)
    apt.to_csv(os.path.join(OUT,"phase3_vishful_amenity_evidence.csv"),index=False)
    apt_idx=apt.set_index("apartment_id") if len(apt) else pd.DataFrame()
    bed_alloc=ALLOC.dropna(subset=["bed_id"])   # bed-level allocations (stronger scope)

    # inventory-amenity matrix: each VACANT bed -> bed-level amenities (else apartment-level)
    mat=[]
    for _,b in VAC.iterrows():
        ap=b["apartment_id"]; bid=b.get("id")
        row={"bed_code":b["bed_code"],"apartment_id":ap,"bed_type":b["bed_type"],
             "toilet_type":b["toilet_type"],"days_vacant":b["days_vacant"],"rev_at_risk_monthly":b["rev_at_risk_monthly"]}
        bsub=bed_alloc[bed_alloc["bed_id"]==bid]
        bed_scope=len(bsub)>0; has_apt=ap in apt_idx.index
        for am,types in AMAP.items():
            if bed_scope:
                row[am]=("present" if int(bsub["atype"].isin(types).sum())>0 else "unknown")
            elif has_apt:
                row[am]=apt_idx.loc[ap,am]
            else:
                row[am]="unknown"
        row["mapping_confidence"]=("bed_level" if bed_scope else "apartment_level" if has_apt else "unknown")
        mat.append(row)
    mx=pd.DataFrame(mat)
    mx.to_csv(os.path.join(OUT,"phase3_inventory_amenity_matrix.csv"),index=False)

    # amenity master (property + apartment scope + service scope), verified status/evidence/scope
    master=[]
    for am,types in AMAP.items():
        n_total=int(ASSETS["atype"].isin(types).sum())
        n_apts=int((apt[am]=="present").sum()) if len(apt) else 0
        master.append(dict(amenity=am,verified_status=("VERIFIED_PRESENT" if n_total>0 else "UNKNOWN"),
            scope="apartment-level (asset linked)",evidence=f"{n_total} '{'/'.join(types)}' assets across {n_apts} apartments",
            source="assets #78 / asset_types #80",mapping_confidence="apartment_level"))
    for am,iss in SERVICE.items():
        present=iss in ISET
        master.append(dict(amenity=am,verified_status=("VERIFIED_PRESENT" if present else "UNKNOWN"),
            scope="property-level (managed service)",evidence=f"issue-type '{iss}' present" if present else "no issue evidence",
            source="issue_types #76",mapping_confidence="property_level"))
    mm=pd.DataFrame(master); mm.to_csv(os.path.join(OUT,"phase3_amenity_master_from_data.csv"),index=False)

    # vacant beds whose apartment has AC (actionable)
    ac_vac=int((mx["AC"]=="present").sum()) if "AC" in mx.columns else 0
    summary=[("apartments_with_amenity_data",len(apt)),("vacant_beds_mapped",len(mx)),
     ("vacant_beds_with_AC_apartment",ac_vac),
     ("amenities_apartment_scope",", ".join(AMAP.keys())),
     ("amenities_service_scope",", ".join(SERVICE.keys())),
     ("mapping_note","apartment-level from asset.apartment_id; bed-level only where asset.bed_id set; unknown stays unknown; nothing marked absent")]
    pd.DataFrame(summary,columns=["metric","value"]).to_csv(os.path.join(OUT,"phase3_amenity_inventory_summary.csv"),index=False)
    print("PHASE-3 AMENITY INVENTORY:")
    for k,v in summary: print(f"  {k}: {v}")
    print("\nvacant-bed amenity matrix (AC column):")
    if "AC" in mx.columns:
        print(mx.groupby(["bed_type","AC"]).size().to_dict())
if __name__=="__main__": main()
