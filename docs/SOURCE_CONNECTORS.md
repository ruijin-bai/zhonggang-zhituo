# 智拓 Source Connector 设计

## 1. 目标

Source Connector 是智拓从“用户手工提供一段文本/URL”升级为“系统持续感知外部市场”的统一入口。

连接器只负责：

1. 安全获取公开来源；
2. 将不同载体解析为统一 `SourceDocument`；
3. 保留来源身份、发布时间、哈希和连接器元数据；
4. 明确失败，不在连接器层虚构业务事实。

项目识别、实体解析、评分、AI 研判和正式入池属于后续管线，不塞进 Connector。

## 2. 统一输出契约

每个连接器输出 `ConnectorResult`，内部包含一个或多个 `SourceDocument`。

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

`content_sha256` 用于文本级去重，`raw_sha256` 为后续 Object Storage 内容寻址和原件一致性校验提供基础。

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

## 5. 为什么现在不直接把 Connector 写入 Opportunity

外部来源不等于商机。

正确链路是：

```text
Connector
  ↓
SourceDocument
  ↓
Object Storage + Source Index
  ↓
Hash / Canonical URL 去重
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

## 6. 下一阶段：Object Storage

下一大步引入 `DocumentStore` 抽象，并提供：

- 本地开发存储；
- S3-compatible 生产实现；
- 以 `raw_sha256` 为主键/对象键的内容寻址；
- 原始 HTML / PDF / XML / JSON 保存；
- MIME、大小、抓取时间、ETag/Last-Modified 等元数据；
- 相同内容不重复写入；
- SourceDocument 只引用 object key，不把大块原件塞入 PostgreSQL。

之后再建设 Scheduled Source Scan 和 Candidate Pipeline。

## 7. 设计原则

> Connector 只负责把“外部世界的文档”可靠地带进系统；AI 负责理解，人负责最终经营判断，数据库负责保存事实和历史。
