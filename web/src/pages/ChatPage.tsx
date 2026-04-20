import { useState, useEffect, useRef, useCallback } from "react";
import { Send, Plus, Paperclip, X, ChevronRight, MessageSquare, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { eConversations, eFiles } from "@/lib/enterpriseApi";
import type { SessionSummary, MessageItem, FileInfo } from "@/lib/enterpriseApi";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

// ── helpers ───────────────────────────────────────────────────────────────────

function fmtTime(ts: number) {
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function fmtSize(bytes: number | null) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

// ── sub-components ────────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: MessageItem & { pending?: boolean } }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={`max-w-[75%] rounded-xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words ${
          isUser
            ? "bg-foreground text-background"
            : "bg-muted text-foreground border border-border"
        }`}
      >
        {msg.pending ? (
          <span className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> 思考中…
          </span>
        ) : (
          msg.content || ""
        )}
        {!msg.pending && (
          <div className={`text-[0.6rem] mt-1 opacity-50 ${isUser ? "text-right" : ""}`}>
            {fmtTime(msg.timestamp)}
          </div>
        )}
      </div>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function ChatPage() {
  const { user } = useAuth();

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<(MessageItem & { pending?: boolean })[]>([]);
  const [userFiles, setUserFiles] = useState<FileInfo[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [showFilePicker, setShowFilePicker] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load sessions and user files on mount
  useEffect(() => {
    eConversations.list().then(setSessions).catch(() => {});
    eFiles.list().then(setUserFiles).catch(() => {});
  }, []);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadMessages = useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setMessages([]);
    try {
      const msgs = await eConversations.messages(sessionId);
      setMessages(msgs.filter((m) => m.role === "user" || m.role === "assistant"));
    } catch {
      setError("加载消息失败");
    }
  }, []);

  const newChat = () => {
    setActiveSessionId(null);
    setMessages([]);
    setSelectedFileIds([]);
  };

  const toggleFile = (id: string) => {
    setSelectedFileIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const sendMessage = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setError(null);
    setSending(true);

    const userMsg: MessageItem & { pending?: boolean } = {
      role: "user",
      content: text,
      timestamp: Date.now() / 1000,
    };
    const pendingMsg: MessageItem & { pending?: boolean } = {
      role: "assistant",
      content: null,
      timestamp: Date.now() / 1000,
      pending: true,
    };
    setMessages((prev) => [...prev, userMsg, pendingMsg]);

    try {
      let assistantContent = "";
      const result = await eConversations.send(
        text,
        activeSessionId,
        selectedFileIds,
        (delta) => {
          assistantContent += delta;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "assistant",
              content: assistantContent,
              timestamp: Date.now() / 1000,
              pending: false,
            };
            return updated;
          });
        },
      );

      // Final update with server response
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: result.content || assistantContent,
          timestamp: Date.now() / 1000,
        };
        return updated;
      });

      if (!activeSessionId) {
        setActiveSessionId(result.session_id);
        // Refresh session list
        eConversations.list().then(setSessions).catch(() => {});
      }
      setSelectedFileIds([]);
    } catch (err) {
      setMessages((prev) => prev.slice(0, -1)); // remove pending
      setError(err instanceof Error ? err.message : "发送失败");
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* ── 左侧：会话列表 ── */}
      <div className="w-56 shrink-0 flex flex-col gap-2">
        <Button variant="outline" size="sm" className="gap-1.5 w-full" onClick={newChat}>
          <Plus className="h-3.5 w-3.5" /> 新对话
        </Button>
        <div className="flex-1 overflow-y-auto space-y-1 min-h-0">
          {sessions.length === 0 && (
            <p className="text-[0.7rem] text-muted-foreground text-center pt-6">暂无会话记录</p>
          )}
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => loadMessages(s.id)}
              className={`w-full text-left rounded-md px-2.5 py-2 text-xs transition-colors flex items-start gap-1.5 ${
                s.id === activeSessionId
                  ? "bg-foreground/10 text-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-foreground/5"
              }`}
            >
              <MessageSquare className="h-3 w-3 mt-0.5 shrink-0" />
              <span className="truncate">{s.title || "新对话"}</span>
              <ChevronRight className="h-3 w-3 ml-auto shrink-0 opacity-40" />
            </button>
          ))}
        </div>
      </div>

      {/* ── 右侧：对话区域 ── */}
      <Card className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto p-4 min-h-0">
          {messages.length === 0 && !sending && (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-2">
              <MessageSquare className="h-10 w-10 opacity-20" />
              <p className="text-sm">开始一段新对话</p>
              <p className="text-xs opacity-60">你好，{user?.username || user?.email}！有什么我可以帮你的吗？</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <MessageBubble key={i} msg={msg} />
          ))}
          <div ref={bottomRef} />
        </div>

        {/* 已选文件标签 */}
        {selectedFileIds.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-4 pt-2 border-t border-border">
            {selectedFileIds.map((id) => {
              const f = userFiles.find((u) => u.id === id);
              return (
                <span
                  key={id}
                  className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs"
                >
                  <Paperclip className="h-3 w-3" />
                  {f?.filename ?? id}
                  <button onClick={() => toggleFile(id)} className="ml-0.5 opacity-60 hover:opacity-100">
                    <X className="h-3 w-3" />
                  </button>
                </span>
              );
            })}
          </div>
        )}

        {/* 错误提示 */}
        {error && (
          <p className="text-xs text-destructive px-4 py-1">{error}</p>
        )}

        {/* 输入区 */}
        <div className="p-3 border-t border-border flex gap-2 items-end relative">
          {/* 文件选择弹窗 */}
          {showFilePicker && (
            <div className="absolute bottom-full left-3 mb-1 w-72 max-h-60 overflow-y-auto bg-background border border-border rounded-lg shadow-lg z-10 p-2">
              <p className="text-[0.65rem] font-display tracking-widest uppercase text-muted-foreground mb-2 px-1">
                选择文件附加到对话
              </p>
              {userFiles.length === 0 && (
                <p className="text-xs text-muted-foreground px-1">暂无上传文件，请先去「文件空间」上传</p>
              )}
              {userFiles.map((f) => (
                <label
                  key={f.id}
                  className="flex items-center gap-2 rounded px-2 py-1.5 cursor-pointer hover:bg-muted text-sm"
                >
                  <input
                    type="checkbox"
                    checked={selectedFileIds.includes(f.id)}
                    onChange={() => toggleFile(f.id)}
                    className="rounded"
                  />
                  <span className="truncate flex-1">{f.filename}</span>
                  <span className="text-[0.65rem] text-muted-foreground shrink-0">
                    {fmtSize(f.size_bytes)}
                  </span>
                </label>
              ))}
              <div className="border-t border-border mt-2 pt-2 flex justify-end">
                <Button size="sm" variant="outline" onClick={() => setShowFilePicker(false)}>
                  确认
                </Button>
              </div>
            </div>
          )}

          <Button
            variant="outline"
            size="sm"
            className={`shrink-0 ${selectedFileIds.length > 0 ? "text-foreground" : "text-muted-foreground"}`}
            onClick={() => setShowFilePicker((v) => !v)}
            title="选择文件"
          >
            <Paperclip className="h-4 w-4" />
            {selectedFileIds.length > 0 && (
              <span className="ml-1 text-xs">{selectedFileIds.length}</span>
            )}
          </Button>

          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息… Enter 发送，Shift+Enter 换行"
            rows={1}
            className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring min-h-[36px] max-h-[120px] overflow-y-auto"
            style={{ height: "auto" }}
            onInput={(e) => {
              const t = e.currentTarget;
              t.style.height = "auto";
              t.style.height = Math.min(t.scrollHeight, 120) + "px";
            }}
          />

          <Button
            size="sm"
            onClick={sendMessage}
            disabled={!input.trim() || sending}
            className="shrink-0"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </Card>
    </div>
  );
}
