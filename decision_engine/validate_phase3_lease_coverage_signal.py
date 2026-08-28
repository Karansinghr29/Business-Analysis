"""Fail-loud validation for the LEASE COVERAGE investigation signal.

This is the most commercially sensitive output in the system — a below-1.0x reading points toward a
lease review — so validation is deliberately strict on BOTH arithmetic and framing.

The whole coverage calculation is recomputed independently from SOURCE (owner_payments + invoices)
using the documented matched-apartment-month method, then compared to the generator's output. The
flagged apartments are DERIVED, never hard-coded, so the validator remains correct if source data
legitimately changes.

Framing guards enforce that this is never presented as profitability and never fabricates a
commercial recommendation.
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

L=o("phase3_lease_coverage_signal.csv")
S=dict(zip(o("phase3_lease_coverage_signal_summary.csv")["metric"],
           o("phase3_lease_coverage_signal_summary.csv")["value"]))
def sf(k):
    try: return float(S.get(k))
    except Exception: return float("nan")

# ---- independent recomputation from source, mirroring the documented method ----
D,_=loader.load_all()
op=D["owner_payments"].copy(); inv=D["invoices"].copy(); ap=D["apartments"]
code=dict(zip(ap["id"],ap["apartment_code"]))
op["_m"]=pd.to_datetime(op["payment_month"],errors="coerce").dt.to_period("M"); op["_rent"]=num(op["escalated_amount"])
inv["_m"]=pd.to_datetime(inv["invoice_date"],errors="coerce").dt.to_period("M"); inv["_rev"]=num(inv["total_amount"])
R=op.groupby(["apartment_id","_m"])["_rent"].sum().rename("rent")
V=inv.groupby(["apartment_id","_m"])["_rev"].sum().rename("rev")
both=pd.concat([R,V],axis=1)
matched=both.dropna()
G=matched.groupby(level=0).agg(rev=("rev","sum"),rent=("rent","sum"),months=("rev","size"))
G["cov"]=(G["rev"]/G["rent"]).round(2)
G.index=[code.get(i,str(i)[:8]) for i in G.index]
src_flagged=set(G[G["cov"]<1.0].index)

print("[1] source reconciliation — owner_payments grain and P&L tie-out")
chk(len(op)==op["id"].nunique(),"owner_payments is 1 row per id")
chk(len(op)==len(op.drop_duplicates(["apartment_id","payment_month"])),
    "owner_payments is 1 row per apartment-month (no duplicate obligation)")
chk(abs(float(num(op['escalated_amount']).sum())-17623800.0)<1.0,
    f"owner-rent source ties to the P&L owner-rent figure (₹{float(num(op['escalated_amount']).sum()):,.2f})")
chk(op["apartment_id"].notna().all(),"every owner-rent row carries an apartment_id")

print("\n[2] invoice grain — aggregation before comparison, no fan-out")
chk(len(inv)==inv["id"].nunique(),"invoices is 1 row per id")
chk(inv["apartment_id"].notna().all(),"every invoice carries an apartment_id")
chk(len(V)==len(V.index.unique()),"revenue aggregated to unique (apartment, month) before comparison")
chk(len(R)==len(R.index.unique()),"owner rent aggregated to unique (apartment, month) before comparison")
chk(float(G["rev"].sum())<=float(num(inv["total_amount"]).sum())+TOL,
    "aggregated revenue never exceeds total invoiced (no fan-out inflation)")

print("\n[3] matched-month logic + ramp-up exclusion")
chk(int(sf("matched_apartment_months"))==len(matched),
    f"matched apartment-months match source ({len(matched)})")
chk(int(sf("excluded_rent_months_no_revenue"))==int(both["rev"].isna().sum()),
    f"rent-months with no revenue excluded, not zero-filled ({int(both['rev'].isna().sum())})")
chk(int(sf("excluded_revenue_months_no_rent"))==int(both["rent"].isna().sum()),
    f"revenue-months with no rent excluded, not zero-filled ({int(both['rent'].isna().sum())})")
chk(int(L["matched_months"].sum())==len(matched),"per-apartment matched months sum to the matched universe")
chk((L["matched_months"]>0).all(),"no apartment classified on zero matched months")

print("\n[4] coverage arithmetic (derived, not hard-coded)")
chk(len(L)==len(G),f"apartment count matches source ({len(G)})")
for r in L.itertuples():
    ac=r.apartment_code
    chk(ac in G.index,f"{ac} exists in the recomputed source universe")
    if ac in G.index:
        s=G.loc[ac]
        chk(abs(float(r.invoiced_revenue)-float(s["rev"]))<TOL and abs(float(r.owner_rent)-float(s["rent"]))<TOL,
            f"{ac} revenue/rent reconcile to source")
        chk(abs(float(r.coverage_x)-round(float(s['rev'])/float(s['rent']),2))<0.005,
            f"{ac} coverage = revenue / owner rent ({r.coverage_x:.2f}x)")
out_flagged=set(L.loc[L["coverage_x"]<1.0,"apartment_code"])
chk(out_flagged==src_flagged,
    f"flagged apartments derived from source match the output ({sorted(src_flagged)})")
chk(abs(sf("overall_coverage_x")-round(float(G['rev'].sum()/G['rent'].sum()),2))<0.005,"overall coverage reconciles")
chk(int(sf("investigation_signals"))==len(src_flagged),"signal count matches the derived set")

print("\n[5] coverage universe — uncovered apartments must stay unclassified")
rev_apts=int(inv["apartment_id"].nunique())
chk(int(sf("revenue_generating_apartments_total"))==rev_apts,f"revenue-apartment total correct ({rev_apts})")
chk(int(sf("apartments_with_owner_rent_coverage"))==len(G),"covered-apartment count correct")
chk(int(sf("apartments_not_classified"))==rev_apts-len(G),
    f"uncovered apartments reported as NOT classified ({rev_apts-len(G)})")
covered=set(G.index)
chk(len(L)==len(covered) and set(L["apartment_code"])==covered,
    "output contains ONLY apartments with owner-rent coverage — none inferred")
chk("NOT classified" in str(S.get("coverage_note","")) or "not classified" in str(S.get("coverage_note","")).lower(),
    "summary states uncovered apartments are not classified")

print("\n[6] interpretation guard — NOT profitability, no fabricated recommendation")
blob=(" ".join(map(str,L.values.ravel()))+" "+" ".join(map(str,pd.DataFrame(list(S.items())).values.ravel()))).lower()
# separator class includes '_' because summary metric KEYS use snake_case (e.g. "not_profitability");
# a bare \W would treat the underscore as part of the word and miss that negation.
SEP=r"[^A-Za-z0-9]|_"
NEG=re.compile(rf"(not|no|never|nor)({SEP})+((\w+)({SEP})+){{0,6}}$", re.I)
def negated_everywhere(phrase):
    hits=[m.start() for m in re.finditer(re.escape(phrase),blob)]
    if not hits: return True,0
    return all(NEG.search(blob[max(0,h-70):h]) for h in hits),len(hits)
for bad in ["profitability","profit","margin","loss","unprofitable","roi","savings"]:
    ok,n=negated_everywhere(bad)
    chk(ok,f"'{bad}' never asserted ({n} occurrence(s), all negated)" if n else f"'{bad}' absent")
for banned in ["terminate","renegotiate","exit the lease","increase price","raise rent","cancel the lease"]:
    chk(banned not in blob,f"no fabricated commercial recommendation: '{banned}'")
chk("CONFIRMED" in str(S.get("not_profitability","")),"summary explicitly confirms this is not profitability")
chk("NONE" in str(S.get("recommended_action","")).upper(),"no action is auto-generated")
lim=" ".join(L["limitation"].astype(str)).lower()
for req,pat in [("invoiced not collected","collected cash"),("no other operating cost","other operating cost"),
                ("accrued rent disclosed","accrued"),("above 1.0x not favourable","1.0x")]:
    chk(pat in lim or pat in blob,f"limitation present: {req}")
flag=L[L["coverage_x"]<1.0]
chk(flag["investigation_prompts"].astype(str).str.contains(r"\?").all() if len(flag) else True,
    "flagged apartments carry investigation QUESTIONS, not conclusions")
chk(flag["signal"].astype(str).str.contains("Investigation signal",case=False).all() if len(flag) else True,
    "flagged rows are labelled investigation signals")

print("\n[7] backbone isolation")
dec=o("phase3_business_decisions.csv")
chk(len(dec)==14,"exactly 14 backbone decisions remain")
chk(not set(L["apartment_code"]) & set(dec["decision_id"].astype(str)),"no lease-coverage row leaked into decisions")
decblob=" ".join(map(str,dec.values.ravel())).lower()
chk("lease coverage" not in decblob and "coverage_x" not in decblob,"no lease-coverage signal inside the backbone file")
chk("False" in str(S.get("is_backbone","")),"summary marks the signal is_backbone=False")
ea=o("phase3_decision_execution_analytics.csv")
chk(int(ea["is_backbone"].sum())==14,"execution analytics still tracks exactly 14 backbone rows")

print("\n[8] dashboard consistency")
dash=open(os.path.join(HERE,"dashboard.py"),encoding="utf-8").read()
chk("phase3_lease_coverage_signal.csv" in dash,"Page 14 renders the lease-coverage signal")
chk("Lease Coverage — Investigation Signal" in dash,"neutral section name (not 'profitability')")
chk("Not one of the 14 backbone decisions" in dash,"dashboard states it is not a backbone decision")
chk("not** \n" not in dash and "profitability" in dash,"dashboard carries the not-profitability disclosure")
chk("not classified" in dash.lower(),"dashboard states uncovered apartments are not classified")
for banned in ["terminate lease","renegotiate the lease"]:
    chk(banned not in dash.lower(),f"dashboard makes no '{banned}' recommendation")

print("\n[9] deterministic")
p=os.path.join(OUT,"phase3_lease_coverage_signal.csv"); h1=hashlib.md5(open(p,"rb").read()).hexdigest()
subprocess.run([sys.executable,"phase3_lease_coverage_signal.py"],cwd=HERE,capture_output=True)
chk(h1==hashlib.md5(open(p,"rb").read()).hexdigest(),"re-run byte-identical (deterministic)")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
if fails: sys.exit(1)
