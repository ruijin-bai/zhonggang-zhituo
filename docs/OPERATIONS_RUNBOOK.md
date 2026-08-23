# 中港智拓生产运维与灾备 Runbook

> 本文档面向实际部署和运维，不是比赛演示说明。生产环境的云平台、数据库服务、Secret Manager、域名和告警系统由部署单位按本 Runbook 对接。

## 1. 服务组成

生产运行至少包含：

- Web：Next.js；
- API：FastAPI；
- Worker：Celery；
- PostgreSQL：业务主数据、证据、策略、审计；
- Redis：Celery broker/result、Job metadata、幂等键；
- 企业身份源：OIDC 或受信任 SSO Gateway；
- 反向代理 / Ingress / WAF：TLS、流量控制、IP 和请求体第一层防护；
- 对象存储：数据库备份长期保存。

## 2. 初始 SLO / RPO / RTO 建议

在正式业务负责人和信息化部门批准前，采用以下**试运行目标**，不得对外宣称为合同承诺：

| 指标 | 试运行目标 |
| --- | --- |
| API 月可用性 | ≥ 99.5% |
| API P95（不含异步 AI Job） | ≤ 800 ms |
| Job 排队等待 P95 | ≤ 60 s |
| PostgreSQL RPO | ≤ 24 h |
| PostgreSQL RTO | ≤ 4 h |
| 严重故障发现时间 | ≤ 15 min |

上线后应根据实际流量和基础设施能力重新核定。

## 3. 健康检查

- Liveness：`GET /api/health/live`
- Readiness：`GET /api/health/ready`

Readiness 失败时实例停止接收新流量；不要因为 PostgreSQL / Redis 短时故障把进程无限重启。

## 4. PostgreSQL 备份

仓库提供：`ops/postgres/backup.sh`。

生产要求：

1. 通过 Secret Manager 注入 `DATABASE_URL`；
2. 至少每日执行一次逻辑备份；
3. 备份采用 custom format，生成 SHA-256；
4. 本地文件只是临时落地点，随后上传到加密对象存储；
5. 对象存储启用版本控制、生命周期和删除保护；
6. 备份账号只需读取业务库，不与 API Runtime Role 共用；
7. 每月至少做一次恢复演练。

示例：

```bash
DATABASE_URL="$BACKUP_DATABASE_URL" \
BACKUP_DIR=/var/backups/zhituo \
RETENTION_DAYS=7 \
bash ops/postgres/backup.sh
```

## 5. 恢复流程

仓库提供：`ops/postgres/restore.sh`。

**优先恢复到新数据库，不要直接覆盖仍在服务的生产主库。**

步骤：

1. 宣布事故并冻结写入；
2. 确认目标恢复点和备份 SHA-256；
3. 创建隔离恢复数据库；
4. 执行 restore；
5. `alembic upgrade head`；
6. 运行 API smoke test、RLS 测试、关键项目抽查；
7. 核对 Organizations / Users / Opportunities / Evidence / Audit 数量；
8. 业务负责人确认；
9. 切换连接或流量；
10. 保留原故障库，不立即销毁。

示例：

```bash
TARGET_DATABASE_URL="$RESTORE_DATABASE_URL" \
BACKUP_FILE=/secure/zhituo-20260823T220000Z.dump \
CONFIRM_RESTORE=YES \
bash ops/postgres/restore.sh
```

## 6. 数据库角色分离

生产至少使用三个不同角色：

- **migration_owner**：执行 Alembic，拥有 DDL 权限；
- **runtime_app**：API/Worker 使用，不拥有表，只获得所需 DML 权限，因此受 PostgreSQL RLS；
- **backup_reader**：只读备份。

严禁 API / Worker 使用数据库超级用户或 migration owner。

## 7. RLS 运行机制

API 或 Worker 在建立业务租户上下文时执行：

```sql
SELECT set_config('app.current_organization_id', '<organization-id>', true);
```

租户表的 PostgreSQL Policy 只允许访问相同 `organization_id` 的记录。SQLAlchemy ORM 同时保留应用层 tenant criteria，形成两道防线。

如果 Runtime Role 能在不设置 tenant context 的情况下读取业务数据，应视为 P0 安全事故并阻断部署。

## 8. 身份认证

推荐优先顺序：

1. 企业 OIDC / OAuth2 JWT；
2. 企业统一身份网关 `trusted_proxy`；
3. `development_header` 仅开发/测试。

OIDC 模式至少配置：

```bash
AUTH_MODE=oidc
OIDC_ISSUER=https://id.example.com/
OIDC_AUDIENCE=zhituo-api
OIDC_JWKS_URL=https://id.example.com/.well-known/jwks.json
OIDC_EMAIL_CLAIM=email
```

多组织用户必须显式传 `X-Zhituo-Organization`（组织 ID 或 Code），系统不自动选择第一个组织。

## 9. Secret 管理

以下值不得进入 Git、镜像、普通 Wiki 或日志：

- PostgreSQL 密码；
- Redis 凭据；
- AI Provider Key；
- Trusted Proxy Secret；
- OIDC Client Secret（若部署模式需要）；
- 备份对象存储凭据。

使用部署平台 Secret/KMS 注入，并建立轮换计划。

## 10. 日志与故障关联

API 响应返回：

- `X-Request-ID`
- `X-Correlation-ID`

日志采用 JSON，故障排查先用 correlation ID 串联 API、Job 和 Worker。日志不得记录 Bearer Token、Gateway Secret、数据库 URL 密码或完整敏感原文。

## 11. 发布前检查

每次生产部署至少通过：

- CI 全绿；
- `pip check`；
- Web production build；
- API/Web production image build；
- clean database `alembic upgrade head`；
- migration downgrade/upgrade smoke；
- PostgreSQL RLS 非 owner 角色测试；
- pytest；
- readiness；
- 上一版本数据库备份已完成；
- 变更说明和回滚方案已记录。

## 12. 严重事故最低处置

### 跨租户数据泄露

立即停止 API/Worker 流量，保存日志和数据库审计，不进行破坏性清理；核查 RLS、Runtime Role、tenant context 和相关请求 correlation ID。

### 数据误删/损坏

冻结写入，优先恢复到隔离库验证，禁止未经验证直接覆盖主库。

### Redis 丢失

Redis 不作为业务事实主库。Job metadata / 幂等窗口可能丢失，但 PostgreSQL 业务数据不得受影响。恢复 Redis 后重新提交未完成任务前必须检查是否已产生业务副作用。

### AI Provider 故障

AI 调用失败不得破坏 Source / Evidence / Opportunity 的既有状态。允许任务失败、重试或人工恢复，不允许为了保持“成功”而生成伪数据。
