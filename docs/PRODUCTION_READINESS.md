# 中港智拓生产就绪基线

> 智拓的目标是可部署、可运维、可审计、可扩展的生产级海外市场经营系统。比赛 Demo 只是生产系统的一种演示模式，不再反向决定架构。

## 1. 生产级定义

生产级至少同时满足：可部署、可升级、可恢复、可观测、可审计、可隔离、可降级、可验证和可安全运行。

## 2. 当前已经落实

- FastAPI + PostgreSQL + Redis + Celery；
- Alembic 全量数据库迁移；
- Opportunity / Source / Evidence / Snapshot / Event / Audit 等持久业务状态；
- Draft 人工确认、证据置信度和 Unknown 机制；
- RBAC：viewer / analyst / manager / admin；
- 生产强制 Queue 模式，长任务不在 API 进程同步执行；
- Demo 与生产配置隔离；
- Liveness `/api/health/live`；
- Readiness `/api/health/ready`，Queue 模式同时检查 PostgreSQL 与 Redis；
- 生产认证入口不再直接信任客户端身份头：`trusted_proxy` 模式必须验证网关 Secret；
- 多组织用户在显式组织选择完成前 fail closed，不静默选择租户；
- 核心业务 ORM 已加入 `organization_id`；
- SQLAlchemy Request Session 自动附加组织过滤，并阻断跨组织写入；
- Celery Job 显式携带 `organization_id`，Worker Session 恢复相同租户上下文；
- Queue Job 支持组织级 + 任务类型级 `Idempotency-Key`，并通过 Redis `SET NX` 抵抗并发重放；
- 同一 Idempotency-Key 重放返回原 Job ID，不重复执行任务；
- Job metadata 保留 request_id / correlation_id / organization_id；
- API 请求自动生成或透传安全格式的 `X-Request-ID` 与 `X-Correlation-ID`；
- API 输出 JSON 结构化请求日志，包含状态码、耗时、组织和用户上下文；
- API / Web 独立生产 Dockerfile，容器以非 root 用户运行；
- Docker build context 排除 `.env`、虚拟环境、缓存等文件；
- CI 会真实启动 PostgreSQL 17 + Redis 8，验证迁移、依赖、编译、测试和 Demo reset；
- CI 已加入 API / Web 生产镜像构建门禁。

## 3. 当前仍属于 P0 的事项

### 身份与 Secret

当前 `trusted_proxy + shared secret` 是可部署的企业网关适配层，但最终企业部署应优先接入 OIDC/OAuth2/JWT 验签或公司统一 SSO。网关必须剥离外部请求中的身份头和 Gateway Secret 后再注入可信值。数据库、Redis、AI Key、Gateway Secret 必须由 Secret Manager/KMS 注入，不进入 Git、镜像和普通配置文件。

### 幂等性继续扩展

Queue Job 提交已经具备 Idempotency-Key。下一步继续覆盖业务写路径：

- 商机 Draft 确认；
- Source / Evidence 入库；
- 自动重评；
- Action 创建/完成；
- Strategy 保存。

这些路径应使用 Idempotency-Key、业务唯一键或乐观锁，防止网络重试和并发修改造成重复记录或丢失更新。

### 备份与恢复

生产上线前必须定义 RPO/RTO，并完成：数据库自动备份、迁移前快照、至少一次真实恢复演练、备份加密和恢复权限隔离。

### 可观测性继续扩展

基础 JSON 请求日志与 request/correlation ID 已完成。继续补：API P95/P99、Worker queue latency、Job failure rate、AI provider latency/error、数据库连接池指标、异常追踪以及日志敏感字段脱敏规范。

### 流量安全

继续补：TLS、可信反向代理列表、请求体限制、速率限制、安全响应头、精确 CORS、外部 URL 抓取出网策略。

## 4. 生产环境最小配置

```bash
APP_ENV=production
DEMO_MODE=false
ALLOW_DEMO_FALLBACK=false
NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=false
DATA_BACKEND=database
JOB_MODE=queue
AUTH_MODE=trusted_proxy
AUTH_PROXY_SECRET=<secret-manager-injected-min-32-chars>
DATABASE_URL=postgresql+psycopg://<secret>@<production-db>/zhituo
REDIS_URL=redis://<production-redis>:6379/0
CORS_ORIGINS=https://<official-domain>
IDEMPOTENCY_TTL_SECONDS=86400
LOG_LEVEL=INFO
```

生产环境不得使用默认数据库密码、localhost 数据库/Redis、Demo fallback、开发身份、同步 AI/网页长任务或未受 Alembic 管理的结构变更。

## 5. 数据隔离原则

租户隔离不依赖前端，也不只依赖 API 路由手写过滤。当前设计是：

1. 身份认证得到唯一 Organization；
2. Organization 写入 Request-scoped SQLAlchemy Session；
3. ORM Select 自动附加 Organization 条件；
4. ORM 新增数据自动绑定当前 Organization；
5. 跨租户 insert/update/delete 被 Session guard 阻断；
6. Queue Task 把 Organization ID 一起传入 Worker；
7. Worker 创建相同 Organization-scoped Session。

后续还应在 PostgreSQL 层增加 Row Level Security 作为第二道防线，实现应用层 + 数据库层双重隔离。

## 6. 幂等性原则

对于可重试的 Queue POST 请求，客户端应生成稳定的 `Idempotency-Key`：

- 长度 8–200；
- 可打印 ASCII，无空格；
- 同一次业务动作重试必须复用同一个 Key；
- 不同业务动作必须使用不同 Key；
- Key 按 `organization_id + job_type` 隔离；
- Redis 仅保存 Key 的 SHA-256 摘要，不把原始 Key 作为 Redis key 暴露；
- 默认保留 24 小时，可通过 `IDEMPOTENCY_TTL_SECONDS` 调整。

如果任务入队失败，系统会释放本次 reservation，使客户端能够安全重试。

## 7. 可观测性原则

每个 HTTP 请求至少具备：

- `request_id`：定位一次具体 API 请求；
- `correlation_id`：串联一次业务链路的多个请求/后台任务；
- method / path / status_code；
- duration_ms；
- 已认证时的 organization_id / user_id。

请求 ID 通过响应头回传。外部传入 ID 只接受长度和字符集受限的安全格式，否则由服务端重新生成 UUID。

## 8. CI/CD 门禁

当前主线必须通过：

1. Web TypeScript check；
2. Web production build；
3. Python 安装与 `pip check`；
4. Python compileall；
5. Clean PostgreSQL `alembic upgrade head`；
6. Redis connectivity；
7. pytest，包括 production configuration、tenant isolation、job idempotency 和 tracing；
8. repeatable demo seed / CLI smoke；
9. API production Docker image build；
10. Web production Docker image build。

下一步继续增加：容器启动 smoke test、迁移 upgrade/downgrade 演练、依赖漏洞扫描、SBOM、镜像签名和部署环境审批。

## 9. 下一批生产化顺序

**P0：PostgreSQL RLS → 业务写路径幂等/乐观锁 → 备份恢复脚本与 Runbook → Secret/OIDC 适配 → Rate Limit / Security Headers。**

然后进入 P1：SLO/告警、Dependency Lock、漏洞扫描、Dead Letter/失败任务恢复、数据归档和零停机迁移规范。

> 从现在起，任何进入生产路径的功能，都按真实企业系统的失败模式、安全边界和恢复能力来评审。
