import { useEffect, useRef, useState, type DragEvent, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { api, streamAgentChat } from "../api";
import { useAuth } from "../auth";
import { MarkdownMessage } from "../components/MarkdownMessage";
import type { NotificationParseResult } from "../types";

type ToolResult = { tool: string; status: string; title: string; data: unknown };
type Source = { title?: string; url?: string; publisher?: string; published_at?: string | null; verified_at?: string | null; source_type?: string };
type MapAction = { type: string; url: string; location_id?: string; campus_id?: string };
type ChatMessage = { id: string; role: "user" | "assistant"; content: string; intent?: string; tool_results?: ToolResult[]; sources?: Source[]; map_action?: MapAction | null; degraded?: boolean; error_id?: string | null; data_status?: string };
type Conversation = { id: string; title: string; updated_at: string };
type ChatResponse = { conversation_id: string; message_id: string; intent: string; answer: string; tool_results: ToolResult[]; sources: Source[]; locations: Record<string, unknown>[]; route: Record<string, unknown> | null; map_action: MapAction | null; degraded: boolean; error_id: string | null; data_status: string };
type AgentStatus = { backend: string; llm_configured: boolean; model: string; database: string };

const QUICK_ACTIONS = [
  ["解析通知", "请帮我解析下面这份通知，并生成可确认的任务：\n"],
  ["找地点", "清远校区北区教学楼在哪里？"],
  ["查饭堂", "清远校区有哪些饭堂？请区分北饭、南饭和西饭的核验状态。"],
  ["设提醒", "明天下午3点提醒我"],
  ["记便签", "把刚才的要求记一下"],
] as const;

const welcome = (): ChatMessage => ({
  id: "welcome",
  role: "assistant",
  content: "你好，我是广金大师兄。你可以直接问学习问题、查清远校区地点，也可以把通知贴过来转成任务和提醒。",
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
  const [stage, setStage] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [attachment, setAttachment] = useState<File | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadConversations = async () => {
    try { setConversations(await api<Conversation[]>("/agent/conversations")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "对话历史加载失败"); }
  };
  const loadAgentStatus = async () => {
    try { setAgentStatus(await api<AgentStatus>("/agent/status")); }
    catch { setAgentStatus(null); }
  };
  useEffect(() => { void loadConversations(); void loadAgentStatus(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: "smooth" }); }, [messages, stage]);
  useEffect(() => {
    const field = textareaRef.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, 180)}px`;
  }, [input]);

  const newConversation = () => {
    abortRef.current?.abort();
    setConversationId(null); setMessages([welcome()]); setInput(""); setError(""); setAttachment(null); setDrawerOpen(false);
  };
  const openConversation = async (id: string) => {
    setError("");
    try {
      const result = await api<{ messages: ChatMessage[] }>(`/agent/conversations/${id}`);
      setConversationId(id); setMessages(result.messages.length ? result.messages : [welcome()]); setDrawerOpen(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "对话加载失败"); }
  };
  const removeConversation = async (id: string) => {
    if (!window.confirm("确定删除这段对话历史吗？")) return;
    try { await api(`/agent/conversations/${id}`, { method: "DELETE" }); if (conversationId === id) newConversation(); await loadConversations(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "删除对话失败"); }
  };

  const sendAttachment = async (file: File, text: string) => {
    const form = new FormData();
    form.append("file", file); if (text) form.append("text", text);
    const result = await api<NotificationParseResult>("/notifications/parse", { method: "POST", body: form, timeoutMs: 75000 });
    setMessages((current) => [...current, {
      id: `parsed-${Date.now()}`,
      role: "assistant",
      content: `已从 **${file.name}** 提取通知内容。请核对下面的任务，再决定是否保存。`,
      tool_results: [{ tool: "notification_parser", status: "success", title: "通知任务预览", data: result }],
    }]);
  };

  const send = async (content: string, appendUser = true) => {
    if ((!content.trim() && !attachment) || busy) return;
    if (!agentStatus?.llm_configured && !attachment) { setError("后端已连接，但尚未配置大模型密钥。"); return; }
    const file = attachment;
    setError(""); setFailedMessage(""); setBusy(true); setStage(file ? "正在提取附件内容" : "正在连接大师兄");
    const localUserId = `local-${Date.now()}`;
    if (appendUser) setMessages((current) => [...current, { id: localUserId, role: "user", content: content || `附件：${file?.name}` }]);
    setAttachment(null);
    if (file) {
      try { await sendAttachment(file, content); }
      catch (reason) { setError(reason instanceof Error ? reason.message : "附件解析失败"); setFailedMessage(content); }
      finally { setBusy(false); setStage(""); }
      return;
    }

    const streamingId = `stream-${Date.now()}`;
    setMessages((current) => [...current, { id: streamingId, role: "assistant", content: "" }]);
    const controller = new AbortController(); abortRef.current = controller;
    try {
      await streamAgentChat(
        { message: content, conversation_id: conversationId, campus_id: user?.campus_id },
        ({ event, data }) => {
          if (event === "stage") setStage(String(data.label || "正在处理"));
          if (event === "token") setMessages((current) => current.map((item) => item.id === streamingId ? { ...item, content: item.content + String(data.content || "") } : item));
          if (event === "final") {
            const result = data as unknown as ChatResponse;
            setConversationId(result.conversation_id);
            setMessages((current) => current.map((item) => item.id === streamingId ? {
              id: result.message_id, role: "assistant", content: result.answer, intent: result.intent,
              tool_results: result.tool_results, sources: result.sources, map_action: result.map_action,
              degraded: result.degraded, error_id: result.error_id, data_status: result.data_status,
            } : item));
          }
        },
        controller.signal,
      );
      await loadConversations();
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") {
        setMessages((current) => current.map((item) => item.id === streamingId && !item.content ? { ...item, content: "已停止生成。" } : item));
      } else {
        setMessages((current) => current.filter((item) => item.id !== streamingId || Boolean(item.content)));
        setError(reason instanceof Error ? reason.message : "消息发送失败"); setFailedMessage(content);
      }
    } finally { abortRef.current = null; setBusy(false); setStage(""); }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault(); const content = input.trim(); if (!content && !attachment) return;
    setInput(""); void send(content);
  };
  const handleKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
  };
  const chooseFile = (file?: File) => {
    if (!file) return;
    if (!/\.(txt|pdf)$/i.test(file.name)) { setError("仅支持 TXT 和 PDF 文件"); return; }
    if (file.size > 5 * 1024 * 1024) { setError("文件不得超过 5 MB"); return; }
    setAttachment(file); setError("");
  };
  const drop = (event: DragEvent) => { event.preventDefault(); chooseFile(event.dataTransfer.files[0]); };
  const lastUserMessage = [...messages].reverse().find((item) => item.role === "user" && !item.id.startsWith("local-attachment"));

  return (
    <section className="chat-page">
      {drawerOpen && <button className="chat-drawer-backdrop" aria-label="关闭对话历史" onClick={() => setDrawerOpen(false)} />}
      <aside className={`conversation-sidebar ${drawerOpen ? "open" : ""}`} aria-label="对话历史">
        <div className="panel-heading"><h2>对话</h2><button className="icon-button" aria-label="新建对话" onClick={newConversation}>＋</button></div>
        {conversations.map((item) => <div className={`conversation-row ${conversationId === item.id ? "active" : ""}`} key={item.id}><button onClick={() => void openConversation(item.id)}><strong>{item.title}</strong><small>{new Date(item.updated_at).toLocaleDateString("zh-CN")}</small></button><button aria-label={`删除对话 ${item.title}`} className="danger-link" onClick={() => void removeConversation(item.id)}>×</button></div>)}
        {!conversations.length && <p className="empty-copy">还没有对话</p>}
      </aside>

      <div className="chat-main">
        <header className="chat-topbar">
          <button className="history-trigger" onClick={() => setDrawerOpen(true)} aria-label="打开对话历史">☰</button>
          <div><h1>问问大师兄</h1><span> · {user?.campus_id ? "当前校区" : "校区未设置"}</span></div>
          <span className={`connection-dot ${agentStatus?.llm_configured ? "online" : ""}`} title={agentStatus?.llm_configured ? "大模型已连接" : "模型未配置"} />
        </header>

        {!agentStatus?.llm_configured && agentStatus && <div className="model-warning" role="status">后端已连接，但尚未配置大模型密钥。<button onClick={() => void loadAgentStatus()}>重新检查</button></div>}
        <div className="message-list" aria-live="polite">
          {messages.map((message) => <MessageView key={message.id} message={message} userInitial={(user?.nickname || "我").slice(0, 1)} />)}
          {busy && stage && <div className="agent-progress" role="status"><span /><span /><span />{stage}</div>}
          <div ref={endRef} />
        </div>

        {messages.length <= 1 && <div className="chat-quick-actions" aria-label="快捷操作">{QUICK_ACTIONS.map(([label, value]) => <button key={label} onClick={() => { setInput(value); textareaRef.current?.focus(); }}>{label}</button>)}</div>}
        {error && <div className="chat-error" role="alert"><span>{error}</span>{failedMessage && <button onClick={() => void send(failedMessage, false)}>重试</button>}</div>}
        <form className="chat-composer" onSubmit={submit} onDragOver={(event) => event.preventDefault()} onDrop={drop}>
          {attachment && <div className="attachment-chip"><span>{attachment.name}</span><button type="button" onClick={() => setAttachment(null)} aria-label="移除附件">×</button></div>}
          <div className="composer-row">
            <button type="button" className="composer-icon" title="添加 TXT 或 PDF" aria-label="添加附件" onClick={() => fileRef.current?.click()}>＋</button>
            <input ref={fileRef} hidden type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={(event) => chooseFile(event.target.files?.[0])} />
            <textarea ref={textareaRef} aria-label="消息" rows={1} value={input} onChange={(event) => setInput(event.target.value)} placeholder="发消息，或粘贴一份通知…" onKeyDown={handleKey} />
            {busy ? <button type="button" className="stop-button" onClick={() => abortRef.current?.abort()}>停止</button> : <button className="send-button" aria-label="发送" disabled={(!input.trim() && !attachment) || (!agentStatus?.llm_configured && !attachment)}>↑</button>}
          </div>
          <div className="composer-meta"><span>Enter 发送 · Shift+Enter 换行 · 可拖入 TXT/PDF</span>{lastUserMessage && !busy && <button type="button" onClick={() => void send(lastUserMessage.content, false)}>重新生成</button>}</div>
        </form>
      </div>
    </section>
  );
}

function MessageView({ message, userInitial }: { message: ChatMessage; userInitial: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { await navigator.clipboard?.writeText(message.content); setCopied(true); window.setTimeout(() => setCopied(false), 1200); };
  return <article className={`message ${message.role}`}><div className="message-avatar">{message.role === "assistant" ? "广" : userInitial}</div><div className="message-column"><div className="message-body">{message.content ? <MarkdownMessage content={message.content} /> : <span className="typing-cursor" />}{message.data_status === "needs_verification" && <div className="data-caution">部分校园资料仍待核验，回答中已保留状态说明。</div>}{message.tool_results?.map((tool, index) => <ToolCard tool={tool} key={`${message.id}-${index}`} />)}{message.map_action && <Link className="inline-action" to={message.map_action.url}>{message.map_action.type === "route" ? "在地图中查看路线" : "在地图中查看"}</Link>}{message.sources && message.sources.length > 0 && <details className="execution-details"><summary>查看来源</summary>{message.sources.map((source, index) => <a href={source.url || undefined} target="_blank" rel="noreferrer" key={`${source.url}-${index}`}>{source.title || "来源"}{source.published_at ? ` · ${new Date(source.published_at).toLocaleDateString("zh-CN")}` : ""}</a>)}</details>}</div>{message.content && <button className="message-copy" onClick={() => void copy()}>{copied ? "已复制" : "复制"}</button>}</div></article>;
}

function ToolCard({ tool }: { tool: ToolResult }) {
  const [status, setStatus] = useState("");
  const [working, setWorking] = useState(false);
  const data = tool.data as Record<string, unknown> | null;
  const rows = Array.isArray(tool.data) ? tool.data as Record<string, unknown>[] : [];
  const saveReminder = async () => {
    if (!data?.remind_at || !window.confirm(`确认在 ${new Date(String(data.remind_at)).toLocaleString("zh-CN")} 提醒？`)) return;
    setWorking(true); try { await api("/reminders", { method: "POST", body: JSON.stringify({ ...data, confirmed: true }) }); setStatus("提醒已保存"); } catch (reason) { setStatus(reason instanceof Error ? reason.message : "保存失败"); } finally { setWorking(false); }
  };
  const saveNote = async () => {
    if (!window.confirm("确认保存这条便签？")) return;
    setWorking(true); try { await api("/notes", { method: "POST", body: JSON.stringify({ ...data, confirmed: true }) }); setStatus("便签已保存"); } catch (reason) { setStatus(reason instanceof Error ? reason.message : "保存失败"); } finally { setWorking(false); }
  };
  const saveNotificationTasks = async () => {
    const parsed = data as unknown as NotificationParseResult;
    if (!parsed?.action_items?.length || !window.confirm(`确认保存 ${parsed.action_items.length} 个任务，并添加24小时和3小时提醒？`)) return;
    setWorking(true); try { await api("/notifications/confirm", { method: "POST", body: JSON.stringify({ action_items: parsed.action_items, confirmed: true, allow_expired: false }) }); setStatus("任务与提醒已保存"); } catch (reason) { setStatus(reason instanceof Error ? reason.message : "保存失败"); } finally { setWorking(false); }
  };
  const summaries = rows.slice(0, 4).map((row) => String(row.name || row.title || row.subject || "结果"));
  return <div className={`tool-card natural ${tool.status === "error" ? "failed" : ""}`}><div className="tool-summary"><span>{tool.status === "error" ? "!" : "✓"}</span><strong>{tool.status === "error" ? `${tool.title}未完成` : `${tool.title}已完成`}</strong></div>{summaries.length > 0 && <p>{summaries.join("、")}{rows.length > 4 ? ` 等 ${rows.length} 条` : ""}</p>}{tool.tool === "reminder_preview" && <button disabled={working || !data?.remind_at} onClick={() => void saveReminder()}>{data?.remind_at ? "确认保存提醒" : "未识别到时间"}</button>}{tool.tool === "note_preview" && <button disabled={working} onClick={() => void saveNote()}>确认保存便签</button>}{tool.tool === "notification_parser" && <button disabled={working} onClick={() => void saveNotificationTasks()}>保存任务并设置提醒</button>}{tool.tool === "calendar_download" && <Link to="/tasks">前往任务中心导出日历</Link>}{status && <small role="status">{status}</small>}<details className="execution-details"><summary>查看执行详情</summary><pre>{JSON.stringify(tool.data, null, 2)}</pre></details></div>;
}
