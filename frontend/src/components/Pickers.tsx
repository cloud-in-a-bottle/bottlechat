import { createMemo, For, Show } from "solid-js";

import { EFFORT_OPTIONS, type Effort, type ModelInfo } from "../types";
import { IconChevronDown } from "./Icons";

export function ModelPicker(props: {
  models: ModelInfo[];
  value: string | null;
  disabled?: boolean;
  onChange: (id: string) => void;
}) {
  const groups = createMemo(() => {
    const byProvider = new Map<string, ModelInfo[]>();
    for (const model of props.models) {
      const bucket = byProvider.get(model.provider);
      if (bucket) bucket.push(model);
      else byProvider.set(model.provider, [model]);
    }
    return [...byProvider.entries()];
  });

  return (
    <label class="select">
      <span class="visually-hidden">Model</span>
      <select
        disabled={props.disabled}
        value={props.value ?? ""}
        onChange={(event) => props.onChange(event.currentTarget.value)}
      >
        <Show when={!props.value}>
          <option value="">Select a model…</option>
        </Show>
        <For each={groups()}>
          {([provider, models]) => (
            <optgroup label={provider}>
              <For each={models}>{(model) => <option value={model.id}>{model.label}</option>}</For>
            </optgroup>
          )}
        </For>
      </select>
      <IconChevronDown />
    </label>
  );
}

export function EffortPicker(props: { value: Effort; disabled?: boolean; onChange: (effort: Effort) => void }) {
  return (
    <label class="select" title="Reasoning effort — ignored by models that don't reason">
      <span class="visually-hidden">Reasoning effort</span>
      <select
        disabled={props.disabled}
        value={props.value}
        onChange={(event) => props.onChange(event.currentTarget.value as Effort)}
      >
        <For each={EFFORT_OPTIONS}>{(option) => <option value={option.value}>{option.label}</option>}</For>
      </select>
      <IconChevronDown />
    </label>
  );
}
