"""
Phase-4 orchestrator + integration verification.
Dependency order: loader (imported) -> phase1 -> step3_collections_hardened ->
overdue -> churn -> revenue_forecast -> segmentation -> eb_anomaly -> maintenance_repeat.

--verify : snapshot locked outputs, regenerate, DIFF regenerated vs locked, then RESTORE
           locked outputs byte-identical. Locked outputs are never silently overwritten.
default  : print the plan only (no regeneration).

Reads source CSVs read-only; does not change any module logic.
"""
from __future__ import annotations
import os, sys, subprocess, shutil, hashlib, glob
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE=os.path.dirname(os.path.abspath(__file__))
OUT=os.path.join(HERE,"outputs"); SNAP=os.path.join(HERE,"_locked_snapshot")
ORDER=["phase1.py","step3_collections_hardened.py","overdue_model.py","churn_model.py",
       "revenue_forecast.py","component_revenue_forecast.py","segmentation.py","eb_anomaly.py","maintenance_repeat.py",
       "eb_leak.py","maintenance_closure_lag.py","asset_age.py","maintenance_sla.py","maintenance_sla_resolved.py",
       # Financial investigation analyses. Included because each reads ONLY source tables via loader
       # (no dependency on other outputs, no network, no API key) and is fully deterministic — so a clean
       # environment can regenerate and verify them. The other phase3 modules stay outside ORDER because
       # the market collectors need credentials and external calls.
       "phase3_ar_recovery_queue.py","phase3_credit_note_analysis.py","phase3_lease_coverage_signal.py",
       "phase4_evidence_pack.py","phase4_opportunity_rules.py"]
STALE_NOT_SURFACED=["step3_collections_worklist.csv"]  # superseded by step3_active_collections_worklist.csv

def _hash(p):
    with open(p,"rb") as f: return hashlib.md5(f.read()).hexdigest()

def snapshot():
    if os.path.exists(SNAP): shutil.rmtree(SNAP)
    shutil.copytree(OUT, SNAP)

def restore():
    for f in glob.glob(os.path.join(OUT,"*.csv")): os.remove(f)
    for f in glob.glob(os.path.join(SNAP,"*.csv")): shutil.copy2(f, OUT)

def run_module(m):
    env=dict(os.environ, PYTHONIOENCODING="utf-8")
    r=subprocess.run([sys.executable, m], cwd=HERE, env=env, capture_output=True, text=True)
    ok = r.returncode==0
    return ok, (r.stdout or "")[-300:], (r.stderr or "")[-400:]

def diff():
    locked={os.path.basename(f):_hash(f) for f in glob.glob(os.path.join(SNAP,"*.csv"))}
    new={os.path.basename(f):_hash(f) for f in glob.glob(os.path.join(OUT,"*.csv"))}
    import pandas as pd
    rows=[]
    for name in sorted(set(locked)|set(new)):
        if name not in locked: rows.append((name,"NEW(regenerated only)","",""))
        elif name not in new: rows.append((name,"MISSING(after regen)","",""))
        elif locked[name]==new[name]: rows.append((name,"IDENTICAL","",""))
        else:
            a=pd.read_csv(os.path.join(SNAP,name)); b=pd.read_csv(os.path.join(OUT,name))
            rows.append((name,"DIFFERENT",f"rows {a.shape[0]}->{b.shape[0]}",f"cols {a.shape[1]}->{b.shape[1]}"))
    return rows

if __name__=="__main__":
    if "--verify" not in sys.argv:
        print("PLAN (dependency order):"); [print("  ",i+1,m) for i,m in enumerate(ORDER)]
        print("Run with --verify to snapshot, regenerate, diff, and restore locked outputs."); sys.exit(0)

    print("="*70); print("PHASE-4 INTEGRATION VERIFICATION"); print("="*70)
    print("1) snapshot locked outputs ->", SNAP); snapshot()
    print("2) regenerate via dependency order:")
    fails=[]
    for m in ORDER:
        ok,so,se=run_module(m)
        print(f"   {'OK ' if ok else 'FAIL'} {m}")
        if not ok: fails.append((m,se))
    print("3) diff regenerated vs locked:")
    d=diff(); ident=sum(1 for r in d if r[1]=='IDENTICAL')
    for name,status,a,b in d:
        if status!="IDENTICAL": print(f"   {status:22} {name} {a} {b}")
    print(f"   IDENTICAL: {ident}/{len(d)}")
    print("4) restore locked outputs byte-identical"); restore()
    if os.path.exists(SNAP): shutil.rmtree(SNAP)
    print("\nSTALE (generated but NOT surfaced to dashboard):", ", ".join(STALE_NOT_SURFACED))
    if fails:
        print("\nMODULE FAILURES:")
        for m,se in fails: print(f"  {m}: {se}")
    print("\nRESULT:", "PASS — locked outputs behaviourally unchanged" if (not fails and all(r[1] in ('IDENTICAL','NEW(regenerated only)') for r in d)) else "REVIEW — differences/failures above")
