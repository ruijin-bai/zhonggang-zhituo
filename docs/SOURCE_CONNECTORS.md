# 智拓 Source Connector、文档归档与持续监测设计

## 1. 目标

Source Connector 是智拓从“用户手工提供一段文本/URL”升级为“系统持续感知外部市场”的统一入口。

连接器只负责：

1. 安全获取公开来源；
2. 将不同载体解析为统一 `SourceDocument`；
3. 保留来源身份、发布时间、哈希和连接器元数据；
4. 明确失败，不在连接器层虚构业务事实。

持续监测层负责决定**什么时候再次抓、是否真的发生变化、这个来源现在是否健康**。项目识别、实体解析、评分、AI 研判和正式入池属于后续 Candidate Pipeline，不塞进 Connector 或 Scheduler。

## 2. 统一输出契约

每个连接器输出 `ConnectorResult`，内部包含一个或多个 `SourceDocument`，并在本次处理生命周期内携带待归档的原始字节。

`SourceDocument` 当前字段：

- `connector`：html / rss / pdf；
- `canonical_url`：规范来源或条目 URL；
- `title`；
- `text`：规范化文本；
- `content_type`；
- `content_sha256`：规范文本 SHA-256；
- `raw_sha256`：本次原始资源 SHA-256；
- `raw_size_bytes`；
- `publisher`；
- `published_at`；
- `metadata`：连接器特有但不参与核心业务模型的元数据。

`content_sha256` 用于规范文本级去重，`raw_sha256` 用于原件内容寻址和一致性校验。

周期抓取使用 `ConnectorFetchOutcome` 包装抓取结果，并额外携带：

- `not_modified`；
- `etag`；
- `last_modified`；
- 当响应为 304 时 `result=None`，不进入归档链。

## 3. 当前连接器

### HTML

- 支持 HTML、XHTML、纯文本；
- 去除 script/style/noscript/svg；
- 保留页面标题与正文文本；
- 单资源默认 2MB 上限；
- 输出单个 `SourceDocument`。

### RSS / Atom

- 支持 RSS、Atom 和通用 XML Feed；
- 单 Feed 默认 5MB 上限；
- 单次最多处理 100 条 entry/item；
- 每个条目输出独立 `SourceDocument`；
- 保留 Feed URL、Feed 标题、条目序号和发布时间。

### PDF

- 单 PDF 默认 25MB 上限；
- 最多 300 页；
- 文本最多保留 500,000 字符；
- 使用 PDF 文本层抽取；
- 加密 PDF、损坏 PDF、纯扫描 PDF 显式失败；
- 扫描件后续进入独立 OCR Worker，不在同步连接器中做高成本 OCR。

## 4. 外部访问安全边界

当前沿用并加强已有公开 URL 安全策略：

- 仅允许 HTTP / HTTPS；
- 禁止 URL 中携带用户名密码；
- 仅允许标准 80 / 443 端口；
- DNS 解析结果不得落到 loopback、private、link-local、multicast、reserved 等地址；
- 每次重定向重新校验目标 URL；
- 最多 3 次重定向；
- 使用流式读取，在下载过程中执行字节上限，而不是响应下载完成后才截断；
- 周期扫描的 `ETag / Last-Modified` 只作为 HTTP cache validator，不作为业务事实。

正式生产还应在容器/网络层增加 Egress Firewall 或域名白名单，应用层校验不能替代网络层隔离。

## 5. 归档链路

```text
HTML / RSS / PDF
       ↓
Source Connector
       ↓
ConnectorResult + SourceDocument
       ↓
DocumentStore
  ├─ raw/sha256/...   原始 HTML / XML / PDF
  └─ text/sha256/...  规范化纯文本
       ↓
PostgreSQL Source Index
  ├─ source_fetches
  └─ source_documents
```

### `source_fetches`

表示一个来源 URL 的一个**不同原始版本**。唯一键为：

`organization + connector + source_url_hash + raw_sha256`

同一个原始版本再次抓到时不新建记录，而是增加 `seen_count` 并刷新 `last_fetched_at`。因此既不会制造重复版本，也能知道该版本被连续观察了多少次。

### `source_documents`

表示从某次抓取中解析出的一个**规范文档版本**。唯一键为：

`organization + canonical_url_hash + content_sha256`

同一 URL、同一规范内容再次出现时更新 `seen_count / last_seen_at / latest_fetch_id`；同一 URL 内容变化时生成新版本，旧版本继续保留。

RSS/Atom 的一个原始 Feed 可以对应多条 `source_documents`，同时只保存一份原始 Feed 对象。

## 6. DocumentStore

### Local

仅用于开发/测试：

```text
DOCUMENT_STORE_BACKEND=local
DOCUMENT_STORE_LOCAL_PATH=./data/objects
```

对象键按 SHA-256 分层：

```text
raw/sha256/ab/cd/<sha256>
text/sha256/ab/cd/<sha256>
```

重复写同一内容不会生成第二份文件；若本地已有对象与键对应哈希不一致，系统直接报损坏错误。

### S3-compatible

生产环境强制使用 S3-compatible Object Storage：

```text
DOCUMENT_STORE_BACKEND=s3
DOCUMENT_STORE_S3_BUCKET=zhituo-production-documents
DOCUMENT_STORE_S3_REGION=<region>
```

支持 AWS S3 或兼容服务；自定义生产 endpoint 必须使用 HTTPS。凭证不通过智拓自定义配置传递，而使用 boto3/AWS SDK 标准 credential chain，例如工作负载身份、实例角色或 Secret 注入环境变量。

可配置：

- Path Style；
- `AES256` SSE；
- `aws:kms` + KMS Key ID。

写入对象时保存 `sha256` Object Metadata；已存在对象再次复用前，同时验证 Content-Length 与 SHA-256 Metadata，防止损坏对象被静默接受。

## 7. Source Subscription 与增量扫描

持续监测链路：

```text
Celery Beat
   ↓ 每分钟只做调度
到期 SourceSubscription
   ↓ claim + lease_until + lease_token
独立 Worker Task
   ↓
Conditional Connector Fetch
   ├─ 304 Not Modified → 只更新健康状态
   └─ 200 Modified     → Archive + Version Index
   ↓
SourceScanRun
```

### `source_subscriptions`

每个 Organization 独立保存：

- 来源名称、Connector、URL；
- `interval_seconds / next_scan_at`；
- `etag / last_modified`；
- active / paused 状态与 pause reason；
- `consecutive_failures / total_scans / total_changes`；
- 最近扫描、成功、变化、错误；
- `lease_until / lease_token`。

同一 Organization 下 `connector + url` 唯一，防止重复订阅同一个源。

### `source_scan_runs`

每次真实 Worker 扫描保存一条长期历史：

- changed / unchanged / not_modified / failed；
- 是否手工扫描；
- 是否 304；
- 对应 fetch_id；
- 文档观察数和新增文档数；
- 错误详情；
- 开始/结束时间。

Celery Result 只是短期运行状态，`source_scan_runs` 才是来源运营历史事实。

## 8. 条件请求与变化判定

如果上一次响应返回 `ETag` 或 `Last-Modified`，后续扫描自动发送：

```http
If-None-Match: <etag>
If-Modified-Since: <last-modified>
```

服务端返回 304 时：

- 不下载正文；
- 不写 Object Storage；
- 不生成 `source_fetches / source_documents` 新版本；
- 只把订阅标记为本次成功、not_modified，并安排下一次扫描。

服务端返回 200 时仍以 `raw_sha256` 作为最终变化事实。即使 ETag 改变，只要原始字节哈希未变，系统仍不会制造新版本。

## 9. 租约、并发与故障恢复

仅有 `lease_until` 不足以防止 stale worker。典型风险是：旧任务在队列中延迟超过租约，调度器重新派发新任务，旧任务随后启动并覆盖新任务状态。

因此智拓采用 fencing token：

1. 每次 claim 生成新的随机 `lease_token`；
2. Worker 携带 token；
3. 网络 I/O 前先快速检查 token；
4. 网络 I/O 后重新锁定订阅行，再校验当前 token；
5. token 不匹配则返回 `stale_claim`，不得归档、不得清新租约、不得写失败状态；
6. dispatch failure 也只能释放自己持有的 token。

数据库行锁只在**认领和最终状态提交**时持有，不在外部网络请求期间长期持锁。

`SOURCE_SCAN_LEASE_SECONDS` 必须大于 Celery hard task timeout，使正常执行中的 Worker 不会在硬超时前被重新认领。

## 10. Source Health、退避与自动暂停

失败不会每分钟无限重试。

第 N 次连续失败的下一次延迟按 `interval × 2^(N-1)` 计算，并受到 `SOURCE_SCAN_MAX_BACKOFF_SECONDS` 上限保护。达到 `SOURCE_SCAN_AUTO_PAUSE_FAILURES` 后：

- `status=paused`；
- `pause_reason=automatic_failure_threshold`；
- 保留最近错误；
- 需要 manager 人工检查并 resume。

恢复时清零连续失败计数并立即进入可扫描状态。

## 11. 数据隔离与审计边界

- `source_fetches`、`source_documents`、`source_subscriptions`、`source_scan_runs` 均绑定 Organization；
- PostgreSQL 对四张表启用 RLS；
- Runtime Role 只在租户上下文内读写；
- 对象本身按内容哈希全局复用，不把 Organization 写进对象键，因为公开原件相同字节无需物理复制；
- PostgreSQL 中的索引、发现次数、订阅健康、扫描关系和后续业务引用仍严格按 Organization 隔离；
- 原始大文件不写入 PostgreSQL；
- 创建、修改、暂停、恢复和手工扫描进入 Audit Log。

这实现了“物理对象可去重、业务事实不串租户”。

## 12. 为什么不直接把 Connector 写入 Opportunity

外部来源不等于商机。

正确链路是：

```text
Connector / Subscription
  ↓
DocumentStore + Source Index
  ↓
新文档版本事件
  ↓
Project Detection
  ↓
Candidate Opportunity
  ↓
人工确认
  ↓
正式 Opportunity + Evidence
```

这样可以避免：

- 同一公告反复生成项目；
- 宏观政策被误报为具体商机；
- PDF/RSS 原件丢失后无法审计；
- AI 抽取结果与原始证据无法重新计算；
- Connector 与业务模型强耦合，导致后续新增数据源困难。

## 13. 下一阶段

持续来源监测完成后，下一阶段不再继续扩连接器数量，而进入 Candidate Opportunity Pipeline：

1. 新 `SourceDocument` 版本触发候选处理；
2. Project Detection 判断是否属于具体工程机会；
3. Canonical Project / URL / Entity 级去重；
4. 形成 Candidate Opportunity，而不是直接进入正式机会池；
5. 经营人员人工确认后生成正式 Opportunity + Evidence。

扫描 PDF 的 OCR、登录态数据源和浏览器自动化继续后置，避免在核心数据闭环形成前引入高成本复杂度。

## 14. 设计原则

> Connector 负责把“外部世界的文档”可靠带进系统；Scheduler 负责持续、克制且可恢复地观察来源；Object Storage 保存不可变原件；PostgreSQL 保存版本、健康和业务事实；AI 负责理解，人负责最终经营判断。
