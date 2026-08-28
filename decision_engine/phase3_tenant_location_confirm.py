"""
Tenant Location Confirmation — APPEND-ONLY writer (operational/mutable — NOT a locked deterministic
output). Store lives OUTSIDE outputs/ (decision_engine/operational/phase3_tenant_location_confirmations.csv)
so run_all --verify never treats it as a locked artifact, exactly mirroring the pattern already
established for owner outcome events in phase4_action_capture.py.

This is the write path for the "Active Tenant Location Data Capture" business action: ops staff
collect State + City + Pincode DIRECTLY FROM THE TENANT (phone/WhatsApp/in person — the collection
channel is a business process outside this pipeline) and enter the confirmed values here. This is the
STRONGEST evidence tier in phase3_tenant_origin.py's resolution hierarchy — stronger than any stored
field or address inference — because it is current, tenant-supplied, and collected for exactly this
purpose. It overrides even a stale/incorrect stored address (e.g. the Vishful-property-address case).

Every confirmation is a NEW appended row; existing rows are NEVER edited or deleted. A correction
appends a new row referencing supersedes_confirmation_id. The latest row per tenant_id wins.

SCOPE NOTE: this project is a read-only CSV-export pipeline with no live connection to the source
application's database. "The proper tenant profile field" is therefore implemented as this project's
own validated, auditable confirmation store — the authoritative evidence source for Tenant Origin
analytics until/unless the source application's own tenant record is separately updated by the app
team. Writing back into the live app database is outside this pipeline's scope.

Validation is FAIL-LOUD: an invalid state, missing city, or malformed pincode raises ValueError and
is never silently coerced or guessed.
"""
from __future__ import annotations
import os, sys, csv, re
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
OPDIR = os.path.join(HERE, "operational")
STORE = os.path.join(OPDIR, "phase3_tenant_location_confirmations.csv")

COLUMNS = ["confirmation_id", "tenant_id", "confirmed_state", "confirmed_city", "confirmed_pincode",
           "pincode_state_consistent", "confirmed_by", "confirmed_at", "notes",
           "supersedes_confirmation_id"]
PIN_RX = re.compile(r"[1-9]\d{5}")


def _valid_tenant_ids():
    import loader
    D, _ = loader.load_all()
    return set(D["tenants"]["id"].astype(str))


def ensure_store(store=STORE):
    os.makedirs(os.path.dirname(store), exist_ok=True)
    if not os.path.exists(store):
        with open(store, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(COLUMNS)
    return store


def _rows(store=STORE):
    if not os.path.exists(store):
        return []
    with open(store, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _next_id(store=STORE):
    n = 0
    for r in _rows(store):
        try:
            n = max(n, int(str(r["confirmation_id"]).split("-")[1]))
        except Exception:
            pass
    return f"TLC-{n + 1:06d}"


def latest_confirmations(store=STORE):
    """One row per tenant_id — the most recent confirmation (append-only; last write wins).
    Returns an empty DataFrame with the right columns if the store does not exist yet."""
    rows = _rows(store)
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(rows)
    # confirmation_id is monotonically increasing (TLC-000001, TLC-000002, ...) — last one per
    # tenant_id in file order is the latest, since rows are only ever appended.
    df = df.drop_duplicates(subset="tenant_id", keep="last")
    return df.reset_index(drop=True)


def append_confirmation(ev: dict, store=STORE, confirmed_at=None, confirmed_by=None):
    """Append one confirmation. Raises ValueError on any invalid/missing required field — never
    silently coerces or guesses. Returns the new confirmation_id."""
    import phase3_tenant_origin as G

    tenant_id = str(ev.get("tenant_id") or "").strip()
    if not tenant_id:
        raise ValueError("tenant_id is required")
    if tenant_id not in _valid_tenant_ids():
        raise ValueError(f"tenant_id {tenant_id!r} does not exist in the tenants table")

    raw_state = str(ev.get("confirmed_state") or "").strip()
    state = G.norm_state(raw_state)
    if not state:
        raise ValueError(f"confirmed_state {raw_state!r} is not a recognised Indian state/UT — "
                         "never guessed or coerced")

    city = str(ev.get("confirmed_city") or "").strip()
    if not city:
        raise ValueError("confirmed_city is required")

    pin = str(ev.get("confirmed_pincode") or "").strip().replace(" ", "")
    if not PIN_RX.fullmatch(pin):
        raise ValueError(f"confirmed_pincode {pin!r} is not a valid 6-digit Indian pincode")

    by = str(confirmed_by or ev.get("confirmed_by") or "").strip()
    if not by:
        raise ValueError("confirmed_by (who collected this from the tenant) is required")

    # cross-check only — does NOT block the write. Tenant-supplied evidence is trusted even when it
    # disagrees with the coarse postal-circle heuristic; the flag is recorded for visibility only.
    pin_state = G.pin_state(pin)
    consistent = (pin_state == state) if pin_state else None

    ensure_store(store)
    cid = _next_id(store)
    row = {
        "confirmation_id": cid,
        "tenant_id": tenant_id,
        "confirmed_state": state,
        "confirmed_city": city,
        "confirmed_pincode": pin,
        "pincode_state_consistent": ("" if consistent is None else str(consistent)),
        "confirmed_by": by,
        "confirmed_at": confirmed_at or pd.Timestamp.utcnow().isoformat(),
        "notes": str(ev.get("notes") or "").strip(),
        "supersedes_confirmation_id": str(ev.get("supersedes_confirmation_id") or ""),
    }
    with open(store, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=COLUMNS).writerow(row)
    return cid


if __name__ == "__main__":
    ensure_store()
    df = latest_confirmations()
    print(f"TENANT LOCATION CONFIRMATIONS: {len(_rows())} total rows, {len(df)} distinct tenants confirmed")
    if len(df):
        print(df[["tenant_id", "confirmed_state", "confirmed_city", "confirmed_pincode",
                  "confirmed_by", "confirmed_at"]].to_string(index=False))
