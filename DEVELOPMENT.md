# 本地开发

## 1. 依赖锁原则

主线使用两份提交到仓库的依赖锁：

- Web：根目录 `package-lock.json`；
- API：`apps/api/uv.lock`。

开发、CI 和生产镜像都应消费锁文件。正常开发不要用 `npm install` 或无锁 `pip install .` 重新解析生产依赖；依赖升级应显式修改声明并更新锁文件。

## 2. Web

```bash
npm ci
npm run dev:web
```

打开 `http://localhost:3000`。

开发/比赛演示模式可保留 Demo fallback。生产模式必须关闭 fallback，避免 API 故障时向经营人员展示模拟数据。

## 3. PostgreSQL + Redis

```bash
docker compose up -d db redis
```

PostgreSQL 保存业务事实；Redis 用作 Celery broker、任务结果与短期 Job 元数据存储。

## 4. API

```bash
cd apps/api
python -m pip install 'uv>=0.8,<1'
uv sync --locked --extra dev
uv run alembic upgrade head
uv run zhituo-api seed
uv run uvicorn app.main:app --reload --port 8000
```

开发 seed 会创建 `admin@zhituo.local` 管理员身份和演示组织。首次演示时，英雄项目刻意初始化为 **72/B**，后续由情报重评链真实推进到 **81/A**。

### 比赛/录屏前一键恢复英雄案例

```bash
cd apps/api
uv run zhituo-api reset-demo
```

`reset-demo` 只删除 `is_demo=true` 的演示业务数据，再重新 seed：

- 英雄项目恢复为 72/B 基线；
- 重置 Demo Evidence / Source / ScoreSnapshot / Event；
- 重置 Demo Watchlist、Action、Alert、AI Analysis；
- 恢复固定的 3 项经营行动和策略版本；
- `is_demo=false` 的公开/真实项目不会被删除；
- 演示组织和开发身份保持不变。

正式录屏前建议：

```bash
docker compose up -d db redis
cd apps/api
uv run alembic upgrade head
uv run zhituo-api reset-demo
uv run zhituo-api status
uv run uvicorn app.main:app --port 8000
```

随后另开终端启动 Web。

## 5. Celery Worker / Beat

Worker：

```bash
cd apps/api
uv run celery -A app.celery_app:celery_app worker --loglevel=INFO
```

本地 Windows 如 prefork 不稳定，可仅在开发环境使用：

```bash
uv run celery -A app.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

Beat：

```bash
uv run celery -A app.celery_app:celery_app beat --loglevel=INFO
```

生产环境必须使用：

```bash
JOB_MODE=queue
REDIS_URL=redis://<redis-host>:6379/0
```

此时旧同步长任务接口返回 `409`，调用方必须使用 `/api/jobs/...`。

## 6. Source Connectors

当前首批统一外部来源连接器：

- `html`：网页/纯文本；
- `rss`：RSS / Atom；
- `pdf`：带文本层 PDF。

连接器统一输出 `SourceDocument`，设计见 `docs/SOURCE_CONNECTORS.md`。

运行 Connector 相关单测：

```bash
cd apps/api
uv run pytest -q tests/test_connectors.py
```

扫描 PDF 如果没有文本层会明确提示后续需要 OCR，不在同步请求中自动执行高成本 OCR。

## 7. 异步 Job API

提交任务：

- `POST /api/jobs/discovery/scan`
- `POST /api/jobs/discovery/batch`
- `POST /api/jobs/sources/ingest`
- `POST /api/jobs/opportunities/{id}/analyze`
- `POST /api/jobs/opportunities/{id}/strategy/generate`
- `POST /api/jobs/opportunities/{id}/strategy/red-team`

查询：

```http
GET /api/jobs/{job_id}
```

Job 元数据绑定 Organization，其他组织不能读取结果。长期任务事实写入 PostgreSQL `background_jobs`，不依赖 Redis Result 的保留周期。

## 8. 身份与权限

开发模式默认使用：

```bash
DEV_USER_EMAIL=admin@zhituo.local
```

也可以通过请求头模拟开发身份：

```http
X-Zhituo-User: admin@zhituo.local
```

生产禁止 `development_header`，应使用 OIDC 或 trusted proxy 企业身份网关。

角色：

- `viewer`：只读；
- `analyst`：扫描、分析、跟踪、提交 AI Job；
- `manager`：确认商机入池、修改经营策略；
- `admin`：管理能力。

关键写操作与 Job 提交进入 Audit Log。

## 9. AI 模型

AI 是可选增强，不是事实数据单点故障。模型名不在仓库中硬编码：

```bash
AI_API_KEY=...
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL_EXTRACTION=<structured-output-model>
AI_MODEL_ANALYSIS=<analysis-model>
```

模型失败时允许确定性抽取或模板化分析降级；已经写入的 Source / Evidence 不因模型失败而损坏。

## 10. Demo fallback 与生产隔离

开发/演示可设置：

```bash
ALLOW_DEMO_FALLBACK=true
NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=true
```

生产必须设置：

```bash
ALLOW_DEMO_FALLBACK=false
NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=false
```

生产故障应显式报错，不能静默展示 Demo 数据。

## 11. 自动重评安全阈值

只有同时满足以下条件，来源事实才允许自动修改评分：

1. 来源等级为 S 或 A；
2. 对应 fact 有 `score_hint`；
3. 抽取置信度 ≥ 0.80；
4. 字段属于既定 8 个评分维度。

否则来源只保存为 Evidence，不自动改变经营等级。

## 12. 生产模式基线

```bash
APP_ENV=production
DEMO_MODE=false
ALLOW_DEMO_FALLBACK=false
NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=false
DATA_BACKEND=database
JOB_MODE=queue
DATABASE_RLS_ENABLED=true
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://...
```

生产环境禁止静默 Demo fallback、禁止同步执行网页抓取和 AI 长任务。

## 13. 本地质量检查

API：

```bash
cd apps/api
uv sync --locked --extra dev
uv run python -m compileall -q app
uv run pytest -q
```

Web：

```bash
npm ci
npm --workspace apps/web run check
npm --workspace apps/web run build
```

生产镜像：

```bash
docker build -t zhituo-api:local apps/api
docker build -f apps/web/Dockerfile -t zhituo-web:local .
```

## 14. 工程原则

- Demo 数据与生产数据明确隔离；
- 新发现项目先进入 Draft；
- 关键事实绑定 Source / Evidence；
- 分数由规则引擎计算，AI 不直接覆盖总分；
- AI 输出采用结构化 Schema；
- ScoreSnapshot / Event / AuditLog 保留变化历史；
- 长任务进入 Queue，可重试、可查询、可超时；
- 外部文档先经过 Connector 标准化，再进入识别/证据管线；
- 系统允许 Unknown，不通过 AI 补造经营事实。
