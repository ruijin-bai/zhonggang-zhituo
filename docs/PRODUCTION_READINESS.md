# 中港智拓生产就绪基线

> 智拓按真实企业系统建设。比赛 Demo 只是生产系统的一种演示模式，不再反向决定架构或安全边界。

## 1. 生产级定义

生产级至少同时满足：**可部署、可升级、可恢复、可观测、可审计、可隔离、可降级、可验证、可安全运行**。

## 2. 当前 Production Foundation 已落实

### 运行与部署

- FastAPI + PostgreSQL + Redis + Celery；
- Next.js Web；
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
- JWT 签名算法限制为 RS/ES 系列，不接受 `none` 等不安全算法；
- OIDC 身份默认不自动创建业务账号，必须存在有效 User + Membership；
- 多组织用户必须显式传 `X-Zhituo-Organization`，系统不会静默选第一个组织；
- 认证用户级 Redis 限流按 `organization_id + user_id` 隔离。

### 多租户隔离

当前形成两道防线：

1. SQLAlchemy Session 自动 Tenant Scope；
2. PostgreSQL Row Level Security。

核心业务表均包含 `organization_id`。API / Worker 进入租户上下文时，同时写入：

- SQLAlchemy `Session.info["organization_id"]`；
- PostgreSQL `app.current_organization_id` transaction-local setting。

Celery Job 显式携带 `organization_id`，Worker 恢复相同上下文。

生产数据库必须拆分：

- `migration_owner`：DDL / Alembic；
- `runtime_app`：非表 owner，只拥有必要 DML 权限，因此受 RLS；
- `backup_reader`：只读备份。

API / Worker 严禁使用超级用户或 migration owner。

### 幂等性

Queue Job 已支持标准 `Idempotency-Key`：

- Redis `SET NX` 原子 reservation；
- Key 按 Organization + Job Type 隔离；
- 同一业务动作重放返回原 Job ID；
- 入队失败自动释放 reservation；
- Redis 中只保存 Key 摘要，不暴露原始 Key；
- Job metadata 保存 organization / request / correlation 信息。

业务同步写路径的通用幂等与乐观并发控制仍为下一批 P0。

### 可观测性

- `X-Request-ID`；
- `X-Correlation-ID`；
- JSON 结构化日志；
- HTTP status / duration_ms；
- organization_id / user_id；
- Job metadata 贯穿 correlation 信息；
- 外部传入 ID 只有满足安全字符集和长度才被接受。

### HTTP 安全边界

应用层已具备：

- 请求体 Content-Length 上限；
- `X-Content-Type-Options: nosniff`；
- `X-Frame-Options: DENY`；
- `Referrer-Policy: no-referrer`；
- Permissions-Policy；
- Cross-Origin-Resource-Policy；
- `Cache-Control: no-store`；
- Production HSTS；
- 生产环境隐藏 `/docs`、`/redoc`、`/openapi.json`；
- 认证用户 Redis 限流。

Ingress/WAF 仍必须独立实现 TLS、未认证流量限流、源 IP/网络策略和请求体第一层限制。

### 备份与恢复

已提供：

- `ops/postgres/backup.sh`：custom-format backup + `pg_restore --list` 验证 + SHA-256；
- `ops/postgres/restore.sh`：显式确认、checksum 验证、restore 后 Alembic 状态检查；
- `docs/OPERATIONS_RUNBOOK.md`：RPO/RTO、恢复演练、角色分离、事故处置。

生产上线前必须至少完成一次真实隔离库恢复演练。

## 3. CI/CD 上线门禁

当前主线要求：

1. Web TypeScript check；
2. Web production build；
3. Python 安装 + `pip check`；
4. Python compileall；
5. 运维 Shell 脚本语法校验；
6. Clean PostgreSQL `alembic upgrade head`；
7. 最新 migration `downgrade -1 → upgrade head`；
8. Redis connectivity；
9. pytest；
10. PostgreSQL RLS **非 owner runtime role** 真实隔离测试；
11. production configuration / tenant isolation / idempotency / tracing / security tests；
12. repeatable demo seed / CLI smoke；
13. API production image build + import smoke；
14. Web production image build。

后续继续增加依赖漏洞扫描、SBOM、镜像签名、部署环境审批和真实容器 HTTP smoke。

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
# A. 企业身份网关
AUTH_MODE=trusted_proxy
AUTH_PROXY_SECRET=<secret-manager-injected-min-32-chars>
```

或：

```bash
# B. 直接 OIDC
AUTH_MODE=oidc
OIDC_ISSUER=https://id.example.com/
OIDC_AUDIENCE=zhituo-api
OIDC_JWKS_URL=https://id.example.com/.well-known/jwks.json
OIDC_EMAIL_CLAIM=email
```

## 5. 仍属于 P0 的事项

### 业务写路径幂等 + 乐观并发

下一批重点覆盖：

- Draft 确认；
- Action 创建；
- Strategy 保存；
- Watch 更新；
- Source / Evidence 重复写入保护；
- 关键实体 ETag / version / If-Match。

目标：网络重试不重复写、并发编辑不静默覆盖。

### Secret / 部署平台集成

仓库只定义 Secret 契约。正式环境还需对接实际 Secret Manager / KMS，并建立轮换、权限和审计策略。

### 可观测指标与告警

继续补：

- API P95 / P99；
- Worker queue latency；
- Job failure rate；
- AI provider latency / failure；
- PostgreSQL pool saturation；
- Redis error rate；
- RLS / 403 / 429 异常增长；
- Error tracking。

## 6. P1 稳定运营

- Dependency lock；
- 自动依赖更新；
- SCA / CVE 扫描；
- SBOM；
- 镜像签名；
- Dead Letter / 失败任务人工恢复；
- 数据保留与归档；
- Audit 查询与导出；
- 零停机迁移规范；
- 组织/成员权限管理 UI；
- SLO Dashboard 与告警值班机制。

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

> **身份必须可验证，租户必须双层隔离，写操作必须可追溯，长任务必须异步，失败必须可恢复，部署必须经过自动门禁。**

后续任何新 AI 功能只有在满足这些生产约束后才进入主产品路径。
