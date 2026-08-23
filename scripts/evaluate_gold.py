#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"apps"/"api"))
from app.evaluation import evaluate_sample,report_dict

def main():
 p=argparse.ArgumentParser();p.add_argument("--predictions",default="data/benchmark/predictions.json");p.add_argument("--output",default="data/benchmark/evaluation_report.json");a=p.parse_args()
 gold=json.loads((ROOT/"data/benchmark/gold_dataset.json").read_text(encoding="utf-8"));pred_path=ROOT/a.predictions
 if not pred_path.exists():
  print(f"No predictions found: {pred_path}\nRun the extraction pipeline and save structured predictions before evaluation. No score has been fabricated.");return
 preds={x["sample_id"]:x for x in json.loads(pred_path.read_text(encoding="utf-8"))};results=[]
 for g in gold:
  if g["sample_id"] in preds:results.append(evaluate_sample(g,preds[g["sample_id"]]))
 report=report_dict(results);out=ROOT/a.output;out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 s=report["summary"];print(f"Samples: {s['samples']} | Field accuracy: {s['field_accuracy_pct']}% | Evidence recall: {s['evidence_recall_pct']}% | Safety pass: {s['safety_pass_pct']}%")
if __name__=="__main__":main()
