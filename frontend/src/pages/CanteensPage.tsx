import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import { formatDate, StatusBadge } from "../components/StatusBadge";
import type { Campus, Canteen } from "../types";

type FoodSearchItem = { id: string; canteen: string; name: string; food_type: string; common_items: string[]; verified_at: string | null; data_status: string };
type FoodSearchResult = { message: string; items: FoodSearchItem[]; today_menu_available: false };
const dataLabel = (value: string) => value === "historical" ? "历史公开资料" : value === "current" ? "当前资料" : "待核验资料";

export default function CanteensPage() {
  const { user } = useAuth();
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [campusId, setCampusId] = useState(user?.campus_id || "");
  const [canteens, setCanteens] = useState<Canteen[]>([]);
  const [query, setQuery] = useState("");
  const [foodResult, setFoodResult] = useState<FoodSearchResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Campus[]>("/campuses").then((rows) => { setCampuses(rows); setCampusId((value) => value || rows[0]?.id || ""); }).catch((reason) => { setError(reason instanceof Error ? reason.message : "校区加载失败"); setLoading(false); });
  }, []);
  useEffect(() => {
    if (!campusId) return;
    setLoading(true);
    setError("");
    setFoodResult(null);
    api<Canteen[]>(`/canteens?campus_id=${encodeURIComponent(campusId)}`).then(setCanteens).catch((reason) => { setCanteens([]); setError(reason instanceof Error ? reason.message : "饭堂数据加载失败"); }).finally(() => setLoading(false));
  }, [campusId]);
  const searchFood = async () => {
    if (!query.trim() || !campusId) return;
    setSearching(true);
    setError("");
    try {
      setFoodResult(await api<FoodSearchResult>(`/food-search?q=${encodeURIComponent(query)}&campus_id=${encodeURIComponent(campusId)}`));
    } catch (reason) {
      setFoodResult(null);
      setError(reason instanceof Error ? reason.message : "查询失败");
    } finally {
      setSearching(false);
    }
  };

  return (
    <section className="page section-wrap">
      <div className="page-heading"><div><p className="eyebrow">饭堂与档口</p><h1>查公开记录，也看资料时效</h1><p>当前档口和菜单没有可靠实时数据；历史公开资料仅用于了解过去情况。</p></div><select aria-label="选择校区" value={campusId} onChange={(event) => setCampusId(event.target.value)}>{campuses.map((campus) => <option value={campus.id} key={campus.id}>{campus.name}</option>)}</select></div>
      <div className="food-search"><label className="search-box"><span>食</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索公开资料中的面、粉、早餐…" onKeyDown={(event) => { if (event.key === "Enter") void searchFood(); }} /></label><button className="button" disabled={searching || !query.trim()} onClick={() => void searchFood()}>{searching ? "正在搜索…" : "搜索已有记录"}</button></div>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {foodResult && <div className="data-notice"><strong>餐品查询结果</strong><p>{foodResult.message}</p>{foodResult.items.length > 0 && <div className="food-result-list">{foodResult.items.map((item) => <article key={item.id}><strong>{item.canteen} · {item.name}</strong><span>{item.food_type || "类型未注明"}</span><p>{item.common_items.length ? item.common_items.join("、") : "未记录具体餐品"}</p><small>{dataLabel(item.data_status)} · 资料日期 {formatDate(item.verified_at)}</small></article>)}</div>}</div>}
      <div className="realtime-warning"><strong>今日菜单：暂无可靠数据</strong><span>系统不会根据旧资料或模型猜测今天供应什么，也不承诺历史档口仍在营业。</span></div>
      {loading ? <Loading /> : canteens.length ? <div className="canteen-grid">{canteens.map((canteen) => <article className="canteen-card" key={canteen.id}>
        <div className="canteen-card-head"><span className="canteen-number">食</span><div><h2>{canteen.name}</h2><div className="badge-row"><StatusBadge value={canteen.verification_status} /><span className={`status-badge status-${canteen.data_status}`}>{dataLabel(canteen.data_status)}</span></div></div></div>
        {canteen.data_status === "historical" && <p className="date-warning">这是历史公开资料，不代表目前楼层布局、营业时间或档口仍然相同。</p>}
        <dl><dt>历史楼层</dt><dd>{canteen.floors.join("、") || "待核验"}</dd><dt>开放时间</dt><dd>{canteen.opening_hours || "无可靠当前数据"}</dd><dt>支付方式</dt><dd>{canteen.payment_methods.join("、") || "无可靠当前数据"}</dd><dt>资料日期</dt><dd>{formatDate(canteen.verified_at)}</dd></dl>
        <div className="stall-list"><h3>公开资料中的楼层/餐品</h3>{canteen.stalls.length ? canteen.stalls.map((stall) => <div key={stall.id}><strong>{stall.name}</strong><small>{stall.floor || "楼层未注明"} · {stall.food_type || "类型未注明"}</small><p>{stall.common_items.length ? `当时公开记录：${stall.common_items.join("、")}` : "未记录具体餐品"}</p><div className="badge-row"><StatusBadge value={stall.verification_status} /><span className={`status-badge status-${stall.data_status}`}>{dataLabel(stall.data_status)}</span></div></div>) : <p>暂无可公开的档口记录。</p>}</div>
        <footer>{canteen.source?.url ? <a href={canteen.source.url} target="_blank" rel="noreferrer">来源：{canteen.source.publisher || canteen.source.title}</a> : <span>来源待补充</span>}<small>可信度 {Math.round(canteen.confidence * 100)}%</small></footer>
      </article>)}</div> : <EmptyState title="该校区暂无可公开饭堂记录" detail="系统不会自动生成饭堂、档口或营业信息。" />}
    </section>
  );
}
