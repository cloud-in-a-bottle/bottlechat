import { createEffect, createMemo, For, onCleanup, onMount, type JSX } from "solid-js";

import type { Message } from "../types";
import { MessageView } from "./MessageView";

/** Scrolling transcript that stays pinned to the bottom while a response streams — unless the
 *  reader has scrolled up, in which case it stays where they put it. */
export function Thread(props: {
  messages: Message[];
  readOnly?: boolean;
  header?: JSX.Element;
  onStop?: (messageId: string) => void;
  onRetry?: (messageId: string) => void;
}) {
  let container: HTMLDivElement | undefined;
  let pinned = true;

  const nearBottom = () =>
    !container || container.scrollHeight - container.scrollTop - container.clientHeight < 120;

  onMount(() => {
    if (!container) return;
    const onScroll = () => (pinned = nearBottom());
    container.addEventListener("scroll", onScroll, { passive: true });
    onCleanup(() => container?.removeEventListener("scroll", onScroll));
  });

  // Sum the lengths that grow during streaming so this re-runs on every delta.
  const streamedLength = createMemo(() =>
    props.messages.reduce((total, m) => total + m.content.length + m.reasoning.length, 0),
  );

  createEffect(() => {
    streamedLength();
    if (pinned && container) container.scrollTop = container.scrollHeight;
  });

  return (
    <div class="thread" ref={container}>
      <div class="thread__inner">
        {props.header}
        <For each={props.messages}>
          {(message) => (
            <MessageView
              message={message}
              readOnly={props.readOnly}
              onStop={props.onStop ? () => props.onStop?.(message.id) : undefined}
              onRetry={props.onRetry ? () => props.onRetry?.(message.id) : undefined}
            />
          )}
        </For>
      </div>
    </div>
  );
}
