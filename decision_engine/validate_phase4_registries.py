"""Fail-loud validation of the Phase-2A registries (KPI direction + measurement window)."""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
D=o("phase4_kpi_direction_registry.csv"); W=o("phase4_measurement_window_registry.csv"); fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

print("[1] direction registry schema + explicit directions")
chk({"kpi_name","direction","unit","measurable","baseline_source","no_change_tolerance","note"}.issubset(D.columns),"direction schema complete")
chk(D["kpi_name"].is_unique,"kpi_name unique")
chk(D["direction"].isin(["higher_is_better","lower_is_better","context_only"]).all(),"every direction is one of the 3 allowed values")
chk(D["measurable"].isin(["yes","no"]).all(),"measurable is yes/no")
chk(bool(D["note"].astype(str).str.len().gt(0).all()),"every KPI has a reviewable note")

print("[2] window registry schema + configurable windows")
chk({"domain","min_window_days","typical_window_days","rationale","applies_to"}.issubset(W.columns),"window schema complete")
chk(W["domain"].is_unique,"domain unique")
chk((W["min_window_days"]<=W["typical_window_days"]).all(),"min_window <= typical_window")
chk(bool(W["rationale"].astype(str).str.len().gt(0).all()),"every window has an explicit rationale (not a hidden constant)")

print("[3] KPI coverage — every REAL KPI name is registered (derived, not invented)")
dea=o("phase3_decision_execution_analytics.csv"); miss_bb=set(dea["kpi_name"].astype(str))-set(D["kpi_name"])
chk(not miss_bb,f"all backbone/opportunity kpi_names covered (missing: {miss_bb})")
ai=o("phase4_ai_opportunities.csv"); miss_ai=set(ai["expected_kpi"].astype(str))-set(D["kpi_name"])
chk(not miss_ai,f"all AIREC expected_kpi covered (missing: {miss_ai})")

print("[4] unavailable preserved, never zero")
un=D[D["measurable"]=="no"]
chk(bool(un["baseline_source"].astype(str).str.contains("Unavailable").all()),"non-measurable KPIs carry the Unavailable sentence (never 0)")
chk(int((D["direction"]=="context_only").sum())>0 and int((D["direction"]=="higher_is_better").sum())>0 and int((D["direction"]=="lower_is_better").sum())>0,"all three directions are represented (reviewable)")

print("[5] deterministic")
h1=[hashlib.md5(open(os.path.join(OUT,f),"rb").read()).hexdigest() for f in ["phase4_kpi_direction_registry.csv","phase4_measurement_window_registry.csv"]]
subprocess.run([sys.executable,"phase4_registries.py"],cwd=HERE,capture_output=True)
h2=[hashlib.md5(open(os.path.join(OUT,f),"rb").read()).hexdigest() for f in ["phase4_kpi_direction_registry.csv","phase4_measurement_window_registry.csv"]]
chk(h1==h2,"registries re-generate byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
