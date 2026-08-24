# 智拓 Entity Resolution / Evidence Aggregation 契约

## 1. 目标

本阶段解决两个生产问题：

1. 同一项目由多份公告、融资文件、业主通知或新闻来源重复出现时，来源不能被简单丢弃为 duplicate，而应汇聚成一个可审计的证据集合；
2. 业主、融资方、竞争对手、合作伙伴不能长期停留在自由文本，需要形成稳定实体身份和跨项目历史关系。

本阶段不做全文搜索、知识图谱推理、OCR、浏览器自动化，也不允许机器自动合并已经正式入池的 Opportunity。

## 2. 数据层

### SourceDocumentInsight

每份归档后的 `SourceDocument` 保存自己的结构化 `ProjectDiscovery`：

- 项目识别结果；
- 项目标题、国家、专业、阶段、业主；
- 评分事实；
- owner / financier / competitor / partner 主体；
- extraction mode；
- 项目身份 fingerprint。

完整正文仍保存在 Object Storage；数据库只保存结构化结果和不可变对象索引。

### CandidateSourceDocument

自动识别出的第一份项目来源创建 Candidate；后续高置信重复来源不会创建第二个 Candidate，而是挂到同一个 Candidate 下。

因此一个 Candidate 可以拥有 1..N 个 `SourceDocument`。

### Entity / Alias / Mention

实体解析采用保守自动策略：

- 实体类型当前为 organization；
- 自动合并只接受规范化名称精确一致；
- 国家为实体身份边界的一部分；
- 同名跨国机构不自动合并；
- 模糊相似名称不自动合并；
- manager 可以增加人工 alias；
- 同一国家内 alias 若会产生身份歧义，直接拒绝。

`SourceEntityMention` 保留原始来源中的主体、角色、证据片段和置信度，不因后续人工复核而删除。

### OpportunityEntityLink

正式 Opportunity 形成实体关系层：

- owner；
- financier；
- competitor；
- partner；
- source_count；
- confidence；
- first_seen / last_seen。

正式 Opportunity 的 `owner` 字段是人工复核后的权威值。如果人工确认时修改业主，正式 owner 实体关系以人工值为准；原来源中机器识别出的旧 owner mention 仍保留作审计证据。

### OpportunitySourceDocument

正式 Opportunity 与不可变 `SourceDocument` 建立独立关系：

- 首次 Candidate 确认时自动写入；
- 后续 Candidate 只能由 manager 明确执行 attach；
- 一份规范 `SourceDocument` 当前只能归属一个正式 Opportunity；
- 该限制用于避免当前“单文档单项目识别模型”下的跨项目误挂。

未来如果支持一份文件内多项目抽取，应通过新的显式多项目模型迁移，而不是放宽当前约束。

## 3. Candidate 行为

### 新来源属于待审 Candidate

如果与一个 pending Candidate 达到安全去重阈值：

1. 保存该文档自己的 `SourceDocumentInsight`；
2. 解析并保存实体 mention；
3. 将 SourceDocument 挂到原 Candidate；
4. processing 状态保留 duplicate 历史语义；
5. Candidate Inbox 的 `source_count` 增加。

### 新来源疑似属于已正式入池 Opportunity

系统只提供 duplicate match 提示，不自动并入正式项目。

manager 复核后执行：

`POST /api/candidates/{draft_id}/attach/{opportunity_id}`

生产环境该写操作要求 `Idempotency-Key`。

成功后：

- Candidate 状态变为 `linked`；
- Candidate 的全部 SourceDocument 分别创建正式 Source；
- 各来源事实分别创建 Evidence；
- 建立 OpportunitySourceDocument；
- 重新汇总 OpportunityEntityLink；
- 写入 `candidate_attached_as_evidence` Opportunity Event；
- 不因普通 B 级公开来源数量增加而自动突破经营判断的证据门槛。

## 4. 正式入池

Candidate 首次人工 confirm 时：

1. 读取全部 CandidateSourceDocument；
2. 从 Object Storage 回取每份规范正文；
3. 每份正文重新校验 SHA-256；
4. 每份来源独立创建 Source / Evidence；
5. 创建 OpportunitySourceDocument；
6. 汇总实体关系；
7. 人工复核字段保持权威；
8. 多份普通公开来源仍保持 `INSUFFICIENT_EVIDENCE`，直到更高等级证据补齐。

## 5. API

实体查询：

- `GET /api/entities`
- `GET /api/entities/{entity_id}`
- `POST /api/entities/{entity_id}/aliases`

Candidate：

- `GET /api/candidates?status=pending|confirmed|rejected|linked|all`
- `GET /api/candidates/{draft_id}`
- `POST /api/candidates/{draft_id}/attach/{opportunity_id}`

## 6. 数据库迁移

- `0012_entity_evidence`：Insight、Candidate 多来源、Entity/Alias/Mention、Opportunity Entity Link；
- `0013_opportunity_source_documents`：正式 Opportunity 与不可变 SourceDocument provenance。

所有新增业务表均启用 Organization 级 PostgreSQL RLS；runtime role 必须 `NOBYPASSRLS`。

迁移后重新执行：

```bash
psql ... -f ops/postgres/provision_runtime_role.sql
```

## 7. 安全边界

以下行为明确禁止自动执行：

- 模糊名称直接合并实体；
- 同名跨国实体自动合并；
- 新 Candidate 自动并入已正式 Opportunity；
- 一份规范 SourceDocument 同时挂多个正式 Opportunity；
- 因来源数量增加而虚增证据等级；
- 人工修正业主后删除原始来源 mention。

## 8. 验收重点

CI 至少覆盖：

1. 两份独立来源汇聚一个 Candidate；
2. Candidate confirm 生成多条 Source；
3. 后续 Candidate 由 manager attach 到已有 Opportunity；
4. OpportunitySourceDocument 数量与正式来源一致；
5. owner / financier source_count 随来源增加；
6. 人工修改 owner 后正式实体关系以人工值为准；
7. 原机器 owner mention 仍保留；
8. 同名跨国实体不合并；
9. alias 冲突拒绝；
10. 新增 intelligence/provenance 表 PostgreSQL RLS 开启；
11. 一份 SourceDocument 不能跨两个正式 Opportunity。
