import { useNavigate, useParams } from "@solidjs/router";
import { createEffect, createSignal, Show } from "solid-js";

import { Composer } from "../components/Composer";
import { IconMenu, IconShare } from "../components/Icons";
import { SetupScreen } from "../components/SetupScreen";
import { ShareDialog } from "../components/ShareDialog";
import { Thread } from "../components/Thread";
import {
  applyEffort,
  applyModel,
  chat,
  chatError,
  clearChat,
  effort,
  ensureChat,
  isStreaming,
  loadChatList,
  messages,
  model,
  openChat,
  retry,
  send,
  share,
  showToast,
  status,
  stop,
} from "../state";

export function ChatPage(props: { onOpenDrawer: () => void }) {
  const params = useParams<{ chatId?: string }>();
  const navigate = useNavigate();
  const [sharing, setSharing] = createSignal(false);

  createEffect(() => {
    const chatId = params.chatId;
    if (!chatId) {
      clearChat();
      return;
    }
    if (chat()?.id === chatId) return;
    void openChat(chatId);
  });

  const provider = () => status();
  const ready = () => provider()?.state === "ready";

  const onSend = async (text: string) => {
    try {
      const target = await ensureChat();
      if (params.chatId !== target.id) navigate(`/c/${target.id}`, { replace: !params.chatId });
      await send(text);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Could not send that message");
    }
  };

  const onStop = async (messageId: string) => {
    try {
      await stop(messageId);
    } catch {
      showToast("Could not stop the response");
    }
  };

  const onRetry = async (messageId: string) => {
    try {
      await retry(messageId);
      void loadChatList();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Could not retry");
    }
  };

  return (
    <main class="main">
      <header class="topbar">
        <button
          type="button"
          class="btn btn--ghost btn--icon drawer-toggle"
          aria-label="Open chat history"
          onClick={props.onOpenDrawer}
        >
          <IconMenu />
        </button>
        <span class="topbar__title">{chat()?.title ?? "New chat"}</span>
        <div class="topbar__controls">
          <Show when={chat() && messages.length > 0}>
            <button
              type="button"
              class="btn btn--ghost"
              onClick={() => setSharing(true)}
              title={share() ? "Shared — manage link" : "Create a share link"}
            >
              <IconShare size={15} /> {share() ? "Shared" : "Share"}
            </button>
          </Show>
        </div>
      </header>

      <Show when={chatError()}>
        <div class="centered">
          <div class="panel">
            <h1>That chat isn't here</h1>
            <p>{chatError()}</p>
            <div class="panel__actions">
              <button type="button" class="btn btn--primary" onClick={() => navigate("/", { replace: true })}>
                Start a new chat
              </button>
            </div>
          </div>
        </div>
      </Show>

      <Show when={!chatError() && provider() && !ready()}>
        <SetupScreen status={provider()!} />
      </Show>

      <Show when={!chatError() && ready()}>
        <Show
          when={messages.length > 0}
          fallback={
            <div class="centered">
              <div class="hero">
                <img src="/icons/icon-192.png" alt="" />
                <h1>What's on your mind?</h1>
                <p>Chats are saved here and stay private to you unless you share them.</p>
              </div>
            </div>
          }
        >
          <Thread messages={messages} onStop={(id) => void onStop(id)} onRetry={(id) => void onRetry(id)} />
        </Show>

        <Composer
          models={provider()?.models ?? []}
          model={model()}
          effort={effort()}
          streaming={isStreaming()}
          disabled={!model()}
          onModel={applyModel}
          onEffort={applyEffort}
          onSend={(text) => void onSend(text)}
          onStop={() => {
            const live = messages.find((m) => m.status === "streaming");
            if (live) void onStop(live.id);
          }}
        />
      </Show>

      <Show when={sharing()}>
        <ShareDialog onClose={() => setSharing(false)} />
      </Show>
    </main>
  );
}
