#!/usr/bin/env bash
set -euo pipefail

: "${TARGET_DATABASE_URL:?TARGET_DATABASE_URL must be set}"
: "${BACKUP_FILE:?BACKUP_FILE must be set}"

if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo "Refusing restore. Set CONFIRM_RESTORE=YES after verifying the target database." >&2
  exit 2
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "Backup file does not exist: ${BACKUP_FILE}" >&2
  exit 2
fi

CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ -f "${CHECKSUM_FILE}" ]]; then
  sha256sum --check "${CHECKSUM_FILE}"
else
  echo "WARNING: checksum file not found; continuing only because restore was explicitly confirmed." >&2
fi

pg_restore --list "${BACKUP_FILE}" >/dev/null

ARGS=(
  --exit-on-error
  --no-owner
  --no-acl
  --dbname="${TARGET_DATABASE_URL}"
)

if [[ "${RESTORE_CLEAN:-false}" == "true" ]]; then
  ARGS+=(--clean --if-exists)
fi

pg_restore "${ARGS[@]}" "${BACKUP_FILE}"

# Verify the database is reachable and has an Alembic state after restore.
psql "${TARGET_DATABASE_URL}" -v ON_ERROR_STOP=1 -Atc \
  "SELECT version_num FROM alembic_version LIMIT 1;"

echo "Restore completed. Run application migrations and smoke tests before accepting traffic."
