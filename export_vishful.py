"""
Vishful full DB export -> CSV (every table + every view + metadata).
NO table selection, NO column exclusion, NO WHERE/LIMIT. Empty & legacy tables included.

USAGE (PowerShell):
    pip install "sqlalchemy>=2" psycopg2-binary pandas
    $env:VISHFUL_DB_URL = "postgresql://<user>:<password>@<host>:5432/<db>"   # Supabase: Project Settings > Database > Connection string (URI)
    python export_vishful.py

Output folder (created next to this script):
    vishful_full_export/tables/<table>.csv
    vishful_full_export/views/<view>.csv
    vishful_full_export/metadata/{table_counts.csv, columns.csv, foreign_keys.csv, view_definitions.csv, export_log.csv}

NOTE: export contains PII + financial data. Keep the folder LOCAL. Do not upload anywhere public.
"""
import os, sys, datetime
import pandas as pd

try:
    import sqlalchemy as sa
except ImportError:
    sys.exit("Install deps first:  pip install \"sqlalchemy>=2\" psycopg2-binary pandas")

DB_URL = os.environ.get("VISHFUL_DB_URL")
if not DB_URL:
    sys.exit("Set VISHFUL_DB_URL env var to the Vishful Postgres/Supabase connection string first.")

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vishful_full_export")
for sub in ("tables", "views", "metadata"):
    os.makedirs(os.path.join(BASE, sub), exist_ok=True)

eng = sa.create_engine(DB_URL)
log = []

COLS_SQL = """
SELECT table_schema, table_name, ordinal_position, column_name, data_type, udt_name,
       is_nullable, column_default
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog','information_schema')
ORDER BY table_schema, table_name, ordinal_position;"""

FK_SQL = """
SELECT tc.table_schema, tc.table_name, tc.constraint_name, tc.constraint_type,
       kcu.column_name,
       ccu.table_schema AS foreign_table_schema, ccu.table_name AS foreign_table_name,
       ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema
LEFT JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name=ccu.constraint_name AND tc.table_schema=ccu.table_schema
WHERE tc.table_schema NOT IN ('pg_catalog','information_schema')
  AND tc.constraint_type IN ('PRIMARY KEY','FOREIGN KEY')
ORDER BY tc.table_name, tc.constraint_type, kcu.column_name;"""

VIEWDEF_SQL = """
SELECT schemaname, viewname, definition FROM pg_views
WHERE schemaname='public' ORDER BY viewname;"""

def dump(conn, name, kind):
    folder = "tables" if kind == "table" else "views"
    try:
        df = pd.read_sql(sa.text(f'SELECT * FROM public."{name}"'), conn)
        path = os.path.join(BASE, folder, f"{name}.csv")
        df.to_csv(path, index=False)
        log.append((kind, name, len(df), "ok", ""))
        print(f"[{kind:5}] {name:40} {len(df):>8} rows")
        return name, len(df)
    except Exception as e:
        log.append((kind, name, -1, "FAIL", str(e)[:200]))
        print(f"[{kind:5}] {name:40} FAILED: {str(e)[:80]}")
        return name, None

with eng.connect() as c:
    tables = pd.read_sql(sa.text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"), c)["tablename"].tolist()
    views = pd.read_sql(sa.text(
        "SELECT viewname FROM pg_views WHERE schemaname='public' ORDER BY viewname"), c)["viewname"].tolist()

    print(f"Exporting {len(tables)} tables + {len(views)} views ...")
    counts = [dump(c, t, "table") for t in tables]
    for v in views:
        dump(c, v, "view")

    # metadata
    pd.DataFrame([(t, n) for t, n in counts], columns=["table_name", "exact_rows"]) \
        .to_csv(os.path.join(BASE, "metadata", "table_counts.csv"), index=False)
    pd.read_sql(sa.text(COLS_SQL), c).to_csv(os.path.join(BASE, "metadata", "columns.csv"), index=False)
    pd.read_sql(sa.text(FK_SQL), c).to_csv(os.path.join(BASE, "metadata", "foreign_keys.csv"), index=False)
    pd.read_sql(sa.text(VIEWDEF_SQL), c).to_csv(os.path.join(BASE, "metadata", "view_definitions.csv"), index=False)
    # objects.csv = every base table + view with type
    pd.read_sql(sa.text("""SELECT table_schema, table_name, table_type FROM information_schema.tables
        WHERE table_schema='public' ORDER BY table_type, table_name"""), c) \
        .to_csv(os.path.join(BASE, "metadata", "objects.csv"), index=False)

logdf = pd.DataFrame(log, columns=["kind", "name", "rows", "status", "error"])
logdf.to_csv(os.path.join(BASE, "metadata", "export_log.csv"), index=False)

# ---------- verification ----------
n_tab_db, n_view_db = len(tables), len(views)
tab_ok  = logdf[(logdf.kind=="table") & (logdf.status=="ok")]
view_ok = logdf[(logdf.kind=="view")  & (logdf.status=="ok")]
failed  = logdf[logdf.status=="FAIL"]
empty   = logdf[(logdf.status=="ok") & (logdf.rows==0)]
print("\n" + "="*60)
print("EXPORT VERIFICATION")
print("="*60)
print(f"BASE TABLES: db={n_tab_db}  exported_ok={len(tab_ok)}  " + ("MATCH" if n_tab_db==len(tab_ok) else "*** MISMATCH ***"))
print(f"VIEWS      : db={n_view_db}  exported_ok={len(view_ok)}  " + ("MATCH" if n_view_db==len(view_ok) else "*** MISMATCH ***"))
print(f"EMPTY (0 rows, exported): {len(empty)}  -> {', '.join(empty.name.tolist()) or '(none)'}")
print(f"FAILED: {len(failed)}  -> {', '.join(failed.name.tolist()) or '(none)'}")
print(f"\nDONE  {datetime.datetime.now():%Y-%m-%d %H:%M}   Folder: {BASE}")
print("Reports: metadata/export_log.csv (per-object status), metadata/objects.csv, metadata/table_counts.csv")
