import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Campus } from "../types";

const entrances = [
  { icon: "⌖", title: "查校园", detail: "按校区搜索地点、饭堂和已核验来源", href: "/map" },
  { icon: "文", title: "处理通知", detail: "把通知拆成可修改、可确认的任务", href: "/notifications" },
  { icon: "✓", title: "我的任务", detail: "查看截止时间并导出双重提醒日历", href: "/tasks" },
];

export default function HomePage() {
  const { user } = useAuth();
  const [campuses, setCampuses] = useState<Campus[]>([]);
  useEffect(() => { api<Campus[]>("/campuses").then(setCampuses).catch(() => setCampuses([])); }, []);
  return (
    <>
      <section className="hero section-wrap">
        <div className="hero-copy">
          <p className="eyebrow">广东金融学院校园信息与执行助手</p>
          <h1>读懂校园信息，<br /><em>帮你把事情办明白。</em></h1>
          <p className="hero-lead">不把旧资料说成最新，不让 AI 猜饭堂和流程。每一条校园事实，都带着来源、核验状态和更新时间。</p>
          <div className="hero-actions">
            <Link className="button" to={user ? "/dashboard" : "/register"}>{user ? "进入工作台" : "开始使用"}</Link>
            <Link className="ghost-button" to={user ? "/chat" : "/login"}>问问大师兄</Link>
          </div>
        </div>
        <div className="trust-board" aria-label="数据可信度说明">
          <span className="board-number">03</span>
          <strong>个校区，分开查询</strong>
          <div className="rule" />
          <p>官方来源</p><small>优先展示学校与校区官网</small>
          <p>人工核验</p><small>管理员填写证据后才能标记已核验</small>
          <p>诚实降级</p><small>没有实时菜单时明确说没有</small>
        </div>
      </section>
      <section className="section-wrap section-block">
        <div className="section-heading"><p className="eyebrow">常用入口</p><h2>少绕一步，快把事情做完</h2></div>
        <div className="entrance-grid">
          {entrances.map((item) => <Link className="entrance-card" to={user ? item.href : "/login"} key={item.title}><span>{item.icon}</span><h3>{item.title}</h3><p>{item.detail}</p><b>打开 →</b></Link>)}
        </div>
      </section>
      <section className="campus-band">
        <div className="section-wrap campus-band-inner">
          <div><p className="eyebrow light">三个校区</p><h2>只看你所在校区的信息</h2><p>跨校区问题会显式区分，避免把广州、肇庆和清远的数据混在一起。</p></div>
          <div className="campus-list">
            {(campuses.length ? campuses : [{ id: "gz", name: "广州校本部" }, { id: "zq", name: "肇庆校区" }, { id: "qy", name: "清远校区" }]).map((campus, index) => (
              <div className="campus-row" key={campus.id}><span>0{index + 1}</span><strong>{campus.name}</strong><small>数据状态逐条标记</small></div>
            ))}
          </div>
        </div>
      </section>
      <section className="section-wrap honesty-note"><strong>关于“实时”</strong><p>当前没有可靠的实时饭堂菜单，也没有经过测绘的校内路线算法。系统只展示已记录信息与外部地图导航，并把待核验内容清楚标出来。</p></section>
    </>
  );
}

