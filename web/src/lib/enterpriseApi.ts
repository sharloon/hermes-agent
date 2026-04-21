/** Enterprise multi-user API client — calls /api/v1/... on the same origin. */

const BASE = "/api/v1";
const TOKEN_KEY = "hermes_enterprise_token";

// ── Token helpers ─────────────────────────────────────────────────────────────

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ── Core fetch ────────────────────────────────────────────────────────────────

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserProfile {
  id: string;
  email: string;
  username: string | null;
  um_id: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: number;
}

export const eAuth = {
  register: (email: string, password: string, username?: string) =>
    req<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, username }),
    }),

  login: (email: string, password: string) => {
    const body = new URLSearchParams({ username: email, password });
    return req<TokenResponse>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });
  },

  me: () => req<UserProfile>("/users/me"),
};

// ── Files ─────────────────────────────────────────────────────────────────────

export interface FileInfo {
  id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  uploaded_at: number;
}

export const eFiles = {
  list: () => req<FileInfo[]>("/files"),

  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<FileInfo>("/files", { method: "POST", body: fd });
  },

  delete: (id: string) => req<void>(`/files/${id}`, { method: "DELETE" }),
};

// ── Conversations ─────────────────────────────────────────────────────────────

export interface SessionSummary {
  id: string;
  title: string | null;
  started_at: number;
  message_count: number;
}

export interface MessageItem {
  role: string;
  content: string | null;
  timestamp: number;
}

export const eConversations = {
  list: () => req<SessionSummary[]>("/conversations"),

  messages: (sessionId: string) =>
    req<MessageItem[]>(`/conversations/${sessionId}/messages`),

  /** Send a message and receive full response (non-streaming). */
  send: async (
    message: string,
    sessionId: string | null,
    fileIds: string[],
    skillId: string | null,
    onChunk?: (chunk: string) => void,
  ): Promise<{ content: string; session_id: string }> => {
    const token = getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    console.log("[eConversations.send] Sending message:", { message, sessionId, fileIds, skillId });

    const res = await fetch(`${BASE}/conversations/send`, {
      method: "POST",
      headers,
      body: JSON.stringify({ message, session_id: sessionId, file_ids: fileIds, skill_id: skillId }),
    });

    console.log("[eConversations.send] Response status:", res.status);

    if (!res.ok) {
      const errorText = await res.text();
      console.error("[eConversations.send] Error response:", errorText);
      throw new Error(`${res.status}: ${errorText}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response body");

    let result = { content: "", session_id: sessionId ?? "" };
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      console.log("[eConversations.send] Received chunk:", buffer);

      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // Keep incomplete line in buffer

      for (const line of lines) {
        if (!line.trim()) continue;
        if (!line.startsWith("data: ")) {
          console.warn("[eConversations.send] Unexpected line format:", line);
          continue;
        }
        try {
          const jsonStr = line.slice(6);
          console.log("[eConversations.send] Parsing JSON:", jsonStr);
          const ev = JSON.parse(jsonStr);
          console.log("[eConversations.send] Parsed event:", ev);

          if (ev.type === "delta" && onChunk) onChunk(ev.content);
          if (ev.type === "done") {
            result = { content: ev.content, session_id: ev.session_id };
            console.log("[eConversations.send] Done event received:", result);
          }
          if (ev.type === "error") throw new Error(ev.detail);
        } catch (e) {
          console.error("[eConversations.send] Failed to parse line:", line, e);
        }
      }
    }

    console.log("[eConversations.send] Final result:", result);
    return result;
  },
};

// ── Skills ────────────────────────────────────────────────────────────────────

export interface SkillSummary {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  visibility: "private" | "public";
  status: "draft" | "published";
  created_at: number;
  updated_at: number;
}

export interface SkillDetail extends SkillSummary {
  skill_content: string;
  published_at: number | null;
}

export interface PublicSkillInfo {
  name: string;
  description: string | null;
  category: string | null;
  source: "builtin" | "user_published";
  id: string | null;
  owner_id: string | null;
  can_remove: boolean;
}

export interface SelectableSkill extends SkillDetail {
  source: "builtin" | "own" | "public";
}

export const eSkills = {
  listMine: () => req<SkillSummary[]>("/skills"),
  listPublic: () => req<SkillSummary[]>("/skills?visibility=public"),
  listAllPublic: () => req<PublicSkillInfo[]>("/skills/all-public"),
  listSelectable: () => req<SelectableSkill[]>("/skills/selectable"),
  get: (id: string) => req<SkillDetail>(`/skills/${id}`),

  create: (name: string, description: string, skill_content: string) =>
    req<SkillDetail>("/skills", {
      method: "POST",
      body: JSON.stringify({ name, description, skill_content }),
    }),

  update: (id: string, fields: Partial<{ name: string; description: string; skill_content: string }>) =>
    req<SkillDetail>(`/skills/${id}`, {
      method: "PUT",
      body: JSON.stringify(fields),
    }),

  delete: (id: string) => req<void>(`/skills/${id}`, { method: "DELETE" }),

  publish: (id: string) =>
    req<SkillDetail>(`/skills/${id}/publish`, { method: "POST" }),

  unpublish: (id: string) =>
    req<SkillDetail>(`/skills/${id}/unpublish`, { method: "POST" }),

  adminRemove: (id: string) =>
    req<{ ok: boolean; skill_id: string }>(`/skills/${id}/admin-remove`, { method: "DELETE" }),
};
