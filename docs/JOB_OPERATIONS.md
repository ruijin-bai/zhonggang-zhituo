# 智拓后台任务运行与失败恢复规范

## 1. 状态事实来源

后台长任务采用两层状态：

- **Celery / Redis**：实时执行与短期结果；
- **PostgreSQL `background_jobs`**：长期、可审计的任务事实台账。

Redis/Celery result 过期不代表任务历史消失。生产排障、审计、失败恢复以 PostgreSQL Job Ledger 为长期依据。

## 2. Job 生命周期

标准状态：

`queued → running → succeeded`

可重试异常：

`queued → running → retrying → running → succeeded/failed`

调度阶段异常：

`queued → failed`

每次 Worker 真正开始执行时 `attempts + 1`。自动重试不会创建新的 Job ID；Celery 自动重试仍属于同一次任务。只有人工重试才创建新的 Job ID。

## 3. 台账字段

每个 Job 至少保留：

- Job ID；
- Organization；
- Job Type / Celery Task Name；
- Resource ID；
- 提交用户与邮箱；
- request_id / correlation_id；
- 状态与尝试次数；
- 提交、开始、完成时间；
- 失败原因；
- 可重试任务参数；
- `retry_of_job_id`。

任务参数属于业务数据，受数据库权限、RLS、备份和数据保留制度约束。禁止把数据库密码、AI Key、Gateway Secret 等 Secret 放入任务 payload。

## 4. 租户隔离

`background_jobs` 属于 Tenant Scoped 数据：

1. SQLAlchemy 自动按 `organization_id` 过滤；
2. PostgreSQL RLS 再做第二层隔离；
3. Worker 更新状态时必须恢复提交任务时的 Organization Context；
4. 管理员只能查看和重试本组织的失败 Job。

## 5. 失败任务查看

管理角色可调用：

`GET /api/jobs/failed?limit=100`

用于查看当前组织的持久失败任务。该接口不依赖 Celery result 是否仍存在。

单个任务：

`GET /api/jobs/{job_id}`

如果 Redis/Celery 状态已经过期，API 会退回 PostgreSQL Job Ledger；如果数据库确认任务失败，不允许 Redis 的 `PENDING` 假象覆盖持久失败事实。

## 6. 人工重试

管理角色可调用：

`POST /api/jobs/{job_id}/retry`

规则：

- 只有 `failed` 状态可以人工重试；
- 任务类型必须在代码白名单中；
- 原失败 Job 永久保留，不修改为成功；
- 重试创建新的 Job ID；
- 新 Job 的 `retry_of_job_id` 指向原 Job；
- 人工重试行为进入 Audit Log；
- 不允许通过用户输入任意 Celery task name 执行任务。

## 7. 自动重试与人工重试边界

自动重试只用于代码明确允许的临时基础设施异常，例如 ConnectionError，并设置最大次数与退避。

以下情况不得盲目自动重试：

- 数据校验失败；
- 权限失败；
- 业务对象不存在；
- 已知可能产生不可逆外部副作用且缺乏外部幂等保证；
- 人工需要先修正输入数据的错误。

人工重试前应先检查 `error_detail`、correlation_id、相关 Audit Log 和上游服务状态。

## 8. 告警建议

生产监控至少建立：

- Job failure rate；
- `failed` Job 数量；
- Queue latency；
- running 超时数量；
- retrying 比例；
- 同类 Job 连续失败次数；
- AI Provider 失败率；
- Redis/Celery broker 连通性。

建议对“同一 job_type 在 10 分钟内连续失败 N 次”建立聚合告警，避免每个 Job 单独轰炸值班人员。

## 9. 后续治理

下一阶段继续增加：

- Job Ledger 数据保留/归档策略；
- 管理端失败任务 UI；
- Stuck Job Reconciler；
- Prometheus 指标；
- Dead Letter Dashboard；
- 外部副作用任务的 Outbox / Saga 机制。
