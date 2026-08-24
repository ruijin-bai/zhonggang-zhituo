# 智拓 Search / Knowledge Layer

## 1. 目标

本阶段把已经沉淀的 Opportunity、Candidate、Entity、Evidence、Source 变成可直接检索和关联浏览的经营知识资产。

当前优先解决“能找到、为什么找到、证据从哪里来、与哪些项目有关”，而不是提前建设向量数据库或聊天式 RAG。

## 2. 设计原则

### 2.1 搜索不是经营评分

`relevance_score` 只表示确定性文本检索相关度，范围 0-100。它不表示：

- 中标概率；
- 项目质量；
- GO/NO-GO 建议；
- AI 置信度。

经营评分仍使用 Opportunity 的正式评分体系。

### 2.2 可解释

每个搜索结果返回 `matched_fields`，例如：

- title；
- owner；
- canonical_name；
- alias；
- fact；
- publisher。

因此前端可以明确展示“为什么搜到这条结果”。

### 2.3 多语言基础能力

当前检索使用 Unicode casefold + 子串/词项匹配，因此英文、中文机构别名和项目字段均可检索。

这不是语言模型语义搜索；例如同义词但完全不同字面的查询不会被擅自扩展。

### 2.4 不复制 Object Storage 正文

当前 Source 的完整 `raw_text` 不进入统一搜索匹配与返回结果，避免：

- 再复制 100k+ 正文；
- 大表无索引扫描；
- 搜索接口意外返回大段原文；
- 与 Object Storage 不可变原件形成两套事实来源。

检索内容重点为结构化项目字段、Entity/Alias、正式 Evidence、来源元数据和 Candidate Discovery。

未来若确有全文语义检索需求，应单独建设 chunk/index pipeline，并保留 SourceDocument SHA-256 provenance。

## 3. 统一搜索 API

```http
GET /api/search?q=port+expansion
```

支持参数：

- `types=opportunity,candidate,entity,evidence,source`
- `country=Nigeria`
- `sector=港口工程`
- `entity_role=owner|financier|competitor|partner`
- `source_rank=S|A|B|C|D`
- `limit=1..100`

查询最短 2 个字符，最长 200 个字符。

### 结果字段

- `resource_type`
- `resource_id`
- `title`
- `subtitle`
- `snippet`
- `relevance_score`
- `matched_fields`
- `opportunity_id`
- `metadata`

结果按确定性相关度排序；同分时优先 Opportunity、Entity、Candidate、Evidence、Source。

## 4. Opportunity Knowledge View

```http
GET /api/knowledge/opportunities/{opportunity_id}
```

返回一个正式 Opportunity 的 360° 知识视图：

### Opportunity

项目基本字段、评分、置信度、经营结论和下一步行动。

### Entities

正式关系中的：

- owner；
- financier；
- competitor；
- partner；
- aliases；
- source_count；
- confidence。

### Sources / Provenance

每个正式 Source 返回对应 `source_document_id`（如存在），从而可以追溯到不可变 SourceDocument/Object Storage 原件。

Knowledge View 不返回 Source.raw_text。

### Evidence

返回正式 Evidence：

- field_name；
- fact；
- rank；
- confidence；
- publisher；
- source_url。

### Events

返回最近 Opportunity Event，用于理解来源添加、评分变化和 Candidate attach 等历史。

### Related Opportunities

不使用模糊标题猜测项目关系。

只有两个正式 Opportunity 共享同一个已解析 Entity 时，才形成 related opportunity；同时返回共享 Entity 和它在相关项目中的角色。

这使“这个业主/融资方还在哪些项目出现过”可以从正式关系层得到可解释答案。

## 5. 多租户与权限

Search 和 Knowledge API 均要求至少 `viewer`。

搜索直接查询现有 tenant-scoped 业务表：

- ORM tenant criteria；
- PostgreSQL RLS；
- runtime role `NOBYPASSRLS`。

没有建立一份脱离 RLS 的全局搜索索引，因此搜索层不会成为绕过 Organization 隔离的旁路。

## 6. 性能边界

当前实现适合智拓现阶段结构化情报规模：

- query 最短 2 字符；
- 单类预选结果有硬上限；
- 最终返回最多 100 条；
- 不扫描/返回 Source.raw_text；
- 不进行在线 embedding 调用。

当数据规模达到需要专用索引的量级后，再引入独立 Search Index/Chunk Pipeline，并要求：

1. 增量同步可恢复；
2. index document 带 organization_id；
3. index 查询强制 tenant filter；
4. 每个 chunk 可反查 SourceDocument + SHA-256；
5. 索引失败不能影响 PostgreSQL 事实库写入。

## 7. 当前明确不做

- Vector DB；
- embedding semantic search；
- 自动问答/RAG；
- 无证据的实体关系推理；
- Object Storage 全文无边界回传；
- 跨 Organization 搜索。
