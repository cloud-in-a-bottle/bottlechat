import DOMPurify from "dompurify";
import hljs from "highlight.js/lib/common";
import { Marked } from "marked";

const marked = new Marked({ gfm: true, breaks: true });

marked.use({
  renderer: {
    code({ text, lang }) {
      const language = lang?.split(/\s+/)[0] ?? "";
      const supported = language && hljs.getLanguage(language);
      const highlighted = supported
        ? hljs.highlight(text, { language, ignoreIllegals: true }).value
        : escapeHtml(text);
      // The label and copy button are wired up by CodeBlockActions, which delegates from the
      // message container rather than attaching per-block listeners.
      return `<figure class="code-block" data-code-block><figcaption><span>${escapeHtml(
        language || "text",
      )}</span><button type="button" data-copy-code>Copy</button></figcaption><pre><code class="hljs">${highlighted}</code></pre></figure>`;
    },
    link({ href, title, text }) {
      const safeTitle = title ? ` title="${escapeHtml(title)}"` : "";
      return `<a href="${escapeHtml(href)}"${safeTitle} target="_blank" rel="noopener noreferrer nofollow ugc">${text}</a>`;
    },
  },
});

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Model output is untrusted input: it is rendered as HTML, so it must be sanitized. */
export function renderMarkdown(source: string): string {
  const html = marked.parse(source, { async: false });
  return DOMPurify.sanitize(html, {
    ADD_ATTR: ["target", "data-copy-code", "data-code-block"],
    FORBID_TAGS: ["style", "form", "input", "button:not([data-copy-code])"],
  });
}
