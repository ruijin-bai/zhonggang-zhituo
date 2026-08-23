# 智拓业务价值 Benchmark

本目录只存放**真实测量结果**。禁止为了申报或路演预填效率提升比例。

## 两类评测

### 1. Gold Pipeline Evaluation

验证智拓对公开工程来源的识别质量：

- 国家/专业/阶段等字段准确率；
- Evidence Recall；
- 禁止推断项 Safety Pass Rate。

Gold Dataset 位于 `gold_dataset.json`。

工程回归可运行：

```bash
python scripts/run_gold_pipeline.py --mode fixture
```

`fixture` 会用 Gold 字段构造测试输入，只用于检查 pipeline 是否退化，**结果严禁用于申报**。

真实来源评测流程：

```bash
python scripts/cache_gold_sources.py
python scripts/run_gold_pipeline.py --mode source-text
```

只有所有样本都具备真实 `source_text` 且报告显示 `publishable: true` 时，输出成绩才允许进入申报材料。

如配置了 AI Provider，可运行：

```bash
python scripts/run_gold_pipeline.py --mode source-text --ai
```

以相同数据分别跑 deterministic 与 AI，可以形成模型增益对比。

注意：HTML 官方页面可由缓存工具自动抓取；PDF 来源当前明确标记为人工缓存，不允许用 Gold 摘要冒充原文。

### 2. Business Value Benchmark

通过同一批公开海外工程信息，进行“人工流程 vs 智拓流程”成对测试，量化：

1. **耗时**：从看到原始来源到形成可研判机会卡所需时间。
2. **字段准确率**：国家、业主、行业、阶段、金额、融资、采购状态等关键字段与人工金标准的一致程度。
3. **证据可追溯率**：关键判断中能够回到明确来源/原文证据的比例。
4. **经营判断一致率**：智拓 GO/WATCH/NO-GO 与评审人员独立判断的一致程度。该指标不是中标预测准确率。

## 推荐实验

- 样本量：首轮至少 10 个，最终建议 20–30 个。
- 来源：优先 AfDB、World Bank、政府采购平台、业主官网等公开一手来源。
- 每个样本由同一名测试者先完成人工流程，再用智拓；为减少学习效应，第二轮应交换样本顺序或由另一人复核。
- 人工金标准由测试结束后统一复核，不能直接把智拓输出当正确答案。
- 计时从打开原始来源开始，到得到“结构化项目卡 + 初步经营判断 + 来源记录”结束。

## CSV 字段

`benchmark_results.csv` 使用：

```text
sample_id,source_name,source_url,manual_seconds,zhituo_seconds,fields_correct,fields_total,evidence_traced,evidence_total,decision_match,reviewer,notes
```

`decision_match` 仅填 `true/false`。

生成汇总：

```bash
python scripts/benchmark_report.py
```

## 申报口径

只有真实结果录入后，才能在申报材料中写：

- 平均处理耗时由 X 分钟降至 Y 分钟；
- 效率提升 Z%；
- 字段准确率 A%；
- 证据可追溯率 B%；
- 经营判断一致率 C%。

样本数量、测试日期、测试方法必须与结果同时披露。