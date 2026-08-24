# 中港智拓生产就绪基线

> 智拓按真实企业系统建设。比赛 Demo 只是生产系统的一种演示模式，不再反向决定架构或安全边界。

## 1. 生产级定义

生产级至少同时满足：**可部署、可升级、可恢复、可观测、可审计、可隔离、可降级、可验证、可安全运行**。

## 2. 当前 Production Foundation 已落实

### 运行与部署

- FastAPI + PostgreSQL + Redis + Celery；
- Next.js Web + BFF 信任边界；
- API / Web 独立生产 Dockerfile；
- 容器非 root 运行；
- Docker build context 排除 `.env`、虚拟环境和缓存；
- 生产强制 Queue 模式，AI/网页抓取等长任务不在 API 进程同步执行；
- Demo / Development / Production 配置隔离；
- Liveness：`/api/health/live`；
- Readiness：`/api/health/ready`，Queue 模式同时检查 PostgreSQL 与 Redis。

### 身份与权限

- RBAC：viewer / analyst / manager / admin；
- 生产禁止 `development_header`；
- 支持 `trusted_proxy` 企业身份网关；
- 支持直接 OIDC JWT 验签：Issuer / Audience / JWKS；
- JWT 签名算法限制为 RS/ES 系列；
- OIDC 身份默认不自动创建业务账号，必须存在有效 User + Membership；
- 多组织用户必须显式选择 Organization；
- 认证用户级 Redis 限流按 `organization_id + user_id` 隔离。

### 多租户隔离

形成两道防线：

1. SQLAlchemy Session 自动 Tenant Scope；
2. PostgreSQL Row Level Security。

核心业务表和后台任务台账均包含 `organization_id`。API / Worker 同时绑定 SQLAlchemy Session 与 PostgreSQL `app.current_organization_id`。

生产数据库必须拆分：

- `migration_owner`：DDL / Alembic；
- `runtime_app`：非表 owner，只拥有必要 DML 权限，受 RLS；
- `backup_reader`：只读备份，可 BYPASSRLS 以保证完整备份。

API / Worker 严禁使用超级用户或 migration owner。

### 请求与业务幂等

Queue Job：

- 标准 `Idempotency-Key`；
- Redis `SET NX` 原子 reservation；
- Organization + Job Type 隔离；
- 重放返回原 Job ID；
- 入队失败释放 reservation。

同步业务写路径：

- Draft 确认；
- Watch 更新；
- Action 创建/完成；
- Alert 关闭；
- Strategy 保存。

使用 PostgreSQL `idempotency_records` 持久化请求摘要与响应结果。同 Key + 不同 payload 直接 409；不确定副作用的 pending/failed 请求不会因 TTL 到期被自动重做。

### 策略乐观并发

策略工作区已经具备版本控制：

- GET 返回 `version`；
- 保存必须提交 `expected_version`；
- 同一项目策略写入先锁定 Opportunity 行；
- 写入前比较当前 Strategy Event 版本；
- 旧版本写入返回 `409 Conflict`；
- 后提交者不能静默覆盖其他经营人员已经保存的修改。

当前采用显式 `expected_version` 请求字段；后续 Web 可在编辑器中进一步映射为 ETag / If-Match 用户体验。

### Durable Job Ledger / 失败恢复

Celery/Redis 负责实时执行，PostgreSQL `background_jobs` 保存长期任务事实：

- Job Type / Celery Task Name；
- 提交组织、用户、资源；
- task args；
- request_id / correlation_id；
- queued / running / retrying / succeeded / failed；
- attempts；
- error detail；
- retry lineage。

Worker 的 before_start / retry / success / failure 自动更新台账。Redis/Celery result 过期后，Job API 可以退回 PostgreSQL 状态。

管理角色可以：

- `GET /api/jobs/failed`；
- `POST /api/jobs/{job_id}/retry`。

人工重试创建新 Job ID，并保留 `retry_of_job_id`，不篡改原失败记录。可重试 task name 使用代码白名单，不允许用户提交任意 Celery task。

### 可观测性

- `X-Request-ID`；
- `X-Correlation-ID`；
- JSON 结构化日志；
- HTTP status / duration_ms；
- organization_id / user_id；
- Job metadata 与 Durable Job Ledger 贯穿 correlation 信息；
- 外部传入 ID 只有满足安全字符集和长度才被接受。

### HTTP 安全边界

应用层已具备：

- 请求体大小限制；
- `X-Content-Type-Options: nosniff`；
- `X-Frame-Options: DENY`；
- `Referrer-Policy: no-referrer`；
- Permissions-Policy；
- Cross-Origin-Resource-Policy；
- `Cache-Control: no-store`；
- Production HSTS；
- 生产隐藏 `/docs`、`/redoc`、`/openapi.json`；
- 认证用户 Redis 限流。

Ingress/WAF 仍必须独立实现 TLS、未认证流量限流、源 IP/网络策略和第一层请求体限制。

### 备份与恢复

已提供：

- `ops/postgres/backup.sh`；
- `ops/postgres/restore.sh`；
- custom-format backup；
- SHA-256 校验；
- restore 后 Alembic 状态检查；
- `docs/OPERATIONS_RUNBOOK.md`。

CI 会实际执行 `pg_dump → 新数据库 → pg_restore → 数据抽查`。

## 3. CI/CD 上线门禁

主线要求：

1. Web TypeScript check；
2. Web production build；
3. Python 安装 + `pip check`；
4. Python compileall；
5. 运维脚本语法校验；
6. Clean PostgreSQL `alembic upgrade head`；
7. 最新 migration `downgrade -1 → upgrade head`；
8. runtime / backup 数据库角色权限验证；
9. Redis connectivity；
10. pytest；
11. PostgreSQL Opportunity RLS 真实非 owner 测试；
12. PostgreSQL Background Job RLS 真实非 owner 测试；
13. strategy concurrency / business idempotency / tracing / security tests；
14. repeatable demo seed / CLI smoke；
15. PostgreSQL 17 backup / restore 演练；
16. API production image build + import smoke；
17. Web production image build；
18. 最终发布 `zhituo/ci-gate` commit status。

以后可通过标准 GitHub commit status 直接判断主线最终门禁结果，无需人工截图 Actions 日志。

## 4. 生产环境最小配置

```bash
APP_ENV=production
DEMO_MODE=false
ALLOW_DEMO_FALLBACK=false
NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=false
DATA_BACKEND=database
DATABASE_RLS_ENABLED=true
JOB_MODE=queue
DATABASE_URL=postgresql+psycopg://<runtime-user>:<secret>@<production-db>/zhituo
REDIS_URL=redis://<production-redis>:6379/0
CORS_ORIGINS=https://<official-domain>
IDEMPOTENCY_TTL_SECONDS=86400
AUTHENTICATED_RATE_LIMIT_PER_MINUTE=300
MAX_REQUEST_BODY_BYTES=2000000
LOG_LEVEL=INFO
```

身份二选一：

```bash
AUTH_MODE=trusted_proxy
AUTH_PROXY_SECRET=<secret-manager-injected-min-32-chars>
```

或：

```bash
AUTH_MODE=oidc
OIDC_ISSUER=https://id.example.com/
OIDC_AUDIENCE=zhituo-api
OIDC_JWKS_URL=https://id.example.com/.well-known/jwks.json
OIDC_EMAIL_CLAIM=email
```

## 5. 下一阶段 P0

### Secret / 部署平台集成

仓库已经定义 Secret 契约，但正式部署仍需接实际 Secret Manager / KMS，并建立：

- Secret 轮换；
- 最小读取权限；
- 环境隔离；
- 审计；
- 数据库 runtime / migration / backup 三套凭据。

### 指标、SLO 与告警

继续补：

- API P50 / P95 / P99；
- Worker queue latency；
- Job failure / retry / stuck rate；
- AI provider latency / failure；
- PostgreSQL pool saturation；
- Redis error rate；
- RLS / 403 / 409 / 429 异常增长；
- Error tracking；
- SLO Dashboard。

### 数据保留与 Stuck Job Reconciliation

Durable Job Ledger 已解决“任务历史消失”和“失败可人工重试”，下一步还需：

- Job Ledger 保留/归档策略；
- running 超时扫描；
- Worker 异常退出后的 stuck job reconciliation；
- Dead Letter Dashboard。

## 6. P1 稳定运营

- Dependency lock；
- 自动依赖更新；
- SCA / CVE 扫描；
- SBOM；
- 镜像签名；
- Audit 查询与导出；
- 零停机迁移规范；
- 组织/成员权限管理 UI；
- 失败任务管理 UI；
- SLO 告警值班机制。

## 7. P2 企业级扩展

- 企业知识库 / 历史项目接入；
- 国别 / 客户 / 竞争对手主数据治理；
- CRM / OA / 邮件 / 企业消息集成；
- Prompt / Schema / Model version governance；
- AI 成本治理；
- PostgreSQL / Redis 高可用；
- 多实例 Worker；
- 灾备环境与跨区域恢复。

## 8. 当前架构原则

> **身份必须可验证，租户必须双层隔离，写操作必须可幂等且防覆盖，长任务必须异步且有持久台账，失败必须可恢复，部署必须经过自动门禁。**

后续任何新 AI 功能只有满足这些生产约束后才进入主产品路径。
