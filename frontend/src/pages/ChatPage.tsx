import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

type ToolResult = { tool: string; status: string; title: string; data: unknown };
type Source = { title?: string; url?: string; publisher?: string; published_at?: string | null; verified_at?: string | null; source_type?: string };
type MapAction = { type: string; url: string; location_id?: string; campus_id?: string };
type ChatMessage = { id: string; role: "user" | "assistant"; content: string; intent?: string; tool_results?: ToolResult[]; sources?: Source[]; map_action?: MapAction | null; degraded?: boolean; error_id?: string | null; data_status?: string };
type Conversation = { id: string; title: string; updated_at: string };
type ChatResponse = { conversation_id: string; message_id: string; intent: string; answer: string; tool_results: ToolResult[]; sources: Source[]; locations: Record<string, unknown>[]; route: Record<string, unknown> | null; map_action: MapAction | null; degraded: boolean; error_id: string | null; data_status: string };
type AgentStatus = { backend: string; llm_configured: boolean; model: string; database: string };

const welcome = (): ChatMessage => ({
  id: "welcome",
  role: "assistant",
  content: "你好，我是广金大师兄。模型连接正常后，你可以在这里进行多轮对话。",
});

export default function ChatPage() {
  const { user } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([welcome()]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [failedMessage, setFailedMessage] = useState("");
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [statusError, setStatusError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const loadConversations = async () => {
    try { setConversations(await api<Conversation[]>("/agent/conversations")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "对话历史加载失败"); }
  };
  const loadAgentStatus = async () => {
    setStatusError("");
    try { setAgentStatus(await api<AgentStatus>("/agent/status")); }
    catch (reason) {
      setAgentStatus(null);
      setStatusError(reason instanceof Error ? reason.message : "无法读取大模型状态");
    }
  };
  useEffect(() => { void loadConversations(); void loadAgentStatus(); }, []);
  useEffect(() => { if (typeof endRef.current?.scrollIntoView === "function") endRef.current.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  const newConversation = () => {
    setConversationId(null);
    setMessages([welcome()]);
    setInput("");
    setError("");
    setFailedMessage("");
  };
  const openConversation = async (id: string) => {
    setError("");
    try {
      const result = await api<{ messages: ChatMessage[] }>(`/agent/conversations/${id}`);
      setConversationId(id);
      setMessages(result.messages.length ? result.messages : [welcome()]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "对话加载失败"); }
  };
  const removeConversation = async (id: string) => {
    if (!window.confirm("确定删除这段对话历史吗？")) return;
    setError("");
    try {
      await api(`/agent/conversations/${id}`, { method: "DELETE" });
      if (conversationId === id) newConversation();
      await loadConversations();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "删除对话失败"); }
  };

  const send = async (content: string, appendUser = true) => {
    if (!content.trim() || busy) return;
    if (!agentStatus?.llm_configured) {
      setError("后端已连接，但尚未配置大模型密钥。");
      return;
    }
    setError(""); setFailedMessage(""); setBusy(true);
    if (appendUser) setMessages((current) => [...current, { id: `local-${Date.now()}`, role: "user", content }]);
    try {
      const result = await api<ChatResponse>("/agent/chat", {
        method: "POST",
        body: JSON.stringify({ message: content, conversation_id: conversationId, campus_id: user?.campus_id }),
        timeoutMs: 75000,
      });
      setConversationId(result.conversation_id);
      setMessages((current) => [...current, {
        id: result.message_id,
        role: "assistant",
        content: result.answer,
        intent: result.intent,
        tool_results: result.tool_results,
        sources: result.sources,
        map_action: result.map_action,
        degraded: result.degraded,
        error_id: result.error_id,
        data_status: result.data_status,
      }]);
      await loadConversations();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "消息发送失败");
      setFailedMessage(content);
    } finally { setBusy(false); }
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const content = input.trim();
    if (!content) return;
    if (!agentStatus?.llm_configured) {
      setError("后端已连接，但尚未配置大模型密钥。");
      return;
    }
    setInput("");
    void send(content);
  };

  return (
    <section className="chat-page section-wrap">
      <aside className="conversation-sidebar">
        <div className="panel-heading"><h2>对话历史</h2><button className="icon-button" aria-label="新建对话" onClick={newConversation}>＋</button></div>
        {conversations.map((item) => <div className={`conversation-row ${conversationId === item.id ? "active" : ""}`} key={item.id}><button onClick={() => void openConversation(item.id)}><strong>{item.title}</strong><small>{new Date(item.updated_at).toLocaleDateString("zh-CN")}</small></button><button aria-label={`删除对话 ${item.title}`} className="danger-link" onClick={() => void removeConversation(item.id)}>×</button></div>)}
        {!conversations.length && <p>还没有保存的对话</p>}
      </aside>
      <div className="chat-main">
        <header><p className="eyebrow">AI 对话</p><h1>问问大师兄</h1><p>回答由后端连接的真实大模型生成，多轮上下文保存在你的对话记录中。</p></header>
        {agentStatus && !agentStatus.llm_configured && <div className="degraded-note" role="status">后端已连接，但尚未配置大模型密钥。<button className="text-link" onClick={() => void loadAgentStatus()}>重新检查</button></div>}
        {agentStatus?.llm_configured && <div className="degraded-note" role="status">大模型已连接：{agentStatus.model}</div>}
        {statusError && <div className="error-banner" role="alert">模型状态检查失败：{statusError}<button className="ghost-button compact" onClick={() => void loadAgentStatus()}>重新检查</button></div>}
        <div className="message-list" aria-live="polite">
          {messages.map((message) => <article className={`message ${message.role}`} key={message.id}><div className="message-avatar">{message.role === "assistant" ? "广" : (user?.nickname || "我").slice(0, 1)}</div><div className="message-body"><p>{message.content}</p>{message.intent && <small className="intent-label">意图：{message.intent}</small>}{message.degraded && <div className="degraded-note">基础模式：当前未使用可用的大模型回答。数据库查询仍然真实可用，请核对不确定日期。{message.error_id ? ` 错误编号：${message.error_id}` : ""}</div>}{message.data_status === "needs_verification" && <div className="date-warning">结果包含历史或待核验数据，请查看来源与日期。</div>}{message.tool_results?.map((tool, index) => <ToolCard tool={tool} key={`${message.id}-${index}`} />)}{message.map_action && <Link className="button compact" to={message.map_action.url}>{message.map_action.type === "route" ? "在地图中查看路线" : "在地图中查看"}</Link>}{message.sources && message.sources.length > 0 && <div className="chat-sources"><strong>来源</strong>{message.sources.map((source, index) => <a href={source.url || undefined} target="_blank" rel="noreferrer" key={`${source.url}-${index}`}><span>{source.title || "来源"}</span><small>{source.publisher || "发布方未注明"}{source.published_at ? ` · 发布 ${new Date(source.published_at).toLocaleDateString("zh-CN")}` : ""}{source.verified_at ? ` · 核验 ${new Date(source.verified_at).toLocaleDateString("zh-CN")}` : ""}</small></a>)}</div>}</div></article>)}
          {busy && <article className="message assistant"><div className="message-avatar">广</div><div className="message-body typing">正在等待大模型回答…</div></article>}
          <div ref={endRef} />
        </div>
        {error && <div className="error-banner" role="alert">{error}{failedMessage && <button className="ghost-button compact" onClick={() => void send(failedMessage, false)}>重新发送</button>}</div>}
        <form className="chat-composer" onSubmit={submit}><textarea aria-label="消息" rows={2} value={input} onChange={(event) => setInput(event.target.value)} placeholder="例如：你好，你能做什么？" onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /><button className="button" disabled={busy || !input.trim() || !agentStatus?.llm_configured}>发送</button><small>Enter 发送 · Shift + Enter 换行</small></form>
      </div>
    </section>
  );
}

function ToolCard({ tool }: { tool: ToolResult }) {
  const rows = Array.isArray(tool.data) ? tool.data : tool.data ? [tool.data] : [];
  const locationTool = ["location_search", "nearby_location_search"].includes(tool.tool);
  const hasId = (item: Record<string, unknown>) => Boolean(item.id);
  const navigationUrl = !Array.isArray(tool.data) && tool.data && typeof tool.data === "object" ? String((tool.data as Record<string, unknown>).url || "") : "";
  return <div className="tool-card"><div><span>工具结果 · {tool.status === "error" ? "未通过" : "已核验流程"}</span><strong>{tool.title}</strong></div>{tool.status === "error" && <p className="date-warning">工具没有返回可用结果，AI 不会据此生成校园事实。</p>}{rows.length ? <div className="tool-items">{rows.slice(0, 8).map((row, index) => { const item = row as Record<string, unknown>; const nested = Array.isArray(item.stalls) ? item.stalls as Record<string, unknown>[] : []; return <div key={String(item.id || index)}><strong>{String(item.name || item.title || item.canteen || `结果 ${index + 1}`)}</strong><small>{String(item.area || item.address || item.deadline || item.verification_status || "")}</small>{Boolean(item.distance_note) && <p>{String(item.distance_note)}</p>}{nested.length > 0 && <p>记录：{nested.map((stall) => String(stall.name || stall.food_type)).join("、")}</p>}{locationTool && hasId(item) && <Link className="text-link" to={`/map?location=${encodeURIComponent(String(item.id))}`}>在地图页查看</Link>}</div>; })}</div> : <p>没有匹配的结构化记录。</p>}{tool.tool === "navigation_link" && navigationUrl && <a className="button compact" href={navigationUrl} target="_blank" rel="noreferrer">开始导航</a>}{tool.tool === "notification_parser" && <Link className="ghost-button compact" to="/notifications">打开可编辑通知预览</Link>}{tool.tool === "calendar_download" && <Link className="ghost-button compact" to="/tasks">前往任务中心确认导出</Link>}</div>;
}
