# 智拓 Candidate Opportunity Pipeline

## 1. 目标

Candidate Opportunity Pipeline 把“已经可靠归档的外部文档”转换成“等待经营人员审核的候选商机”，但不允许自动把 AI 识别结果直接写入正式机会池。

核心边界：

```text
SourceDocument
  ↓
CandidateProcessing（持久化处理台账）
  ↓
Project Detection
  ├─ 非具体项目 → no_project
  ├─ 已有高相似待审候选 → duplicate
  └─ 具体项目 → OpportunityDraft / Candidate Inbox
                         ↓ 人工审核
                   confirm / reject
                         ↓
                 正式 Opportunity
```

## 2. 为什么增加 CandidateProcessing

不能把“SourceDocument 写入成功”与“Celery 消息发送成功”绑成一次不可恢复操作。

每个新 `source_documents` 版本在同一 PostgreSQL 事务中获得唯一的 `candidate_processing` 记录。因此：

- Redis 临时不可用不会丢项目；
- Worker 重启不会丢项目；
- 失败可以指数退避并人工重试；
- 每个规范文档最多存在一条处理台账；
- 历史 SourceDocument 在 `0011_candidate_processing` 迁移时自动补入待处理队列。

Beat 只扫描 PostgreSQL 的 due rows，再把具体 processing id 投递给 Worker。Redis 是执行通道，不是业务事实来源。

## 3. 数据模型

`candidate_processing` 关键字段：

- `source_document_id`：唯一对应规范文档；
- `status`：pending / processing / retry / candidate_created / duplicate / no_project / failed；
- `draft_id`：生成的候选商机；
- `duplicate_draft_id`：被判定为同一个待审候选时指向已有 Draft；
- `project_detected`、`extraction_mode`；
- `attempts / next_attempt_at`；
- `lease_until + lease_token`；
- `error_detail / processed_at`。

表按 Organization 隔离并启用 PostgreSQL RLS。

## 4. Worker 事务边界

Candidate Worker 不允许把 PostgreSQL 事务跨越 S3/Object Storage 或 AI 外部调用。

执行顺序：

1. 在租户上下文内读取 CandidateProcessing 和 SourceDocument 元数据；
2. 结束数据库读事务；
3. 从 DocumentStore 读取规范文本并验证 SHA-256；
4. 调用规则/AI 做 Project Detection；
5. 重新开启短事务并 `FOR UPDATE` CandidateProcessing；
6. 校验 `lease_token`，过期 Worker 返回 `stale_claim`；
7. PostgreSQL 下取得 organization 级 transaction advisory lock；
8. 完成 pending candidate 去重并写入最终状态。

这样既不长期占数据库事务，也防止旧 Worker 或并发 Worker 覆盖新状态。

## 5. 项目识别原则

Project Detection 延续智拓的证据原则：

- 宏观政策、行业趋势、无具体工程项目的信息不得形成 Candidate；
- 无法确认的国别、业主、金额、阶段保留“待识别/待核实”；
- AI 不可补造关系、融资或项目事实；
- 当前最多读取规范文本前 100,000 字符做发现，上游完整文本仍不可变保存在 DocumentStore，可在后续检索/分块管线中重新处理。

## 6. 去重策略

### 待审 Candidate 对 Candidate

使用较高阈值进行自动去重。只有非常相似的项目画像才把后续文档标记为 `duplicate` 并关联已有 `OpportunityDraft`。

默认：

```text
CANDIDATE_DRAFT_DUPLICATE_THRESHOLD=0.88
```

此动作只抑制候选收件箱中的重复卡片，不删除 SourceDocument，也不丢失 processing history。

### Candidate 对正式 Opportunity

只生成 `duplicate_matches` 提示，不自动合并。原因是同一项目名称可能对应：

- 新标段；
- 新采购包；
- 新阶段；
- 补充融资；
- 二次招标。

是否属于同一正式商机必须由经营人员判断。

## 7. 人工确认与证据链

自动 Candidate 的 `OpportunityDraft.raw_text` 留空，不在 PostgreSQL 再复制一份 100k+ 规范正文。

确认入池时：

1. 通过 CandidateProcessing 找回 `source_document_id`；
2. 从 DocumentStore 读取规范正文；
3. 再次校验 SHA-256；
4. 创建正式 `SourceRecord`；
5. 将 ProjectDiscovery 中有明确证据的事实写为 Evidence；
6. 创建初始 ScoreSnapshot / OpportunityEvent；
7. 将 Draft 标记为 confirmed。

如果 SourceDocument 或对象已经损坏/丢失，系统拒绝确认，避免“无原始证据入池”。

## 8. Candidate Inbox API

只读：

```http
GET /api/candidates?status=pending
GET /api/candidates/{draft_id}
GET /api/candidates/processing
```

Manager 操作：

```http
POST /api/candidates/{draft_id}/reject
POST /api/candidates/processing/{processing_id}/retry
POST /api/discovery/drafts/{draft_id}/confirm
```

正式确认继续复用既有 idempotency / audit 机制。

## 9. 失败与重试

默认：

```text
CANDIDATE_DISPATCH_INTERVAL_SECONDS=30
CANDIDATE_LEASE_SECONDS=300
CANDIDATE_MAX_ATTEMPTS=5
CANDIDATE_MAX_BACKOFF_SECONDS=3600
CANDIDATE_DISPATCH_BATCH_SIZE=50
```

失败进入指数退避；达到最大尝试次数进入 `failed`，由 Manager 明确人工 retry 后才重新开始。

## 10. 当前边界与后续

本阶段只负责“文档 → 项目候选 → 人工正式入池”。暂不在这里做：

- 客户/融资方/竞争对手 Entity Resolution；
- 跨文档多证据自动聚合；
- Search / Knowledge Layer；
- 登录态和浏览器自动化来源；
- 扫描 PDF OCR。

下一阶段优先进入 Entity Resolution 与 Candidate/Opportunity 的多来源证据聚合，而不是继续增加更多抓取器。
