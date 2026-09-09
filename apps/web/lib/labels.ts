// 枚举值的中文展示映射。后端 API 返回英文枚举（open / high / GO 等），
// 前端只在这里做展示层的本地化，绝不改变传输的原始枚举值。

export const STATUS_LABEL: Record<string, string> = {
  open: "待办",
  in_progress: "进行中",
  blocked: "已阻塞",
  done: "已完成",
  cancelled: "已取消",
};

export const PRIORITY_LABEL: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export const ROLE_LABEL: Record<string, string> = {
  lead: "牵头人",
  contributor: "贡献者",
  reviewer: "复核人",
  watcher: "观察者",
};

export const WORK_TYPE_LABEL: Record<string, string> = {
  action: "行动",
  milestone: "里程碑",
  request: "请求",
};

export const GATE_TYPE_LABEL: Record<string, string> = {
  qualification: "资格预审",
  pursuit: "经营决策",
  bid: "投标决策",
  submission: "交标决策",
  closeout: "收尾复盘",
};

export const REVIEW_STATUS_LABEL: Record<string, string> = {
  pending: "待复核",
  approved: "通过",
  changes_requested: "要求修改",
  waived: "豁免",
};

export const DECISION_LABEL: Record<string, string> = {
  GO: "放行",
  HOLD: "暂缓",
  NO_GO: "否决",
};

export function enumLabel(
  map: Record<string, string>,
  value: string | null | undefined,
): string {
  if (value == null) return "";
  return map[value] ?? value;
}
