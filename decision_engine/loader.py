"""
CSV loader for the Vishful decision engine.
Source of truth = the exported CSVs in the parent 'Business Decision' folder.
Files are named 'Supabase Snippet Untitled query (N).csv' etc., so we identify each
table/view by matching its HEADER column-set against a known signature (robust to renames).
Read-only. Never writes to source CSVs.
"""
from __future__ import annotations
import os, glob
import pandas as pd

DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the Business Decision folder

# canonical table/view -> distinctive columns that MUST all be present in the header
SIG = {
 # base tables
 "properties":        {"property_name","gps_latitude","pincode"},
 "apartments":        {"apartment_code","floor_number","gender_allowed"},
 "beds":              {"bed_code","bed_type","toilet_type","bed_lifecycle_status"},
 "bed_rates":         {"bed_type","toilet_type","monthly_rate","from_date"},
 "tenant_allotments": {"booking_date","monthly_rental","bed_id","tenant_id","actual_exit_date"},
 "tenants":           {"full_name","gender","food_preference","staying_status"},
 "invoices":          {"invoice_number","rent_amount","electricity_amount","total_amount","balance"},
 "invoice_line_items":{"invoice_id","line_type","amount","description"},
 "receipts":          {"receipt_number","amount_paid","payment_mode","tenant_allotment_id"} ,
 "tenant_transactions":{"direction","ledger_type","category","reference_table"},
 "tenant_adjustments":{"adjustment_type","amount","adjustment_date","reason"},
 "deposit_settlements":{"deposit_amount","pending_rent","refund_amount","total_deductions"},
 "tenant_notices":    {"notice_date","exit_date","actual_exit_date","status"},
 "tenant_exits":      {"exit_date","has_notice","room_inspection","damage_charges"},
 "room_switches":     {"old_bed_id","new_bed_id","switch_type","switch_date"},
 "expenses":          {"expense_date","amount","category_id","billing_month"},
 "expense_bed_allocations":{"expense_id","bed_id","allocated_amount"},
 "journal_entries":   {"entry_date","period","source_table","is_reversal_of"},
 "journal_lines":     {"journal_entry_id","account_id","debit","credit"},
 "coa_accounts":      {"code","name","account_type","normal_balance"},
 "owners":            {"full_name","pan_number","aadhar_number","bank_name"},
 "owner_contracts":   {"owner_id","contract_type","monthly_rent","revenue_share_percentage"},
 "owner_payments":    {"owner_id","contract_id","payment_month","base_amount","escalated_amount"},
 "electricity_readings":{"reading_start","reading_end","units_consumed","billing_month"},
 "eb_tenant_shares":  {"total_apartment_bill","tenant_eb_charge","per_day_rate"},
 "eb_payments":       {"bill_date","bill_amount","payment_date","billing_period_start"},
 "maintenance_tickets":{"ticket_number","issue_type_id","priority","status"},
 "issue_types":       {"name","priority","sla_hours"},
 "ticket_resolutions":{"resolution_type","total_cost","resolved_at"},
 "assets":            {"asset_code","asset_type_id","serial_number","purchase_date"},
 "asset_allocations": {"asset_id","allocation_type","allocated_date","bed_id"},
 "asset_types":       {"name","category_id","expected_life_months"},
 # views
 "v_pnl_by_category": {"revenue","rental_income","owner_rent","total_expenses","month"},
 "v_revenue_by_period":{"month","account_code","account_name","revenue"},
 "v_expenses_by_period":{"month","account_code","account_name","expense"},
 "v_bed_expense_breakdown":{"bed_id","month","category_code","amount"},
 "v_tenant_aging":    {"bucket_0_30","bucket_31_60","bucket_90_plus","total"},
 "v_tenant_current_dues":{"ar_balance","deposit_held","booking_advance","net_dues","last_payment_date"},
 "v_outstanding_receivables":{"outstanding","last_charge_date","last_payment_date"},
 "v_tenant_ledger":   {"journal_entry_id","account_code","debit","credit","running_balance"},
 "v_invoice_settlement_status":{"invoice_amount","amount_settled","amount_outstanding","settlement_status"},
 "v_occupancy":       {"total_beds","occupied","vacant","occupancy_pct"},
 "v_tenant_lifecycle_events":{"event_date","event","staying_status"},
 "v_org_cash_balance":{"cash_on_hand"},
 "v_trial_balance":   {"account_code","account_type","total_debit","total_credit","balance"},
 "v_je_amount_reconciliation":{"source_table","legacy_amount","je_net_amount","diff","verdict"},
 "v_diag_allotment_balance_drift":{"allotment_id","stored_balance","computed_balance","drift"},
 "v_diag_invoice_drift":{"invoice_id","total_amount","amount_paid","balance","drift"},
}

def _score(header: set, must: set) -> int:
    return len(must) if must <= header else 0

def scan():
    """Return {table_name: (filepath, mtime)} best match per table."""
    found = {}
    for f in glob.glob(os.path.join(DATA_DIR, "*.csv")):
        try:
            hdr = set(pd.read_csv(f, nrows=0).columns)
        except Exception:
            continue
        for name, must in SIG.items():
            if _score(hdr, must):
                mt = os.path.getmtime(f)
                # keep newest file for each table (handles re-exports like eb_payments)
                if name not in found or mt > found[name][1]:
                    found[name] = (f, mt)
    return found

def load_all():
    idx = scan()
    data = {}
    for name, (f, _mt) in idx.items():
        data[name] = pd.read_csv(f, low_memory=False)
    missing = [t for t in SIG if t not in idx]
    return data, missing

def num(s):
    return pd.to_numeric(s, errors="coerce")

def to_dt(s):
    return pd.to_datetime(s, errors="coerce")

if __name__ == "__main__":
    d, miss = load_all()
    print(f"loaded {len(d)} objects")
    for k in sorted(d): print(f"  {k:34} {d[k].shape}")
    print("MISSING (not found in folder):", ", ".join(miss) if miss else "(none)")
