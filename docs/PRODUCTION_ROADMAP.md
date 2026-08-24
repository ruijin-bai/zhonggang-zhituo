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
→ 主动提醒 / 升级
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

Stage A 已于 `eddc8aaf` 合入 `main`。

## 6. Stage B — Pursuit Orchestration（已完成）

目标：从“告诉经营人员应该做什么”升级为“推动组织把事情做完”。

### B1 — 协同与决策内核

- [x] `PursuitWorkspace`
- [x] Work Item 绑定真实 `Membership`
- [x] Lead / Contributor / Reviewer / Watcher
- [x] Deadline / Priority / Status
- [x] Dependency / Blocker
- [x] Decision Gate
- [x] Go / Hold / No-Go append-only Decision Record
- [x] Review / Approval lineage
- [x] `My Work` / `Team Work` / `Portfolio` 读模型
- [x] PostgreSQL RLS + runtime role grants
- [x] Tracking v1 → canonical Work Item 单向兼容桥

B1 已于 `260eaacd` 合入 `main`。

### B2 — 协同工作台

- [x] My Work Web
- [x] Team Work Web
- [x] Pursuit Workspace Web
- [x] blocked / overdue / dependency 视图
- [x] Gate / Review / Decision UI
- [x] Portfolio 管理视图
- [x] Opportunity 360° → Pursuit Workspace 连续入口
- [x] 白名单 BFF + 浏览器稳定 Idempotency-Key

B2 已于 `5f4db141` 合入 `main`。

### B3 — 提醒与升级

- [x] Durable `PursuitReminder` ledger
- [x] due-soon / overdue / blocked / Gate / Review / Workspace review policy
- [x] `blocked_since` 精确阻塞时长
- [x] Reminder dedup / acknowledge / auto-resolve / recurrence count
- [x] overdue / blocked / pending-review escalation to Workspace Lead
- [x] Beat dispatcher → per-tenant Worker reconciliation
- [x] My Work Reminder Inbox + 受控“已知悉”
- [x] Critical / Escalated Reminder → Daily Brief
- [x] PostgreSQL RLS + runtime grants + lifecycle/idempotency tests

B3 已于 `bbd12b0f` 合入 `main`。到此 Stage B 完整形成“责任—行动—依赖—复核—决策—提醒—升级”的经营执行闭环。

兼容原则：

- `PursuitWorkItem` 是权威协同事实；旧 `pursuit_actions` 仅为 Tracking v1 兼容对象；
- 旧字符串负责人只保存为 `legacy_owner_text`，绝不自动伪装成真实用户；
- Web 主路径已切换到 `/pursuit`；后续按 Expand-Migrate-Contract 清理 Tracking v1。

## 7. 当前主战场：Stage C — 企业连接与真实数据

目标：不重造企业已有系统，而是让智拓与真实组织身份、通知渠道、项目主数据和历史经营结果连接起来。

### C1 — Reminder Email Delivery Adapter（当前分支）

- [x] Durable `PursuitReminderDelivery` outbox（本分支实现，待 CI）
- [x] Reminder occurrence / escalation / recipient / email snapshot 确定性 delivery key（本分支实现，待 CI）
- [x] Beat staging + claim + per-message Worker（本分支实现，待 CI）
- [x] lease / fencing token / SKIP LOCKED（本分支实现，待 CI）
- [x] exponential retry / failed ledger / manager manual retry（本分支实现，待 CI）
- [x] stale delivery cancellation：Reminder 已知悉/解除、目标或邮箱变化时不发送旧通知（本分支实现，待 CI）
- [x] SMTP STARTTLS / SSL Adapter + server-only secrets（本分支实现，待 CI）
- [x] deterministic Message-ID + plain/HTML body + optional Pursuit deep link（本分支实现，待 CI）
- [x] manager delivery health API + manual retry business idempotency / Audit（本分支实现，待 CI）
- [x] PostgreSQL RLS + runtime grants + outbox tests（本分支实现，待 CI）

投递语义：**durable at-least-once**。SMTP 无法提供端到端 exactly-once；系统通过持久化 outbox、确定性 Message-ID、租约/fencing 和发送账本降低重复风险，并显式记录发送结果，不宣传不存在的 exactly-once 保证。

### Stage C 后续顺序

1. [ ] 企业身份目录深化 / Membership provisioning；
2. [x] 邮件通知 Delivery Adapter（当前分支实现，待 CI）；
3. [ ] CRM / 市场项目主数据同步；
4. [ ] 历史投标 / 中标 / 失标数据；
5. [ ] 企业知识库连接；
6. [ ] OCR / 高价值采购平台/API Connector；
7. [ ] 视真实企业环境再增加 Teams / 企业微信 / OA Delivery Adapter。

原则：外部系统继续作为其权威事实源，智拓只保存智能上下文、映射、审计、必要快照和可靠投递状态。

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

## 10. 当前仍暂缓的事项

以下内容不作为当前主线优先级：

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
