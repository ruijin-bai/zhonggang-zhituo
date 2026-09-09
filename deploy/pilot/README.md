# Zhituo Oracle Internal Pilot

This layer is intentionally separate from `deploy/staging` and the external-infrastructure
`deploy/docker-compose.production.yml`. It runs the existing Compose architecture on one ARM64
host as a persistent Production Alpha / Internal Pilot.

## Runtime contract

- `APP_ENV=production`, database backend, PostgreSQL RLS, queued jobs, no demo mode or fallback.
- PostgreSQL, Redis, MinIO, Celery Worker and the single Celery Beat are mandatory.
- PostgreSQL, Redis, MinIO, Beat and Caddy state use stable named volumes.
- PostgreSQL, Redis, MinIO and FastAPI have no host or public ports.
- MinIO uses a locally generated TLS certificate; API/Worker trust only that certificate.
- Caddy exposes only Web on `127.0.0.1:8080` by default, strips caller-supplied Zhituo identity
  headers, requires Basic Auth, and injects the configured Pilot administrator identity.
- Cloudflare Tunnel is optional and outbound-only. Configure Cloudflare Access before adding its
  token; the tunnel must route only to `http://caddy:8080`.

## First start

On Ubuntu ARM64 with Docker Engine, Compose v2, Git and OpenSSL:

```bash
PILOT_ADMIN_EMAIL=owner@example.com bash scripts/pilot-up.sh
```

The script creates `deploy/pilot/.env` with mode `0600`, strong random credentials, a MinIO TLS
certificate and immutable image tags based on Git SHA. It never seeds demo opportunities. Save the
printed Basic Auth password in the operator password manager.

For a loopback-only Oracle VM, use SSH forwarding:

```bash
ssh -L 8080:127.0.0.1:8080 ubuntu@VM_IP
```

Then open `http://127.0.0.1:8080`. Do not open 3000, 8000, 5432, 6379, 9000 or 9001 in OCI.

## Operations

```bash
bash scripts/pilot-health.sh
bash scripts/pilot-logs.sh api
bash scripts/pilot-backup.sh
bash scripts/pilot-restore.sh /var/lib/zhituo/backups/pilot-YYYYMMDDTHHMMSSZ --minio-drill
bash scripts/pilot-real-source.sh Zambia 5
bash scripts/pilot-down.sh
```

`pilot-health.sh` returns non-zero on required failures and checks PostgreSQL, authenticated Redis,
TLS MinIO, FastAPI live/ready, Web -> BFF -> API, Worker and Beat. No recorded source scan is a warning
until the first real-source run.

Backups contain a PostgreSQL custom dump, MinIO archive and SHA-256 manifest. Restore defaults to a
new isolated database and optional new MinIO drill volume; it refuses the live `zhituo` database.
Normal shutdown and upgrade never use `docker compose down -v`.

## Upgrade and rollback

After a normal `git pull`, deploy the current checkout:

```bash
bash scripts/pilot-update.sh
```

Or deploy a SHA already reachable from `origin/main`:

```bash
bash scripts/pilot-update.sh <git-sha>
```

The script builds SHA-tagged images, takes a backup, migrates, reapplies least-privilege roles,
restarts and runs health checks. `bash scripts/pilot-update.sh --rollback` switches back to the
previous application images. It deliberately does not auto-downgrade the database; use the verified
pre-migration backup for an explicit schema/data rollback.

## Reboot recovery

Every long-running service uses `restart: unless-stopped`. Oracle cloud-init also installs
`zhituo-pilot.service`; after the repository exists at `/opt/zhituo/current`, enable it with:

```bash
sudo systemctl enable --now zhituo-pilot.service
```

Always run `pilot-health.sh` after a reboot. A restore drill should remain a scheduled operator task;
a backup file alone is not evidence that recovery works.
