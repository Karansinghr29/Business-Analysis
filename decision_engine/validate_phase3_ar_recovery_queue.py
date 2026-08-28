"""Fail-loud validation for the aged-AR recovery REVIEW QUEUE.

Independently recomputes the split from SOURCE (v_tenant_aging + tenant_allotments +
deposit_settlements) and compares it to the generator's output — this is a genuine cross-check,
not a self-consistency check of the output against itself.

Guards the business framing as strictly as the arithmetic: deposit evidence must never become a
recovery estimate, and the exited-without-settlement queue must never be presented as confirmed loss.
"""
from __future__ import annotations
import os, sys, subprocess, hashlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd
import loader

HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"outputs")
def o(f): return pd.read_csv(os.path.join(OUT,f))
num=lambda s: pd.to_numeric(s,errors="coerce")
TOL=0.01
fails=[]
def chk(c,m): print(("  PASS " if c else "  FAIL ")+m); (fails.append(m) if not c else None)

Q=o("phase3_ar_recovery_queue.csv")
S=dict(zip(o("phase3_ar_recovery_queue_summary.csv")["metric"],
           o("phase3_ar_recovery_queue_summary.csv")["value"]))
def sf(k):
    try: return float(S.get(k))
    except Exception: return float("nan")

# ---- independent recomputation from source ----
D,_=loader.load_all()
ag=D["v_tenant_aging"]; al=D["tenant_allotments"].copy(); ds=D["deposit_settlements"]
al["_exit"]=pd.to_datetime(al.get("actual_exit_date"),errors="coerce")
src_active=set(al.loc[al["_exit"].isna(),"id"]); src_exited=set(al.loc[al["_exit"].notna(),"id"])
src90=ag[num(ag["bucket_90_plus"])>0]
src_total=float(num(src90["bucket_90_plus"]).sum()); src_n=len(src90)

print("[1] reconciliation against the independently-recomputed source universe")
chk(len(Q)==src_n,f"queue rows == source 90+ allotments ({len(Q)} vs {src_n})")
chk(abs(float(Q['ar_90_plus'].sum())-src_total)<TOL,
    f"queue AR total reconciles to source ₹{src_total:,.2f} (got ₹{float(Q['ar_90_plus'].sum()):,.2f})")
a_ar=float(Q.loc[Q.tenant_status=="ACTIVE","ar_90_plus"].sum())
e_ar=float(Q.loc[Q.tenant_status=="EXITED","ar_90_plus"].sum())
chk(abs((a_ar+e_ar)-float(Q['ar_90_plus'].sum()))<TOL,
    f"active AR + exited AR == total (₹{a_ar:,.2f} + ₹{e_ar:,.2f})")
chk(abs(a_ar-sf("active_ar"))<TOL and abs(e_ar-sf("exited_ar"))<TOL,"summary AR split matches the queue rows")
chk(int(sf("active_allotments"))+int(sf("exited_allotments"))==len(Q),"active count + exited count == queue rows")
chk(abs(sf("aged_90_plus_total")-src_total)<TOL,"summary total reconciles to source")

print("\n[2] grain integrity — no join inflation")
chk(Q["allotment_id"].nunique()==len(Q),"one row per allotment (no duplicated allotment contribution)")
chk(len(ag)==ag["allotment_id"].nunique(),"source v_tenant_aging is 1 row per allotment")
chk(len(ds)==ds["allotment_id"].nunique(),"source deposit_settlements is 1 row per allotment")
chk(abs(float(Q['ar_90_plus'].sum())-src_total)<TOL,"no aged-AR amount duplicated by the settlement join")

print("\n[3] status classification derived from real tenancy state")
qa=set(Q.loc[Q.tenant_status=="ACTIVE","allotment_id"]); qe=set(Q.loc[Q.tenant_status=="EXITED","allotment_id"])
chk(qa.issubset(src_active),"every ACTIVE row has no actual_exit_date in source")
chk(qe.issubset(src_exited),"every EXITED row has an actual_exit_date in source")
chk(set(Q["allotment_id"])==set(src90["allotment_id"]),"no source 90+ record silently dropped")
chk(Q["tenant_status"].isin(["ACTIVE","EXITED"]).all(),"every record carries a resolved status")
chk(Q["classification"].notna().all() and (Q["classification"].astype(str).str.len()>0).all(),"every record is classified")

print("\n[4] settlement investigation queue is real and correctly framed")
noset=Q[Q["classification"].str.contains("no settlement record",case=False,na=False)]
src_noset=qe-set(ds["allotment_id"].dropna())
chk(len(noset)==len(src_noset),f"no-settlement queue matches source ({len(noset)} vs {len(src_noset)})")
chk(set(noset["allotment_id"])==src_noset,"no-settlement queue contains exactly the exited allotments absent from deposit_settlements")
chk(abs(float(noset['ar_90_plus'].sum())-sf("insufficient_linkage_ar"))<TOL,"no-settlement AR matches the summary")
chk(noset["review_action"].astype(str).str.contains("investigate",case=False).all(),
    "no-settlement cases are framed as investigation, not loss")
blob=" ".join(map(str,Q.values.ravel())).lower()
for bad in ["confirmed loss","written off","unrecoverable","bad debt","will recover","guaranteed"]:
    chk(bad not in blob,f"no confirmed-loss language: '{bad}'")

print("\n[5] deposit evidence never becomes a recovery estimate")
# These phrases legitimately appear inside the output's own limitation text, where they are NEGATED
# ("NOT a recovery estimate", "no ... recovery probability is computed"). A naive substring test would
# flag the safeguard itself, so require a negation immediately before every occurrence.
import re as _re
# separator class includes '_' because metric KEYS use snake_case; a bare \W would treat the
# underscore as part of the word and miss that negation.
_SEP=r"[^A-Za-z0-9]|_"
NEG=_re.compile(rf"(not|no|never|nor)({_SEP})+((\w+)({_SEP})+){{0,6}}$", _re.I)
def negated_everywhere(phrase):
    hits=[m.start() for m in _re.finditer(_re.escape(phrase),blob)]
    if not hits: return True,0
    ok=all(NEG.search(blob[max(0,h-60):h]) for h in hits)
    return ok,len(hits)
for bad in ["net ar after","recovery estimate","collectable after","expected recovery","recovery probability"]:
    ok,n=negated_everywhere(bad)
    chk(ok,f"'{bad}' never asserted ({n} occurrence(s), all negated)" if n else f"'{bad}' absent")
chk("NOT COMPUTED" in str(S.get("recovery_estimate","")),"summary states recovery is NOT computed")
chk("UNAVAILABLE" in str(S.get("reconciliation_status","")),"summary preserves the receipt_allocations reconciliation limitation")
act_dep=Q.loc[Q.tenant_status=="ACTIVE","deposit_held_active"]
chk(Q.loc[Q.tenant_status=="EXITED","deposit_held_active"].isna().all(),
    "deposit_held_active is populated for ACTIVE rows only (exited deposits were settled at exit)")
bk=Q[Q["classification"].str.startswith("Deposit-backed",na=False)]
chk((num(bk["deposit_held_active"])>0).all() if len(bk) else True,"every 'Deposit-backed' row has a positive deposit on file")

print("\n[6] dashboard consistency — a SPLIT of the existing aged AR, not an extra amount")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_ar_recovery_queue.csv" in dash,"Page 2 renders the recovery queue")
chk("Aged 90+ AR — recovery review queue" in dash,"section titled as a review queue")
chk("not** a recovery estimate" in dash or "not a recovery estimate" in dash,"dashboard states it is not a recovery estimate")
dec=o("phase3_business_decisions.csv")
ar90=dec[dec["decision_id"]=="DEC-REVPROTECT-AR90"]
if len(ar90):
    # take the ₹-prefixed figure specifically; a bare digit scan would also capture the "#89" source ref
    m=_re.search(r"₹\s*([\d,]+(?:\.\d+)?)", str(ar90.iloc[0]["expected_impact"]))
    dec_amt=float(m.group(1).replace(",","")) if m else None
    chk(dec_amt is not None and abs(dec_amt-src_total)<1.0,
        f"queue total equals the existing DEC-REVPROTECT-AR90 amount "
        f"(decision ₹{dec_amt:,.2f} vs queue ₹{src_total:,.2f}) — a split, not an addition")
chk(len(dec)==14,"backbone still exactly 14 — the queue adds no decision")

print("\n[7] deterministic")
p=os.path.join(OUT,"phase3_ar_recovery_queue.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_ar_recovery_queue.py"],cwd=HERE,capture_output=True)
chk(h1==hashlib.md5(open(p,"rb").read()).hexdigest(),"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
