import { useParams } from "@solidjs/router";
import { createResource, For, Show } from "solid-js";

import { Markdown } from "../components/Markdown";
import { Reasoning } from "../components/Reasoning";
import { api } from "../api";
import { formatTimestamp } from "../lib/format";

export function SharePage() {
  const params = useParams<{ token: string }>();
  const [shared] = createResource(() => params.token, api.sharedChat);

  return (
    <div class="share-page">
      <Show when={shared()}>
        {(chat) => (
          <header class="share-page__head">
            <div class="share-page__head-inner">
              <img src="/icons/icon-192.png" alt="" />
              <div>
                <h1>{chat().title}</h1>
                <p>Shared conversation · last updated {formatTimestamp(chat().updated_at)}</p>
              </div>
            </div>
          </header>
        )}
      </Show>

      <Show when={shared.loading}>
        <div class="centered">
          <span class="spinner" />
        </div>
      </Show>

      <Show when={shared.error}>
        <div class="centered">
          <div class="panel">
            <h1>This link isn't valid</h1>
            <p>It may have been revoked by its owner, or the address may be mistyped.</p>
          </div>
        </div>
      </Show>

      <Show when={shared()}>
        {(chat) => (
          <>
            <div class="thread">
              <div class="thread__inner">
                <For each={chat().messages}>
                  {(message) => (
                    <Show
                      when={message.role === "assistant"}
                      fallback={
                        <div class="msg msg--user">
                          <div class="msg__body">{message.content}</div>
                        </div>
                      }
                    >
                      <div class="msg msg--assistant">
                        <Show when={message.reasoning}>
                          <Reasoning text={message.reasoning} streaming={false} hasAnswer={!!message.content} />
                        </Show>
                        <Markdown text={message.content} />
                      </div>
                    </Show>
                  )}
                </For>
              </div>
            </div>
            <p class="share-page__foot">Shared from bottlechat</p>
          </>
        )}
      </Show>
    </div>
  );
}
