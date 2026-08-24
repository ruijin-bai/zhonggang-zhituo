# 智拓生产 SLO 与监控基线

> 本文定义首版生产目标。阈值用于上线初期的工程治理，不代表永久承诺；正式运行 30 天后应根据真实流量、业务时段和故障数据重新校准。

## 1. 服务目标

### API

- 月度可用性目标：99.5%；
- 非异步业务 API P95：< 1 秒；
- 5xx 比例：10 分钟窗口 < 2%；
- 429 异常突增：持续超过 10 次/分钟触发告警。

AI、网页抓取、批量扫描等长任务不以同步 HTTP 响应时延衡量，必须进入后台队列。

### Background Jobs

- Queue latency P95：< 30 秒；
- 终态失败比例：15 分钟窗口 < 5%；
- Stuck Job：任何自动 Reconcile 都视为需要调查的异常事件；
- 单任务 hard time limit：120 秒；
- Stuck 判定默认：连续 300 秒无状态更新。

## 2. 指标入口

应用提供：

`GET /internal/metrics`

默认关闭。生产开启时必须配置：

```bash
METRICS_ENABLED=true
METRICS_TOKEN=<secret-manager-injected-min-32-chars>
```

采集端请求必须携带：

```text
X-Metrics-Token: <token>
```

生产环境错误 Token 返回 404，不向公网确认指标端点是否存在。网络层仍应限制只有 Prometheus/监控子网能够访问该路径。

## 3. 核心指标

### HTTP

- `zhituo_http_requests_total`
- `zhituo_http_request_duration_seconds`
- `zhituo_http_requests_in_flight`

HTTP route label 使用 FastAPI 路由模板，不记录具体 Opportunity ID / Job ID，防止指标基数失控。

### Jobs

- `zhituo_background_job_transitions_total`
- `zhituo_background_job_attempts_total`
- `zhituo_background_job_failures_total`
- `zhituo_background_job_retries_total`
- `zhituo_background_job_queue_latency_seconds`
- `zhituo_background_job_duration_seconds`
- `zhituo_background_jobs_reconciled_stuck_total`

### Dependencies

- `zhituo_dependency_up{dependency="postgresql"}`
- `zhituo_dependency_up{dependency="redis"}`
- `zhituo_db_pool_checked_out_connections`
- `zhituo_db_pool_size_connections`

## 4. Stuck Job Reconciler

Celery Beat 每 60 秒运行一次：

`zhituo.maintenance.reconcile_stuck_jobs`

流程：

1. 读取有效 Organization；
2. 每个组织单独建立 Tenant Context；
3. 依赖 SQLAlchemy Tenant Scope + PostgreSQL RLS 查询本组织活动任务；
4. 超过 `JOB_STUCK_AFTER_SECONDS` 无状态更新的 queued/running/retrying Job 标记 failed；
5. 保留错误原因、历史 Job、重试链路并增加 Prometheus Counter；
6. 触发 Critical 告警，由管理员核查后决定是否人工 retry。

Reconciler 不使用超级用户或 BYPASSRLS 运行账号。

## 5. Prometheus 告警规则

仓库文件：

`ops/prometheus/alerts.yml`

首版包含：

- PostgreSQL / Redis 不可用；
- API 5xx 比例持续过高；
- API P95 持续过高；
- 429 异常突增；
- Job 失败率持续过高；
- Job queue latency P95 持续过高；
- Stuck Job 被 Reconciler 捕获。

## 6. 上线后 30 天复盘

至少复盘：

- 工作日/非工作日流量差异；
- API P50/P95/P99；
- 各 job_type 的 queue latency 与 duration；
- AI Provider 的错误与超时分布；
- 429 是否来自异常客户端还是容量不足；
- 数据库连接池峰值；
- Stuck Job 根因；
- 告警误报率和漏报情况。

完成基线后再确定正式 SLA、扩容阈值和值班策略。
