import { createSignal, Show } from "solid-js";

import { share, showToast, toggleShare } from "../state";

export function ShareDialog(props: { onClose: () => void }) {
  const [busy, setBusy] = createSignal(false);

  const enable = async () => {
    setBusy(true);
    try {
      await toggleShare(true);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    setBusy(true);
    try {
      await toggleShare(false);
      showToast("Share link revoked");
      props.onClose();
    } finally {
      setBusy(false);
    }
  };

  const copy = () => {
    const url = share()?.url;
    if (url) void navigator.clipboard.writeText(url).then(() => showToast("Link copied"));
  };

  return (
    <>
      <div class="scrim" onClick={props.onClose} />
      <div class="modal" role="dialog" aria-modal="true" aria-label="Share chat">
        <div class="modal__panel">
          <h2>Share this chat</h2>
          <Show
            when={share()}
            fallback={
              <>
                <p>
                  Creating a link makes this conversation readable by anyone who has it, without signing in. The
                  link always shows the chat's current contents, including messages you add later.
                </p>
                <div class="modal__actions">
                  <button type="button" class="btn btn--ghost" onClick={props.onClose}>
                    Cancel
                  </button>
                  <button type="button" class="btn btn--primary" disabled={busy()} onClick={() => void enable()}>
                    Create link
                  </button>
                </div>
              </>
            }
          >
            {(active) => (
              <>
                <p>Anyone with this link can read the conversation, including messages added later.</p>
                <div class="share-url">
                  <input type="text" readOnly value={active().url} onFocus={(e) => e.currentTarget.select()} />
                  <button type="button" class="btn" onClick={copy}>
                    Copy
                  </button>
                </div>
                <div class="modal__actions">
                  <button type="button" class="btn btn--ghost" disabled={busy()} onClick={() => void revoke()}>
                    Revoke link
                  </button>
                  <button type="button" class="btn btn--primary" onClick={props.onClose}>
                    Done
                  </button>
                </div>
              </>
            )}
          </Show>
        </div>
      </div>
    </>
  );
}
