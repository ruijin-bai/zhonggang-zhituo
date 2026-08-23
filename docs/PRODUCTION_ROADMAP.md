# 中港智拓 Production Roadmap

> 产品目标：面向海外工程企业的 AI 市场情报与经营决策平台。

智拓不再以“比赛 Demo”作为最终架构约束。比赛展示保留为独立 Demo Mode；主线按可持续运行、真实数据、多人协同和企业治理推进。

## 1. 核心经营闭环

**持续感知全球市场 → 自动发现项目机会 → 建立证据链 → 评估经营价值 → 形成经营策略 → 驱动跟踪行动 → 沉淀企业市场资产**

产品仍围绕三个管理问题组织：

1. **去哪里（Where to Play）**：国别、区域、行业、资金来源与市场活跃度。
2. **追什么（What to Pursue）**：项目成熟度、融资、客户、竞争、能力匹配、风险和证据置信度。
3. **怎么拿（How to Win）**：客户诉求、竞争策略、伙伴策略、赢标主张、红队挑战、责任人与行动计划。

## 2. 环境隔离

### Demo / Development

- `APP_ENV=development`
- `DEMO_MODE=true`
- `ALLOW_DEMO_FALLBACK=true`
- `NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=true`
- `DATA_BACKEND=auto`
- `JOB_MODE=inline` 或 `queue`

允许数据库未启动时使用内置 Demo 数据；开发者可选择同步调试或完整 Redis/Celery 异步链路。

### Production

- `APP_ENV=production`
- `DEMO_MODE=false`
- `ALLOW_DEMO_FALLBACK=false`
- `NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=false`
- `DATA_BACKEND=database`
- `JOB_MODE=queue`

生产环境禁止静默回退 Demo 数据，禁止同步执行网页抓取、情报抽取和 AI 长任务。API/数据库/Worker 故障必须显式失败并进入监控。

## 3. Production Alpha

目标：让系统连续处理真实公开信息，并由真实用户完成一次完整经营闭环。

### P0 — 必须完成

- [x] PostgreSQL + Alembic 数据模型
- [x] Source / Evidence / Opportunity / ScoreSnapshot / Event
- [x] 商机发现与人工确认
- [x] 动态重评
- [x] 市场雷达
- [x] 跟踪 / 策略 / 作战卡基础链路
- [x] Demo 与 Production fallback 隔离
- [x] 用户身份与基础 RBAC
- [x] Organization 基础模型与 Job 组织隔离
- [x] Audit Log 基础能力
- [x] Redis + Celery 后台任务队列
- [x] 采集、情报抽取、AI 研判、策略生成和红队任务不阻塞生产 HTTP 请求
- [ ] Region / Team 细粒度数据隔离
- [ ] 企业 SSO / OIDC 身份接入
- [ ] 生产部署配置与 Secrets 管理
- [ ] API 请求日志、错误追踪与 Worker 可观测性
- [ ] 数据库自动备份与恢复演练
- [ ] Source Connector：RSS / 官方公告页 / API / PDF
- [ ] 文档原件存储与内容哈希去重
- [ ] 真实经营 Action：负责人账号、截止时间、状态、提醒

### P1 — Internal Pilot

- [ ] 客户、竞争对手、合作伙伴独立实体模型
- [ ] Entity Resolution：同一机构跨来源合并
- [ ] 全局检索
- [ ] 项目时间线
- [ ] 国别知识页
- [ ] 客户画像与历史项目关系
- [ ] 竞争对手画像
- [ ] 人工评分调整必须记录理由和操作者
- [ ] AI Prompt / Model / Output 版本审计
- [ ] Evidence 引用可回到原始文档位置
- [ ] 邮件/企业协同工具通知接口

### P2 — Production Beta

- [ ] 审批流与 Go / No-Go 决策留痕
- [ ] 管理层组合视图与资源配置
- [ ] 多区域公司协同与权限继承
- [ ] 数据质量 SLA
- [ ] AI 成本、延迟、失败率监控
- [ ] 灾备、限流、WAF、安全扫描
- [ ] 数据保留、删除、导出和合规策略

## 4. 当前目标技术架构

短期坚持**模块化单体 + 独立 Worker**，不为了“生产级”过早微服务化。

```text
Browser
  ↓
Next.js Web
  ↓
FastAPI Application
  ├─ Market / Opportunity / Strategy domain modules
  ├─ Auth adapter + RBAC
  ├─ Audit
  └─ Job dispatcher
       ↓
Redis
  ├─ Celery Broker
  ├─ Job Result Backend
  └─ Organization-scoped Job metadata
       ↓
Celery Workers
  ├─ Public-source discovery
  ├─ Batch scanning
  ├─ AI extraction / re-score
  ├─ Opportunity analysis
  ├─ Strategy generation
  └─ Red-team challenge

PostgreSQL       Object Storage       Search / Vector
(structured)     (source originals)   (retrieval)
```

只有当采集规模、组织规模或独立发布需求真正出现时，再拆 Collector、AI Worker、Search 等独立服务。

## 5. 后台任务约束

- Job 使用 Organization 元数据隔离，其他组织不能查询结果。
- 默认启用 `task_track_started`、late ack、worker-lost reject 和有限重试。
- Worker `prefetch_multiplier=1`，避免单个 Worker 一次预取大量慢任务。
- 长任务设置软/硬超时；超时不得破坏已存在事实数据。
- Job Result 默认只作为短期结果保存；长期经营事实必须进入 PostgreSQL，而不是依赖 Redis。
- 生产环境旧同步长任务接口被阻断，必须通过 `/api/jobs/...` 提交。

## 6. 数据原则

### 事实、推断、建议必须分层

- **Fact**：必须绑定 Source / Evidence。
- **Inference**：必须能解释由哪些 Fact 得出，并记录模型/规则版本。
- **Recommendation**：属于经营建议，不伪装成事实。

### Unknown is valid

系统允许“不知道”。不得为了让字段完整而让 AI 补造客户关系、领导态度、竞争报价、未公开融资状态、中标概率或未核实伙伴关系。

### 生产评分不是中标概率

Score 用于经营资源排序与风险暴露，不表达统计意义上的精确中标概率。

## 7. Production Definition of Done

一个功能只有满足以下条件才视为生产完成：

1. 有真实数据库模型或明确无状态设计；
2. 有权限边界；
3. 有输入校验和失败路径；
4. 有日志/审计；
5. 有自动化测试；
6. 不依赖 Demo 数据才能运行；
7. AI 失败时不会破坏事实数据；
8. 关键结果可以追溯到来源；
9. 数据变更可以知道“谁、何时、为什么”；
10. 有可部署、可回滚、可恢复路径。

## 8. 下一工程阶段

当前优先级调整为：

1. **真实 Source Connectors + Object Storage**
2. **Region / Team 数据隔离 + 企业 SSO/OIDC**
3. **Worker / API Observability + Backup**
4. **Entity / Search / Knowledge Layer**
5. **真实 Action / Reminder / Workflow**
6. **Security hardening + Secrets management**

比赛 Demo 继续从同一产品代码构建，但只是一种运行模式，不再决定主产品架构。
