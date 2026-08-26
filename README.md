# 中港智拓 Zhonggang Zhituo

> **海外工程经营操作系统的一层智能中枢**  
> System of Intelligence for Overseas Engineering Business Development

智拓持续回答海外经营最重要的问题：**去哪里、追什么、怎么拿、谁来做、如何越做越好。**

## 产品定位

智拓不替代 CRM、OA、ERP、合同、投标和项目履约系统。它连接这些记录系统与外部市场，把分散在网站、PDF、项目资料、系统和人员经验中的信息转化为：

**可追溯经营事实 → 可解释机会判断 → 可执行责任行动 → 可复用企业知识 → 可校准经营经验**

最终闭环：

```text
感知 → 理解 → 判断 → 协同 → 复盘 → 学习
```

详细北极星、产品边界、五大引擎和阶段路线见：

- [海外工程经营智能中枢总计划](docs/INTELLIGENCE_HUB_MASTER_PLAN.md)
- [Production Roadmap](docs/PRODUCTION_ROADMAP.md)

## 当前阶段：Production Alpha 中后段

### 1. Market Intelligence Engine｜市场感知

已具备：

- HTML / RSS / Atom / PDF Source Connector；
- Local + S3-compatible DocumentStore；
- raw/text SHA-256 内容寻址与不可变原件；
- SourceFetch / SourceDocument 去重与版本历史；
- SourceSubscription / SourceScanRun；
- ETag / Last-Modified / 304 增量抓取；
- Beat / Worker 调度、lease + fencing token；
- 指数退避、自动暂停、人工恢复；
- Durable CandidateProcessing；
- SourceDocument → Project Detection → Candidate Inbox。

### 2. Opportunity Decision Engine｜机会决策

已具备：

- Candidate 人工 confirm / reject；
- 正式 Opportunity 疑似重复只提示人工，不自动吞并；
- 多来源 Candidate 聚合；
- Candidate → Opportunity 的原件恢复与 SHA-256 校验；
- Source / Evidence / Confidence；
- 100 分可解释评分与动态重评；
- Pursuit Thesis / Strategy / Red Team；
- immutable OpportunitySourceDocument provenance；
- 后续 Candidate 可由经营人员显式 attach 为正式 Opportunity 补充证据。

### 3. Enterprise Knowledge Engine｜经营知识

已具备：

- Owner / Financier / Competitor / Partner Entity；
- 保守 Entity Resolution；
- 同名跨国不自动合并；
- Alias 与人工纠错边界；
- 多来源 Entity Evidence；
- Opportunity / Candidate / Entity / Evidence / Source 统一结构化检索；
- deterministic relevance + matched fields；
- Opportunity 360° Knowledge View；
- 共享已解析 Entity 的相关 Opportunity；
- Entity 360° 浏览；
- Evidence / Source / SourceDocument provenance 追溯。

### 4. Stage A｜经营工作台产品化

当前已实现：

- `/knowledge` 经营情报工作台；
- Candidate Inbox；
- Candidate 审核详情；
- manager/admin 受控 confirm / reject / attach evidence；
- viewer/analyst 只读；
- Opportunity 360°；
- Entity 浏览与 Entity 360°；
- 首页 Daily Operating Brief：最近变化、待审 Candidate、逾期 Action、Alert、到期 Review。

Daily Brief 是对现有业务事实的实时读模型，不新建第二套待办状态。

## 下一主战场：Pursuit Orchestration Engine

下一阶段不继续横向堆 AI 功能，而把“建议”升级为真实组织执行：

```text
Opportunity
  ↓
Pursuit Workspace
  ├─ Owner / Team / Watcher
  ├─ Action / Deadline / Dependency / Blocker
  ├─ Reminder / Escalation
  ├─ Decision Gate
  ├─ Go / Hold / No-Go
  ├─ Review / Approval
  └─ Outcome
```

优先交付：

1. Action 绑定真实 User / Membership；
2. Pursuit Workspace；
3. Decision Gate 与决策留痕；
4. My Work / Team Work；
5. Portfolio；
6. Reminder / Escalation。

之后进入企业连接和 Outcome / Win-Loss 学习闭环。

## 技术与生产底座

当前主线包括：

- Next.js Web / BFF + FastAPI；
- PostgreSQL + Alembic；
- Redis + Celery Worker / Beat；
- RBAC + Organization + OIDC / trusted proxy；
- SQLAlchemy Tenant Scope + PostgreSQL RLS；
- runtime / migration / backup 数据库角色隔离；
- 同步业务幂等、Queue 幂等、Strategy 乐观并发；
- Durable Background Job Ledger + retry lineage + stuck reconciler；
- JSON logging / Request ID / Correlation ID；
- Prometheus / SLO / Alerts；
- PostgreSQL backup / restore drill；
- API/Web production images + Production Compose；
- npm / uv lock；
- Python/Web dependency audit + CycloneDX SBOM；
- `zhituo/ci-gate` 自动主线门禁。

短期坚持：**模块化单体 + 独立 Worker**。不为了形式上的“企业级”过早拆微服务。

Oracle Cloud 单机长期 Internal Pilot 的独立部署层、Free Tier IaC、升级、健康、备份、恢复与真实来源验收见：

- `deploy/pilot/README.md`
- `infra/oracle-pilot/README.md`

## 核心数据原则

1. **Fact / Inference / Recommendation 分层**：事实必须绑定 Source / Evidence。
2. **Unknown is valid**：证据不足允许不知道，不让 AI 补造客户关系、融资状态、报价或关键人态度。
3. **Score ≠ 中标概率**：评分用于资源排序与风险暴露。
4. **正式 Opportunity 必须人工确认**。
5. **原件不可变、索引可演进**：原始字节按哈希保存，抽取和模型可以重算。
6. **生产故障显式失败**：Production 禁止静默回退 Demo 数据伪装真实状态。
7. **调度必须可恢复**：持久状态、租约和 fencing token。
8. **外部网络调用不跨数据库长事务**。
9. **机器不自动合并正式项目**：新标段、新包件、新阶段必须保留人工判断空间。

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

持续来源扫描和 Candidate Pipeline 需要 Worker 与唯一 Beat。开发默认 Local DocumentStore；生产强制 S3-compatible Object Storage。

## 核心文档

- [智能中枢总计划](docs/INTELLIGENCE_HUB_MASTER_PLAN.md)
- [Production Roadmap](docs/PRODUCTION_ROADMAP.md)
- [Production Readiness](docs/PRODUCTION_READINESS.md)
- [Production Architecture](docs/PRODUCTION_ARCHITECTURE.md)
- [Production Deployment](docs/PRODUCTION_DEPLOYMENT.md)
- [Source Connector](docs/SOURCE_CONNECTORS.md)
- [Candidate Pipeline](docs/CANDIDATE_PIPELINE.md)
- [Search / Knowledge](docs/SEARCH_KNOWLEDGE_LAYER.md)
- [SLO / Monitoring](docs/SLO_AND_MONITORING.md)
- [Operations Runbook](docs/OPERATIONS_RUNBOOK.md)

## 竞赛

竞赛不再决定主产品路线。需要参赛时，从完整智拓中抽取一个可验证的小闭环作为作品，不为比赛反向修改核心架构。
