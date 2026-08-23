# 本地开发

## 1. Web

```bash
npm install
npm run dev:web
```

打开 `http://localhost:3000`。

开发模式可保留 Demo fallback。生产模式必须关闭 fallback，避免 API 故障时向经营人员展示模拟数据。

## 2. PostgreSQL + Redis

```bash
docker compose up -d db redis
```

PostgreSQL 保存业务事实；Redis 用作 Celery broker、任务结果与短期 Job 元数据存储。

## 3. API

```bash
cd apps/api
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
zhituo-api seed
uvicorn app.main:app --reload --port 8000
```

开发 seed 会创建 `admin@zhituo.local` 管理员身份和演示组织。首次演示时，英雄项目刻意初始化为 **72/B**，后续由情报重评链真实推进到 **81/A**。

## 4. Celery Worker

另开终端：

```bash
cd apps/api
# 激活同一个虚拟环境
celery -A app.celery_app:celery_app worker --loglevel=INFO
```

Linux 生产环境保持默认 prefork；本地 Windows 如 prefork 不稳定，可仅在开发环境使用：

```bash
celery -A app.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

当前队列任务包括：

- 商机单条扫描
- 商机批量扫描
- 情报抽取与自动重评
- AI 项目经营研判
- 赢标策略生成
- 红队挑战

生产环境必须：

```bash
JOB_MODE=queue
REDIS_URL=redis://<redis-host>:6379/0
```

此时旧同步长任务接口返回 `409`，调用方必须使用 `/api/jobs/...`。

## 5. 异步 Job API

提交任务：

- `POST /api/jobs/discovery/scan`
- `POST /api/jobs/discovery/batch`
- `POST /api/jobs/sources/ingest`
- `POST /api/jobs/opportunities/{id}/analyze`
- `POST /api/jobs/opportunities/{id}/strategy/generate`
- `POST /api/jobs/opportunities/{id}/strategy/red-team`

返回：

```json
{
  "job_id": "...",
  "job_type": "discovery.scan",
  "state": "PENDING",
  "status_url": "/api/jobs/..."
}
```

查询：

```http
GET /api/jobs/{job_id}
```

状态通常为 `PENDING / STARTED / SUCCESS / FAILURE / RETRY`。Job 元数据绑定 Organization，其他组织不能读取结果。结果默认保留 24 小时，可通过 `CELERY_RESULT_EXPIRES_SECONDS` 调整。

## 6. 身份与权限

开发模式默认使用：

```bash
DEV_USER_EMAIL=admin@zhituo.local
```

也可以通过请求头模拟已认证身份：

```http
X-Zhituo-User: admin@zhituo.local
```

该请求头当前只是开发/可信网关适配层，不是生产登录方案。生产环境应由 SSO/OIDC 或企业身份网关提供可信身份。

角色：

- `viewer`：只读
- `analyst`：扫描、分析、跟踪、提交 AI Job
- `manager`：确认商机入池、修改经营策略
- `admin`：管理基础

关键写操作与 Job 提交进入 `audit_logs`。

## 7. AI 模型

AI 是可选增强，不是事实数据单点故障。模型名不在仓库中硬编码：

```bash
AI_API_KEY=...
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL_EXTRACTION=<structured-output-model>
AI_MODEL_ANALYSIS=<analysis-model>
```

模型失败时，允许确定性抽取或模板化分析降级；已经写入的 Source / Evidence 不因模型失败而损坏。

## 8. 自动重评安全阈值

只有同时满足以下条件，来源事实才允许自动修改评分：

1. 来源等级为 S 或 A；
2. 对应 fact 有 `score_hint`；
3. 抽取置信度 ≥ 0.80；
4. 字段属于既定 8 个评分维度。

否则来源只保存为 Evidence，不自动改变经营等级。

## 9. 生产模式基线

生产环境至少需要：

```bash
APP_ENV=production
DEMO_MODE=false
ALLOW_DEMO_FALLBACK=false
NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=false
DATA_BACKEND=database
JOB_MODE=queue
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://...
```

生产环境禁止本地数据库/Redis 地址、禁止静默 Demo fallback、禁止同步执行网页抓取和 AI 长任务。

## 10. 工程原则

- Demo 数据与生产数据明确隔离；
- 新发现项目先进入 Draft；
- 关键事实绑定 Source / Evidence；
- 分数由规则引擎计算，AI 不直接覆盖总分；
- AI 输出采用结构化 Schema；
- ScoreSnapshot / Event / AuditLog 保留变化历史；
- 长任务进入 Queue，可重试、可查询、可超时；
- 系统允许 Unknown，不通过 AI 补造经营事实。
