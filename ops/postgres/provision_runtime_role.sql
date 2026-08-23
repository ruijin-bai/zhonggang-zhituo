\set ON_ERROR_STOP on

-- Usage:
--   psql "$MIGRATION_DATABASE_URL" \
--     --set=runtime_role=zhituo_runtime \
--     --set=runtime_password='secret-from-manager' \
--     --set=backup_role=zhituo_backup \
--     --set=backup_password='another-secret' \
--     -f ops/postgres/provision_runtime_role.sql
--
-- Run as migration_owner / database administrator after Alembic migrations.

DO $block$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'runtime_role') THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', :'runtime_role', :'runtime_password');
    ELSE
        EXECUTE format('ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', :'runtime_role', :'runtime_password');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'backup_role') THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', :'backup_role', :'backup_password');
    ELSE
        EXECUTE format('ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', :'backup_role', :'backup_password');
    END IF;
END
$block$;

GRANT CONNECT ON DATABASE :DBNAME TO :"runtime_role", :"backup_role";
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

-- Identity values and audit/action/event tables use sequences.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"runtime_role";

-- Backup reader is read-only. Table owner/migration role is intentionally separate.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"backup_role";

-- Make privilege intent explicit. Runtime must never bypass RLS.
ALTER ROLE :"runtime_role" NOBYPASSRLS;
ALTER ROLE :"backup_role" NOBYPASSRLS;

\echo 'Runtime and backup roles provisioned. Verify runtime user is NOT a table owner and passes RLS smoke tests.'
