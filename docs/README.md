# 智拓文档中心

本目录是 **中港智拓 Zhonggang Zhituo** 的产品、业务、数据、AI、技术与竞赛建设基线。

> 核心命题：**去哪里、追什么、怎么拿。**  
> 核心闭环：**市场扫描 → 商机发现 → 项目画像 → 机会研判 → 经营策略 → 持续跟踪**

## 文档地图

| 文档 | 作用 | 当前状态 |
|---|---|---|
| [PRODUCT_PLAN.md](./PRODUCT_PLAN.md) | 产品总纲：愿景、定位、价值、模块、竞赛首版范围 | 已建立 |
| [01_BUSINESS_WORKFLOW.md](./01_BUSINESS_WORKFLOW.md) | 海外市场经营业务流程、角色、决策节点、AI介入点 | v0.1 |
| [02_PRODUCT_REQUIREMENTS.md](./02_PRODUCT_REQUIREMENTS.md) | 产品需求、模块边界、页面、功能优先级、验收条件 | v0.1 |
| [03_SCORING_ENGINE.md](./03_SCORING_ENGINE.md) | 机会评分、Go/No-Go、置信度、规则与解释机制 | v0.1 |
| [04_DATA_AI_DESIGN.md](./04_DATA_AI_DESIGN.md) | 数据源、实体模型、证据链、RAG/Agent/规则协同 | v0.1 |
| [05_TECH_ARCHITECTURE.md](./05_TECH_ARCHITECTURE.md) | 技术架构、服务边界、存储、接口、安全与部署 | v0.1 |
| [06_UI_UX_DESIGN.md](./06_UI_UX_DESIGN.md) | 信息架构、页面布局、关键交互、竞赛演示路径 | v0.1 |
| [07_COMPETITION_STRATEGY.md](./07_COMPETITION_STRATEGY.md) | 个人赛定位、评分映射、演示故事线、验证指标 | v0.1 |
| [08_IMPLEMENTATION_ROADMAP.md](./08_IMPLEMENTATION_ROADMAP.md) | 开发阶段、里程碑、任务拆解、完成定义 | v0.1 |
| [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) | 5–7 分钟英雄项目演示脚本与现场容错 | 可排练 |
| [ACCEPTANCE_CHECKLIST.md](./ACCEPTANCE_CHECKLIST.md) | 赛前产品、AI、安全、工程和材料验收清单 | 执行中 |
| [COMPETITION_SUBMISSION.md](./COMPETITION_SUBMISSION.md) | 个人赛申报书底稿：痛点、方案、创新、价值、合规、推广 | 初稿 |

## 文档使用规则

1. `PRODUCT_PLAN.md` 是产品方向总纲，出现方向冲突时优先以总纲和最新决策为准。
2. 功能开发前，先在 `02_PRODUCT_REQUIREMENTS.md` 中确认功能边界与验收条件。
3. 涉及机会分数、评级、Go/No-Go 的逻辑，只在 `03_SCORING_ENGINE.md` 维护唯一口径。
4. 涉及实体字段、信息来源、引用、AI输入输出约束，在 `04_DATA_AI_DESIGN.md` 维护。
5. 技术选型允许迭代，但必须服务于“易用、主流、专业、可演示、可部署”，不为技术炫技增加复杂度。
6. 竞赛版优先形成完整经营闭环，不追求一次性覆盖企业全部市场管理场景。
7. 准备录屏或提交前，必须逐项执行 `ACCEPTANCE_CHECKLIST.md`，不得用“现场应该能跑”代替验收。
8. 申报材料中的效率、准确率、业务提升数字必须来自实际验证；未测试的数据不写百分比。

## 当前产品边界

### 必须做

- 市场机会发现
- 机会池与项目画像
- 机会评分与可解释研判
- Go/No-Go 辅助判断
- 经营策略建议
- 证据来源追溯
- 关键变化持续跟踪
- 可验证的效率与质量提升

### 暂不做

- CRM 全量替代
- OA/审批全流程
- 正式投标文件自动生成
- 自动替代经营负责人作最终决策
- 复杂项目成本测算与报价
- 企业级权限体系的全部细节
- 大规模爬虫平台和通用搜索引擎

## 当前真实公开验证样例

`data/public_samples/afdb_abia_roads_2026.json` 保存了一个仅由非洲开发银行公开资料构成的尼日利亚道路项目样例，用于验证项目发现、融资/采购信号抽取和 Evidence 流程。

真实公开样例只证明系统能够处理外部公开信息，不代表公司已决定跟踪、投标或具有特定中标可能性。

## 竞赛首版成功标准

首版不是“功能很多”，而是评委能在短时间内明确看到：

> 一条原本需要市场人员跨网站搜集、人工整理、凭经验判断的海外项目机会，能够由智拓完成 **发现、结构化、评分、解释、策略生成、持续跟踪**，并且所有关键判断都有来源、有规则、有人工最终确认。
