import { createEffect, createMemo, createSignal, onCleanup } from "solid-js";

import { renderMarkdown } from "../lib/markdown";

// Re-parsing and re-highlighting on every token is the single most expensive thing the UI does.
// While streaming, coalesce to this cadence; the final text always renders exactly once more.
const STREAM_RENDER_MS = 90;

export function Markdown(props: { text: string; streaming?: boolean }) {
  const [shown, setShown] = createSignal(props.text);
  let timer: number | undefined;

  createEffect(() => {
    const text = props.text;
    if (!props.streaming) {
      window.clearTimeout(timer);
      timer = undefined;
      setShown(text);
      return;
    }
    if (timer !== undefined) return;
    timer = window.setTimeout(() => {
      timer = undefined;
      setShown(props.text);
    }, STREAM_RENDER_MS);
  });

  onCleanup(() => window.clearTimeout(timer));

  const html = createMemo(() => renderMarkdown(shown()));

  return <div class="msg__body" onClick={copyOnClick} innerHTML={html()} />;
}

function copyOnClick(event: MouseEvent) {
  const button = (event.target as HTMLElement).closest("button[data-copy-code]");
  if (!button) return;
  const code = button.closest("[data-code-block]")?.querySelector("code");
  if (!code) return;
  void navigator.clipboard.writeText(code.textContent ?? "").then(() => {
    const original = button.textContent;
    button.textContent = "Copied";
    window.setTimeout(() => (button.textContent = original), 1400);
  });
}
