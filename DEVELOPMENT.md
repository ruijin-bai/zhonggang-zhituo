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

PostgreSQL 保存业务事实、外部来源版本索引和来源订阅健康状态；Redis 用作 Celery broker、任务结果与短期 Job 元数据存储。

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

此时旧同步长任务接口返回 `409`，调用方必须使用 `/api/jobs/...`。Beat 同时负责每分钟检查到期的 Source Subscription，但不直接执行网络抓取；每个订阅会被派发为独立 Worker Task。

## 6. Source Connectors、DocumentStore 与持续监测

当前首批统一外部来源连接器：

- `html`：网页/纯文本；
- `rss`：RSS / Atom；
- `pdf`：带文本层 PDF。

连接器统一输出 `SourceDocument`，再进入内容寻址 DocumentStore 与 PostgreSQL 来源版本索引。设计见 `docs/SOURCE_CONNECTORS.md`。

### 本地开发存储

默认配置：

```bash
DOCUMENT_STORE_BACKEND=local
DOCUMENT_STORE_LOCAL_PATH=./data/objects
```

原件和规范文本分别进入：

```text
raw/sha256/...
text/sha256/...
```

相同内容重复归档不会产生第二份对象。

### 生产存储

生产模式强制 S3-compatible：

```bash
DOCUMENT_STORE_BACKEND=s3
DOCUMENT_STORE_S3_BUCKET=zhituo-production-documents
DOCUMENT_STORE_S3_REGION=<region>
# AWS S3 可不填 endpoint；兼容服务必须使用 HTTPS。
DOCUMENT_STORE_S3_ENDPOINT_URL=
DOCUMENT_STORE_S3_FORCE_PATH_STYLE=false
DOCUMENT_STORE_S3_SSE=AES256
```

如使用 KMS：

```bash
DOCUMENT_STORE_S3_SSE=aws:kms
DOCUMENT_STORE_S3_KMS_KEY_ID=<key-id-or-alias>
```

凭证使用 boto3/AWS SDK 标准 credential chain，不在仓库或智拓自定义配置中保存 Access Key。

### Source Subscription

持续监测使用 `source_subscriptions` 保存来源配置和健康状态，`source_scan_runs` 保存每次扫描历史。主要接口：

```http
GET  /api/sources/subscriptions
POST /api/sources/subscriptions
GET  /api/sources/subscriptions/{id}
PUT  /api/sources/subscriptions/{id}
POST /api/sources/subscriptions/{id}/pause
POST /api/sources/subscriptions/{id}/resume
POST /api/sources/subscriptions/{id}/scan
GET  /api/sources/subscriptions/{id}/runs
```

创建、修改、暂停、恢复和手工扫描要求 `manager`；读取要求 `viewer`。

调度参数：

```bash
SOURCE_SCAN_DISPATCH_INTERVAL_SECONDS=60
SOURCE_SCAN_MIN_INTERVAL_SECONDS=300
SOURCE_SCAN_LEASE_SECONDS=300
SOURCE_SCAN_MAX_BACKOFF_SECONDS=86400
SOURCE_SCAN_AUTO_PAUSE_FAILURES=8
SOURCE_SCAN_DISPATCH_BATCH_SIZE=50
```

运行原则：

1. Beat 只认领 `next_scan_at` 已到期、状态为 active 且当前租约已过期的订阅；
2. 认领时写入 `lease_until + lease_token`，Worker 必须携带当前 token 才能落状态；
3. 因队列延迟启动的旧 Worker 如果 token 已失效，只返回 `stale_claim`，不能清除新租约或覆盖新结果；
4. Connector 自动发送 `If-None-Match / If-Modified-Since`，304 只更新健康状态，不重复下载和归档原件；
5. 失败按指数退避，达到 `SOURCE_SCAN_AUTO_PAUSE_FAILURES` 后自动暂停，需人工检查后恢复；
6. 手工扫描也使用相同租约围栏，避免重复提交。

`SOURCE_SCAN_LEASE_SECONDS` 必须大于 Celery hard task timeout，避免正常运行中的 Worker 被调度器误判为失联。

### Connector / Archive / Monitoring 单测

```bash
cd apps/api
uv run pytest -q \
  tests/test_connectors.py \
  tests/test_conditional_source_fetch.py \
  tests/test_document_store.py \
  tests/test_source_archive.py \
  tests/test_source_monitoring.py
```

扫描 PDF 如果没有文本层会明确提示后续需要 OCR，不在同步请求中自动执行高成本 OCR。

## 7. 异步 Job API

提交任务：

- `POST /api/jobs/discovery/scan`
- `POST /api/jobs/discovery/batch`
- `POST /api/jobs/sources/fetch`：抓取 HTML/RSS/PDF 并归档原件与规范文档；
- `POST /api/jobs/sources/ingest`：现有机会的情报抽取/重评链；
- `POST /api/jobs/opportunities/{id}/analyze`
- `POST /api/jobs/opportunities/{id}/strategy/generate`
- `POST /api/jobs/opportunities/{id}/strategy/red-team`

查看已归档规范文档：

```http
GET /api/jobs/sources/documents?limit=100
```

查询 Job：

```http
GET /api/jobs/{job_id}
```

Job 元数据绑定 Organization，其他组织不能读取结果。长期任务事实写入 PostgreSQL `background_jobs`，不依赖 Redis Result 的保留周期。Source Subscription 扫描本身则以 `source_scan_runs` 作为长期任务事实与健康历史，不依赖 Celery Result 保留周期。

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
- `analyst`：扫描、分析、跟踪、提交 AI / Source Job；
- `manager`：确认商机入池、修改经营策略、管理持续来源订阅；
- `admin`：管理能力。

关键写操作与 Job/Source Subscription 操作进入 Audit Log。

## 9. AI 模型

AI 是可选增强，不是事实数据单点故障。模型名不在仓库中硬编码：

```bash
AI_API_KEY=...
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL_EXTRACTION=<structured-output-model>
AI_MODEL_ANALYSIS=<analysis-model>
```

模型失败时允许确定性抽取或模板化分析降级；已经归档的原件和 Source / Evidence 不因模型失败而损坏。

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
DOCUMENT_STORE_BACKEND=s3
DOCUMENT_STORE_S3_BUCKET=...
SOURCE_SCAN_DISPATCH_INTERVAL_SECONDS=60
SOURCE_SCAN_MIN_INTERVAL_SECONDS=300
SOURCE_SCAN_LEASE_SECONDS=300
SOURCE_SCAN_MAX_BACKOFF_SECONDS=86400
SOURCE_SCAN_AUTO_PAUSE_FAILURES=8
```

生产环境禁止静默 Demo fallback、禁止同步执行网页抓取和 AI 长任务、禁止使用本地文件系统保存正式来源原件。

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
- 原始外部文档按内容哈希不可变归档；
- PostgreSQL 保存版本、订阅健康、租户关系和业务事实，不保存大块原件；
- 周期抓取使用 HTTP 条件请求，304 不重复制造版本；
- 调度租约使用 fencing token，过期 Worker 不得覆盖新 Worker；
- 分数由规则引擎计算，AI 不直接覆盖总分；
- AI 输出采用结构化 Schema；
- ScoreSnapshot / Event / AuditLog 保留变化历史；
- 长任务进入 Queue，可重试、可查询、可超时；
- 外部文档先经过 Connector 标准化和归档，再进入识别/证据管线；
- 系统允许 Unknown，不通过 AI 补造经营事实。
