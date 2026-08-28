"""Loud validation helpers for the integration layer."""
from __future__ import annotations

class SourceValidationError(RuntimeError): pass

def require_tables(D: dict, tables: list[str]):
    missing=[t for t in tables if t not in D or len(D[t])==0]
    if missing:
        raise SourceValidationError(f"Required source tables missing/empty: {missing}")

def require_columns(df, table: str, cols: list[str]):
    miss=[c for c in cols if c not in df.columns]
    if miss:
        raise SourceValidationError(f"Table '{table}' missing required columns: {miss}")
