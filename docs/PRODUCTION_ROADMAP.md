# 中港智拓 Production Roadmap

> 北极星：**海外工程经营操作系统的一层智能中枢**。
>
> 详细产品边界、五大引擎和最终成功定义见 `docs/INTELLIGENCE_HUB_MASTER_PLAN.md`。本文件只保留当前生产阶段、完成项和近期执行顺序。

## 1. 当前阶段：Production Alpha 中后段

当前主线已经完成从“比赛原型”向真实企业系统架构的转变。后续优先级不再由 Demo 功能决定，而由真实经营团队是否能持续使用决定。

核心闭环：

```text
感知市场
→ 识别商机
→ 汇聚证据与实体
→ 机会研判
→ 形成策略
→ 编排行动
→ 记录结果
→ 复盘学习
```

## 2. 已完成的生产底座

### 工程与治理

- [x] Next.js Web + BFF
- [x] FastAPI API
- [x] PostgreSQL + Alembic
- [x] Redis + Celery Worker + Beat
- [x] Web / API production images
- [x] Production Compose
- [x] npm workspace lock + Python uv lock
- [x] Python/Web dependency audit + CycloneDX SBOM
- [x] `zhituo/ci-gate`
- [x] PostgreSQL backup / restore drill
- [x] JSON logging / Request ID / Correlation ID
- [x] Prometheus metrics / SLO / alert rules

### 身份、安全与一致性

- [x] User / Organization / Membership / RBAC
- [x] trusted proxy + OIDC JWT
- [x] SQLAlchemy Tenant Scope
- [x] PostgreSQL RLS
- [x] runtime / migration / backup DB roles
- [x] Idempotency-Key
- [x] business-write idempotency
- [x] Strategy optimistic concurrency
- [x] Durable Background Job Ledger
- [x] retry lineage / stuck-job reconciliation
- [x] tenant-switch identity-map cache hardening

## 3. 已完成的市场感知与商机链

### Source / Document

- [x] Connector contract / registry
- [x] HTML / Text
- [x] RSS / Atom
- [x] PDF text extraction
- [x] streaming download / size limits / SSRF boundary
- [x] Local + S3-compatible `DocumentStore`
- [x] raw/text SHA-256 content addressing
- [x] immutable raw object archival
- [x] SourceFetch / SourceDocument versioning and dedup

### Scheduled Market Sensing

- [x] SourceSubscription / SourceScanRun
- [x] ETag / Last-Modified / 304 conditional fetch
- [x] Beat dispatcher + Worker scan
- [x] lease + fencing token
- [x] exponential backoff / auto-pause / manual resume
- [x] source health history

### Candidate Opportunity

- [x] durable CandidateProcessing ledger
- [x] SourceDocument → Project Detection
- [x] no-project separation
- [x] Candidate Inbox
- [x] high-threshold candidate dedup
- [x] formal Opportunity duplicate warning only
- [x] Candidate → human confirmation → Opportunity
- [x] original text restored from DocumentStore before formal evidence creation
- [x] multi-source Candidate aggregation
- [x] immutable OpportunitySourceDocument provenance
- [x] manager-controlled “attach as evidence” path

## 4. 已完成的经营知识层

### Evidence / Entity

- [x] Source / Evidence / Confidence
- [x] SourceDocumentInsight
- [x] Entity / Alias
- [x] Owner / Financier / Competitor / Partner roles
- [x] conservative entity normalization
- [x] same-name cross-country separation
- [x] human alias management with ambiguity rejection
- [x] Opportunity entity relations
- [x] multi-source entity evidence aggregation

### Search / Knowledge

- [x] unified structured search
- [x] Opportunity / Candidate / Entity / Evidence / Source search
- [x] deterministic relevance + matched fields
- [x] country / sector / role / source-rank filters
- [x] Opportunity 360° Knowledge API
- [x] related opportunities by shared resolved entities
- [x] source/evidence provenance
- [x] tenant-safe search through existing RLS-backed facts

## 5. Stage A — 经营工作台产品化（已完成）

- [x] 统一经营情报 Web 工作台
- [x] Candidate Inbox + 受控 confirm / reject / attach evidence
- [x] 全局 Search Web
- [x] Opportunity 360° Web
- [x] Entity 360° Web
- [x] Opportunity / Candidate / Entity 连续导航
- [x] Daily Brief：“今天发生什么 / 我需要处理什么”
- [x] viewer / analyst / manager / admin 审核边界
- [x] Candidate 审核业务幂等 + Audit
- [x] Web check / build / production image / full `zhituo/ci-gate`

Stage A 已于 `eddc8aaf` 合入 `main`。首页和经营情报工作台已经从比赛入口转为日常经营入口。

## 6. 当前主战场：Stage B — Pursuit Orchestration

目标：从“告诉经营人员应该做什么”升级为“推动组织把事情做完”。

### B1 — 协同与决策内核（当前分支）

- [x] `PursuitWorkspace`（本分支实现，待 CI）
- [x] Work Item 绑定真实 `Membership`（本分支实现，待 CI）
- [x] Lead / Contributor / Reviewer / Watcher（本分支实现，待 CI）
- [x] Deadline / Priority / Status（本分支实现，待 CI）
- [x] Dependency / Blocker（本分支实现，待 CI）
- [x] Decision Gate（本分支实现，待 CI）
- [x] Go / Hold / No-Go append-only Decision Record（本分支实现，待 CI）
- [x] Review / Approval lineage（本分支实现，待 CI）
- [x] `My Work` 读模型（本分支实现，待 CI）
- [x] `Team Work` 读模型（本分支实现，待 CI）
- [x] `Portfolio` 读模型（本分支实现，待 CI）
- [x] PostgreSQL RLS + runtime role grants（本分支实现，待 CI）
- [x] Tracking v1 → canonical Work Item 单向兼容桥（本分支实现，待 CI）

兼容原则：

- Stage B 的 `PursuitWorkItem` 是新的权威协同事实；
- 旧 `pursuit_actions` 仅为 Tracking v1 兼容对象；
- 旧写入单向同步到新模型，防止新增历史入口造成数据丢失；
- 旧字符串负责人只保存为 `legacy_owner_text`，绝不自动伪装成真实用户；
- 新 Stage B 写入不反向制造旧 Action；
- 后续 Web 切换完成后再移除 Tracking v1 写入口。

### B2 — 协同工作台（B1 合入后立即推进）

- [ ] My Work Web
- [ ] Team Work Web
- [ ] Pursuit Workspace Web
- [ ] blocked / overdue / dependency 视图
- [ ] Gate / Review / Decision UI
- [ ] Portfolio 管理视图
- [ ] Opportunity 360° → Pursuit Workspace 连续入口

### B3 — 提醒与升级

- [ ] Reminder policy
- [ ] Escalation policy
- [ ] overdue / review-due notifications
- [ ] 邮件 / Teams / 企业微信 / OA 至少一个通知出口

Stage B 完成标准：

> 一个 Opportunity 从正式确认入池到决策、行动、复核和退出/继续投入，全部能够回答“谁、何时、做了什么、依据什么、结果如何”。

## 7. Stage C — 企业连接与真实数据

按最小业务价值优先连接，不以连接器数量为目标：

1. [ ] 企业身份目录深化；
2. [ ] 邮件 / Teams / 企业微信 / OA 通知之一；
3. [ ] CRM / 市场项目主数据；
4. [ ] 历史投标 / 中标 / 失标数据；
5. [ ] 企业知识库；
6. [ ] OCR / 高价值采购平台/API Connector。

原则：外部系统继续作为其权威事实源，智拓只保存智能上下文、映射、审计和必要快照。

## 8. Stage D — Outcome / Learning Loop

- [ ] Opportunity Outcome
- [ ] Bid / No-Bid
- [ ] Win / Loss
- [ ] cancellation / postponement
- [ ] Win-Loss Review
- [ ] historical hypothesis validation
- [ ] action effectiveness
- [ ] score calibration dataset
- [ ] source quality calibration
- [ ] prompt/model/rule evaluation dataset

目标：让企业历史经营结果反向改善下一次机会判断，而不是长期依赖静态经验规则。

## 9. Stage E — Beta 企业治理

- [ ] Secret Manager / KMS
- [ ] Prompt / Schema / Model Version Governance
- [ ] AI cost / latency / failure governance
- [ ] Data Quality SLA
- [ ] retention / export / delete policies
- [ ] container CVE scan / image signing / provenance
- [ ] Expand-Migrate-Contract
- [ ] Canary / rolling / rollback gate
- [ ] PostgreSQL / Redis HA（业务证明需要后）

## 10. 暂缓事项

在 Stage B 完成前，不把以下内容作为主线优先级：

- 通用 Chat/RAG 壳；
- 大规模 Vector DB；
- 通用知识图谱；
- 多 Agent 编排展示；
- 精确中标概率；
- 为比赛单独增加一级模块；
- 过早微服务化；
- 重造 CRM / OA / ERP。

## 11. Production Definition of Done

功能只有同时满足以下条件才算完成：

1. 有真实数据模型或明确无状态设计；
2. 有权限边界；
3. 有输入校验和失败路径；
4. 有审计/日志；
5. 有自动化测试；
6. 不依赖 Demo 数据；
7. AI 失败不能破坏事实；
8. 关键结论可追溯；
9. 关键写入可说明谁、何时、为什么；
10. 有部署、回滚和恢复路径；
11. 最终 `zhituo/ci-gate` 全绿。

当前详细路线以 `INTELLIGENCE_HUB_MASTER_PLAN.md` 为最高优先级产品计划。