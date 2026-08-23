#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set}"

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASENAME="zhituo-${TIMESTAMP}.dump"
TMP_FILE="${BACKUP_DIR}/.${BASENAME}.tmp"
FINAL_FILE="${BACKUP_DIR}/${BASENAME}"
CHECKSUM_FILE="${FINAL_FILE}.sha256"

mkdir -p "${BACKUP_DIR}"
umask 077

cleanup() {
  rm -f "${TMP_FILE}"
}
trap cleanup EXIT

pg_dump \
  --format=custom \
  --compress=6 \
  --no-owner \
  --no-acl \
  --file="${TMP_FILE}" \
  "${DATABASE_URL}"

# A backup that cannot be parsed by pg_restore is not considered successful.
pg_restore --list "${TMP_FILE}" >/dev/null
mv "${TMP_FILE}" "${FINAL_FILE}"
sha256sum "${FINAL_FILE}" > "${CHECKSUM_FILE}"

# Local retention is a convenience only; production object-storage lifecycle rules remain authoritative.
if [[ "${RETENTION_DAYS}" =~ ^[0-9]+$ ]] && (( RETENTION_DAYS > 0 )); then
  find "${BACKUP_DIR}" -type f \( -name 'zhituo-*.dump' -o -name 'zhituo-*.dump.sha256' \) \
    -mtime "+${RETENTION_DAYS}" -delete
fi

printf 'backup=%s\nchecksum=%s\n' "${FINAL_FILE}" "${CHECKSUM_FILE}"
