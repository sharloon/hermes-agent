import { useState, useEffect, useRef, useCallback } from "react";
import { Send, Plus, Paperclip, X, ChevronDown, Sparkles, Loader2, Bot, User, Package, Pencil, Square, Trash2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { eConversations, eFiles, eSkills } from "@/lib/enterpriseApi";
import type { SessionSummary, MessageItem, FileInfo, SelectableSkill } from "@/lib/enterpriseApi";
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
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div className={`flex items-start gap-3 max-w-[80%] ${isUser ? "flex-row-reverse" : ""}`}>
        {/* Avatar */}
        <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
          isUser ? "bg-[#F97316]" : "bg-[#21262D]"
        }`}>
          {isUser ? <User className="h-4 w-4 text-white" /> : <Bot className="h-4 w-4 text-gray-400" />}
        </div>
        {/* Message content */}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap break-words ${
            isUser
              ? "bg-[#F97316] text-white"
              : "bg-[#161B22] text-gray-200 border border-[#334155]"
          }`}
        >
          {msg.pending ? (
            <span className="flex items-center gap-2 text-gray-400">
              <Loader2 className="h-4 w-4 animate-spin" /> 思考中…
            </span>
          ) : (
            msg.content || ""
          )}
          {!msg.pending && (
            <div className={`text-[0.65rem] mt-2 opacity-60 ${isUser ? "text-white/60" : "text-gray-500"}`}>
              {fmtTime(msg.timestamp)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Skill selector dropdown ───────────────────────────────────────────────────

function SkillSelector({
  skills,
  selectedSkill,
  onSelect,
  isOpen,
  onToggle,
}: {
  skills: SelectableSkill[];
  selectedSkill: SelectableSkill | null;
  onSelect: (skill: SelectableSkill | null) => void;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const [searchQuery, setSearchQuery] = useState("");

  // Clear search when dropdown closes
  useEffect(() => {
    if (!isOpen) setSearchQuery("");
  }, [isOpen]);

  // Filter skills by search query
  const filteredSkills = skills.filter(s =>
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (s.description && s.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  // Group filtered skills by source, with own skills first
  const ownSkills = filteredSkills.filter(s => s.source === "own");
  const builtinSkills = filteredSkills.filter(s => s.source === "builtin");
  const publicSkills = filteredSkills.filter(s => s.source === "public");

  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${
          selectedSkill
            ? "bg-[#F97316]/20 border-[#F97316] text-[#F97316]"
            : "bg-[#21262D] border-[#334155] text-gray-400 hover:border-gray-500 hover:text-gray-300"
        }`}
      >
        <Sparkles className="h-4 w-4" />
        <span className="text-sm">{selectedSkill ? selectedSkill.name : "选择技能"}</span>
        <ChevronDown className="h-3 w-3" />
      </button>

      {isOpen && (
        <div className="absolute bottom-full left-0 mb-2 w-72 max-h-64 overflow-hidden bg-[#161B22] border border-[#334155] rounded-xl shadow-xl z-20">
          {/* Search input */}
          <div className="px-3 py-2 border-b border-[#334155]">
            <input
              type="text"
              placeholder="搜索技能..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#21262D] border border-[#334155] rounded-lg px-3 py-1.5 text-sm text-gray-200 placeholder:text-gray-500 focus:outline-none focus:border-[#F97316]"
              autoFocus
            />
          </div>

          {/* Skills list */}
          <div className="max-h-48 overflow-y-auto">
            {/* Clear selection option */}
            <button
              onClick={() => { onSelect(null); onToggle(); }}
              className="w-full text-left px-3 py-2 text-sm text-gray-400 hover:bg-[#21262D] hover:text-gray-200"
            >
              不使用技能
            </button>

            {/* Own skills - shown first */}
            {ownSkills.length > 0 && (
              <div className="border-t border-[#334155]">
                <div className="px-3 py-1.5 text-xs text-[#F97316] flex items-center gap-1">
                  <User className="h-3 w-3" /> 我的技能
                </div>
                {ownSkills.map((skill) => (
                  <button
                    key={skill.id}
                    onClick={() => { onSelect(skill); onToggle(); }}
                    className={`w-full text-left px-3 py-2 hover:bg-[#21262D] ${
                      selectedSkill?.id === skill.id
                        ? "bg-[#F97316]/20 text-[#F97316]"
                        : "text-gray-300 hover:text-gray-100"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-3.5 w-3.5 shrink-0" />
                      <span className="text-sm font-medium truncate">{skill.name}</span>
                      <span className="text-xs text-gray-500">{skill.visibility === "public" ? "公开" : "私有"}</span>
                    </div>
                    {skill.description && (
                      <p className="text-xs text-gray-500 mt-0.5 truncate pl-5">{skill.description}</p>
                    )}
                  </button>
                ))}
              </div>
            )}

            {/* Builtin skills */}
            {builtinSkills.length > 0 && (
              <div className="border-t border-[#334155]">
                <div className="px-3 py-1.5 text-xs text-gray-500 flex items-center gap-1">
                  <Package className="h-3 w-3" /> 内置技能
                </div>
                {builtinSkills.map((skill) => (
                  <button
                    key={skill.id}
                    onClick={() => { onSelect(skill); onToggle(); }}
                    className={`w-full text-left px-3 py-2 hover:bg-[#21262D] ${
                      selectedSkill?.id === skill.id
                        ? "bg-[#F97316]/20 text-[#F97316]"
                        : "text-gray-300 hover:text-gray-100"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-3.5 w-3.5 shrink-0" />
                      <span className="text-sm font-medium truncate">{skill.name}</span>
                    </div>
                    {skill.description && (
                      <p className="text-xs text-gray-500 mt-0.5 truncate pl-5">{skill.description}</p>
                    )}
                  </button>
                ))}
              </div>
            )}

            {/* Public skills from others */}
            {publicSkills.length > 0 && (
              <div className="border-t border-[#334155]">
                <div className="px-3 py-1.5 text-xs text-gray-500 flex items-center gap-1">
                  <Package className="h-3 w-3" /> 公共技能
                </div>
                {publicSkills.map((skill) => (
                  <button
                    key={skill.id}
                    onClick={() => { onSelect(skill); onToggle(); }}
                    className={`w-full text-left px-3 py-2 hover:bg-[#21262D] ${
                      selectedSkill?.id === skill.id
                        ? "bg-[#F97316]/20 text-[#F97316]"
                        : "text-gray-300 hover:text-gray-100"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-3.5 w-3.5 shrink-0" />
                      <span className="text-sm font-medium truncate">{skill.name}</span>
                    </div>
                    {skill.description && (
                      <p className="text-xs text-gray-500 mt-0.5 truncate pl-5">{skill.description}</p>
                    )}
                  </button>
                ))}
              </div>
            )}

            {/* Empty state */}
            {filteredSkills.length === 0 && searchQuery && (
              <p className="text-xs text-gray-500 px-3 py-4 text-center">未找到匹配的技能</p>
            )}
            {skills.length === 0 && !searchQuery && (
              <p className="text-xs text-gray-500 px-3 py-4 text-center">暂无可用技能</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── File selector dropdown ────────────────────────────────────────────────────

function FileSelector({
  files,
  selectedIds,
  onToggleId,
  isOpen,
  onToggle,
}: {
  files: FileInfo[];
  selectedIds: string[];
  onToggleId: (id: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${
          selectedIds.length > 0
            ? "bg-[#F97316]/20 border-[#F97316] text-[#F97316]"
            : "bg-[#21262D] border-[#334155] text-gray-400 hover:border-gray-500 hover:text-gray-300"
        }`}
      >
        <Paperclip className="h-4 w-4" />
        <span className="text-sm">{selectedIds.length > 0 ? `${selectedIds.length} 文件` : "附件"}</span>
      </button>

      {isOpen && (
        <div className="absolute bottom-full left-0 mb-2 w-72 max-h-60 overflow-y-auto bg-[#161B22] border border-[#334155] rounded-xl shadow-xl z-20 p-3">
          <p className="text-xs text-gray-500 mb-2">选择要附加的文件</p>
          {files.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-4">暂无上传文件</p>
          )}
          {files.map((f) => (
            <label
              key={f.id}
              className={`flex items-center gap-2 rounded-lg px-2 py-2 cursor-pointer ${
                selectedIds.includes(f.id)
                  ? "bg-[#F97316]/20"
                  : "hover:bg-[#21262D]"
              }`}
            >
              <input
                type="checkbox"
                checked={selectedIds.includes(f.id)}
                onChange={() => onToggleId(f.id)}
                className="rounded border-[#334155] text-[#F97316] focus:ring-[#F97316]"
              />
              <span className="text-sm text-gray-300 truncate flex-1">{f.filename}</span>
              <span className="text-xs text-gray-500 shrink-0">{fmtSize(f.size_bytes)}</span>
            </label>
          ))}
          <div className="border-t border-[#334155] mt-2 pt-2 flex justify-end">
            <Button size="sm" variant="outline" onClick={onToggle} className="text-xs">
              确认
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function ChatPage() {
  const { user } = useAuth();

  // Persist activeSessionId to localStorage
  const ACTIVE_SESSION_KEY = "hermes_chat_active_session";

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionIdState] = useState<string | null>(() => {
    // Restore from localStorage on initial load
    return localStorage.getItem(ACTIVE_SESSION_KEY);
  });
  const [messages, setMessages] = useState<(MessageItem & { pending?: boolean })[]>([]);
  const [userFiles, setUserFiles] = useState<FileInfo[]>([]);
  const [selectableSkills, setSelectableSkills] = useState<SelectableSkill[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<SelectableSkill | null>(null);
  const [showFilePicker, setShowFilePicker] = useState(false);
  const [showSkillPicker, setShowSkillPicker] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSidebar, setShowSidebar] = useState(true);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Wrapper for setActiveSessionId that also persists to localStorage
  const setActiveSessionId = useCallback((id: string | null) => {
    setActiveSessionIdState(id);
    if (id) {
      localStorage.setItem(ACTIVE_SESSION_KEY, id);
    } else {
      localStorage.removeItem(ACTIVE_SESSION_KEY);
    }
  }, []);

  // Load sessions, files and skills on mount
  useEffect(() => {
    eConversations.list().then(setSessions).catch(() => {});
    eFiles.list().then(setUserFiles).catch(() => {});
    eSkills.listSelectable().then(setSelectableSkills).catch(() => {});
  }, []);

  // Auto-load messages for persisted activeSessionId on mount
  useEffect(() => {
    if (activeSessionId) {
      eConversations.messages(activeSessionId)
        .then((msgs) => {
          setMessages(msgs.filter((m) => m.role === "user" || m.role === "assistant"));
        })
        .catch(() => {
          // Session may not exist or belong to user, clear it
          setActiveSessionId(null);
        });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadMessages = useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setMessages([]);
    setSelectedSkill(null);
    setSelectedFileIds([]);
    try {
      const msgs = await eConversations.messages(sessionId);
      setMessages(msgs.filter((m) => m.role === "user" || m.role === "assistant"));
    } catch {
      setError("加载消息失败");
    }
  }, [setActiveSessionId]);

  const newChat = () => {
    // Generate session_id upfront so first message has it
    const newSessionId = crypto.randomUUID();
    setActiveSessionId(newSessionId);
    setMessages([]);
    setSelectedSkill(null);
    setSelectedFileIds([]);
  };

  const startEditTitle = (sessionId: string, currentTitle: string) => {
    setEditingSessionId(sessionId);
    setEditingTitle(currentTitle || "");
  };

  const cancelEditTitle = () => {
    setEditingSessionId(null);
    setEditingTitle("");
  };

  const saveTitle = async (sessionId: string) => {
    if (!editingTitle.trim()) return;
    try {
      await eConversations.updateTitle(sessionId, editingTitle.trim());
      // Update local state
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId ? { ...s, title: editingTitle.trim() } : s
        )
      );
      cancelEditTitle();
    } catch (err) {
      setError(err instanceof Error ? err.message : "修改标题失败");
    }
  };

  const deleteSession = async (sessionId: string) => {
    try {
      await eConversations.delete(sessionId);
      // Remove from local state
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      // If deleted session was active, clear it
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        setMessages([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  };

  const toggleFile = (id: string) => {
    setSelectedFileIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const stopGeneration = async () => {
    if (!activeSessionId) return;
    try {
      await eConversations.stop(activeSessionId);
      setSending(false);
      // Update pending message to show it was stopped
      setMessages((prev) => {
        const updated = [...prev];
        if (updated.length > 0 && updated[updated.length - 1].pending) {
          updated[updated.length - 1] = {
            role: "assistant",
            content: "[已停止]",
            timestamp: Date.now() / 1000,
            pending: false,
          };
        }
        return updated;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "停止失败");
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setError(null);
    setSending(true);
    setShowFilePicker(false);
    setShowSkillPicker(false);

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
        selectedSkill?.id || null,
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

      // Update session_id from server response if it was null
      if (!activeSessionId && result.session_id) {
        setActiveSessionId(result.session_id);
      }

      // Refresh session list to show the new/updated session
      eConversations.list().then(setSessions).catch(() => {});
      // Keep skill/file selection for next message
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
    <div className="flex h-[calc(100vh-3rem)] gap-0">
      {/* ── 左侧：会话列表（可折叠） ── */}
      {showSidebar && (
        <div className="w-64 shrink-0 flex flex-col bg-[#161B22] border-r border-[#334155]">
          {/* New chat button */}
          <div className="p-3">
            <button
              onClick={newChat}
              className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg bg-[#21262D] border border-[#334155] text-gray-300 hover:bg-[#30363D] hover:text-white transition-colors"
            >
              <Plus className="h-4 w-4" />
              <span className="text-sm font-medium">新建对话</span>
            </button>
          </div>

          {/* Session list */}
          <div className="flex-1 overflow-y-auto px-2 pb-3">
            {sessions.length === 0 && (
              <p className="text-xs text-gray-500 text-center pt-8">暂无历史对话</p>
            )}
            {sessions.map((s) => (
              <div
                key={s.id}
                className={`group w-full rounded-lg px-3 py-2.5 text-sm transition-colors mb-1 flex items-center gap-2 ${
                  s.id === activeSessionId
                    ? "bg-[#F97316]/20 text-[#F97316] border border-[#F97316]/30"
                    : "text-gray-400 hover:bg-[#21262D] hover:text-gray-200"
                }`}
              >
                {editingSessionId === s.id ? (
                  <>
                    <input
                      type="text"
                      value={editingTitle}
                      onChange={(e) => setEditingTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveTitle(s.id);
                        if (e.key === "Escape") cancelEditTitle();
                      }}
                      className="flex-1 bg-transparent border border-[#F97316] rounded px-1 py-0.5 text-sm focus:outline-none"
                      autoFocus
                    />
                    <button
                      onClick={() => saveTitle(s.id)}
                      className="text-xs text-[#F97316] hover:text-white"
                    >
                      保存
                    </button>
                    <button onClick={cancelEditTitle} className="text-xs text-gray-400 hover:text-white">
                      取消
                    </button>
                  </>
                ) : (
                  <>
                    <span
                      className="truncate flex-1 cursor-pointer"
                      onClick={() => loadMessages(s.id)}
                    >
                      {s.title || "新对话"}
                    </span>
                    <button
                      onClick={() => startEditTitle(s.id, s.title || "")}
                      className="p-1 rounded hover:bg-[#30363D] transition-all group-hover:opacity-100 opacity-0"
                    >
                      <Pencil className="h-3 w-3 text-gray-400 hover:text-gray-200" />
                    </button>
                    <button
                      onClick={() => deleteSession(s.id)}
                      className="p-1 rounded hover:bg-red-500/20 transition-all group-hover:opacity-100 opacity-0"
                    >
                      <Trash2 className="h-3 w-3 text-gray-400 hover:text-red-400" />
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 右侧：对话主区域 ── */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#0D1117]">
        {/* Header with sidebar toggle */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#334155]">
          <button
            onClick={() => setShowSidebar(!showSidebar)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-200 hover:bg-[#21262D] transition-colors"
          >
            <ChevronDown className={`h-4 w-4 transition-transform ${showSidebar ? "-rotate-90" : "rotate-90"}`} />
          </button>
          <div className="flex items-center gap-2">
            {selectedSkill && (
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#F97316]/20 text-[#F97316] text-xs">
                <Sparkles className="h-3 w-3" />
                {selectedSkill.name}
                <button onClick={() => setSelectedSkill(null)} className="ml-0.5 hover:text-white">
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            {selectedFileIds.length > 0 && (
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#21262D] text-gray-300 text-xs">
                <Paperclip className="h-3 w-3" />
                {selectedFileIds.length} 文件
              </span>
            )}
          </div>
        </div>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto px-4 py-6">
          {messages.length === 0 && !sending && (
            <div className="h-full flex flex-col items-center justify-center text-gray-400 gap-4">
              <div className="w-16 h-16 rounded-full bg-[#21262D] flex items-center justify-center">
                <Bot className="h-8 w-8 text-gray-500" />
              </div>
              <div className="text-center">
                <p className="text-lg text-gray-300 mb-2">你好，{user?.username || user?.email}</p>
                <p className="text-sm text-gray-500">有什么我可以帮你的吗？</p>
              </div>
              {/* Quick skill selection */}
              {selectableSkills.length > 0 && (
                <div className="mt-4 text-center">
                  <p className="text-xs text-gray-500 mb-2">选择一个技能快速开始</p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    {selectableSkills.slice(0, 4).map((skill) => (
                      <button
                        key={skill.id}
                        onClick={() => setSelectedSkill(skill)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#21262D] text-gray-400 hover:bg-[#30363D] hover:text-gray-200 text-xs transition-colors"
                      >
                        <Sparkles className="h-3 w-3" />
                        {skill.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          {messages.map((msg, i) => (
            <MessageBubble key={i} msg={msg} />
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Error */}
        {error && (
          <p className="text-xs text-red-400 px-4 py-2 bg-red-500/10">{error}</p>
        )}

        {/* Input area */}
        <div className="px-4 py-3 border-t border-[#334155]">
          <div className="max-w-3xl mx-auto">
            {/* Selected files preview */}
            {selectedFileIds.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {selectedFileIds.map((id) => {
                  const f = userFiles.find((u) => u.id === id);
                  return (
                    <span
                      key={id}
                      className="inline-flex items-center gap-1 rounded-full bg-[#21262D] px-2 py-1 text-xs text-gray-400"
                    >
                      <Paperclip className="h-3 w-3" />
                      {f?.filename ?? id}
                      <button onClick={() => toggleFile(id)} className="ml-0.5 hover:text-white">
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  );
                })}
              </div>
            )}

            {/* Input box */}
            <div className="relative flex items-end gap-2 p-3 rounded-2xl bg-[#161B22] border border-[#334155]">
              {/* Attachment buttons */}
              <div className="flex items-center gap-2 shrink-0">
                <FileSelector
                  files={userFiles}
                  selectedIds={selectedFileIds}
                  onToggleId={toggleFile}
                  isOpen={showFilePicker}
                  onToggle={() => { setShowFilePicker(!showFilePicker); setShowSkillPicker(false); }}
                />
                <SkillSelector
                  skills={selectableSkills}
                  selectedSkill={selectedSkill}
                  onSelect={setSelectedSkill}
                  isOpen={showSkillPicker}
                  onToggle={() => { setShowSkillPicker(!showSkillPicker); setShowFilePicker(false); }}
                />
              </div>

              {/* Textarea */}
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入消息，按 Enter 发送…"
                rows={1}
                className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-gray-200 placeholder:text-gray-500 focus:outline-none min-h-[36px] max-h-[120px] overflow-y-auto"
                style={{ height: "auto" }}
                onInput={(e) => {
                  const t = e.currentTarget;
                  t.style.height = "auto";
                  t.style.height = Math.min(t.scrollHeight, 120) + "px";
                }}
              />

              {/* Send/Stop button */}
              {sending ? (
                <button
                  onClick={stopGeneration}
                  className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center bg-red-500/80 text-white hover:bg-red-500 transition-colors"
                >
                  <Square className="h-4 w-4" />
                </button>
              ) : (
                <button
                  onClick={sendMessage}
                  disabled={!input.trim()}
                  className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
                    input.trim()
                      ? "bg-[#F97316] text-white hover:bg-[#ea580c]"
                      : "bg-[#21262D] text-gray-500"
                  }`}
                >
                  <Send className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Helper text */}
            <p className="text-xs text-gray-500 text-center mt-2">
              {selectedSkill
                ? `当前使用技能: ${selectedSkill.name}`
                : "可选择技能或附加文件来增强对话"
              }
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}