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
- SourceSubscription / SourceScanRun 持续来源监测；
- ETag / Last-Modified 条件抓取与 304 增量扫描；
- 扫描租约 fencing token、失败指数退避、自动暂停与人工恢复；
- CandidateProcessing 持久化候选处理队列；
- SourceDocument → Project Detection → Candidate Inbox → 人工确认入池；
- 候选高阈值自动去重、正式 Opportunity 疑似重复人工复核；
- Candidate 原文从 DocumentStore 恢复并校验后再绑定正式 Source/Evidence；
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

## Market Sensing → Candidate Opportunity

Production Alpha 已从“人工粘贴 URL”推进到统一外部情报接入、原件归档、持续来源监测和候选机会自动发现。

首批 Connector：

- `html`：公开 HTML / 文本网页；
- `rss`：RSS / Atom / XML 订阅源；
- `pdf`：公开 PDF 文档文本抽取。

所有 Connector 统一输出 `SourceDocument`。抓取后进入 DocumentStore：开发环境可使用 Local Store，生产环境强制 S3-compatible Object Storage。原件和规范文本均以 SHA-256 内容寻址；PostgreSQL 保存版本关系、观察历史、来源健康和后续候选处理状态。

持续监测通过 `source_subscriptions` 保存来源配置、扫描周期、ETag / Last-Modified、健康状态和下一次扫描时间；`source_scan_runs` 保存每次扫描历史。Beat 只负责认领到期来源，实际网络抓取由独立 Worker 完成。

每个新 `SourceDocument` 在归档事务内同步产生唯一 `candidate_processing` 记录。因此 Redis 暂时不可用、Worker 重启或投递失败都不会导致“文档已经入库但商机永远没被识别”。另一个 Beat 调度任务会持续认领待处理文档，由 Worker 从 DocumentStore 校验并读取规范正文后执行 Project Detection。

明确不是具体工程项目的文档进入 `no_project`；识别出的具体项目进入 Candidate Inbox。高度相似的**待审候选**可自动压成一张卡，但对已经正式入池的 Opportunity 只给疑似重复提示，防止把新标段、新采购包或二次招标误吞掉。

Candidate 不直接成为正式 Opportunity。经营人员必须人工 confirm/reject。确认时系统重新从 DocumentStore 取回原始规范正文并校验 SHA-256，之后才创建正式 Source / Evidence / ScoreSnapshot / Event；原件缺失或损坏时拒绝无证据入池。

设计见：

- [Source Connector、归档与持续监测](docs/SOURCE_CONNECTORS.md)
- [Candidate Opportunity Pipeline](docs/CANDIDATE_PIPELINE.md)

## 技术架构

```text
Browser
  ↓
Next.js Web / BFF
  ↓
FastAPI Application
  ├─ Market / Opportunity / Strategy / Tracking
  ├─ Auth / RBAC / Audit
  ├─ Source Subscription Management
  ├─ Candidate Inbox
  └─ Job Dispatcher
       ↓
Redis → Celery Worker / Beat
       │
       ├─ SourceSubscription → Conditional Fetch
       │                         ↓
       │                   Source Connector
       │                         ↓
       │                   DocumentStore
       │                  raw/ + text/sha256/...
       │                         ↓
       └─ CandidateProcessing ← SourceDocument
                                 ↓
                         Project Detection
                       ┌─────────┴─────────┐
                  no_project        OpportunityDraft
                                           ↓ 人工确认
                                      Opportunity
                                      Source/Evidence

PostgreSQL
├─ 结构化经营事实 / RLS
├─ SourceFetch / SourceDocument
├─ SourceSubscription / SourceScanRun
└─ CandidateProcessing / OpportunityDraft
```

短期坚持**模块化单体 + 独立 Worker**，不为了形式上的“生产级”过早微服务化。

## 数据原则

1. **Fact / Inference / Recommendation 分层**：事实必须绑定 Source / Evidence；推断必须可解释；建议不得伪装成事实。
2. **Unknown is valid**：缺少证据时允许不知道，不让 AI 补造客户关系、融资状态、竞争报价或中标概率。
3. **Score 不是精确中标概率**：评分用于经营资源排序和风险暴露。
4. **正式机会必须人工确认**：自动发现先进入 Candidate/Draft，确认后才进入正式机会池。
5. **生产故障显式失败**：Production 禁止静默回退 Demo 数据。
6. **原件不可变、索引可演进**：外部原始字节按哈希保存，后续抽取规则和 AI 模型可以重新计算。
7. **调度必须可恢复**：周期任务使用持久化状态、租约和 fencing token，不把可靠性寄托在 Celery 内存状态上。
8. **外部调用不跨数据库长事务**：Object Storage / AI 网络工作在数据库事务之外执行，最终状态使用短事务和 fencing token 落库。

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

持续来源扫描和 Candidate Pipeline 还需启动 Worker 与唯一 Beat。开发环境默认把归档原件写入 `./data/objects`；生产环境必须配置 S3-compatible DocumentStore。详细说明见 [DEVELOPMENT.md](DEVELOPMENT.md) 和 [.env.example](.env.example)。

## 当前下一阶段

Production Alpha 下一大步按以下顺序推进：

1. **Entity Resolution / Evidence Aggregation**：客户、融资方、竞争对手、合作伙伴实体化，并把多来源证据持续汇聚到 Candidate / Opportunity；
2. **Search / Knowledge Layer**：跨项目、客户、国别和历史经营知识检索；
3. **真实 Action / Reminder / Approval**：把经营建议推进为多人协同工作流；
4. **OCR / 高成本连接器**：在核心闭环稳定后再接扫描 PDF、浏览器自动化和登录态来源。

## 核心文档

- [产品总纲](docs/PRODUCT_PLAN.md)
- [生产路线图](docs/PRODUCTION_ROADMAP.md)
- [生产就绪基线](docs/PRODUCTION_READINESS.md)
- [生产架构](docs/PRODUCTION_ARCHITECTURE.md)
- [生产部署](docs/PRODUCTION_DEPLOYMENT.md)
- [Source Connector 与文档归档设计](docs/SOURCE_CONNECTORS.md)
- [Candidate Opportunity Pipeline](docs/CANDIDATE_PIPELINE.md)
- [SLO 与监控](docs/SLO_AND_MONITORING.md)
- [运维手册](docs/OPERATIONS_RUNBOOK.md)

## 竞赛定位

智拓仍可作为中国港湾 2026 年“人工智能+”创新大赛个人赛软件系统类成果进行展示，但比赛 Demo 只是同一套产品代码的一种运行模式。主线目标是形成可持续运行、可积累企业市场资产、可逐步推广的海外市场经营智能平台。
