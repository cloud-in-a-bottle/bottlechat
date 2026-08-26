import { render } from "solid-js/web";

import { App } from "./App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

render(() => <App />, root);

// The share page is opened by people who aren't the owner; there's nothing there worth
// installing, and registering a worker on their device would be presumptuous.
if ("serviceWorker" in navigator && !location.pathname.startsWith("/share/")) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => {
      /* a failed registration only costs the install prompt */
    });
  });
}
