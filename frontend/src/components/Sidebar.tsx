import { A, useNavigate } from "@solidjs/router";
import { createMemo, createSignal, For, Show } from "solid-js";

import { formatDateGroup } from "../lib/format";
import { chatList, loadChatList, removeChat, renameChat, searchQuery, setSearchQuery, showToast } from "../state";
import type { ChatSummary } from "../types";
import { IconDots, IconPencil, IconPlus, IconSearch, IconTrash } from "./Icons";
import { Menu } from "./Menu";

interface Group {
  label: string;
  chats: ChatSummary[];
}

export function Sidebar(props: { open: boolean; activeId: string | null; onNavigate: () => void }) {
  const navigate = useNavigate();
  const [menu, setMenu] = createSignal<{ chat: ChatSummary; x: number; y: number } | null>(null);
  let searchTimer: number | undefined;

  const onSearch = (value: string) => {
    setSearchQuery(value);
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => void loadChatList(), 180);
  };

  const groups = createMemo<Group[]>(() => {
    // Search results are already ranked by recency across all time; grouping them by day just
    // adds noise, so they stay in one flat list.
    if (searchQuery().trim()) return [{ label: "Results", chats: chatList.items }];
    const out: Group[] = [];
    for (const chat of chatList.items) {
      const label = formatDateGroup(chat.updated_at);
      const last = out[out.length - 1];
      if (last && last.label === label) last.chats.push(chat);
      else out.push({ label, chats: [chat] });
    }
    return out;
  });

  const rename = async (chat: ChatSummary) => {
    const title = window.prompt("Rename chat", chat.title);
    if (title === null || !title.trim()) return;
    await renameChat(chat.id, title.trim());
  };

  const remove = async (chat: ChatSummary) => {
    if (!window.confirm(`Delete “${chat.title}”? This can't be undone.`)) return;
    await removeChat(chat.id);
    showToast("Chat deleted");
    if (props.activeId === chat.id) navigate("/", { replace: true });
  };

  return (
    <aside class="sidebar" data-open={props.open}>
      <div class="sidebar__head">
        <A href="/" class="brand" onClick={props.onNavigate}>
          <img src="/icons/icon-192.png" alt="" />
          bottlechat
        </A>
        <button
          type="button"
          class="btn btn--ghost btn--icon"
          title="New chat"
          aria-label="New chat"
          onClick={() => {
            navigate("/");
            props.onNavigate();
          }}
        >
          <IconPlus />
        </button>
      </div>

      <div class="sidebar__search">
        <div class="search-field">
          <IconSearch />
          <input
            type="search"
            placeholder="Search chats"
            value={searchQuery()}
            aria-label="Search chats"
            onInput={(event) => onSearch(event.currentTarget.value)}
          />
        </div>
      </div>

      <nav class="sidebar__list" aria-label="Chat history">
        <Show
          when={chatList.items.length > 0}
          fallback={
            <p class="sidebar__empty">
              {chatList.loading ? "Loading…" : searchQuery().trim() ? "No chats match that search." : "No chats yet."}
            </p>
          }
        >
          <For each={groups()}>
            {(group) => (
              <>
                <div class="sidebar__group">{group.label}</div>
                <For each={group.chats}>
                  {(item) => (
                    <div class="chat-row" data-active={item.id === props.activeId}>
                      <A href={`/c/${item.id}`} class="chat-row__link" onClick={props.onNavigate}>
                        <span class="chat-row__title">{item.title}</span>
                        <Show when={item.snippet}>
                          <span class="chat-row__snippet" innerHTML={item.snippet ?? ""} />
                        </Show>
                      </A>
                      <button
                        type="button"
                        class="btn btn--ghost btn--icon chat-row__menu"
                        aria-label={`Actions for ${item.title}`}
                        onClick={(event) => {
                          const rect = event.currentTarget.getBoundingClientRect();
                          setMenu({ chat: item, x: rect.left - 40, y: rect.bottom + 4 });
                        }}
                      >
                        <IconDots size={15} />
                      </button>
                    </div>
                  )}
                </For>
              </>
            )}
          </For>
        </Show>
      </nav>

      <Show when={menu()}>
        {(active) => (
          <Menu x={active().x} y={active().y} onClose={() => setMenu(null)}>
            <button
              type="button"
              onClick={() => {
                setMenu(null);
                void rename(active().chat);
              }}
            >
              <IconPencil size={14} /> Rename
            </button>
            <button
              type="button"
              data-danger="true"
              onClick={() => {
                setMenu(null);
                void remove(active().chat);
              }}
            >
              <IconTrash size={14} /> Delete
            </button>
          </Menu>
        )}
      </Show>
    </aside>
  );
}
