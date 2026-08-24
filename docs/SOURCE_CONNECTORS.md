# 智拓 Source Connector 与文档归档设计

## 1. 目标

Source Connector 是智拓从“用户手工提供一段文本/URL”升级为“系统持续感知外部市场”的统一入口。

连接器只负责：

1. 安全获取公开来源；
2. 将不同载体解析为统一 `SourceDocument`；
3. 保留来源身份、发布时间、哈希和连接器元数据；
4. 明确失败，不在连接器层虚构业务事实。

项目识别、实体解析、评分、AI 研判和正式入池属于后续管线，不塞进 Connector。

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
- 使用流式读取，在下载过程中执行字节上限，而不是响应下载完成后才截断。

正式生产还应在容器/网络层增加 Egress Firewall 或域名白名单，应用层校验不能替代网络层隔离。

## 5. 当前归档链路

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

## 7. 数据隔离与审计边界

- `source_fetches` 和 `source_documents` 均绑定 Organization；
- PostgreSQL 启用 RLS；
- Runtime Role 只在租户上下文内读写；
- 对象本身按内容哈希全局复用，不把 Organization 写进对象键，因为公开原件相同字节无需物理复制；
- PostgreSQL 中的索引、发现次数、抓取关系和后续业务引用仍严格按 Organization 隔离；
- 原始大文件不写入 PostgreSQL。

这实现了“物理对象可去重、业务事实不串租户”。

## 8. 为什么不直接把 Connector 写入 Opportunity

外部来源不等于商机。

正确链路是：

```text
Connector
  ↓
DocumentStore + Source Index
  ↓
版本 / Hash / Canonical URL 去重
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

## 9. 下一阶段

下一阶段不再继续扩连接器数量，而优先建设：

1. `SourceSubscription` / Scheduled Source Scan；
2. ETag / Last-Modified 条件抓取；
3. Source Health、失败次数、退避与人工停用；
4. 新文档版本检测；
5. Candidate Opportunity Pipeline。

扫描 PDF 的 OCR、登录态数据源和浏览器自动化继续后置，避免在核心数据闭环形成前引入高成本复杂度。

## 10. 设计原则

> Connector 负责把“外部世界的文档”可靠带进系统；Object Storage 保存不可变原件；PostgreSQL 保存版本关系和业务事实；AI 负责理解，人负责最终经营判断。
