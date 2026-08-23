# 05｜技术架构规划

## 1. 架构目标

技术选型以四个标准为优先：

1. 好用；
2. 主流；
3. 专业；
4. 适合个人赛快速交付与演示。

不为“技术炫技”引入不必要复杂度。

---

## 2. 推荐技术栈

### 前端

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- Recharts / ECharts
- Mapbox GL 或 MapLibre

### 后端

首版推荐：

- Next.js API / Server Actions 负责轻量业务接口；
- Python FastAPI 负责 AI、数据处理、评分与任务编排。

这样兼顾：

- 前端开发效率；
- Python AI 生态；
- 后续服务拆分空间。

### 数据库

- PostgreSQL
- Prisma 或 SQLAlchemy
- pgvector（若需要向量检索）

### AI

- 支持 OpenAI-compatible API
- 统一封装 Model Provider
- Structured Output / JSON Schema
- RAG 按需引入

### 部署

竞赛首版优先：

- Web：Vercel / Cloudflare
- API：Railway / Render / Fly.io / 自托管服务器
- DB：Supabase / Neon / PostgreSQL

正式企业部署可切换私有云或内网，不影响首版产品结构。

---

## 3. 逻辑架构

```text
┌───────────────────────────────┐
│        Web Application        │
│ Dashboard / Opportunity / AI  │
└──────────────┬────────────────┘
               │
┌──────────────▼────────────────┐
│      Application API Layer    │
│ Auth / CRUD / Query / Export  │
└───────┬───────────────┬───────┘
        │               │
┌───────▼──────┐  ┌─────▼───────────┐
│ Business Core│  │ AI Orchestrator │
│ Scoring/Rules│  │ Extract/Analyze │
└───────┬──────┘  └─────┬───────────┘
        │               │
┌───────▼───────────────▼───────┐
│ PostgreSQL / pgvector / Cache │
└──────────────┬────────────────┘
               │
┌──────────────▼────────────────┐
│ Data Sources / Ingestion      │
│ Official / News / Manual      │
└───────────────────────────────┘
```

---

## 4. 核心服务边界

### Opportunity Service

负责：

- 项目 CRUD
- 状态流转
- 机会池
- 关注列表

### Evidence Service

负责：

- 来源管理
- 证据片段
- 字段证据绑定
- 来源质量等级

### Scoring Service

负责：

- 评分规则
- 权重配置
- 评分计算
- 快照
- 变化说明基础数据

### AI Service

负责：

- 项目抽取
- 项目分析
- 经营策略
- AI 问答
- 结构化输出校验

### Monitoring Service

负责：

- 新事件进入
- 字段变化识别
- 触发重评
- 变化通知

竞赛首版不必物理拆成微服务，可以在代码层模块化。

---

## 5. 数据库原则

### 必须保存历史

不能只保存项目“当前值”，必须保留：

- 来源历史；
- 事件历史；
- 评分快照；
- 状态变化；
- AI 分析版本。

否则无法展示“为什么从 72 变成 81”。

### 关键字段来源化

例如融资状态不是一个孤立字段，而应知道：

```text
financing_status = approved
source_id = xxx
verified_at = xxx
confidence = 0.95
```

---

## 6. API 设计原则

示例：

```text
GET  /api/opportunities
GET  /api/opportunities/:id
POST /api/opportunities
POST /api/opportunities/:id/analyze
POST /api/opportunities/:id/rescore
POST /api/opportunities/:id/strategy
GET  /api/opportunities/:id/events
GET  /api/opportunities/:id/evidence
GET  /api/countries
```

AI 长任务如后续变慢，再引入队列。

---

## 7. 任务编排

首版处理一条新来源：

```text
1. ingest source
2. extract opportunity facts
3. validate schema
4. match existing opportunity
5. create/update evidence
6. update facts
7. calculate score
8. compare score snapshot
9. generate analysis if meaningful change
10. save event
```

必须保证步骤可观察、失败可定位。

---

## 8. 安全

- `.env` 管理密钥；
- 仓库不得提交真实 API Key；
- 输入数据进行基础清洗；
- 后端调用模型，避免关键密钥前端暴露；
- 正式环境预留身份认证与权限；
- Demo 只使用公开数据或明确脱敏模拟数据。

---

## 9. 可观测性

竞赛开发阶段至少记录：

- AI 调用耗时；
- token / 调用成本；
- 抽取成功率；
- JSON 校验失败；
- 评分计算异常；
- 来源抓取/导入异常。

目的不是做复杂运维平台，而是保证演示稳定和后续优化有依据。

---

## 10. 首版避免的技术债

不建议一开始：

- 微服务拆分；
- Kubernetes；
- 自建向量数据库；
- 多 Agent 自主协作；
- 复杂消息队列；
- Neo4j 作为硬依赖；
- 从零开发通用爬虫框架。

如果后续某能力被真实需求证明必要，再加入。

---

## 11. 推荐代码结构

```text
zhonggang-zhituo/
├── apps/
│   ├── web/               # Next.js
│   └── api/               # FastAPI
├── packages/
│   ├── shared/            # shared types/schema
│   └── scoring/           # scoring definitions if shared
├── docs/
├── data/
│   ├── demo/
│   └── seeds/
├── scripts/
├── .env.example
├── docker-compose.yml
└── README.md
```

是否采用 monorepo 可在真正初始化代码时根据开发体验再最终确认，但文档、数据与业务逻辑边界保持不变。
