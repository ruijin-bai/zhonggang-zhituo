#!/usr/bin/env python3
import argparse,json,os,sys
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"apps"/"api"))
from app.evaluation_runner import evaluate_pipeline_sync  # noqa: E402

def main()->None:
 parser=argparse.ArgumentParser(description="Run Zhituo pipeline against Gold Dataset");parser.add_argument("--mode",choices=["fixture","source-text"],default="source-text");parser.add_argument("--ai",action="store_true");parser.add_argument("--output",default="data/benchmark/latest_evaluation.json");args=parser.parse_args()
 samples=json.loads((ROOT/"data"/"benchmark"/"gold_dataset.json").read_text(encoding="utf-8"));cache=ROOT/"data"/"benchmark"/"source_cache"
 report=evaluate_pipeline_sync(samples,use_ai=args.ai,input_mode=args.mode,source_cache_dir=cache)
 out=ROOT/args.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(asdict(report),ensure_ascii=False,indent=2),encoding="utf-8")
 s=report.summary;print("中港智拓 Gold Pipeline Evaluation");print(f"输入模式: {report.mode}");print(f"可用于正式成绩: {'YES' if report.publishable else 'NO'}");print(f"总样本: {report.samples_total} | 已评测: {report.samples_evaluated} | 跳过: {report.samples_skipped}");print(f"运行模式分布: {report.extraction_modes}");print(f"字段准确率: {s['field_accuracy_pct']}%");print(f"证据召回率: {s['evidence_recall_pct']}%");print(f"安全通过率: {s['safety_pass_pct']}%");print(report.note);print(f"详细结果: {out.relative_to(ROOT)}")
 if args.mode=="fixture" and os.environ.get("CI"):print("CI regression fixture completed; scores above are not business claims.")
 if args.mode=="source-text" and not report.publishable:print("提示: 先运行 python scripts/cache_gold_sources.py；PDF 样本需人工提取原文后放入 source_cache。")
if __name__=="__main__":main()
