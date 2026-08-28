"""Shared UUID -> human label adapter (authoritative source tables).
tenant_id -> tenants.full_name | apartment_id -> apartments.apartment_code
bed_id -> beds.bed_code | issue_type_id -> issue_types.name
Read-only. Fails loudly if a required table/column is missing.
"""
from __future__ import annotations
import pandas as pd
from loader import load_all
from validation import require_tables, require_columns

_MAPS={
 "tenant_id":   ("tenants","id","full_name","tenant_name"),
 "apartment_id":("apartments","id","apartment_code","apartment_code"),
 "bed_id":      ("beds","id","bed_code","bed_code"),
 "issue_type_id":("issue_types","id","name","issue_type_name"),
}

def build_maps(D=None):
    if D is None: D,_=load_all()
    require_tables(D, ["tenants","apartments","beds","issue_types"])
    maps={}
    for idcol,(tbl,key,val,out) in _MAPS.items():
        require_columns(D[tbl], tbl, [key,val])
        maps[idcol]=(dict(zip(D[tbl][key], D[tbl][val])), out)
    return maps

def add_labels(df: pd.DataFrame, D=None) -> pd.DataFrame:
    """Return a copy of df with *_label columns added next to any known id columns present."""
    maps=build_maps(D); out=df.copy()
    for idcol,(m,outname) in maps.items():
        if idcol in out.columns:
            out[outname]=out[idcol].map(m)
    return out

if __name__=="__main__":
    D,_=load_all(); m=build_maps(D)
    for k,(mp,out) in m.items():
        print(f"{k:14} -> {out:16} coverage entries={len(mp)}")
