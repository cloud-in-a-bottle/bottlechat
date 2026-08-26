import { Route, Router, useParams } from "@solidjs/router";
import { createSignal, onMount, Show } from "solid-js";

import { Sidebar } from "./components/Sidebar";
import { ChatPage } from "./pages/ChatPage";
import { SharePage } from "./pages/SharePage";
import { loadChatList, loadStatus, statusError, toast } from "./state";

function Workspace() {
  const params = useParams<{ chatId?: string }>();
  const [drawerOpen, setDrawerOpen] = createSignal(false);

  onMount(() => {
    void loadStatus();
    void loadChatList();
  });

  return (
    <div class="shell">
      <Sidebar
        open={drawerOpen()}
        activeId={params.chatId ?? null}
        onNavigate={() => setDrawerOpen(false)}
      />
      <Show when={drawerOpen()}>
        <div class="scrim" onClick={() => setDrawerOpen(false)} />
      </Show>
      <ChatPage onOpenDrawer={() => setDrawerOpen(true)} />
      <Show when={statusError()}>
        <div class="toast" role="status">
          Couldn't reach the server: {statusError()}
        </div>
      </Show>
    </div>
  );
}

export function App() {
  return (
    <>
      <Router>
        <Route path="/share/:token" component={SharePage} />
        <Route path="/c/:chatId" component={Workspace} />
        <Route path="/" component={Workspace} />
      </Router>
      <Show when={toast()}>
        <div class="toast" role="status">
          {toast()}
        </div>
      </Show>
    </>
  );
}
