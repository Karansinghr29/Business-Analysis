"""Fail-loud validation for the credit-note / revenue-adjustment analysis.

Independently recomputes credit-note totals from SOURCE (tenant_adjustments) and compares them to the
generator's output. Guards the two errors this analysis is most exposed to:
  * mixing credit notes (which reduce revenue) with debit notes (which add charges) — the historic
    ₹521,688 combined figure must never reappear as a credit-note value;
  * presenting credit notes as confirmed revenue leakage when the data only supports a categorisation
    and governance finding.
"""
from __future__ import annotations
import os, sys, re, subprocess, hashlib
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

C=o("phase3_credit_note_analysis.csv")
S=dict(zip(o("phase3_credit_note_analysis_summary.csv")["metric"],
           o("phase3_credit_note_analysis_summary.csv")["value"]))
def sf(k):
    try: return float(S.get(k))
    except Exception: return float("nan")

# ---- independent recomputation from source ----
D,_=loader.load_all()
a=D["tenant_adjustments"].copy()
a["_del"]=a["is_deleted"].astype(str).str.lower().isin(["true","1"])
live=a[~a["_del"]].copy(); live["_amt"]=num(live["amount"])
src_cn=live[live["adjustment_type"]=="credit_note"]; src_dn=live[live["adjustment_type"]=="debit_note"]
src_cn_tot=float(src_cn["_amt"].sum()); src_dn_tot=float(src_dn["_amt"].sum())
COMBINED=src_cn_tot+src_dn_tot

print("[1] credit notes are NOT mixed with debit notes")
chk(abs(sf("credit_notes_total")-src_cn_tot)<TOL,
    f"reported credit-note total is credit notes ONLY (₹{src_cn_tot:,.2f})")
chk(int(sf("credit_notes_count"))==len(src_cn),f"credit-note count matches source ({len(src_cn)})")
chk(abs(sf("debit_notes_total")-src_dn_tot)<TOL,"debit notes reported separately with their own total")
chk(abs(sf("credit_notes_total")-COMBINED)>TOL,
    f"credit-note value is NOT the combined credit+debit figure (₹{COMBINED:,.2f}) — the historic ₹521,688 error")
chk(abs(float(C['amount'].sum())-src_cn_tot)<TOL,"category table sums to credit notes only")
chk("never sum the two" in str(S.get("note","")).lower(),"summary warns the two note types must not be summed")

print("\n[2] amount + category reconciliation")
chk(abs(float(C['amount'].sum())-sf("credit_notes_total"))<TOL,"category totals reconcile to the overall credit-note total")
chk(int(C['notes'].sum())==len(src_cn),f"category note counts reconcile to {len(src_cn)}")
src_by=src_cn.assign(category=src_cn["category"].fillna("others").astype(str)).groupby("category")["_amt"].sum()
for cat,amt in src_by.items():
    row=C[C["category"]==cat]
    chk(len(row)==1 and abs(float(row.iloc[0]["amount"])-float(amt))<TOL,
        f"category '{cat}' amount matches source (₹{float(amt):,.2f})")

print("\n[3] category integrity — no unexplained loss")
chk(set(C["category"])==set(src_by.index),"no source category dropped or invented")
chk(int(sf("categories"))==len(C),"summary category count matches the table")
oth=C[C["category"]=="others"]
if len(oth):
    src_oth=float(src_by.get("others",0.0))
    chk(abs(float(oth.iloc[0]["amount"])-src_oth)<TOL,f"'others' amount correct (₹{src_oth:,.2f})")
    chk(abs(sf("uncategorised_amount")-src_oth)<TOL,"summary uncategorised amount matches 'others'")
    share=100*src_oth/max(src_cn_tot,1)
    chk(abs(float(str(S.get("uncategorised_share","0")).rstrip("%"))-share)<0.15,
        f"uncategorised share correct ({share:.1f}%)")
chk(int(sf("deleted_rows_excluded"))==int(a["_del"].sum()),"deleted rows excluded and reported")

print("\n[4] reason-field limitation stays visible; category is authoritative")
cov=str(S.get("reason_field_coverage",""))
m=re.match(r"(\d+)\s*/\s*(\d+)",cov)
chk(bool(m),"summary reports reason-field coverage")
if m:
    chk(int(m.group(1))==int(live["reason"].notna().sum()) and int(m.group(2))==len(live),
        f"reason coverage matches source ({live['reason'].notna().sum()}/{len(live)})")
    chk(int(m.group(1))<int(m.group(2)),"reason coverage is acknowledged as incomplete")
chk("category" in " ".join(map(str,C.columns)).lower(),"category is the grouping dimension, not free-text reason")
chk((C["classification"]!="").all() and C["classification"].notna().all(),"every category carries a classification")

print("\n[5] NO fabricated leakage / loss / ROI claim")
blob=(" ".join(map(str,C.values.ravel()))+" "+" ".join(map(str,pd.DataFrame(list(S.items())).values.ravel()))).lower()
_SEP=r"[^A-Za-z0-9]|_"
NEG=re.compile(rf"(not|no|never|nor)({_SEP})+((\w+)({_SEP})+){{0,6}}$", re.I)
def negated_everywhere(phrase):
    hits=[mm.start() for mm in re.finditer(re.escape(phrase),blob)]
    if not hits: return True,0
    return all(NEG.search(blob[max(0,h-70):h]) for h in hits),len(hits)
for bad in ["preventable","confirmed loss","revenue lost","savings","roi","recovered revenue","avoidable leakage"]:
    ok,n=negated_everywhere(bad)
    chk(ok,f"'{bad}' never asserted ({n} occurrence(s), all negated)" if n else f"'{bad}' absent")
chk("NOT established" in str(S.get("causality","")) or "not established" in str(S.get("causality","")).lower(),
    "summary states causality is NOT established")
exp=C[C["classification"]=="Expected/normal adjustment"]
chk(len(exp)>0,"ordinary adjustments (referral/card-fee/EB) are classified as expected, not leakage")
chk(not C["classification"].astype(str).str.contains("confirmed",case=False).any(),
    "no category is marked as confirmed leakage")
oth_cls=C.loc[C["category"]=="others","classification"]
chk((oth_cls=="Insufficient reason data").all() if len(oth_cls) else True,
    "'others' is classified as insufficient reason data, NOT as confirmed loss")

print("\n[6] dashboard consistency")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_credit_note_analysis.csv" in dash,"Page 2 renders the credit-note analysis")
chk("Credit notes — revenue adjustments" in dash,"section titled as revenue adjustments, not leakage")
chk("not** automatically a loss" in dash or "not automatically a loss" in dash,
    "dashboard states a credit note is not automatically a loss")
chk("debit notes" in dash.lower() and "never be added" in dash.lower(),
    "dashboard warns debit notes must never be added to the credit-note figure")
chk(len(o("phase3_business_decisions.csv"))==14,"backbone still exactly 14 — analysis adds no decision")

print("\n[7] deterministic")
p=os.path.join(OUT,"phase3_credit_note_analysis.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_credit_note_analysis.py"],cwd=HERE,capture_output=True)
chk(h1==hashlib.md5(open(p,"rb").read()).hexdigest(),"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
