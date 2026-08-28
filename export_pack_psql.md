# Vishful full export — psql \copy pack (alternative to export_vishful.py)

`\copy` is a **client-side** psql command → use the `psql` CLI (NOT the Supabase web SQL editor, which cannot write files).
Get the connection string: Supabase → Project Settings → Database → Connection string (URI form).

```bash
# 0) folders (run from the parent dir where you want the export)
mkdir -p vishful_full_export/tables vishful_full_export/views vishful_full_export/metadata
export DB="postgresql://<user>:<password>@<host>:5432/<db>"   # keep this local

# 1) generate \copy lines for EVERY base table + EVERY view -> gen_copy.sql
psql "$DB" -At -o gen_copy.sql -c "
SELECT format('\copy (SELECT * FROM %I.%I) TO ''vishful_full_export/tables/%I.csv'' WITH (FORMAT CSV, HEADER TRUE)', schemaname, tablename, tablename)
FROM pg_tables  WHERE schemaname='public'
UNION ALL
SELECT format('\copy (SELECT * FROM %I.%I) TO ''vishful_full_export/views/%I.csv'' WITH (FORMAT CSV, HEADER TRUE)', schemaname, viewname, viewname)
FROM pg_views  WHERE schemaname='public';
"

# 2) run the generated exports (ON_ERROR_STOP=0 so one bad view doesn't abort the rest)
psql "$DB" -v ON_ERROR_STOP=0 -f gen_copy.sql

# 3) EXACT COUNT(*) for every table -> one \copy line -> table_counts.csv
psql "$DB" -At -o gen_counts.sql -c "
SELECT '\copy (' ||
  string_agg(format('SELECT %L::text AS table_name, count(*) AS exact_rows FROM %I.%I', tablename, schemaname, tablename), ' UNION ALL ' ORDER BY tablename)
  || ') TO ''vishful_full_export/metadata/table_counts.csv'' WITH (FORMAT CSV, HEADER TRUE)'
FROM pg_tables WHERE schemaname='public';
"
psql "$DB" -f gen_counts.sql

# 4) metadata: columns, foreign keys, view definitions
psql "$DB" -c "\copy (SELECT table_schema,table_name,ordinal_position,column_name,data_type,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position) TO 'vishful_full_export/metadata/columns.csv' WITH (FORMAT CSV, HEADER TRUE)"

psql "$DB" -c "\copy (SELECT tc.table_schema,tc.table_name,tc.constraint_name,tc.constraint_type,kcu.column_name,ccu.table_name AS foreign_table_name,ccu.column_name AS foreign_column_name FROM information_schema.table_constraints tc LEFT JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema LEFT JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name=ccu.constraint_name AND tc.table_schema=ccu.table_schema WHERE tc.table_schema='public' AND tc.constraint_type IN ('PRIMARY KEY','FOREIGN KEY') ORDER BY tc.table_name,tc.constraint_type) TO 'vishful_full_export/metadata/foreign_keys.csv' WITH (FORMAT CSV, HEADER TRUE)"

psql "$DB" -c "\copy (SELECT schemaname,viewname,definition FROM pg_views WHERE schemaname='public' ORDER BY viewname) TO 'vishful_full_export/metadata/view_definitions.csv' WITH (FORMAT CSV, HEADER TRUE)"
```

## 5) objects list + verification
```bash
psql "$DB" -c "\copy (SELECT table_schema,table_name,table_type FROM information_schema.tables WHERE table_schema='public' ORDER BY table_type,table_name) TO 'vishful_full_export/metadata/objects.csv' WITH (FORMAT CSV, HEADER TRUE)"

# verify: DB object count vs exported file count
echo "DB base tables:"; psql "$DB" -At -c "SELECT count(*) FROM pg_tables  WHERE schemaname='public'"
echo "DB views:";       psql "$DB" -At -c "SELECT count(*) FROM pg_views   WHERE schemaname='public'"
echo "CSV in tables/:"; ls vishful_full_export/tables/*.csv 2>/dev/null | wc -l
echo "CSV in views/:";  ls vishful_full_export/views/*.csv  2>/dev/null | wc -l
# empties (header-only files)
for f in vishful_full_export/tables/*.csv vishful_full_export/views/*.csv; do
  [ "$(wc -l < "$f")" -le 1 ] && echo "EMPTY: $f"; done
```

## CRITICAL — Supabase gotcha
- **Server-side `COPY (...) TO '/path/file.csv'` FAILS on Supabase** (managed Postgres, no server filesystem / not superuser). Your pasted `COPY ... TO STDOUT` streams to the client and cannot fan out into per-object files from the web SQL editor.
- **Use client-side `\copy` via the `psql` CLI** (above) or `export_vishful.py`. Both write real files to YOUR machine and auto-discover every object — no hardcoded names.

Notes:
- Filenames == table/view names. Tables and views in separate folders.
- No filter/limit/aggregation/transform; NULLs preserved; empty tables produce a header-only CSV.
- Contains PII + financial data → keep the folder local; do not upload publicly.
