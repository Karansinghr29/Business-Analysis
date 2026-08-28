"""Shared date-normalization utilities for the source date formats seen in Vishful CSVs.
Does not change any locked module; provided for the integration/dashboard layer.
"""
from __future__ import annotations
import pandas as pd

def to_naive(s):
    """Parse to datetime and drop timezone (source has mixed tz-aware/naive)."""
    d = pd.to_datetime(s, errors="coerce")
    try:
        if getattr(d.dt, "tz", None) is not None:
            d = d.dt.tz_localize(None)
    except Exception:
        pass
    return d

def parse_billing_month_mmm_yy(s):
    """electricity_readings.billing_month is 'MMM-YY' e.g. 'Apr-23' -> 2023-04-01."""
    return pd.to_datetime(s.astype(str), format="%b-%y", errors="coerce")

def parse_billing_month_ym(s):
    """invoices/v_pnl_by_category billing month is 'YYYY-MM' or 'YYYY-MM-01'."""
    return pd.to_datetime(s.astype(str), errors="coerce")
