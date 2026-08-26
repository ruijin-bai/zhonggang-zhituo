# 智拓真实业务 Pilot

本目录用于 **Stage 5：真实业务验证**。目标不是继续制造 demo 分数，而是把公开一手来源真正送入智拓，并把系统运行证据与人工业务对照分开记录。

## 1. 第一批真实来源

`worldbank_sources.json` 当前包含 5 个重点市场：

- Nigeria
- Ghana
- Senegal
- Mozambique
- Zambia

数据来自 World Bank Group 官方 Procurement Notices API：

`https://search.worldbank.org/api/v2/procnotices`

World Bank Supplier 页面公开使用该 API 展示 current opportunities。该数据源公开、无需项目自建 API key，并持续更新采购公告。

每个 source pack 查询最多返回 25 条 Invitation for Bids / Invitation for Prequalification / Request for Expression of Interest。Pilot runner 默认每个市场只处理前 10 条，避免一次运行无上限扩张。

## 2. 系统真实来源运行

```bash
uv run --project apps/api python scripts/run_real_source_pilot.py --require-all-sources
```

启用已配置 AI Provider：

```bash
uv run --project apps/api python scripts/run_real_source_pilot.py --require-all-sources --ai
```

输出：

`data/pilot/latest_run.json`

该文件包含：

- source pack ID、市场、官方 URL；
- source response SHA-256；
- 每条 notice 的 canonical URL、正文 SHA-256、发布时间和原始 metadata；
- 智拓 project detection、country、sector、stage、owner、confidence；
- 每个结构化事实的 evidence quote；
- extraction mode；
- 每个 source 成功/失败及错误信息。

`latest_run.json` 是运行产物，默认不进 Git 历史。GitHub Actions 的 Real Source Pilot 会把它作为 artifact 保存。

## 3. 它能证明什么

真实来源系统运行可以证明：

1. 官方来源当前可访问；
2. Connector 可以把原始采购数据规范化为 SourceDocument；
3. 智拓能够对真实公告执行项目识别和证据抽取；
4. 每条输出可以回溯到官方 notice URL 和 source hash；
5. 错误和外部访问失败会显式暴露，而不是静默回退到 demo fixture。

它 **不能单独证明**：

- 节省了多少人工时间；
- 字段准确率达到多少；
- 经营判断一致率达到多少；
- 中标概率或市场胜率。

因此 `latest_run.json` 固定标记 `business_claims_publishable=false`。

## 4. 人工 vs 智拓成对测试

正式业务价值数据仍写入：

`data/benchmark/benchmark_results.csv`

每条样本必须由真实 reviewer 完成同一来源的人工流程与智拓流程，然后记录：

- `manual_seconds`
- `zhituo_seconds`
- `fields_correct / fields_total`
- `evidence_traced / evidence_total`
- `decision_match`
- `reviewer`
- `notes`

运行：

```bash
python scripts/benchmark_report.py
```

汇总前会拒绝以下脏数据：

- 缺少或重复 `sample_id`；
- 非 HTTPS 来源；
- 缺 reviewer；
- 0/负耗时；
- 正确字段数大于字段总数；
- 证据命中数大于证据总数；
- 非严格 true/false 的 decision match。

在真实成对记录为空时，报告必须继续显示“尚无真实测试结果”，不得生成效率提升宣传数字。

## 5. Pilot 判定

第一阶段 Pilot 通过条件：

- 5/5 source pack 可完成真实 fetch；
- 每个成功 source 至少产生 1 个 SourceDocument；
- runner 输出 source/content hashes 与 canonical notice URL；
- 系统运行不依赖 demo fallback；
- 普通 CI 继续全绿。

人工业务价值结论是第二层验收，必须等真实 reviewer 数据产生后再计算。
