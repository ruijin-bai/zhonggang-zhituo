# 中港智拓｜海外工程经营智能中枢总计划

> 北极星：把智拓建设为**海外工程经营操作系统的一层智能中枢**（System of Intelligence），而不是新的 CRM、OA、ERP 或投标系统。

## 1. 最终产品定义

智拓持续感知外部市场与内部经营状态，把分散在网站、PDF、项目资料、人员经验和既有系统中的信息，转化为可追溯的经营事实、机会判断、责任行动和组织知识。

最终形成闭环：

```text
感知 → 理解 → 判断 → 协同 → 复盘 → 学习
```

对应管理问题：

1. **去哪里 Where to Play**：哪些国别、区域、业务、客户和资金来源值得配置经营资源？
2. **追什么 What to Pursue**：哪些项目值得进入正式追踪，为什么，证据是否充分？
3. **怎么拿 How to Win**：客户诉求、竞争态势、伙伴路径、赢标主张和资源缺口是什么？
4. **谁来做 How to Execute**：谁负责、何时完成、谁复核、什么条件继续投入或退出？
5. **怎么越做越好 How to Learn**：过去为什么赢、为什么输、哪些判断和行动应被复用或校准？

## 2. 产品边界

### 智拓负责

- 外部市场持续感知；
- 商机识别和多来源汇聚；
- 证据链、实体和经营知识；
- 机会评分、置信度和缺口分析；
- Go / No-Go 辅助决策；
- Pursuit Strategy 和红队挑战；
- 行动编排、提醒、复盘；
- 跨项目、客户、国家和历史经营经验检索；
- 经营结果反馈和规则/模型校准。

### 智拓不替代

- CRM 的客户主数据和正式客户活动记录；
- OA 的法定/行政审批；
- ERP/财务系统；
- 合同系统；
- 正式投标文件编制和档案系统；
- 项目履约管理系统。

原则：**连接记录系统，提供智能判断和经营编排，不复制已有企业系统。**

## 3. 五大核心引擎

### 3.1 Market Intelligence Engine｜市场感知引擎

目标：持续回答“世界正在发生什么”。

核心能力：

- Source Connector / Subscription；
- HTML / RSS / PDF / 后续 OCR / API Connector；
- ETag / Last-Modified 增量抓取；
- 原件不可变归档；
- Project Detection；
- Candidate Opportunity；
- 变化检测和来源健康。

当前成熟度：**较高**。

### 3.2 Opportunity Decision Engine｜机会决策引擎

目标：持续回答“什么值得追”。

核心能力：

- Opportunity Profile；
- Evidence / Confidence；
- Owner / Financier / Competitor / Partner；
- 100 分可解释评分；
- Missing Information；
- 动态重评；
- Go / No-Go 辅助判断；
- 多来源证据聚合。

当前成熟度：**较高**。

### 3.3 Pursuit Orchestration Engine｜经营编排引擎

目标：把“建议”变成组织执行。

核心对象：

```text
Pursuit
├─ Owner / Team
├─ Decision Gate
├─ Action
├─ Deadline
├─ Dependency
├─ Reminder
├─ Review
├─ Approval / Decision
└─ Outcome
```

必须支持：

- Action 绑定真实用户；
- 责任人、协同人和观察人；
- 截止日期、优先级、状态、阻塞原因；
- Reminder / Escalation；
- Go / Hold / No-Go 决策门；
- 决策依据、审批人和版本留痕；
- Portfolio 视角的项目、资源、逾期和风险管理。

当前成熟度：**不足，是下一主战场**。

### 3.4 Enterprise Knowledge Engine｜企业经营知识引擎

目标：回答“我们过去知道什么、做过什么”。

核心能力：

- Entity Resolution；
- Opportunity 360°；
- Search / Knowledge View；
- 客户/融资方/竞争对手/伙伴画像；
- 国别和区域经营知识；
- 历史项目、策略、行动和结果关联；
- 企业内部知识库连接；
- Evidence-first 问答。

原则：先结构化事实和可追溯检索，后向量/RAG；不为技术复杂度提前引入第二事实源。

当前成熟度：**中高，继续积累**。

### 3.5 Learning & Optimization Engine｜经营学习引擎

目标：形成企业独有的数据飞轮。

每个机会必须最终形成 Outcome：

- 未追 / 放弃；
- Go / 投标；
- 入围；
- 中标；
- 失标；
- 延期；
- 取消。

复盘至少回答：

- 当时掌握了什么信息？
- 当时为何给出该评分和决策？
- 哪些假设被后续事实证实/否定？
- 哪些 Action 真正有效？
- 实际竞争对手和客户偏好是什么？
- 赢/输的关键原因是什么？

输出用于：

- 评分规则校准；
- Strategy 模板优化；
- 来源质量评估；
- 客户/国别/竞争认知更新；
- 模型与 Prompt 评测。

当前成熟度：**早期**。

## 4. 当前产品状态

当前 `main` 已完成或基本完成：

- Production Foundation；
- Source Connector / DocumentStore；
- Scheduled Source Scan；
- Candidate Opportunity Pipeline；
- Multi-source Evidence；
- Entity Resolution；
- Structured Search；
- Opportunity Knowledge View；
- Score / Strategy / Tracking / Battlecard 基础链；
- RBAC / OIDC / trusted proxy；
- SQLAlchemy Tenant Scope + PostgreSQL RLS；
- Idempotency / Durable Job Ledger；
- Observability / SLO / Backup / SBOM / CI Gate。

因此后续开发不再按“还能加什么 AI 功能”排序，而按**能否让真实经营团队每天使用**排序。

## 5. 阶段路线

### Stage A｜经营工作台产品化

目标：让已完成的能力变成市场人员日常可用的工作入口。

交付：

- 统一经营情报工作台；
- Candidate Inbox；
- 全局 Search；
- Opportunity 360°；
- Entity 浏览；
- Source / Evidence 追溯；
- 首页呈现“今天发生什么 / 我需要处理什么”。

完成标准：

- 核心只读路径 3 次点击内完成；
- 真实 API 数据，不依赖 Demo fallback；
- viewer/analyst/manager 权限在 Web 上表现一致；
- Web TypeScript/build/production image 全绿。

### Stage B｜Pursuit Orchestration 经营编排

目标：从“告诉你应该做什么”升级为“推动组织把事做完”。

交付：

- Pursuit Workspace；
- Action 真实用户化；
- Deadline / Dependency / Blocker；
- Reminder / Escalation；
- Decision Gate；
- Go / Hold / No-Go 留痕；
- Portfolio；
- 个人 My Work / Team Work。

完成标准：

- 一个 Opportunity 从确认入池到决策和行动闭环完全可追溯；
- 每个 Action 有 owner、deadline、status；
- 到期、逾期和阻塞可主动暴露；
- 管理者能跨 Opportunity 看资源和风险。

### Stage C｜真实数据与企业连接

目标：避免智拓成为新的信息孤岛。

优先连接：

1. 企业身份目录；
2. 邮件 / Teams / 企业微信 / OA 通知之一；
3. CRM / 市场项目主数据；
4. 内部历史项目/投标结果；
5. 企业知识库。

原则：

- 外部系统仍是其权威事实源；
- 智拓保存映射、快照和智能上下文；
- 所有写回动作显式、可审计、可重试。

### Stage D｜经营结果与学习闭环

目标：建立 Outcome 和 Post-Mortem。

交付：

- Opportunity Outcome；
- Bid / No-Bid 结果；
- Win / Loss Review；
- 假设验证；
- Action effectiveness；
- Scoring calibration dataset；
- Prompt / Model / Rule evaluation。

完成标准：

- 历史机会能够回答“当时为什么这么判断、最后发生了什么”；
- 评分规则可基于真实结果校准而非凭经验静态维护。

### Stage E｜Beta 企业治理与规模化

目标：满足真实企业 Pilot / Beta 运行。

交付：

- Secret Manager / KMS；
- Prompt / Schema / Model Version Governance；
- AI cost / latency / failure governance；
- Data Quality SLA；
- Retention / Export / Delete；
- Container CVE / signing / provenance；
- Expand-Migrate-Contract；
- Canary / rollback gate；
- PostgreSQL / Redis HA（在业务证明需要后）。

## 6. 真实业务验证路线

从 Stage A 开始同步进行，不等开发结束。

### 效率指标

- 找到一个有效项目线索耗时；
- 建立标准机会卡耗时；
- 查找关键事实耗时；
- 形成初步研判耗时；
- 周/月市场经营汇报整理耗时。

### 质量指标

- Project Detection precision / recall；
- 关键字段抽取准确率；
- Evidence coverage；
- Duplicate merge precision；
- Entity resolution precision；
- 人工确认后的有效 Candidate 比例；
- 评分解释完整率。

### 组织指标

- Action 按期完成率；
- Decision Gate 平均停留时间；
- 无负责人机会比例；
- 逾期/阻塞项目暴露速度；
- 重复信息整理次数减少量。

### 学习指标

- Win/Loss 复盘覆盖率；
- 评分与实际结果的校准度；
- 关键假设命中率；
- 高价值来源命中率。

不在真实测试前预写“效率提升 80%”等结果。

## 7. 开发决策规则

任何新功能进入 Backlog 前依次回答：

1. 是否增强感知、判断、协同、记忆、学习中的至少一项？
2. 是否直接减少真实市场人员的重复劳动或提高经营判断质量？
3. 是否能进入真实组织工作流，而不只是 Demo？
4. 是否有明确的权限、审计、失败和恢复边界？
5. 是否制造新的事实孤岛或重复已有企业系统？
6. 是否只是为了 AI/架构看起来更复杂？

若 1–4 大多为否，或第 5/6 为是，不优先实施。

## 8. 明确暂缓事项

在 Stage B 完成前，不把以下内容作为主线优先级：

- 通用聊天壳；
- 大规模 Vector DB；
- 通用知识图谱；
- 多 Agent 编排秀；
- 精确“中标概率”预测；
- 为比赛单独增加产品主模块；
- 为形式上的企业级过早拆微服务；
- 重造 CRM / OA / ERP 功能。

## 9. 当前立即执行顺序

```text
A1. 完成经营情报工作台 Web
A2. Opportunity 360° Web + Entity/Search 导航
A3. Candidate 审核与补充 Evidence 的受控写操作 UI
A4. Pursuit 数据模型重构：真实用户 / Action / Decision Gate
A5. My Work + Portfolio
A6. Reminder / Escalation
A7. 选择第一个真实企业连接器
A8. Outcome / Win-Loss Review
```

每一个阶段继续采用：

**feature branch → tests → PR → CI gate 全绿 → squash merge**。

## 10. 最终成功定义

智拓达到目标，不以页面数量、模型数量或代码量衡量，而以以下场景是否成立衡量：

> 市场人员每天打开智拓，系统知道最近发生了什么、哪些机会值得处理、哪些事实发生变化、谁应该做什么；管理层能看到全球 Pursuit Portfolio、风险和资源卡点；项目结束后，系统知道当初为什么这样判断、最终为什么赢或输，并把经验沉淀给下一次经营。

当这条闭环能够在真实团队中持续运行，智拓才真正成为**海外工程经营操作系统的一层智能中枢**。
