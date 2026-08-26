import { createEffect, createSignal, Show } from "solid-js";

import { IconBrain, IconChevronRight } from "./Icons";

/** The model's thinking.  Open while it streams so there's something to watch, then collapsed
 *  automatically once the answer itself starts arriving — the answer is what you came for. */
export function Reasoning(props: { text: string; streaming: boolean; hasAnswer: boolean }) {
  const [manual, setManual] = createSignal<boolean | null>(null);
  let body: HTMLDivElement | undefined;

  const open = () => manual() ?? (props.streaming && !props.hasAnswer);

  createEffect(() => {
    if (open() && props.streaming && body) body.scrollTop = body.scrollHeight;
  });

  const label = () => {
    if (props.streaming && !props.hasAnswer) return "Thinking…";
    return props.streaming ? "Thought while answering" : "Thought process";
  };

  return (
    <div class="reasoning" data-open={open()}>
      <button
        type="button"
        class="reasoning__toggle"
        aria-expanded={open()}
        onClick={() => setManual(!open())}
      >
        <IconChevronRight class="reasoning__chevron" />
        <IconBrain />
        <span>{label()}</span>
      </button>
      <Show when={open()} fallback={<Show when={!props.hasAnswer}><div class="reasoning__peek">{props.text}</div></Show>}>
        <div class="reasoning__body" ref={body}>
          {props.text}
        </div>
      </Show>
    </div>
  );
}
