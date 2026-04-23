/** Enterprise multi-user API client — calls /api/v1/... on the same origin. */

const BASE = "/api/v1";
const TOKEN_KEY = "hermes_enterprise_token";
const REFRESH_TOKEN_KEY = "hermes_enterprise_refresh_token";
const TOKEN_EXPIRY_KEY = "hermes_enterprise_token_expiry";

// ── Token helpers ─────────────────────────────────────────────────────────────

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(TOKEN_EXPIRY_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setRefreshToken(token: string): void {
  localStorage.setItem(REFRESH_TOKEN_KEY, token);
}

export function setTokenExpiry(expiryMinutes: number): void {
  const expiryTime = Date.now() + expiryMinutes * 60 * 1000;
  localStorage.setItem(TOKEN_EXPIRY_KEY, String(expiryTime));
}

export function isTokenExpiring(thresholdMinutes: number = 10): boolean {
  const expiryStr = localStorage.getItem(TOKEN_EXPIRY_KEY);
  if (!expiryStr) return false;
  const expiryTime = parseInt(expiryStr, 10);
  const threshold = thresholdMinutes * 60 * 1000;
  return Date.now() > expiryTime - threshold;
}

// ── Token refresh ─────────────────────────────────────────────────────────────

let refreshPromise: Promise<boolean> | null = null;

async function doRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) {
      // Don't clear tokens here - let the 401 handler or AuthContext decide
      return false;
    }

    const data = await res.json();
    setToken(data.access_token);
    setRefreshToken(data.refresh_token);
    setTokenExpiry(60); // ACCESS_TOKEN_EXPIRE_MINUTES = 60
    return true;
  } catch {
    // Don't clear tokens on network error - might be transient
    return false;
  }
}

async function ensureValidToken(): Promise<boolean> {
  // If no token, nothing to refresh
  if (!getToken()) return false;

  // If refresh is already in progress, wait for it
  if (refreshPromise) {
    return refreshPromise;
  }

  // Check if token is expiring soon
  if (isTokenExpiring(10)) {
    refreshPromise = doRefreshToken();
    const result = await refreshPromise;
    refreshPromise = null;
    return result;
  }

  return true;
}

// ── Core fetch ────────────────────────────────────────────────────────────────

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  // Only check token expiry if we have a stored expiry time
  // (users who logged in before we added this feature won't have it)
  const expiryStr = localStorage.getItem(TOKEN_EXPIRY_KEY);
  if (expiryStr && isTokenExpiring(10)) {
    await ensureValidToken();
  }

  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  // On 401, try to refresh token and retry once
  if (res.status === 401) {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      const refreshed = await doRefreshToken();
      if (refreshed) {
        // Retry with new token
        const newHeaders = new Headers(init.headers);
        const newToken = getToken();
        if (newToken) newHeaders.set("Authorization", `Bearer ${newToken}`);
        if (!newHeaders.has("Content-Type") && !(init.body instanceof FormData)) {
          newHeaders.set("Content-Type", "application/json");
        }
        const retryRes = await fetch(`${BASE}${path}`, { ...init, headers: newHeaders });
        if (!retryRes.ok) {
          // Retry failed - only clear tokens here
          clearToken();
          const text = await retryRes.text().catch(() => retryRes.statusText);
          throw new Error(`${retryRes.status}: ${text}`);
        }
        if (retryRes.status === 204) return undefined as unknown as T;
        return retryRes.json();
      }
    }
    // No refresh token or refresh failed - only clear here
    clearToken();
    throw new Error(`401: Unauthorized`);
  }

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

  updateTitle: (sessionId: string, title: string) =>
    req<{ ok: boolean; title: string }>(`/conversations/${sessionId}/title`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  /** Send a message with streaming SSE response.
   * @param onChunk - Called for each 'delta' event (text chunk)
   * @param stream - Enable streaming (default true). When false, waits for complete response.
   */
  send: async (
    message: string,
    sessionId: string | null,
    fileIds: string[],
    skillId: string | null,
    onChunk?: (chunk: string) => void,
    stream: boolean = true,
  ): Promise<{ content: string; session_id: string }> => {
    const token = getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    console.log("[eConversations.send] Sending message:", { message, sessionId, fileIds, skillId, stream });

    const res = await fetch(`${BASE}/conversations/send`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        message,
        session_id: sessionId,
        file_ids: fileIds,
        skill_id: skillId,
        stream,
      }),
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

export interface SkillFileInfo {
  path: string;
  size: number;
  is_dir: boolean;
}

export interface SkillZipUploadResult extends SkillSummary {
  files: string[];
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

  // ── Zip upload API ────────────────────────────────────────────────────────────
  uploadZip: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<SkillZipUploadResult>("/skills/upload-zip", { method: "POST", body: fd });
  },

  listFiles: (id: string) =>
    req<SkillFileInfo[]>(`/skills/${id}/files`),

  getFile: async (id: string, path: string): Promise<string> => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${BASE}/skills/${id}/files/${path}`, { headers });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`${res.status}: ${text}`);
    }
    return res.text();
  },

  downloadZip: async (id: string, name: string): Promise<void> => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${BASE}/skills/${id}/download`, { headers });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`${res.status}: ${text}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  },
};
