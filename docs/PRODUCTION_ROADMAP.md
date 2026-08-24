# 中港智拓 Production Roadmap

> 产品目标：面向海外工程企业的 AI 市场情报与经营决策平台。

智拓不再以比赛 Demo 作为最终架构约束。比赛展示保留为独立 Demo Mode；主线按真实数据、持续运行、多人协同和企业治理推进。

## 1. 核心经营闭环

**持续感知全球市场 → 自动发现项目机会 → 建立证据链 → 评估经营价值 → 形成经营策略 → 驱动跟踪行动 → 沉淀企业市场资产**

产品围绕三个管理问题组织：

1. **去哪里（Where to Play）**：国别、区域、行业、资金来源与市场活跃度。
2. **追什么（What to Pursue）**：项目成熟度、融资、客户、竞争、能力匹配、风险和证据置信度。
3. **怎么拿（How to Win）**：客户诉求、竞争策略、伙伴策略、赢标主张、红队挑战、责任人与行动计划。

## 2. 当前阶段：Production Alpha

### Foundation — 已完成

- [x] Next.js Web + FastAPI API
- [x] PostgreSQL + Alembic
- [x] Redis + Celery Worker + Beat
- [x] Opportunity / Source / Evidence / ScoreSnapshot / Event
- [x] 市场雷达、商机发现、人工确认、动态重评
- [x] Strategy / Tracking / Battlecard 基础经营链
- [x] Demo / Development / Production 配置隔离
- [x] User / Organization / RBAC
- [x] trusted proxy + OIDC JWT 身份适配
- [x] SQLAlchemy Tenant Scope + PostgreSQL RLS
- [x] runtime / migration / backup 数据库角色拆分
- [x] Queue Idempotency + 关键同步写操作幂等
- [x] Strategy optimistic concurrency
- [x] Durable Background Job Ledger + retry lineage
- [x] Stuck Job Reconciler
- [x] JSON 日志、Request ID、Correlation ID
- [x] Prometheus metrics、首版 SLO 和告警规则
- [x] PostgreSQL backup / restore drill
- [x] Web/API production image + production Compose
- [x] Python/Web dependency audit + CycloneDX SBOM
- [x] npm workspace lock + Python uv lock
- [x] `zhituo/ci-gate` 自动质量门禁

Foundation 完成后，除明确的高风险缺陷外，不再优先投入“为了更像大系统”的基础设施建设。工程资源转向真实数据、知识资产和经营闭环。

## 3. Alpha-1 — 外部市场感知与原件资产化

### A. Source Connector Foundation — 当前实现

- [x] 统一 `SourceDocument` 契约
- [x] Connector Registry
- [x] HTML / Text Connector
- [x] RSS / Atom Connector
- [x] PDF Connector
- [x] 流式下载与字节上限
- [x] 公开 URL / redirect SSRF 边界复用
- [x] 内容 SHA-256 / 原件 SHA-256
- [x] 首批 Connector 单元测试
- [ ] OCR Connector / OCR Worker
- [ ] 采购平台/API 专用 Connector

### B. Object Storage — 下一大步

- [ ] `DocumentStore` 抽象
- [ ] 本地开发实现
- [ ] S3-compatible 生产实现
- [ ] 以 `raw_sha256` 进行内容寻址
- [ ] 原始 HTML / PDF / XML / JSON 持久化
- [ ] MIME / size / fetched_at / ETag / Last-Modified 元数据
- [ ] 相同原件不重复写入
- [ ] PostgreSQL 仅保存对象引用和结构化索引

### C. Scheduled Source Scan

- [ ] Source Feed / Connector Configuration 模型
- [ ] 调度周期、启停、抓取状态
- [ ] ETag / If-Modified-Since 增量抓取
- [ ] 单源失败隔离与重试
- [ ] 抓取成功率、延迟和新文档量指标
- [ ] 管理员 Source Health 视图

## 4. Alpha-2 — Candidate Opportunity Pipeline

目标：让系统从“读文档”升级为“持续产生可审核的候选商机”。

```text
Source Scan
  ↓
SourceDocument
  ↓
Object Storage / Hash Dedup
  ↓
Project Detection
  ↓
Entity Resolution
  ↓
Candidate Opportunity
  ↓
AI 初筛 + Evidence
  ↓
人工确认
  ↓
正式 Opportunity
```

### P0

- [ ] canonical URL + hash 双重去重
- [ ] 同一项目跨来源聚合
- [ ] Candidate Opportunity 独立状态模型
- [ ] 来源增量触发项目重评
- [ ] Candidate → Confirmed 审计链
- [ ] 重复项目合并/关联操作
- [ ] “为什么识别成商机”证据解释

## 5. Alpha-3 — Entity / Search / Knowledge Layer

### 实体化

- [ ] Client / Owner
- [ ] Financier
- [ ] Competitor
- [ ] Partner
- [ ] Country / Region
- [ ] Project / Opportunity

### Entity Resolution

- [ ] Alias
- [ ] 名称规范化
- [ ] 同一机构跨来源合并
- [ ] 人工纠错和合并历史

### Search / Knowledge

- [ ] 全局检索
- [ ] 项目时间线
- [ ] 国别知识页
- [ ] 客户画像与历史项目
- [ ] 竞争对手画像
- [ ] Evidence 可回到原始文档位置
- [ ] 历史经营策略与结果可复盘

短期继续使用 PostgreSQL；只有实体关系规模和查询模式证明需要时，再引入专门图数据库或向量检索服务。

## 6. Alpha-4 — 真实经营协同

- [ ] Action 绑定真实负责人账号
- [ ] Deadline / Status / Reminder
- [ ] Alert routing
- [ ] Go / No-Go 审批与留痕
- [ ] 管理层 Portfolio / Resource Allocation
- [ ] Audit 查询与导出 UI
- [ ] Failed / Dead Letter Job 管理 UI
- [ ] Organization / Team / Member 管理 UI
- [ ] 邮件 / OA / 企业协同通知接口

## 7. Beta — 企业治理与规模化

- [ ] Region / Team 细粒度权限继承
- [ ] Prompt / Schema / Model Version Governance
- [ ] AI 成本、延迟、失败率治理
- [ ] 数据质量 SLA
- [ ] 数据保留、删除、导出和合规策略
- [ ] Secret Manager / KMS 与自动轮换
- [ ] Container CVE scan / image signing / provenance
- [ ] Expand-Migrate-Contract 数据库迁移规范
- [ ] Canary / rolling deploy / rollback gate
- [ ] PostgreSQL / Redis 高可用
- [ ] 跨区域灾备（有明确业务需求后）

## 8. 环境原则

### Demo / Development

允许：

- `DEMO_MODE=true`
- `ALLOW_DEMO_FALLBACK=true`
- `DATA_BACKEND=auto`
- `JOB_MODE=inline` 或 `queue`

### Production

必须：

- `APP_ENV=production`
- `DEMO_MODE=false`
- `ALLOW_DEMO_FALLBACK=false`
- `DATA_BACKEND=database`
- `JOB_MODE=queue`
- `DATABASE_RLS_ENABLED=true`

生产故障必须显式失败并进入监控，不得静默展示 Demo 数据。

## 9. Production Definition of Done

一个功能只有同时满足以下条件才视为生产完成：

1. 有真实数据库模型或明确无状态设计；
2. 有权限边界；
3. 有输入校验和失败路径；
4. 有日志/审计；
5. 有自动化测试；
6. 不依赖 Demo 数据才能运行；
7. AI 失败时不会破坏事实数据；
8. 关键结果可以追溯到来源；
9. 数据变更可以知道谁、何时、为什么；
10. 有可部署、可回滚、可恢复路径。

## 10. 当前执行顺序

当前主线不再继续横向堆功能，按以下顺序推进：

1. **Object Storage + DocumentStore**
2. **Scheduled Source Scan**
3. **Candidate Opportunity Pipeline**
4. **Entity Resolution + Search/Knowledge**
5. **真实 Action / Reminder / Approval**
6. **Beta 级企业治理和规模化**

> 原则：先让智拓真正持续“看世界、记原件、识别机会”，再扩大管理功能和基础设施复杂度。
