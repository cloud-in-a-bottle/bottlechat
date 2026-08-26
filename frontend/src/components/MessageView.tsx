import { createSignal, Show } from "solid-js";

import { showToast } from "../state";
import type { Message } from "../types";
import { IconCopy, IconRefresh, IconStop, IconWarning } from "./Icons";
import { Markdown } from "./Markdown";
import { Reasoning } from "./Reasoning";

const STATUS_NOTE: Partial<Record<Message["status"], string>> = {
  cancelled: "Stopped",
  interrupted: "Interrupted — the server restarted while this was being written",
};

export function MessageView(props: {
  message: Message;
  onStop?: () => void;
  onRetry?: () => void;
  readOnly?: boolean;
}) {
  const [copied, setCopied] = createSignal(false);
  const streaming = () => props.message.status === "streaming";
  const hasContent = () => props.message.content.length > 0;

  const copy = () => {
    void navigator.clipboard.writeText(props.message.content).then(() => {
      setCopied(true);
      showToast("Copied to clipboard");
      window.setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <Show
      when={props.message.role === "assistant"}
      fallback={
        <div class="msg msg--user">
          <div class="msg__body">{props.message.content}</div>
        </div>
      }
    >
      <div class="msg msg--assistant">
        <Show when={props.message.reasoning}>
          <Reasoning text={props.message.reasoning} streaming={streaming()} hasAnswer={hasContent()} />
        </Show>

        <Show when={hasContent()}>
          <Markdown text={props.message.content} streaming={streaming()} />
        </Show>

        <Show when={streaming() && !hasContent() && !props.message.reasoning}>
          <div class="msg__body">
            <span class="typing" />
          </div>
        </Show>

        <Show when={props.message.error}>
          <div class="msg__error" role="alert">
            <IconWarning size={17} />
            <p>{props.message.error}</p>
            <Show when={props.onRetry}>
              <button type="button" class="btn btn--ghost" onClick={() => props.onRetry?.()}>
                <IconRefresh /> Retry
              </button>
            </Show>
          </div>
        </Show>

        <Show when={!props.readOnly}>
          <div class="msg__meta">
            <Show when={streaming()}>
              <span class="spinner" />
              <button type="button" onClick={() => props.onStop?.()}>
                <IconStop size={13} /> Stop
              </button>
            </Show>
            <Show when={!streaming() && hasContent()}>
              <button type="button" onClick={copy}>
                <IconCopy /> {copied() ? "Copied" : "Copy"}
              </button>
              <Show when={props.onRetry && !props.message.error}>
                <button type="button" onClick={() => props.onRetry?.()}>
                  <IconRefresh /> Retry
                </button>
              </Show>
            </Show>
            <Show when={STATUS_NOTE[props.message.status]}>
              <span>{STATUS_NOTE[props.message.status]}</span>
            </Show>
            <Show when={!streaming() && props.message.model}>
              <span>{props.message.model}</span>
            </Show>
          </div>
        </Show>
      </div>
    </Show>
  );
}
