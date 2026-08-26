import { createSignal, Show } from "solid-js";

import { IconSend, IconStop } from "./Icons";
import { EffortPicker, ModelPicker } from "./Pickers";
import type { Effort, ModelInfo } from "../types";

export function Composer(props: {
  models: ModelInfo[];
  model: string | null;
  effort: Effort;
  streaming: boolean;
  disabled?: boolean;
  onModel: (id: string) => void;
  onEffort: (effort: Effort) => void;
  onSend: (text: string) => void;
  onStop: () => void;
}) {
  const [text, setText] = createSignal("");
  let textarea: HTMLTextAreaElement | undefined;

  const canSend = () => text().trim().length > 0 && !props.disabled && !props.streaming;

  const submit = () => {
    if (!canSend()) return;
    props.onSend(text().trim());
    setText("");
    if (textarea) {
      textarea.style.height = "auto";
      textarea.focus();
    }
  };

  const onKeyDown = (event: KeyboardEvent) => {
    // Enter sends; Shift+Enter (and any modifier chord) inserts a newline.
    if (event.key === "Enter" && !event.shiftKey && !event.metaKey && !event.ctrlKey && !event.altKey) {
      event.preventDefault();
      submit();
    }
  };

  const resize = () => {
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, window.innerHeight * 0.4)}px`;
  };

  return (
    <div class="composer">
      <div class="composer__inner">
        <textarea
          ref={textarea}
          rows="1"
          placeholder={props.disabled ? "Pick a model to start" : "Send a message…"}
          value={text()}
          disabled={props.disabled}
          aria-label="Message"
          onInput={(event) => {
            setText(event.currentTarget.value);
            resize();
          }}
          onKeyDown={onKeyDown}
        />
        <div class="composer__row">
          <ModelPicker models={props.models} value={props.model} onChange={props.onModel} />
          <EffortPicker value={props.effort} onChange={props.onEffort} />
          <span class="composer__hint">Enter to send · Shift+Enter for a new line</span>
          <Show
            when={props.streaming}
            fallback={
              <button
                type="button"
                class="btn btn--primary btn--send"
                disabled={!canSend()}
                aria-label="Send message"
                onClick={submit}
              >
                <IconSend />
              </button>
            }
          >
            <button type="button" class="btn btn--send" aria-label="Stop generating" onClick={props.onStop}>
              <IconStop size={14} />
            </button>
          </Show>
        </div>
      </div>
    </div>
  );
}
