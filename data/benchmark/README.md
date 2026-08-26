# 智拓业务价值 Benchmark

本目录只存放**可追溯的 Gold 数据、工程回归 fixture 和真实测量结果**。禁止为了申报或路演预填效率提升比例，也禁止把 fixture 回归分数包装成真实业务准确率。

## 1. Gold Pipeline Evaluation

当前真实来源 Gold corpus 由以下版本化文件共同组成：

- `gold_dataset.json`：首批 10 个公开一手来源样本；
- `gold_dataset_extension.json`：追加 3 个公开一手来源样本；
- `regression_negatives.json`：4 个**合成负样本**，仅用于 CI false-positive 回归，不属于真实来源 Gold，不得用于正式准确率。

统一 loader 会自动合并真实 Gold 主集和 extension，避免 extension 存在但评测脚本没有实际使用。

### CI 工程回归

```bash
python scripts/run_gold_pipeline.py --mode fixture --output data/benchmark/ci_evaluation.json
python scripts/check_gold_gate.py --report data/benchmark/ci_evaluation.json
```

`fixture` 会用 Gold 字段构造正样本输入，并加入显式标记的合成负样本。它只回答：**代码修改有没有把既有工程能力明显改坏**。

当前回归 floor 是保守起点，只能上调，不能无说明下调：

- 项目识别准确率：100%；
- 字段准确率：≥60%；
- Gold evidence recall：≥10%；
- structured safety pass：100%；
- 真实来源正样本：≥13；
- 合成负样本：≥4。

这些阈值不是业务 KPI，也不是模型对真实市场信息的正式准确率。

### Structured Safety

Safety 不再通过“在 JSON 字符串中搜索 `win probability` 之类标签”判断。评测器直接检查结构化输出：

- 无证据时不得生成 `competitor` / `partner` party；
- Gold 未授权金额时 `estimated_value_usd_m` 必须保持未知；
- `must_not_infer` 保留为人工复核说明，但机器 gate 依赖结构化约束。

原则：**宁可明确“待核实”，也不能为了字段完整度编造事实。**

### 真实来源评测

真实来源评测流程：

```bash
python scripts/cache_gold_sources.py
python scripts/run_gold_pipeline.py --mode source-text
```

只有全部真实 Gold 样本都具备真实 `source_text` / `source_cache`，且报告显示：

```text
publishable: true
```

成绩才允许进入正式报告或竞赛材料。

如配置了 AI Provider，可运行：

```bash
python scripts/run_gold_pipeline.py --mode source-text --ai
```

以完全相同的真实 Gold corpus 分别跑 deterministic 与 AI，才能形成有意义的模型增益对比。

HTML 官方页面可由缓存工具自动抓取；PDF 来源仍明确标记为人工缓存，不允许用 Gold 摘要冒充原文。

## 2. Gold Dataset Contract

CI/评测前会验证：

- `sample_id` 唯一；
- 真实正样本来源必须为绝对 HTTPS URL；
- 必须有国家、专业、阶段、标题、业主、融资、采购信号等 Gold 字段；
- 必须至少包含一条 `gold_evidence`；
- 必须至少包含一条 `must_not_infer`；
- 合成负样本必须显式 `project_expected=false`，必须提供 `fixture_text`，且不得伪造 `source_url`。

## 3. Business Value Benchmark

通过同一批公开海外工程信息进行“人工流程 vs 智拓流程”成对测试，量化：

1. **耗时**：从看到原始来源到形成可研判机会卡所需时间；
2. **字段准确率**：国家、业主、行业、阶段、金额、融资、采购状态等关键字段与人工金标准的一致程度；
3. **证据可追溯率**：关键判断中能够回到明确来源/原文证据的比例；
4. **经营判断一致率**：智拓 GO/WATCH/NO-GO 与评审人员独立判断的一致程度。该指标不是中标预测准确率。

`benchmark_results.csv` 目前只有表头，意味着**尚没有真实业务效率成绩**。在真实人工对照实验完成前，不得写“节省 X% 时间”之类数字。

### 推荐实验

- 首轮至少 10 个，正式建议 20–30 个真实来源；
- 优先 AfDB、World Bank、政府采购平台、业主官网等公开一手来源；
- 同一测试者做人工作业和智拓作业时要交换样本顺序，或由另一人复核，降低学习效应；
- Gold 由测试结束后的独立复核形成，不能直接把智拓输出当正确答案；
- 计时从打开原始来源开始，到得到“结构化项目卡 + 初步经营判断 + 来源记录”结束。

CSV 字段：

```text
sample_id,source_name,source_url,manual_seconds,zhituo_seconds,fields_correct,fields_total,evidence_traced,evidence_total,decision_match,reviewer,notes
```

汇总：

```bash
python scripts/benchmark_report.py
```

## 4. 正式披露口径

只有真实结果录入后，才能写：

- 平均处理耗时由 X 分钟降至 Y 分钟；
- 效率提升 Z%；
- 字段准确率 A%；
- 证据可追溯率 B%；
- 经营判断一致率 C%。

样本数量、来源范围、测试日期、测试方法、是否使用 AI Provider 必须和结果同时披露。
