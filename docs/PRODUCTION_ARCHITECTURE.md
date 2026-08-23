# 中港智拓生产架构

## 1. 目标拓扑

```text
User Browser
    |
    v
Enterprise SSO / OIDC
    |
    v
WAF / Ingress / Reverse Proxy
    | TLS, unauthenticated rate limit, request-size first gate
    v
+---------------------+        +----------------------+
| Next.js Web         |        | FastAPI API          |
| stateless           |------->| stateless            |
+---------------------+        +----------+-----------+
                                          |
                           +--------------+--------------+
                           |                             |
                           v                             v
                  PostgreSQL runtime role             Redis
                  RLS + audit + state          broker/result/idempotency
                           ^                             |
                           |                             v
                           +--------------------- Celery Worker
                                                   tenant-scoped
```

生产环境另外存在不承载用户流量的管理平面：

- Alembic migration owner；
- Backup reader；
- Secret Manager / KMS；
- 日志、指标和错误追踪平台；
- 加密对象存储备份；
- CI/CD Runner。

## 2. 信任边界

### 浏览器 → Ingress

不信任浏览器提供的身份、源 IP 转发头或网关 Secret。Ingress 必须终止 TLS、清理受保护 Headers，并做未认证流量防护。

### Ingress → API

有两种生产认证模式：

- `trusted_proxy`：网关完成认证后注入用户身份和 Gateway Secret；
- `oidc`：API 自己验 Bearer JWT 的 Issuer、Audience、JWKS 和签名算法。

### API / Worker → PostgreSQL

Runtime Role 不是表 owner。业务请求进入后设置 `app.current_organization_id`，PostgreSQL RLS 只放行同组织记录。应用 ORM 再做一次 tenant filter。

### API / Worker → Redis

Redis 不存放最终业务事实，只承担队列、任务结果、幂等窗口和限流状态。Redis 丢失不能导致 PostgreSQL 业务事实丢失。

### AI Provider / 外部网站

它们都是不可信外部依赖：

- AI 输出必须经过 Schema / Pydantic 验证；
- URL 抓取必须经过 SSRF 防护；
- 外部失败不能回滚已确认的业务事实；
- Prompt 不得携带超出当前组织授权范围的数据。

## 3. 数据分层

### 权威业务事实

PostgreSQL：Organization、User、Membership、Opportunity、Source、Evidence、Score Snapshot、Action、Alert、Strategy Event、Audit。

### 易失运行状态

Redis：Celery broker/result、Job metadata、Idempotency reservation、Rate Limit counters。

### 可重建输出

AI 分析、策略草稿等如可由权威事实重新生成，不应成为唯一事实来源。

## 4. 多租户规则

任何业务表必须满足至少一个条件才能合入：

1. 明确包含 `organization_id` 并进入 RLS；或
2. 被证明是全局主数据且有独立权限模型。

禁止仅靠前端隐藏或 API 参数约定实现租户隔离。

## 5. 同步与异步边界

同步 API 只承担：

- 查询；
- 短数据库写入；
- 权限验证；
- Job 提交。

以下必须异步：

- 外部网页抓取；
- 批量扫描；
- AI 分析；
- AI 策略生成；
- 红队挑战；
- 后续大规模文件解析。

## 6. 失败模式

### PostgreSQL 不可用

Readiness 失败，API 停止接新流量。不得回退到 Demo 数据。

### Redis 不可用

Queue 模式 Readiness 失败。已持久化 PostgreSQL 数据仍保持正确；未完成 Job 需恢复后检查副作用再重试。

### AI 不可用

AI Job 失败或降级，不得篡改 Evidence / Opportunity 权威事实。

### OIDC / SSO 不可用

新请求认证失败，不允许绕过到开发 Header。

### 跨租户上下文缺失

Runtime Role 的 RLS 默认不返回租户业务数据，写入也不通过 Policy。

## 7. 发布单元

API、Web、Worker 使用同一 Git commit 构建，但作为独立 Deployment 发布。数据库 migration 是独立发布步骤，必须在应用切换前完成兼容性评审。

## 8. 未来演进

当实际规模需要时，可演进到：

- PostgreSQL HA / read replica；
- Redis Sentinel / managed HA；
- Celery queue 按任务类型拆分；
- Object storage + document processing service；
- OpenTelemetry；
- 企业数据湖 / 主数据服务；
- 多区域灾备。

在没有负载数据前，不提前引入 Kubernetes、Kafka、向量数据库等额外复杂度。生产级不等于技术栈越多，而是失败边界、数据责任和运维能力明确。
