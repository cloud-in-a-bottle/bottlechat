import type {
  Chat,
  ChatDetail,
  ChatSummary,
  Effort,
  SharedChat,
  ShareRef,
  StatusResponse,
  TurnResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (typeof body?.message === "string") return body.message;
  } catch {
    /* fall through to the status text */
  }
  return `${response.status} ${response.statusText}`;
}

export const api = {
  status: (refresh = false) => request<StatusResponse>(`/api/status${refresh ? "?refresh=true" : ""}`),

  listChats: (query?: string) =>
    request<{ chats: ChatSummary[] }>(`/api/chats${query ? `?q=${encodeURIComponent(query)}` : ""}`),

  createChat: (model: string | null, effort: Effort) =>
    request<Chat>("/api/chats", { method: "POST", body: JSON.stringify({ model, effort }) }),

  getChat: (chatId: string) => request<ChatDetail>(`/api/chats/${chatId}`),

  updateChat: (chatId: string, patch: { title?: string; model?: string; effort?: Effort }) =>
    request<Chat>(`/api/chats/${chatId}`, { method: "PATCH", body: JSON.stringify(patch) }),

  deleteChat: (chatId: string) => request<{ ok: boolean }>(`/api/chats/${chatId}`, { method: "DELETE" }),

  sendMessage: (chatId: string, content: string, model: string | null, effort: Effort) =>
    request<TurnResponse>(`/api/chats/${chatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, model, effort }),
    }),

  retry: (chatId: string, messageId: string, model: string | null, effort: Effort) =>
    request<TurnResponse["assistant_message"]>(`/api/chats/${chatId}/messages/${messageId}/retry`, {
      method: "POST",
      body: JSON.stringify({ model, effort }),
    }),

  stop: (chatId: string, messageId: string) =>
    request<{ ok: boolean }>(`/api/chats/${chatId}/messages/${messageId}/stop`, { method: "POST" }),

  createShare: (chatId: string) => request<ShareRef>(`/api/chats/${chatId}/share`, { method: "POST" }),

  revokeShare: (chatId: string) => request<{ ok: boolean }>(`/api/chats/${chatId}/share`, { method: "DELETE" }),

  sharedChat: (token: string) => request<SharedChat>(`/share/api/${encodeURIComponent(token)}`),
};

export interface StreamHandlers {
  onDelta: (kind: "content" | "reasoning", text: string) => void;
  onStatus: (status: string, error: string | null) => void;
  onTitle: (title: string) => void;
  onEnd: () => void;
}

/** Subscribe to a response as it is generated.  Returns a function that detaches this tab from
 *  the stream — the server keeps generating and persisting either way. */
export function streamMessage(chatId: string, messageId: string, handlers: StreamHandlers): () => void {
  const source = new EventSource(`/api/chats/${chatId}/messages/${messageId}/stream`);
  let closed = false;
  const close = () => {
    if (!closed) {
      closed = true;
      source.close();
    }
  };

  source.addEventListener("delta", (event) => {
    const payload = JSON.parse((event as MessageEvent).data) as { kind: "content" | "reasoning"; text: string };
    handlers.onDelta(payload.kind, payload.text);
  });
  source.addEventListener("status", (event) => {
    const payload = JSON.parse((event as MessageEvent).data) as { status: string; error: string | null };
    handlers.onStatus(payload.status, payload.error);
  });
  source.addEventListener("title", (event) => {
    handlers.onTitle((JSON.parse((event as MessageEvent).data) as { title: string }).title);
  });
  source.addEventListener("end", () => {
    close();
    handlers.onEnd();
  });
  source.addEventListener("error", () => {
    // EventSource reconnects on its own (resending Last-Event-ID, which the server honours), so
    // a transient drop needs no handling here.  A permanent failure lands in CLOSED.
    if (source.readyState === EventSource.CLOSED) {
      close();
      handlers.onEnd();
    }
  });

  return close;
}
