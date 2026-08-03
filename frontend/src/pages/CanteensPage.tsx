import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import { formatDate, StatusBadge } from "../components/StatusBadge";
import type { Campus, Canteen } from "../types";

export default function CanteensPage() {
  const { user } = useAuth();
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [campusId, setCampusId] = useState(user?.campus_id || "");
  const [canteens, setCanteens] = useState<Canteen[]>([]);
  const [query, setQuery] = useState("");
  const [foodResult, setFoodResult] = useState<{ message: string; items: unknown[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { api<Campus[]>("/campuses").then((rows) => { setCampuses(rows); setCampusId((value) => value || rows[0]?.id || ""); }); }, []);
  useEffect(() => { if (campusId) { setLoading(true); setError(""); api<Canteen[]>(`/canteens?campus_id=${campusId}`).then(setCanteens).catch((reason) => { setCanteens([]); setError(reason instanceof Error ? reason.message : "饭堂数据加载失败"); }).finally(() => setLoading(false)); } }, [campusId]);
  const searchFood = async () => { if (!query.trim()) return; try { setFoodResult(await api(`/food-search?q=${encodeURIComponent(query)}&campus_id=${campusId}`)); } catch (reason) { setFoodResult({ message: reason instanceof Error ? reason.message : "查询失败", items: [] }); } };
  return (
    <section className="page section-wrap">
      <div className="page-heading"><div><p className="eyebrow">饭堂与档口</p><h1>看记录，也看它靠不靠谱</h1><p>常见餐品是最近核验信息，不代表今日供应。</p></div><select value={campusId} onChange={(e) => setCampusId(e.target.value)}>{campuses.map((campus) => <option value={campus.id} key={campus.id}>{campus.name}</option>)}</select></div>
      <div className="food-search"><label className="search-box"><span>食</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索面、粉、早餐、奶茶…" onKeyDown={(e) => { if (e.key === "Enter") void searchFood(); }} /></label><button className="button" onClick={() => void searchFood()}>搜索已核验餐品</button></div>
      {foodResult && <div className="data-notice"><strong>餐品查询结果</strong><p>{foodResult.message}</p></div>}
      {error && <div className="error-banner" role="alert">{error}</div>}
      <div className="realtime-warning"><strong>今日菜单：暂无可靠数据</strong><span>系统不会根据旧资料或模型猜测今天供应什么。</span></div>
      {loading ? <Loading /> : canteens.length ? <div className="canteen-grid">{canteens.map((canteen) => <article className="canteen-card" key={canteen.id}><div className="canteen-card-head"><span className="canteen-number">食</span><div><h2>{canteen.name}</h2><div className="badge-row"><StatusBadge value={canteen.verification_status} /></div></div></div><dl><dt>楼层</dt><dd>{canteen.floors.join("、") || "待核验"}</dd><dt>开放时间</dt><dd>{canteen.opening_hours || "待核验"}</dd><dt>支付方式</dt><dd>{canteen.payment_methods.join("、") || "待核验"}</dd><dt>最后核验</dt><dd>{formatDate(canteen.verified_at)}</dd></dl><div className="stall-list"><h3>已记录档口</h3>{canteen.stalls.length ? canteen.stalls.map((stall) => <div key={stall.id}><strong>{stall.name}</strong><small>{stall.floor || "楼层待核验"} · {stall.food_type || "类型待核验"}</small><p>{stall.common_items.length ? `常见：${stall.common_items.join("、")}` : "没有已核验常见餐品"}</p><StatusBadge value={stall.verification_status} /></div>) : <p>暂无档口记录，等待管理员核验。</p>}</div><footer>{canteen.source ? <a href={canteen.source.url || undefined} target="_blank" rel="noreferrer">来源：{canteen.source.publisher || canteen.source.title}</a> : <span>来源待补充</span>}<small>可信度 {Math.round(canteen.confidence * 100)}%</small></footer></article>)}</div> : <EmptyState title="该校区暂无饭堂记录" detail="数据待管理员核验补充，系统不会自动生成名称和营业信息。" />}
    </section>
  );
}
