#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/lib/pilot-common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/pilot-common.sh"

usage() {
  printf 'Usage: %s <pilot-backup-directory> [--target-database NAME] [--minio-drill]\n' "$0" >&2
  exit 2
}

[[ $# -ge 1 ]] || usage
backup_dir="$1"
shift
target_database="zhituo_restore_$(date -u +%Y%m%d%H%M%S)"
minio_drill=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-database)
      [[ $# -ge 2 ]] || usage
      target_database="$2"
      shift 2
      ;;
    --minio-drill)
      minio_drill=true
      shift
      ;;
    *) usage ;;
  esac
done

[[ "$target_database" =~ ^[A-Za-z][A-Za-z0-9_]{0,62}$ ]] || \
  pilot_fail "Target database must be a safe PostgreSQL identifier"
[[ "$target_database" != "zhituo" ]] || \
  pilot_fail "This script never overwrites the live zhituo database"
[[ -d "$backup_dir" ]] || pilot_fail "Backup directory does not exist: $backup_dir"

pilot_require_command docker
pilot_require_command sha256sum
pilot_load_env

(
  cd "$backup_dir"
  sha256sum --check SHA256SUMS
)

dump_file="$(find "$backup_dir" -maxdepth 1 -type f -name 'zhituo-*.dump' | head -n 1)"
[[ -n "$dump_file" ]] || pilot_fail "PostgreSQL dump not found"

exists="$(pilot_compose exec -T postgres psql -U zhituo_owner -d postgres -Atc \
  "SELECT 1 FROM pg_database WHERE datname = '$target_database';" | tr -d '\r')"
[[ "$exists" != "1" ]] || pilot_fail "Target database already exists: $target_database"

pilot_info "Creating isolated restore target: $target_database"
pilot_compose exec -T postgres createdb -U zhituo_owner "$target_database"

docker run --rm \
  --network zhituo-pilot-backend \
  -e "TARGET_DATABASE_URL=postgresql://zhituo_owner:${POSTGRES_OWNER_PASSWORD}@postgres:5432/${target_database}" \
  -e BACKUP_FILE=/backups/restore.dump \
  -e CONFIRM_RESTORE=YES \
  -v "$PILOT_ROOT_DIR/ops/postgres/restore.sh:/opt/zhituo/restore.sh:ro" \
  -v "$dump_file:/backups/restore.dump:ro" \
  postgres:17-alpine sh -ec \
  'sha256sum /backups/restore.dump > /backups/restore.dump.sha256; sh /opt/zhituo/restore.sh'

pilot_compose exec -T postgres psql -U zhituo_owner -d "$target_database" -Atc \
  "SELECT 'tables=' || count(*) FROM information_schema.tables WHERE table_schema='public';"

if [[ "$minio_drill" == "true" ]]; then
  minio_file="$(find "$backup_dir" -maxdepth 1 -type f -name 'minio-*.tar.gz' | head -n 1)"
  [[ -n "$minio_file" ]] || pilot_fail "MinIO archive not found"
  drill_volume="zhituo-pilot-minio-restore-$(date -u +%Y%m%d%H%M%S)"
  docker volume create "$drill_volume" >/dev/null
  docker run --rm \
    -v "$drill_volume:/restore" \
    -v "$minio_file:/backups/minio.tar.gz:ro" \
    alpine:3.22.1 tar -C /restore -xzf /backups/minio.tar.gz
  printf 'PASS  MinIO restore drill volume=%s (active MinIO was not touched)\n' "$drill_volume"
fi

printf 'PASS  PostgreSQL restore drill database=%s (live database was not touched)\n' "$target_database"
