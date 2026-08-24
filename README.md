# 中港智拓 Zhonggang Zhituo

> **海外工程市场机会发现与战略经营智能平台**  
> 让 AI 持续回答海外经营最重要的三个问题：**去哪里、追什么、怎么拿。**

## 产品定位

智拓面向海外工程企业市场经营场景，将公开市场、国别环境、业主、融资、项目、竞争对手和企业能力等多源信息，转化为可追踪、可解释、可比较、可协同的经营判断。

它不是新闻聚合器，也不是单纯的 AI 报告生成器，而是一套完整经营闭环：

**持续感知市场 → 自动发现机会 → 建立证据链 → 机会研判 → Go/No-Go 辅助决策 → 赢标策略 → 行动跟踪 → 企业知识沉淀**

## 当前阶段：Production Alpha

主线已从比赛 Demo 架构升级为真实企业系统架构。比赛展示继续作为独立 Demo Mode 保留，但不反向约束生产设计。

当前已经形成：

- Next.js Web + FastAPI API；
- PostgreSQL + Alembic；
- Redis + Celery Worker + Beat；
- Opportunity / Source / Evidence / Score / Strategy / Tracking / Battlecard 业务链；
- HTML / RSS / Atom / PDF Source Connector；
- 内容寻址 DocumentStore（Local + S3-compatible）；
- SourceFetch / SourceDocument 版本、去重和抓取观察历史；
- RBAC + Organization + OIDC / trusted proxy；
- SQLAlchemy Tenant Scope + PostgreSQL RLS 双层租户隔离；
- 写操作幂等、策略乐观并发、持久化后台任务台账和人工重试；
- JSON 日志、Request/Correlation ID、Prometheus 指标、SLO 和告警；
- PostgreSQL 备份恢复演练；
- API/Web 生产镜像和生产 Compose；
- npm / Python 锁文件、依赖审计和 CycloneDX SBOM；
- `zhituo/ci-gate` 自动质量门禁。

## 三个核心经营问题

### 去哪里？Where to Play

从国家、区域、业务类型、融资来源、市场活跃度、风险和企业资源基础判断经营资源应投向哪里。

### 追什么？What to Pursue

项目进入机会池后，以统一规则评价战略匹配、项目成熟度、融资、客户、能力匹配、属地基础、竞争和风险，并明确证据置信度与信息缺口。

### 怎么拿？How to Win

针对重点机会形成客户诉求、竞争策略、伙伴策略、差异化主张、红队挑战和下一步责任行动。

## Source Intake & Archive

Production Alpha 已从“人工粘贴 URL”推进到统一外部情报接入与原件归档。

首批 Connector：

- `html`：公开 HTML / 文本网页；
- `rss`：RSS / Atom / XML 订阅源；
- `pdf`：公开 PDF 文档文本抽取。

所有 Connector 统一输出 `SourceDocument`：规范 URL、标题、正文、发布时间、发布方、内容类型、原始内容哈希、规范文本哈希和连接器元数据。

抓取后进入 DocumentStore：开发环境可使用 Local Store，生产环境强制 S3-compatible Object Storage。原件和规范文本均以 SHA-256 内容寻址，相同字节不重复保存；PostgreSQL 保存 `source_fetches / source_documents` 版本关系、首次/最近观察时间和出现次数。

同一 URL 同一内容再次出现只更新观察历史；内容发生变化才保留为新版本。RSS/Atom 一个 Feed 可产生多条规范文档，但原始 Feed 只存一份。

外部下载沿用公开 URL 安全校验，并采用流式读取和体积上限，避免把无限响应直接读入内存。PDF 当前只处理存在文本层的文档；扫描件明确进入后续 OCR 管线，而不是静默产生低质量事实。

设计见 [Source Connector 与文档归档设计](docs/SOURCE_CONNECTORS.md)。

## 技术架构

```text
Browser
  ↓
Next.js Web / BFF
  ↓
FastAPI Application
  ├─ Market / Opportunity / Strategy / Tracking
  ├─ Auth / RBAC / Audit
  ├─ Source Connector Registry
  └─ Job Dispatcher
       ↓
Redis → Celery Worker / Beat
       ↓
Source Connector → DocumentStore
                   ├─ raw/sha256/...   原始 HTML / XML / PDF
                   └─ text/sha256/...  规范文本

PostgreSQL
├─ 结构化经营事实 / RLS
└─ SourceFetch / SourceDocument 版本索引

Search / Entity Layer（后续）
```

短期坚持**模块化单体 + 独立 Worker**，不为了形式上的“生产级”过早微服务化。

## 数据原则

1. **Fact / Inference / Recommendation 分层**：事实必须绑定 Source / Evidence；推断必须可解释；建议不得伪装成事实。
2. **Unknown is valid**：缺少证据时允许不知道，不让 AI 补造客户关系、融资状态、竞争报价或中标概率。
3. **Score 不是精确中标概率**：评分用于经营资源排序和风险暴露。
4. **正式机会必须人工确认**：自动发现先进入 Draft，确认后才进入正式机会池。
5. **生产故障显式失败**：Production 禁止静默回退 Demo 数据。
6. **原件不可变、索引可演进**：外部原始字节按哈希保存，后续抽取规则和 AI 模型可以重新计算。

## 本地开发

Web：

```bash
npm ci
npm run dev:web
```

基础设施：

```bash
docker compose up -d db redis
```

API：

```bash
cd apps/api
python -m pip install 'uv>=0.8,<1'
uv sync --locked --extra dev
uv run alembic upgrade head
uv run zhituo-api seed
uv run uvicorn app.main:app --reload --port 8000
```

开发环境默认把归档原件写入 `./data/objects`；生产环境必须配置 S3-compatible DocumentStore。详细说明见 [DEVELOPMENT.md](DEVELOPMENT.md) 和 [.env.example](.env.example)。

## 当前下一阶段

Production Alpha 下一大步按以下顺序推进：

1. **Scheduled Source Scan**：来源订阅、周期扫描、ETag / Last-Modified 增量抓取、Source Health；
2. **Candidate Pipeline**：新增文档版本 → 项目识别 → 候选机会 → 人工确认；
3. **Entity Resolution**：客户、融资方、竞争对手、合作伙伴独立实体化；
4. **Search / Knowledge Layer**：跨项目、客户、国别和历史经营知识检索；
5. **真实 Action / Reminder / Approval**：把经营建议推进为多人协同工作流；
6. **OCR / 高成本连接器**：在核心闭环稳定后再接扫描 PDF、浏览器自动化和登录态来源。

## 核心文档

- [产品总纲](docs/PRODUCT_PLAN.md)
- [生产路线图](docs/PRODUCTION_ROADMAP.md)
- [生产就绪基线](docs/PRODUCTION_READINESS.md)
- [生产架构](docs/PRODUCTION_ARCHITECTURE.md)
- [生产部署](docs/PRODUCTION_DEPLOYMENT.md)
- [Source Connector 与文档归档设计](docs/SOURCE_CONNECTORS.md)
- [SLO 与监控](docs/SLO_AND_MONITORING.md)
- [运维手册](docs/OPERATIONS_RUNBOOK.md)

## 竞赛定位

智拓仍可作为中国港湾 2026 年“人工智能+”创新大赛个人赛软件系统类成果进行展示，但比赛 Demo 只是同一套产品代码的一种运行模式。主线目标是形成可持续运行、可积累企业市场资产、可逐步推广的海外市场经营智能平台。
