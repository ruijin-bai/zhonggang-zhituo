\set ON_ERROR_STOP on

-- Usage (run as a DBA/migration administrator; BYPASSRLS assignment requires sufficient privilege):
--   psql "$MIGRATION_DATABASE_URL" \
--     --set=runtime_role=zhituo_runtime \
--     --set=runtime_password='secret-from-manager' \
--     --set=backup_role=zhituo_backup \
--     --set=backup_password='another-secret' \
--     -f ops/postgres/provision_runtime_role.sql
--
-- Re-run after migrations when new tables are added so explicit grants stay current.

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
    :'runtime_role', :'runtime_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'runtime_role')
\gexec

SELECT format(
    'ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
    :'runtime_role', :'runtime_password'
)
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'runtime_role')
\gexec

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS',
    :'backup_role', :'backup_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'backup_role')
\gexec

SELECT format(
    'ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS',
    :'backup_role', :'backup_password'
)
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'backup_role')
\gexec

GRANT CONNECT ON DATABASE :"DBNAME" TO :"runtime_role", :"backup_role";
GRANT USAGE ON SCHEMA public TO :"runtime_role", :"backup_role";

-- Identity/control-plane reads required before tenant context is selected.
GRANT SELECT ON TABLE organizations, users, memberships TO :"runtime_role";

-- Tenant-scoped business tables. RLS remains authoritative for runtime_role.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    opportunities,
    sources,
    evidence,
    score_snapshots,
    opportunity_events,
    ai_analyses,
    opportunity_drafts,
    watch_items,
    pursuit_actions,
    pursuit_alerts,
    idempotency_records
TO :"runtime_role";

-- Audit is append/read but never updated/deleted by the application.
GRANT SELECT, INSERT ON TABLE audit_logs TO :"runtime_role";

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"runtime_role";

-- backup_role is deliberately read-only but BYPASSRLS so a full database backup is complete.
-- Treat its credential as a high-sensitivity secret and never use it for API/Worker traffic.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"backup_role";
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO :"backup_role";

\echo 'Roles provisioned. Verify runtime_role is not a table owner and cannot see another tenant; verify backup_role has no DML grants.'
