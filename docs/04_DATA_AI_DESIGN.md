# 04｜数据与 AI 设计

## 1. 设计目标

智拓的数据与 AI 层必须服务于三件事：

1. 把分散信息变成结构化经营事实；
2. 把事实转化为可解释的机会判断；
3. 把判断转化为可执行的经营行动。

---

## 2. 核心实体

首版建议实体：

- `Country` 国别
- `Opportunity` 市场机会/项目
- `Organization` 业主、融资方、咨询方、竞争对手、合作伙伴
- `Person` 关键人物（竞赛版可弱化）
- `Source` 信息来源
- `Evidence` 证据片段
- `Event` 项目变化事件
- `ScoreSnapshot` 评分快照
- `Strategy` 经营策略
- `WatchItem` 关注任务/触发条件

---

## 3. Opportunity 最小字段

```text
id
name_cn
name_en
country
city
sector
subsector
project_type
owner
estimated_value
currency
financing_status
financiers
project_stage
procurement_mode
expected_timeline
summary
source_count
last_verified_at
confidence
score
rating
status
```

除上述字段外，应保留：

- 字段来源；
- 字段更新时间；
- 字段置信度；
- 人工修正状态。

---

## 4. 证据链模型

智拓不允许只有“结论”，没有“依据”。

建议链路：

```text
Source
→ Evidence
→ Fact / Entity Field
→ Score Item
→ Score Dimension
→ Overall Judgment
→ Strategy Recommendation
```

示例：

```text
AfDB 官方公告
→ “Board approved USD 200m...”
→ financing_status = approved
→ financing.score = 15
→ 总分 +7
→ WATCH → GO
→ 建议提升经营优先级
```

---

## 5. 数据来源分层

### 5.1 S/A 级优先来源

- 世界银行
- 非洲开发银行等多边金融机构
- 政府官网
- 采购/招标门户
- 业主官网
- 公司公告
- 官方预算与规划

### 5.2 B 级补充来源

- 主流财经媒体
- 主流行业媒体
- 专业数据库

### 5.3 C/D 级线索来源

- 一般媒体
- 社交网络
- 二次转载

低等级来源可以帮助发现线索，但重大判断必须尽量由高等级来源验证。

---

## 6. AI 工作流

推荐采用“任务编排 + 结构化输出”，而不是一个万能 Agent 自由发挥。

### 6.1 Opportunity Discovery

输入：网页/新闻/公告文本。

AI：

- 判断是否存在基础设施项目机会；
- 抽取项目名称、国家、行业、业主、金额、阶段、融资等；
- 判断与现有项目是否可能重复；
- 给出抽取置信度。

输出严格 JSON Schema。

### 6.2 Evidence Extraction

对来源文本抽取与某字段直接相关的证据片段，并绑定来源。

### 6.3 Opportunity Analysis

输入：

- 已验证结构化事实；
- 评分结果；
- 缺失字段；
- 相关证据。

AI 输出：

- 一句话判断；
- 正向因素；
- 负向因素；
- 关键不确定性；
- 需要补充的信息。

### 6.4 Pursuit Strategy

只针对重点机会生成：

- pursuit thesis；
- stakeholder analysis；
- competitive angle；
- capability gaps；
- next actions；
- monitoring triggers。

---

## 7. 规则、RAG 与 Agent 的分工

### 规则引擎负责

- 机会评分；
- 权重；
- 等级；
- 硬约束；
- 评分重算。

### RAG 负责

- 企业能力库；
- 历史项目经验；
- 业务规则文档；
- 已归档市场报告；
- 来源证据检索。

### LLM 负责

- 信息抽取；
- 去重辅助；
- 解释；
- 综合研判；
- 策略生成；
- 自然语言问答。

### Workflow / Agent 负责

- 串联多个步骤；
- 触发工具；
- 判断下一步需要查询什么；
- 在信息不足时停止强行结论。

---

## 8. AI 输出原则

所有 AI 输出建议至少包含：

```json
{
  "conclusion": "...",
  "facts": [],
  "inferences": [],
  "risks": [],
  "missing_information": [],
  "citations": [],
  "confidence": 0.0
}
```

UI 不一定原样显示 JSON，但后端应保持结构化。

---

## 9. 幻觉控制

核心措施：

1. 事实字段必须绑定证据；
2. 无来源的事实不得进入“已验证事实”；
3. AI 推断单独标识；
4. 金额、日期、融资状态等关键字段优先规则校验；
5. 发现来源冲突时不强行合并；
6. 允许输出“未知/证据不足”；
7. 关键策略建议显示依赖哪些事实。

---

## 10. Demo 数据策略

竞赛版建议混合使用：

### 真实公开数据

用于：

- 项目名称
- 项目基本事实
- 融资事件
- 公开业主信息
- 公开新闻与公告

### 脱敏模拟企业数据

用于：

- 企业类似业绩
- 区域资源基础
- 客户关系强度
- 内部经营状态

界面中应明确区分“公开来源”与“演示企业数据”。

---

## 11. 后续可扩展能力

- 企业知识图谱
- 客户关系网络
- 竞争对手历史行为建模
- 项目赢标/失标复盘学习
- 内部邮件与 CRM 情报融合
- 多语言市场情报采集
- 时序机会预测

这些不应阻塞竞赛首版。
