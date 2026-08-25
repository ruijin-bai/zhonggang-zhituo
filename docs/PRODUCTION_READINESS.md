# 中港智拓生产就绪基线

> 智拓按真实企业系统建设。比赛 Demo 只是生产系统的一种演示模式，不反向决定架构、安全边界或运维标准。

## 1. 生产级定义

生产级至少同时满足：**可部署、可升级、可恢复、可观测、可审计、可隔离、可降级、可验证、可安全运行**。

## 2. 当前 Production Foundation 已落实

### 运行与部署

- Next.js Web + BFF；
- FastAPI API；
- PostgreSQL；
- Redis；
- Celery Worker；
- Celery Beat；
- API / Web 独立生产镜像；
- 非 root、只读文件系统、`no-new-privileges`、`cap_drop: ALL`；
- `deploy/docker-compose.production.yml` 明确拆分 Web / API / Worker / Beat 四进程；
- Web 与后端使用独立环境文件；
- API 不直接映射公网端口；
- backend 内网与 egress 网络分离；
- Liveness / Readiness；
- Demo / Development / Production 配置隔离。

详见 `docs/PRODUCTION_DEPLOYMENT.md`。

### 身份与权限

- RBAC：viewer / analyst / manager / admin；
- 生产禁止 `development_header`；
- 支持 `trusted_proxy` 企业身份网关；
- 支持 OIDC JWT：Issuer / Audience / JWKS 校验；
- JWT 签名算法限制；
- OIDC 用户必须存在有效 User + Membership；
- 多组织用户必须显式选择 Organization；
- 认证用户限流按 `organization_id + user_id` 隔离。

### 多租户隔离

形成两道防线：

1. SQLAlchemy Tenant Scope；
2. PostgreSQL Row Level Security。

Opportunity、Evidence、Source、Tracking、Strategy Event、Idempotency Record、Background Job 等业务数据均受租户隔离。

生产数据库角色拆分：

- `migration_owner`：DDL / Alembic；
- `runtime_app`：API / Worker / Beat，`NOBYPASSRLS`；
- `backup_reader`：只读备份，可 BYPASSRLS 以获得完整备份。

CI 使用真实非 owner PostgreSQL Role 验证 Opportunity 与 Background Job 的跨租户读取被数据库直接阻断。

### 写入一致性

#### Queue Idempotency

- 标准 `Idempotency-Key`；
- Redis `SET NX` 原子 reservation；
- Organization + Job Type 隔离；
- 重放返回原 Job ID；
- 入队失败释放 reservation。

#### 同步业务幂等

Draft 确认、Watch 更新、Action 创建/完成、Alert 关闭、Strategy 保存均使用 PostgreSQL `idempotency_records`。

- 同 Key + 同 payload 返回原结果；
- 同 Key + 不同 payload 返回 409；
- pending / failed 的不确定副作用不会自动重做。

#### 策略乐观并发

- Strategy Workspace 返回 `version`；
- 保存提交 `expected_version`；
- 同项目写入先锁定 Opportunity；
- stale version 返回 `409 Conflict`；
- 后提交者不能静默覆盖他人已保存策略。

### Durable Background Jobs

PostgreSQL `background_jobs` 保存长期任务事实：

- Job / Job Type / Task；
- Organization / User / Resource；
- task args；
- request_id / correlation_id；
- queued / running / retrying / succeeded / failed；
- attempts；
- error detail；
- retry lineage。

Worker 生命周期自动回写台账。Redis/Celery Result 过期后，任务事实仍可追溯。

管理角色支持：

- `GET /api/jobs/failed`；
- `POST /api/jobs/{job_id}/retry`。

人工重试生成新 Job 并保留 `retry_of_job_id`，不篡改历史失败记录。

### Stuck Job Reconciler

Celery Beat 每 60 秒运行 `zhituo.maintenance.reconcile_stuck_jobs`。

- `running/retrying` 超过 `JOB_STUCK_AFTER_SECONDS` 且长期无状态更新：自动标记 failed，并保留审计原因；
- `queued` 长期未启动：**只监控和告警，不自动判失败**，避免把容量不足误判为任务失败；
- Reconciler 按 Organization 逐租户建立 Session/RLS 上下文，不使用 BYPASSRLS。

### 可观测性与 SLO

已具备：

- `X-Request-ID`；
- `X-Correlation-ID`；
- JSON 结构化日志；
- HTTP status / duration；
- Organization / User / Job 链路上下文；
- Prometheus `/internal/metrics`，默认关闭；
- 生产启用指标必须配置独立 `METRICS_TOKEN`；
- HTTP route 使用模板 label，避免具体 Opportunity/Job ID 造成高基数；
- PostgreSQL / Redis health；
- DB pool 指标；
- Job queue latency；
- Job duration；
- failure / retry / stuck / stale queued 指标。

首版 SLO 与告警规则：

- `docs/SLO_AND_MONITORING.md`；
- `ops/prometheus/alerts.yml`。

首版目标包括 API 99.5% 月度可用性、非异步 API P95 < 1s、Job queue P95 < 30s、Job 失败率 < 5% 等；上线 30 天后根据真实数据校准。

### HTTP 安全边界

- 请求体限制；
- HSTS；
- nosniff；
- `X-Frame-Options: DENY`；
- no-referrer；
- Permissions Policy；
- Cross-Origin Resource Policy；
- `Cache-Control: no-store`；
- Production 隐藏 Swagger/OpenAPI；
- 认证用户 Redis 限流。

Ingress/WAF 仍负责 TLS、未认证流量限流、IP/网络策略与第一层请求限制。

### 备份与恢复

- PostgreSQL custom-format backup；
- SHA-256 校验；
- 显式恢复确认；
- restore 后 Alembic 状态检查；
- CI 实际执行 `pg_dump → 新数据库 → pg_restore → 数据抽查`；
- `docs/OPERATIONS_RUNBOOK.md` 定义恢复演练、RPO/RTO 与事故处置。

### 软件供应链

CI 已加入：

- Python `pip-audit`；
- Web `npm audit --omit=dev --audit-level=high`；
- Python CycloneDX SBOM；
- Web CycloneDX SBOM；
- SBOM Workflow Artifact；
- High severity Web 依赖漏洞已推动 Next.js 从 16.2.11 升至 16.3.2；
- 生产 Compose 静态解析门禁；
- API/Web production image build。

Web lockfile 正在通过 CI 固化，完成后 Web CI、Security 与 Docker build 将统一切换为 `npm ci`。

## 3. 当前 CI/CD 门禁

主线至少验证：

1. Web TypeScript check；
2. Web production build；
3. Python install + `pip check`；
4. Python compileall；
5. 运维 Shell 语法；
6. Clean PostgreSQL migration；
7. latest migration downgrade/re-upgrade；
8. runtime / backup DB role 权限；
9. Redis connectivity；
10. unit / integration / PostgreSQL RLS tests；
11. strategy concurrency / business idempotency / tracing / security tests；
12. repeatable demo seed / CLI smoke；
13. PostgreSQL 17 backup/restore drill；
14. production Compose config validation；
15. API production image build + import smoke；
16. Web production image build；
17. Python vulnerability audit；
18. Web high-severity vulnerability audit；
19. Python/Web SBOM generation；
20. `zhituo/ci-gate` 标准 commit status。

后续开发由 `zhituo/ci-gate` 作为主线最终结果，不再依赖人工截图 Actions 日志。

### GitHub `main` Ruleset

仓库用版本化脚本创建或更新 `main-protection` Ruleset：

```bash
gh auth login
./scripts/configure-github-ruleset.sh
```

脚本要求 `main` 必须走 PR、`Required approvals = 0`、严格通过
`zhituo/ci-gate`、分支基于最新 `main`，并禁止删除、force push 和非线性历史；
不设置 bypass actor。可先用 `--dry-run` 查看目标配置，不写入 GitHub。

脚本只管理同名 Ruleset，不删除其他 Ruleset 或经典 Branch Protection。GitHub 会叠加执行
所有适用规则；如仓库另有保护规则，实际合并条件可能更严格。

## 4. 生产环境关键配置

```bash
APP_ENV=production
DATA_BACKEND=database
DEMO_MODE=false
ALLOW_DEMO_FALLBACK=false
DATABASE_RLS_ENABLED=true
JOB_MODE=queue
DATABASE_URL=postgresql+psycopg://<runtime_app>:<secret>@<db>/zhituo
REDIS_URL=redis://<redis>/0
CELERY_TASK_SOFT_TIME_LIMIT_SECONDS=90
CELERY_TASK_TIME_LIMIT_SECONDS=120
JOB_STUCK_AFTER_SECONDS=300
IDEMPOTENCY_TTL_SECONDS=86400
AUTHENTICATED_RATE_LIMIT_PER_MINUTE=300
MAX_REQUEST_BODY_BYTES=2000000
METRICS_ENABLED=true
METRICS_TOKEN=<secret-manager-injected-min-32-chars>
```

身份采用：

```bash
AUTH_MODE=trusted_proxy
AUTH_PROXY_SECRET=<secret>
```

或 OIDC：

```bash
AUTH_MODE=oidc
OIDC_ISSUER=https://id.example.com/
OIDC_AUDIENCE=zhituo-api
OIDC_JWKS_URL=https://id.example.com/.well-known/jwks.json
```

## 5. 下一阶段 P0

### Secret Manager / KMS 落地

仓库已经定义 Secret 契约，下一步需要与最终部署平台结合：

- runtime / migration / backup 三类数据库凭据；
- Redis；
- OIDC / trusted proxy；
- AI Provider；
- Metrics；
- Secret 轮换、最小读取权限、审计和环境隔离。

### 软件供应链进一步加固

- 提交并强制使用 Web lockfile；
- Python 依赖锁；
- 自动依赖更新；
- 容器 CVE 扫描；
- 镜像 digest 固定；
- 镜像签名与 provenance。

### 零停机迁移与发布

- Expand / Migrate / Contract migration 规范；
- 部署前兼容窗口；
- DB migration 与 runtime image 解耦；
- Canary / rolling deployment；
- 自动 rollback 条件；
- 发布后 smoke / SLO gate。

### 容量与告警治理

- 30 天真实 SLO 基线；
- Worker concurrency / autoscaling；
- DB pool saturation；
- Redis capacity；
- AI Provider latency / failure 指标；
- 告警路由和值班策略。

## 6. 后续企业级扩展

- Audit 查询/导出 UI；
- Failed/Dead Letter Job 管理 UI；
- 组织/成员权限管理 UI；
- 企业知识库 / 历史项目；
- CRM / OA / 邮件集成；
- Prompt / Schema / Model version governance；
- AI 成本治理；
- PostgreSQL / Redis 高可用；
- 跨区域灾备。

## 7. 当前架构原则

> **身份必须可验证，租户必须双层隔离，写操作必须可幂等且防覆盖，长任务必须异步且有持久台账，未知状态不擅自改写事实，失败必须可恢复，运行必须可观测，部署必须经过自动安全门禁。**
