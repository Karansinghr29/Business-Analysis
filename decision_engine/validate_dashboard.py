"""Dashboard/integration validation (no UI render). Fails loudly.
Checks: every dataset loads + required cols present; labels apply; UUIDs hidden where a
label exists; stale file never in registry; app compiles. Prints a pass/fail matrix.
"""
from __future__ import annotations
import os, py_compile, sys
import pandas as pd
import dashboard as DB
from labels import build_maps
from validation import SourceValidationError

HERE=os.path.dirname(os.path.abspath(__file__))
UUID_COLS={"tenant_id","apartment_id","bed_id","issue_type_id"}
LABEL_OF={"tenant_id":"tenant_name","apartment_id":"apartment_code","bed_id":"bed_code","issue_type_id":"issue_type_name"}
rows=[]; fails=0

# 0. stale must not be referenced
stale_ref=[k for k,(fn,_) in DB.DATASETS.items() if fn in DB.STALE_BLOCKLIST]
rows.append(("stale-not-surfaced", "PASS" if not stale_ref else f"FAIL {stale_ref}"))
fails+=bool(stale_ref)

# 1. label maps build
try: build_maps(); rows.append(("labels build","PASS"))
except Exception as e: rows.append(("labels build",f"FAIL {e}")); fails+=1

# 2. each dataset: load + required cols + label + no-uuid-leak in displayed frame
for key,(fn,cols) in DB.DATASETS.items():
    try:
        df=DB.load.__wrapped__(key) if hasattr(DB.load,"__wrapped__") else pd.read_csv(os.path.join(HERE,"outputs",fn))
        from validation import require_columns; require_columns(df,fn,cols)
        disp=DB.show(df)
        leaked=[c for c in disp.columns if c in UUID_COLS and LABEL_OF[c] in disp.columns]
        # a labelled id present in display alongside its label = leak
        leak_ids=[c for c in UUID_COLS if c in disp.columns and LABEL_OF.get(c) in df.columns]
        status="PASS" if not leak_ids else f"FAIL uuid-leak {leak_ids}"
        rows.append((f"{key} ({fn})", status)); fails+=bool(leak_ids)
    except Exception as e:
        rows.append((f"{key} ({fn})", f"FAIL {e}")); fails+=1

# 3. app compiles
try: py_compile.compile(os.path.join(HERE,"dashboard.py"), doraise=True); rows.append(("dashboard.py compiles","PASS"))
except Exception as e: rows.append(("dashboard.py compiles",f"FAIL {e}")); fails+=1

print("="*70); print("DASHBOARD VALIDATION"); print("="*70)
for name,st in rows: print(f"  {'✓' if st=='PASS' else '✗'} {name:46} {st}")
print(f"\n{'ALL PASS' if fails==0 else str(fails)+' FAILURE(S)'}")
sys.exit(1 if fails else 0)
