import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

type ToolResult = { tool: string; status: string; title: string; data: unknown };
type ChatMessage = { id: string; role: "user" | "assistant"; content: string; intent?: string; tool_results?: ToolResult[]; sources?: Record<string, unknown>[]; degraded?: boolean };
type Conversation = { id: string; title: string; updated_at: string };

export default function ChatPage() {
  const { user } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([{ id: "welcome", role: "assistant", content: "你好，我是广金大师兄。可以查校园、看饭堂、处理通知、管理任务，也可以聊学习和校园生活。" }]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const loadConversations = () => api<Conversation[]>("/agent/conversations").then(setConversations).catch(() => setConversations([]));
  useEffect(() => { void loadConversations(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  const openConversation = async (id: string) => {
    const result = await api<{ messages: ChatMessage[] }>(`/agent/conversations/${id}`);
    setConversationId(id); setMessages(result.messages);
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!input.trim() || busy) return;
    const content = input.trim(); setInput(""); setError(""); setBusy(true);
    setMessages((current) => [...current, { id: `local-${Date.now()}`, role: "user", content }]);
    try {
      const result = await api<{ conversation_id: string; message_id: string; intent: string; answer: string; tool_results: ToolResult[]; sources: Record<string, unknown>[]; degraded: boolean }>("/agent/chat", { method: "POST", body: JSON.stringify({ message: content, conversation_id: conversationId, campus_id: user?.campus_id }) });
      setConversationId(result.conversation_id);
      setMessages((current) => [...current, { id: result.message_id, role: "assistant", content: result.answer, intent: result.intent, tool_results: result.tool_results, sources: result.sources, degraded: result.degraded }]);
      void loadConversations();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "消息发送失败"); }
    finally { setBusy(false); }
  };
  return (
    <section className="chat-page section-wrap">
      <aside className="conversation-sidebar"><div className="panel-heading"><h2>对话历史</h2><button className="icon-button" onClick={() => { setConversationId(null); setMessages([]); }}>＋</button></div>{conversations.map((item) => <button className={conversationId === item.id ? "active" : ""} onClick={() => void openConversation(item.id)} key={item.id}>{item.title}<small>{new Date(item.updated_at).toLocaleDateString("zh-CN")}</small></button>)}{!conversations.length && <p>还没有保存的对话</p>}</aside>
      <div className="chat-main"><header><p className="eyebrow">AI 对话</p><h1>问问大师兄</h1><p>校园事实只从工具和知识库返回；模型不可用时会显示降级提示。</p></header><div className="message-list" aria-live="polite">{messages.map((message) => <article className={`message ${message.role}`} key={message.id}><div className="message-avatar">{message.role === "assistant" ? "广" : (user?.nickname || "我").slice(0, 1)}</div><div className="message-body"><p>{message.content}</p>{message.degraded && <div className="degraded-note">当前使用规则降级，关键日期和校园事实请核对。</div>}{message.tool_results?.map((tool, index) => <ToolCard tool={tool} key={`${message.id}-${index}`} />)}{message.sources && message.sources.length > 0 && <div className="chat-sources"><strong>来源</strong>{message.sources.map((source, index) => <a href={String(source.url || "") || undefined} target="_blank" rel="noreferrer" key={index}>{String(source.title || "来源待补充")}<small>{String(source.publisher || "")}</small></a>)}</div>}</div></article>)}{busy && <article className="message assistant"><div className="message-avatar">广</div><div className="message-body typing">正在查询和核对…</div></article>}<div ref={endRef} /></div>{error && <div className="error-banner" role="alert">{error}</div>}<form className="chat-composer" onSubmit={submit}><textarea rows={2} value={input} onChange={(e) => setInput(e.target.value)} placeholder="例如：广州校本部有哪些饭堂？或粘贴一条通知…" onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} /><button className="button" disabled={busy || !input.trim()}>发送</button><small>Enter 发送 · Shift + Enter 换行</small></form></div>
    </section>
  );
}

function ToolCard({ tool }: { tool: ToolResult }) {
  const rows = Array.isArray(tool.data) ? tool.data : tool.data ? [tool.data] : [];
  return <div className="tool-card"><div><span>工具结果</span><strong>{tool.title}</strong></div>{rows.length ? <div className="tool-items">{rows.slice(0, 8).map((row, index) => { const item = row as Record<string, unknown>; return <div key={index}><strong>{String(item.name || item.title || item.canteen || `结果 ${index + 1}`)}</strong><small>{String(item.area || item.deadline || item.verification_status || "")}</small></div>; })}</div> : <p>没有匹配的结构化记录。</p>}</div>;
}
