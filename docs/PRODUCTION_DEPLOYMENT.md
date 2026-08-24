# 智拓生产部署契约

## 1. 进程拓扑

生产环境至少拆分四个独立进程角色：

- `web`：Next.js / BFF；
- `api`：FastAPI；
- `worker`：Celery Worker；
- `beat`：Celery Beat，仅负责周期调度。

PostgreSQL、Redis、S3-compatible Object Storage、Ingress/WAF、Prometheus/Alertmanager 建议由独立基础设施提供，不与应用容器绑定生命周期。

示例编排：`deploy/docker-compose.production.yml`。

## 2. 网络边界

- API 不映射宿主机公网端口；
- Web 仅绑定 `127.0.0.1`，由宿主机反向代理/WAF 提供 TLS 与公网入口；
- Web 与 API 通过 `backend` 内部网络通信；
- API / Worker / Beat 同时加入独立 `egress` 网络，以访问 OIDC JWKS、AI Provider、Object Storage 和经批准的公开情报源；
- 正式云环境应进一步使用 Egress Policy / Firewall 限制允许访问的外部域名和端口。

## 3. Secret 与工作负载身份

API/Worker/Beat 使用同一类后端运行 Secret，包括：

- runtime PostgreSQL credential；
- Redis credential；
- OIDC / trusted-proxy 配置；
- AI Provider credential；
- Metrics token（仅 API 实际使用，容器平台可进一步拆分）。

Object Storage 优先使用云平台 workload identity / instance role。若平台只能注入静态 S3 credential，也必须通过 Secret Manager 注入标准 AWS SDK 环境变量，不新增智拓自定义 Access Key 配置，更不能提交到仓库。

Web 使用独立环境文件，只应包含 BFF 所需配置，例如：

```bash
API_BASE_URL=http://api:8000
API_AUTH_MODE=trusted_proxy
API_TRUSTED_PROXY_SECRET=<secret>
NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=false
```

**Web 不应获得 DATABASE_URL、Redis 凭据、Object Storage credential 或 AI Provider Key。**

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

DOCUMENT_STORE_BACKEND=s3
DOCUMENT_STORE_S3_BUCKET=zhituo-production-documents
DOCUMENT_STORE_S3_REGION=<region>
DOCUMENT_STORE_S3_ENDPOINT_URL=
DOCUMENT_STORE_S3_FORCE_PATH_STYLE=false
DOCUMENT_STORE_S3_SSE=AES256

SOURCE_SCAN_DISPATCH_INTERVAL_SECONDS=60
SOURCE_SCAN_MIN_INTERVAL_SECONDS=300
SOURCE_SCAN_LEASE_SECONDS=300
SOURCE_SCAN_MAX_BACKOFF_SECONDS=86400
SOURCE_SCAN_AUTO_PAUSE_FAILURES=8
SOURCE_SCAN_DISPATCH_BATCH_SIZE=50

CANDIDATE_DISPATCH_INTERVAL_SECONDS=30
CANDIDATE_LEASE_SECONDS=300
CANDIDATE_MAX_ATTEMPTS=5
CANDIDATE_MAX_BACKOFF_SECONDS=3600
CANDIDATE_DISPATCH_BATCH_SIZE=50
CANDIDATE_DRAFT_DUPLICATE_THRESHOLD=0.88

AUTHENTICATED_RATE_LIMIT_PER_MINUTE=300
CELERY_TASK_SOFT_TIME_LIMIT_SECONDS=90
CELERY_TASK_TIME_LIMIT_SECONDS=120
JOB_STUCK_AFTER_SECONDS=300
METRICS_ENABLED=true
METRICS_TOKEN=<secret-manager-injected-min-32-chars>
```

身份采用 `trusted_proxy` 或 `oidc`，生产禁止 `development_header`。自定义 S3-compatible endpoint 在 production 必须使用 HTTPS；若使用 `aws:kms`，同时配置 `DOCUMENT_STORE_S3_KMS_KEY_ID`。

`SOURCE_SCAN_LEASE_SECONDS` 和 `CANDIDATE_LEASE_SECONDS` 都必须严格大于 `CELERY_TASK_TIME_LIMIT_SECONDS`。两个调度链均使用 fencing token，旧 Worker 失去租约后不得覆盖新 Worker 状态。

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

Beat 当前负责两个独立持久化调度链：

1. `zhituo.sources.dispatch_due_scans`：按 Organization 认领到期 SourceSubscription，分别派发来源扫描 Worker；
2. `zhituo.candidates.dispatch_pending`：按 Organization 认领待处理 CandidateProcessing，分别派发项目识别 Worker。

Beat 本身不执行网页抓取、Object Storage 下载或 AI 推理。

## 6. Source Monitoring 运行保障

持续来源监测依赖 PostgreSQL 中的长期状态，而不是依赖 Celery Result：

- `source_subscriptions`：周期、下一次扫描、ETag、Last-Modified、健康、租约；
- `source_scan_runs`：每次扫描结果和错误历史；
- `source_fetches / source_documents`：真实内容版本；
- Object Storage：不可变原件与规范文本。

上线后应至少验证：

1. 新订阅能够被唯一 Beat 认领；
2. Worker 完成后 `lease_until / lease_token` 被清除；
3. 支持 ETag 的来源第二次扫描可出现 `not_modified`；
4. 连续失败会指数退避而非每分钟重打上游；
5. 达到阈值后来源自动暂停；
6. manager 可以恢复并立即重新扫描；
7. 其他 Organization 无法读取该订阅和扫描历史。

## 7. Candidate Pipeline 运行保障

每个新 SourceDocument 必须在相同数据库事务中获得一条唯一 `candidate_processing`，因此 Redis 不是可靠性单点。

Worker 流程：

1. 读取 CandidateProcessing 与 SourceDocument 元数据；
2. 结束数据库读事务；
3. 从 S3/Object Storage 读取并校验规范文本；
4. 执行 Project Detection；
5. 重新开启短事务，使用 `FOR UPDATE + lease_token` fencing；
6. PostgreSQL 下使用 organization 级 advisory lock 收紧并发候选去重；
7. 写入 `no_project / duplicate / candidate_created / retry / failed`。

上线后应至少验证：

1. 新 SourceDocument 能自动出现 CandidateProcessing；
2. Redis 暂时不可用后，待处理行仍保留并可后续派发；
3. 明确非项目文档进入 `no_project`，不产生 OpportunityDraft；
4. 明确项目进入 `/api/candidates` 待审收件箱；
5. 两个高度相似待审项目只出现一个候选卡片；
6. 失去 token 的旧 Worker 返回 stale claim，不覆盖新租约；
7. 达到最大尝试次数后进入 `failed`，manager 可人工 retry；
8. 人工 confirm 前重新从 Object Storage 校验正文，原件缺失/损坏时拒绝入池；
9. 其他 Organization 无法读取或写入该 CandidateProcessing。

## 8. 容器安全基线

示例 Compose 已启用：

- 非 root 镜像用户；
- `read_only: true`；
- `/tmp` 独立 tmpfs；
- `no-new-privileges`；
- `cap_drop: ALL`；
- API 不直接公开端口；
- API 与 Web 使用不同环境变量文件。

生产镜像应使用不可变 digest，而不是长期使用 `latest`。

注意：Production DocumentStore 为外部 S3-compatible 服务，因此 API/Worker 容器不需要通过可写本地卷保存正式来源原件。

## 9. 数据库角色

- `migration_owner`：仅部署迁移；
- `runtime_app`：API / Worker / Beat，`NOBYPASSRLS`；
- `backup_reader`：只读备份，可 `BYPASSRLS`，不得用于应用流量。

运行容器严禁使用 migration owner 或 PostgreSQL superuser。

每次新增表并执行 Alembic 迁移后，都需要重新运行 `ops/postgres/provision_runtime_role.sql`，确保 runtime role 获得新表 DML 权限；RLS 仍是租户隔离的最终数据库边界。

## 10. 上线顺序

1. 备份当前数据库；
2. 使用 migration owner 执行 `alembic upgrade head`；
3. 重新执行 runtime role grant 脚本，确保 `candidate_processing` 等新表权限完整；
4. 验证 S3 Bucket、SSE/KMS 与 workload identity；
5. 启动 API；
6. Readiness 通过；
7. 启动 Worker；
8. 启动唯一 Beat；
9. 启动 Web；
10. 接入反向代理流量；
11. 验证 `/internal/metrics`、Prometheus Target 和告警规则；
12. 执行一次普通异步任务 smoke test；
13. 创建一个测试 SourceSubscription，并验证首次 changed/unchanged 与后续 304/健康历史；
14. 验证该 SourceDocument 进入 CandidateProcessing，并最终形成 no_project 或 Candidate Inbox；
15. 对测试 Candidate 执行 reject，或确认其证据链完整后 confirm；
16. 观察错误率、队列延迟、来源失败率、Candidate retry/failed 数量和数据库连接池后再扩大流量。
