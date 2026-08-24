# 智拓生产部署契约

## 1. 进程拓扑

生产环境至少拆分四个独立进程角色：

- `web`：Next.js / BFF；
- `api`：FastAPI；
- `worker`：Celery Worker；
- `beat`：Celery Beat，仅负责周期调度。

PostgreSQL、Redis、Ingress/WAF、Prometheus/Alertmanager 建议由独立基础设施提供，不与应用容器绑定生命周期。

示例编排：`deploy/docker-compose.production.yml`。

## 2. 网络边界

- API 不映射宿主机公网端口；
- Web 仅绑定 `127.0.0.1`，由宿主机反向代理/WAF 提供 TLS 与公网入口；
- Web 与 API 通过 `backend` 内部网络通信；
- API / Worker / Beat 同时加入独立 `egress` 网络，以访问 OIDC JWKS、AI Provider 和经批准的公开情报源；
- 正式云环境应进一步使用 Egress Policy / Firewall 限制允许访问的外部域名和端口。

## 3. Secret 最小权限

API/Worker/Beat 使用同一类后端运行 Secret，包括：

- runtime PostgreSQL credential；
- Redis credential；
- OIDC / trusted-proxy 配置；
- AI Provider credential；
- Metrics token（仅 API 实际使用，容器平台可进一步拆分）。

Web 使用独立环境文件，只应包含 BFF 所需配置，例如：

```bash
API_BASE_URL=http://api:8000
API_AUTH_MODE=trusted_proxy
API_TRUSTED_PROXY_SECRET=<secret>
NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=false
```

**Web 不应获得 DATABASE_URL、Redis 凭据或 AI Provider Key。**

正式环境不要把 `.env.production` 提交到仓库；由 Secret Manager/KMS/平台 Secret 注入。

## 4. 后端关键生产配置

```bash
APP_ENV=production
DATA_BACKEND=database
DEMO_MODE=false
ALLOW_DEMO_FALLBACK=false
JOB_MODE=queue
DATABASE_RLS_ENABLED=true
DATABASE_URL=postgresql+psycopg://<runtime_app>:<secret>@<db>/zhituo
REDIS_URL=redis://<redis>/0
AUTHENTICATED_RATE_LIMIT_PER_MINUTE=300
CELERY_TASK_SOFT_TIME_LIMIT_SECONDS=90
CELERY_TASK_TIME_LIMIT_SECONDS=120
JOB_STUCK_AFTER_SECONDS=300
METRICS_ENABLED=true
METRICS_TOKEN=<secret-manager-injected-min-32-chars>
```

身份采用 `trusted_proxy` 或 `oidc`，生产禁止 `development_header`。

## 5. Worker 与 Beat

Worker：

```bash
celery -A app.celery_app.celery_app worker --loglevel=INFO --concurrency=2
```

Beat：

```bash
celery -A app.celery_app.celery_app beat --loglevel=INFO --schedule=/tmp/celerybeat-schedule
```

Beat 不能和 API 进程混跑。多副本部署时只能存在一个有效 Beat 调度器，或改用具有分布式锁的调度方案。

## 6. 容器安全基线

示例 Compose 已启用：

- 非 root 镜像用户；
- `read_only: true`；
- `/tmp` 独立 tmpfs；
- `no-new-privileges`；
- `cap_drop: ALL`；
- API 不直接公开端口；
- API 与 Web 使用不同环境变量文件。

生产镜像应使用不可变 digest，而不是长期使用 `latest`。

## 7. 数据库角色

- `migration_owner`：仅部署迁移；
- `runtime_app`：API / Worker / Beat，`NOBYPASSRLS`；
- `backup_reader`：只读备份，可 `BYPASSRLS`，不得用于应用流量。

运行容器严禁使用 migration owner 或 PostgreSQL superuser。

## 8. 上线顺序

1. 备份当前数据库；
2. 使用 migration owner 执行 `alembic upgrade head`；
3. 重新执行 runtime role grant 脚本，确保新表权限完整；
4. 启动 API；
5. Readiness 通过；
6. 启动 Worker；
7. 启动唯一 Beat；
8. 启动 Web；
9. 接入反向代理流量；
10. 验证 `/internal/metrics`、Prometheus Target 和告警规则；
11. 执行一次异步任务 smoke test；
12. 观察错误率、队列延迟和数据库连接池后再扩大流量。
