import { createSignal, Show } from "solid-js";

import { loadStatus } from "../state";
import type { StatusResponse } from "../types";
import { IconLock, IconPlug, IconRefresh, IconSpark, IconWarning } from "./Icons";

/** Shown instead of the composer whenever inference isn't usable yet.  Each state names the one
 *  thing the owner has to go do, and links straight to where they do it. */
export function SetupScreen(props: { status: StatusResponse }) {
  const [checking, setChecking] = createSignal(false);

  const recheck = async () => {
    setChecking(true);
    try {
      await loadStatus(true);
    } finally {
      setChecking(false);
    }
  };

  return (
    <div class="centered">
      <div class="panel">
        <Show when={props.status.state === "no_provider"}>
          <div class="panel__icon">
            <IconPlug />
          </div>
          <h1>No LLM gateway installed</h1>
          <p>
            bottlechat doesn't talk to model providers itself — it uses whichever app on this compute space
            provides the <code>openai-compat</code> service. Nothing provides it yet.
          </p>
          <ol>
            <li>
              Install the Bifrost gateway app from{" "}
              <a href={props.status.provider_repo_url} target="_blank" rel="noreferrer">
                its repository
              </a>
              , or any other app that provides the same service.
            </li>
            <li>Add your provider API keys in that app and configure at least one model.</li>
            <li>Come back here and re-check.</li>
          </ol>
          <div class="panel__actions">
            <a class="btn" href={props.status.dashboard_url} target="_blank" rel="noreferrer">
              Open the dashboard
            </a>
            <button type="button" class="btn btn--primary" disabled={checking()} onClick={() => void recheck()}>
              <IconRefresh /> {checking() ? "Checking…" : "Check again"}
            </button>
          </div>
        </Show>

        <Show when={props.status.state === "permission_required"}>
          <div class="panel__icon">
            <IconLock />
          </div>
          <h1>Permission needed</h1>
          <p>
            A gateway is installed{props.status.provider ? ` (${props.status.provider.app_name})` : ""}, but
            bottlechat hasn't been granted access to it yet. Approving takes one click.
          </p>
          <div class="panel__actions">
            <Show when={props.status.grant_url}>
              {(url) => (
                <a class="btn btn--primary" href={url()}>
                  Grant access
                </a>
              )}
            </Show>
            <button type="button" class="btn" disabled={checking()} onClick={() => void recheck()}>
              <IconRefresh /> {checking() ? "Checking…" : "Check again"}
            </button>
          </div>
        </Show>

        <Show when={props.status.state === "no_models"}>
          <div class="panel__icon">
            <IconSpark />
          </div>
          <h1>No models configured</h1>
          <p>
            {props.status.provider?.app_name ?? "The gateway"} is running, but it has no models set up, so there's
            nothing to chat with. Add a provider API key and enable at least one model there.
          </p>
          <div class="panel__actions">
            <Show when={props.status.provider}>
              {(provider) => (
                <a class="btn btn--primary" href={provider().url} target="_blank" rel="noreferrer">
                  Configure {provider().app_name}
                </a>
              )}
            </Show>
            <button type="button" class="btn" disabled={checking()} onClick={() => void recheck()}>
              <IconRefresh /> {checking() ? "Checking…" : "Check again"}
            </button>
          </div>
        </Show>

        <Show when={props.status.state === "error"}>
          <div class="panel__icon">
            <IconWarning />
          </div>
          <h1>The gateway isn't responding</h1>
          <p>
            bottlechat reached the service router, but the request for the model list failed. The gateway app may
            be starting up, stopped, or misconfigured.
          </p>
          <Show when={props.status.detail}>
            <div class="panel__detail">{props.status.detail}</div>
          </Show>
          <div class="panel__actions">
            <Show when={props.status.provider}>
              {(provider) => (
                <a class="btn" href={provider().url} target="_blank" rel="noreferrer">
                  Open {provider().app_name}
                </a>
              )}
            </Show>
            <button type="button" class="btn btn--primary" disabled={checking()} onClick={() => void recheck()}>
              <IconRefresh /> {checking() ? "Checking…" : "Try again"}
            </button>
          </div>
        </Show>
      </div>
    </div>
  );
}
