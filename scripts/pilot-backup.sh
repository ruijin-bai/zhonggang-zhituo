#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/lib/pilot-common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/pilot-common.sh"

pilot_require_command docker
pilot_require_command sha256sum
pilot_load_env

[[ -d "$PILOT_BACKUP_DIR" ]] || mkdir -p "$PILOT_BACKUP_DIR"
chmod 700 "$PILOT_BACKUP_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
package_dir="$PILOT_BACKUP_DIR/pilot-${timestamp}"
mkdir -p "$package_dir"
chmod 700 "$package_dir"

pilot_info "Backing up PostgreSQL with the least-privilege backup role"
docker run --rm \
  --network zhituo-pilot-backend \
  -e "DATABASE_URL=postgresql://zhituo_backup:${POSTGRES_BACKUP_PASSWORD}@postgres:5432/zhituo" \
  -e BACKUP_DIR=/backups \
  -e RETENTION_DAYS=0 \
  -v "$PILOT_ROOT_DIR/ops/postgres/backup.sh:/opt/zhituo/backup.sh:ro" \
  -v "$package_dir:/backups" \
  postgres:17-alpine sh /opt/zhituo/backup.sh

pilot_info "Backing up the MinIO data volume"
docker run --rm \
  -v zhituo-pilot-minio:/source:ro \
  -v "$package_dir:/backups" \
  alpine:3.22.1 \
  tar -C /source -czf "/backups/minio-${timestamp}.tar.gz" .

(
  cd "$package_dir"
  sha256sum ./* > SHA256SUMS
)

retention_days="${PILOT_BACKUP_RETENTION_DAYS:-14}"
if [[ "$retention_days" =~ ^[0-9]+$ ]] && (( retention_days > 0 )); then
  find "$PILOT_BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -name 'pilot-*' \
    -mtime "+${retention_days}" -exec rm -rf -- {} +
fi

printf 'PASS  backup=%s\n' "$package_dir"
