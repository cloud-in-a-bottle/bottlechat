import { batch, createSignal } from "solid-js";
import { createStore, produce, reconcile } from "solid-js/store";

import { api, streamMessage } from "./api";
import type { Chat, ChatSummary, Effort, Message, ShareRef, StatusResponse } from "./types";

export const [status, setStatus] = createSignal<StatusResponse | null>(null);
export const [statusError, setStatusError] = createSignal<string | null>(null);

export const [chatList, setChatList] = createStore<{ items: ChatSummary[]; loading: boolean }>({
  items: [],
  loading: true,
});

/** The active sidebar search.  Held here so background refreshes (e.g. after a response lands)
 *  re-run the same query instead of dropping the filter the user is looking at. */
export const [searchQuery, setSearchQuery] = createSignal("");

export const [chat, setChat] = createSignal<Chat | null>(null);
export const [share, setShare] = createSignal<ShareRef | null>(null);
export const [messages, setMessages] = createStore<Message[]>([]);
export const [chatError, setChatError] = createSignal<string | null>(null);
export const [chatLoading, setChatLoading] = createSignal(false);

export const [toast, setToast] = createSignal<string | null>(null);

/** The model/effort the composer will use.  Seeded from the open chat, else the saved defaults. */
export const [model, setModel] = createSignal<string | null>(null);
export const [effort, setEffort] = createSignal<Effort>("off");

let detachStream: (() => void) | null = null;
let toastTimer: number | undefined;

export function showToast(text: string): void {
  window.clearTimeout(toastTimer);
  setToast(text);
  toastTimer = window.setTimeout(() => setToast(null), 2600);
}

export function isStreaming(): boolean {
  return messages.some((m) => m.status === "streaming");
}

export async function loadStatus(refresh = false): Promise<void> {
  try {
    const next = await api.status(refresh);
    batch(() => {
      setStatus(next);
      setStatusError(null);
      if (model() === null) setModel(next.defaults.model);
      if (!chat()) setEffort(next.defaults.effort);
    });
  } catch (error) {
    setStatusError(error instanceof Error ? error.message : String(error));
  }
}

export async function loadChatList(): Promise<void> {
  setChatList("loading", true);
  const query = searchQuery().trim() || undefined;
  try {
    const { chats } = await api.listChats(query);
    setChatList(reconcile({ items: chats, loading: false }, { key: "id" }));
  } catch {
    setChatList("loading", false);
  }
}

export function clearChat(): void {
  detachStream?.();
  detachStream = null;
  batch(() => {
    setChat(null);
    setShare(null);
    setMessages(reconcile([], { key: "id" }));
    setChatError(null);
  });
}

export async function openChat(chatId: string): Promise<void> {
  detachStream?.();
  detachStream = null;
  setChatLoading(true);
  try {
    const detail = await api.getChat(chatId);
    batch(() => {
      setChat(detail.chat);
      setShare(detail.share);
      setMessages(reconcile(detail.messages, { key: "id" }));
      setChatError(null);
      setModel(detail.chat.model ?? status()?.defaults.model ?? null);
      setEffort(detail.chat.effort);
    });
    const live = detail.messages.find((m) => m.status === "streaming");
    if (live) attachStream(chatId, live.id);
  } catch (error) {
    batch(() => {
      setChat(null);
      setMessages(reconcile([], { key: "id" }));
      setChatError(error instanceof Error ? error.message : String(error));
    });
  } finally {
    setChatLoading(false);
  }
}

function messageIndex(messageId: string): number {
  return messages.findIndex((m) => m.id === messageId);
}

function attachStream(chatId: string, messageId: string): void {
  // The server replays the whole response from the start, so clear whatever was loaded from the
  // DB rather than trying to work out where the persisted prefix ends.
  const index = messageIndex(messageId);
  if (index >= 0) setMessages(index, produce((m) => ((m.content = ""), (m.reasoning = ""))));

  detachStream = streamMessage(chatId, messageId, {
    onDelta(kind, text) {
      const at = messageIndex(messageId);
      if (at < 0) return;
      setMessages(
        at,
        produce((m) => {
          if (kind === "content") m.content += text;
          else m.reasoning += text;
        }),
      );
    },
    onStatus(nextStatus, error) {
      const at = messageIndex(messageId);
      if (at < 0) return;
      setMessages(at, produce((m) => ((m.status = nextStatus as Message["status"]), (m.error = error))));
    },
    onTitle(title) {
      const current = chat();
      if (current && current.id === chatId) setChat({ ...current, title });
      const at = chatList.items.findIndex((c) => c.id === chatId);
      if (at >= 0) setChatList("items", at, "title", title);
    },
    onEnd() {
      detachStream = null;
      void loadChatList();
    },
  });
}

export async function ensureChat(): Promise<Chat> {
  const current = chat();
  if (current) return current;
  const created = await api.createChat(model(), effort());
  batch(() => {
    setChat(created);
    setMessages(reconcile([], { key: "id" }));
    setChatList("items", (items) => [{ id: created.id, title: created.title, updated_at: created.updated_at, snippet: null }, ...items]);
  });
  return created;
}

export async function send(content: string): Promise<void> {
  const current = chat();
  if (!current) throw new Error("no chat is open");
  const turn = await api.sendMessage(current.id, content, model(), effort());
  batch(() => {
    setMessages(produce((list) => list.push(turn.user_message, turn.assistant_message)));
  });
  attachStream(current.id, turn.assistant_message.id);
}

export async function stop(messageId: string): Promise<void> {
  const current = chat();
  if (!current) return;
  await api.stop(current.id, messageId);
}

export async function retry(messageId: string): Promise<void> {
  const current = chat();
  if (!current) return;
  detachStream?.();
  detachStream = null;
  const reset = await api.retry(current.id, messageId, model(), effort());
  const at = messageIndex(messageId);
  if (at >= 0) setMessages(at, reconcile(reset, { key: "id" }));
  attachStream(current.id, messageId);
}

export async function renameChat(chatId: string, title: string): Promise<void> {
  const updated = await api.updateChat(chatId, { title });
  const current = chat();
  if (current && current.id === chatId) setChat(updated);
  const at = chatList.items.findIndex((c) => c.id === chatId);
  if (at >= 0) setChatList("items", at, "title", updated.title);
}

export async function removeChat(chatId: string): Promise<void> {
  await api.deleteChat(chatId);
  setChatList("items", (items) => items.filter((c) => c.id !== chatId));
}

export async function toggleShare(enable: boolean): Promise<void> {
  const current = chat();
  if (!current) return;
  if (enable) {
    setShare(await api.createShare(current.id));
  } else {
    await api.revokeShare(current.id);
    setShare(null);
  }
}

export function applyModel(next: string): void {
  setModel(next);
  const current = chat();
  if (current) void api.updateChat(current.id, { model: next });
}

export function applyEffort(next: Effort): void {
  setEffort(next);
  const current = chat();
  if (current) void api.updateChat(current.id, { effort: next });
}
