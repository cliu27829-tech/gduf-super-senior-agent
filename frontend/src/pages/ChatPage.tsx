import { useEffect, useRef, useState, type DragEvent, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, streamAgentChat } from "../api";
import { useAuth } from "../auth";
import { MarkdownMessage } from "../components/MarkdownMessage";
import { LocationPermissionSheet, locationAccuracy, useGeolocation, type BrowserLocation } from "../location";
import type { NotificationParseResult } from "../types";

type ToolResult = { tool: string; status: string; title: string; data: unknown };
type Source = { title?: string; url?: string; publisher?: string; published_at?: string | null; verified_at?: string | null; source_type?: string };
type MapAction = { type: string; url?: string; location_id?: string; destination_location_id?: string; campus_id?: string; reason?: string };
type AgentStep = { id?: string; sequence?: number; tool_name?: string; public_label: string; status: string; success?: boolean | null; output_summary?: string };
type AgentAction = { id: string; type: string; label: string; style?: string; url?: string | null; api_path?: string | null; method?: string; payload?: Record<string, unknown>; requires_confirmation?: boolean };
type ChatMessage = { id: string; role: "user" | "assistant"; content: string; intent?: string; tool_results?: ToolResult[]; sources?: Source[]; map_action?: MapAction | null; degraded?: boolean; error_id?: string | null; data_status?: string; agent_run_id?: string | null; agent_status?: string | null; agent_steps?: AgentStep[]; actions?: AgentAction[] };
type Conversation = { id: string; title: string; updated_at: string };
type ChatResponse = { conversation_id: string; message_id: string; intent: string; answer: string; tool_results: ToolResult[]; sources: Source[]; locations: Record<string, unknown>[]; route: Record<string, unknown> | null; map_action: MapAction | null; degraded: boolean; error_id: string | null; data_status: string; agent_run_id: string | null; agent_status: string | null; agent_steps: AgentStep[]; actions: AgentAction[] };
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
  const [chatBusy, setChatBusy] = useState(false);
  const [error, setError] = useState("");
  const [failedMessage, setFailedMessage] = useState("");
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [stage, setStage] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [pendingNavigation, setPendingNavigation] = useState<{ destinationId: string; destinationName: string; message: string; agentRunId: string | null } | null>(null);
  const [locationSheetOpen, setLocationSheetOpen] = useState(false);
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]);
  const endRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const navigate = useNavigate();
  const geolocation = useGeolocation();

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

  const send = async (content: string, appendUser = true, locationContext?: BrowserLocation, resumeNavigation = false, agentRunId: string | null = null) => {
    if ((!content.trim() && !attachment) || chatBusy) return;
    if (!agentStatus?.llm_configured && !attachment) { setError("后端已连接，但尚未配置大模型密钥。"); return; }
    const file = attachment;
    setError(""); setFailedMessage(""); setChatBusy(true); setStage(file ? "正在提取附件内容" : "正在连接大师兄"); setLiveSteps([]);
    const localUserId = `local-${Date.now()}`;
    if (appendUser) setMessages((current) => [...current, { id: localUserId, role: "user", content: content || `附件：${file?.name}` }]);
    setAttachment(null);
    if (file) {
      try { await sendAttachment(file, content); }
      catch (reason) { setError(reason instanceof Error ? reason.message : "附件解析失败"); setFailedMessage(content); }
      finally { setChatBusy(false); setStage(""); }
      return;
    }

    const streamingId = `stream-${Date.now()}`;
    setMessages((current) => [...current, { id: streamingId, role: "assistant", content: "" }]);
    const controller = new AbortController(); abortRef.current = controller;
    try {
      await streamAgentChat(
        {
          message: content,
          conversation_id: conversationId,
          campus_id: user?.campus_id,
          location_context: locationContext,
          resume_navigation: resumeNavigation,
          agent_run_id: agentRunId,
        },
        ({ event, data }) => {
          if (event === "stage") setStage(String(data.label || "正在处理"));
          if (event === "plan" && Array.isArray(data.steps)) {
            setLiveSteps((data.steps as Record<string, unknown>[]).map((step, index) => ({
              id: `planned-${index}-${String(step.tool || "step")}`,
              tool_name: String(step.tool || ""), public_label: String(step.label || "执行计划"), status: "planned",
            })));
          }
          if (event === "tool_start") {
            const id = String(data.step_id || data.tool || Date.now());
            setLiveSteps((current) => {
              const next = { id, tool_name: String(data.tool || ""), public_label: String(data.label || "正在执行"), status: "running" };
              const matched = current.findIndex((step) => step.tool_name === next.tool_name && step.status === "planned");
              if (matched < 0) return [...current, next];
              return current.map((step, index) => index === matched ? next : step);
            });
          }
          if (event === "tool_end") {
            const id = String(data.step_id || "");
            setLiveSteps((current) => current.map((step) => step.id === id || (!id && step.tool_name === String(data.tool || "")) ? {
              ...step, status: data.success ? "completed" : "failed", success: Boolean(data.success), output_summary: String(data.summary || ""),
            } : step));
          }
          if (event === "verify") setLiveSteps((current) => [...current, {
            id: String(data.step_id || `verify-${Date.now()}`), public_label: "核对来源、校区和结果完整性",
            status: data.success ? "completed" : "failed", success: Boolean(data.success),
          }]);
          if (event === "token") setMessages((current) => current.map((item) => item.id === streamingId ? { ...item, content: item.content + String(data.content || "") } : item));
          if (event === "final") {
            const result = data as unknown as ChatResponse;
            setConversationId(result.conversation_id);
            if (result.map_action?.type === "request_location" && result.map_action.destination_location_id) {
              setPendingNavigation({
                destinationId: result.map_action.destination_location_id,
                destinationName: String(result.locations?.[0]?.name || "目的地"),
                message: content,
                agentRunId: result.agent_run_id,
              });
              setLocationSheetOpen(true);
            } else if (resumeNavigation) {
              setPendingNavigation(null);
              setLocationSheetOpen(false);
            }
            setMessages((current) => current.map((item) => item.id === streamingId ? {
              id: result.message_id, role: "assistant", content: result.answer, intent: result.intent,
              tool_results: result.tool_results, sources: result.sources, map_action: result.map_action,
              degraded: result.degraded, error_id: result.error_id, data_status: result.data_status,
              agent_run_id: result.agent_run_id, agent_status: result.agent_status,
              agent_steps: result.agent_steps, actions: result.actions,
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
    } finally { abortRef.current = null; setChatBusy(false); setStage(""); }
  };

  const allowLocation = async () => {
    if (!pendingNavigation) return;
    try {
      const position = await geolocation.locate();
      const accuracy = locationAccuracy(position.accuracy);
      if (accuracy.status === "low") {
        const continueWithApproximate = window.confirm(`${accuracy.message}\n\n仍要使用这个近似位置继续规划吗？选择“取消”可重新定位或手动选择起点。`);
        if (!continueWithApproximate) { setError(accuracy.message); return; }
      }
      setLocationSheetOpen(false);
      await send(pendingNavigation.message, false, position, true, pendingNavigation.agentRunId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "定位失败，请选择其他起点");
    }
  };

  const chooseManualOrigin = () => {
    if (!pendingNavigation) return;
    setLocationSheetOpen(false);
    navigate(`/map?destination=${encodeURIComponent(pendingNavigation.destinationId)}&manual_origin=1`);
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
          {messages.map((message) => <MessageView key={message.id} message={message} userInitial={(user?.nickname || "我").slice(0, 1)} onRequestLocation={() => {
            if (message.map_action?.destination_location_id) {
              setPendingNavigation({ destinationId: message.map_action.destination_location_id, destinationName: "目的地", message: [...messages].reverse().find((item) => item.role === "user")?.content || "怎么走？", agentRunId: message.agent_run_id || null });
            }
            setLocationSheetOpen(true);
          }} />)}
          {chatBusy && (stage || liveSteps.length > 0) && <div className="agent-run-live" role="status">
            <div className="agent-progress"><span /><span /><span />{stage || "正在执行"}</div>
            {liveSteps.length > 0 && <AgentTrace steps={liveSteps} compact />}
          </div>}
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
            {chatBusy ? <button type="button" className="stop-button" onClick={() => abortRef.current?.abort()}>停止</button> : <button className="send-button" aria-label="发送" disabled={(!input.trim() && !attachment) || (!agentStatus?.llm_configured && !attachment)}>↑</button>}
          </div>
          <div className="composer-meta"><span>Enter 发送 · Shift+Enter 换行 · 可拖入 TXT/PDF</span>{lastUserMessage && !chatBusy && <button type="button" onClick={() => void send(lastUserMessage.content, false)}>重新生成</button>}</div>
        </form>
      </div>
      <LocationPermissionSheet
        open={locationSheetOpen}
        destinationName={pendingNavigation?.destinationName}
        locating={geolocation.locating}
        onAllow={() => void allowLocation()}
        onManual={chooseManualOrigin}
        onClose={() => setLocationSheetOpen(false)}
      />
    </section>
  );
}

function MessageView({ message, userInitial, onRequestLocation }: { message: ChatMessage; userInitial: string; onRequestLocation: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { await navigator.clipboard?.writeText(message.content); setCopied(true); window.setTimeout(() => setCopied(false), 1200); };
  return <article className={`message ${message.role}`}>
    <div className="message-avatar">{message.role === "assistant" ? "广" : userInitial}</div>
    <div className="message-column">
      <div className="message-body">
        {message.content ? <MarkdownMessage content={message.content} /> : <span className="typing-cursor" />}
        {message.data_status === "needs_verification" && <div className="data-caution">部分校园资料仍待核验，回答中已保留状态说明。</div>}
        {message.agent_steps && message.agent_steps.length > 0 && <AgentTrace steps={message.agent_steps} status={message.agent_status || undefined} />}
        {message.tool_results?.map((tool, index) => <ToolCard tool={tool} key={`${message.id}-${index}`} />)}
        {message.actions && message.actions.length > 0 && <div className="action-card-row">{message.actions.map((action) => <ActionCard key={action.id} action={action} runId={message.agent_run_id || null} onRequestLocation={onRequestLocation} />)}</div>}
        {!message.actions?.length && message.map_action?.type === "request_location" && <button className="inline-action" onClick={onRequestLocation}>⌖ 使用当前位置规划</button>}
        {!message.actions?.length && message.map_action?.url && message.map_action.type !== "request_location" && <Link className="inline-action" to={message.map_action.url}>{["route", "client_route"].includes(message.map_action.type) ? "在地图中查看路线" : "在地图中查看"}</Link>}
        {message.sources && message.sources.length > 0 && <details className="execution-details"><summary>查看来源</summary>{message.sources.map((source, index) => <a href={source.url || undefined} target="_blank" rel="noreferrer" key={`${source.url}-${index}`}>{source.title || "来源"}{source.published_at ? ` · ${new Date(source.published_at).toLocaleDateString("zh-CN")}` : ""}</a>)}</details>}
      </div>
      {message.content && <button className="message-copy" onClick={() => void copy()}>{copied ? "已复制" : "复制"}</button>}
    </div>
  </article>;
}

function AgentTrace({ steps, status, compact = false }: { steps: AgentStep[]; status?: string; compact?: boolean }) {
  const visible = steps.filter((step, index) => index === steps.findIndex((candidate) => candidate.id === step.id));
  return <div className={`agent-trace ${compact ? "compact" : ""}`}>
    {!compact && <div className="agent-trace-heading"><strong>大师兄执行过程</strong>{status && <span>{status === "completed" ? "已完成" : status === "failed" ? "未完成" : status === "waiting_for_location" ? "等待定位" : status === "waiting_for_confirmation" ? "等待确认" : "处理中"}</span>}</div>}
    <ol>{visible.map((step) => <li className={step.status} key={step.id || `${step.tool_name}-${step.public_label}`}>
      <span aria-hidden="true">{step.status === "completed" ? "✓" : step.status === "failed" ? "!" : step.status === "running" ? "●" : "○"}</span>
      <div><strong>{step.public_label}</strong>{step.output_summary && !compact && <small>{step.output_summary}</small>}</div>
    </li>)}</ol>
  </div>;
}

function ActionCard({ action, runId, onRequestLocation }: { action: AgentAction; runId: string | null; onRequestLocation: () => void }) {
  const [working, setWorking] = useState(false);
  const [status, setStatus] = useState("");
  if (action.url) return <Link className="agent-action-card" to={action.url}><span>{action.type === "navigation" ? "↗" : "→"}</span><strong>{action.label}</strong></Link>;
  const execute = async () => {
    if (action.type === "location") { onRequestLocation(); return; }
    if (!action.api_path) return;
    if (action.requires_confirmation && !window.confirm(`确认执行“${action.label}”？`)) return;
    setWorking(true); setStatus("");
    try {
      await api(action.api_path, { method: action.method || "POST", body: JSON.stringify(action.payload || {}) });
      if (runId && action.requires_confirmation) await api(`/agent/runs/${runId}/confirm`, { method: "POST", body: JSON.stringify({ action_id: action.id }) });
      setStatus("已完成");
    } catch (reason) { setStatus(reason instanceof Error ? reason.message : "执行失败"); }
    finally { setWorking(false); }
  };
  return <div className="agent-action-card"><button disabled={working} onClick={() => void execute()}><span>{action.type === "reminder" ? "◷" : action.type === "note" ? "▤" : action.type === "location" ? "⌖" : "✓"}</span><strong>{working ? "正在执行…" : action.label}</strong></button>{status && <small role="status">{status}</small>}</div>;
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
