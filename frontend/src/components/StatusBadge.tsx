const labels: Record<string, string> = {
  verified: "已核验",
  current: "时效内",
  needs_verification: "待核验",
  stale: "可能过期",
  expired: "已过期",
  historical: "历史信息",
  historical_seed: "历史种子",
  demo_fixture: "演示数据",
  unverified_seed: "待核验种子",
  inactive: "已停用",
};

export function StatusBadge({ value }: { value: string }) {
  return <span className={`status-badge status-${value}`}>{labels[value] || value}</span>;
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "未记录";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Shanghai" }).format(new Date(value));
}

