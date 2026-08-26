import { onCleanup, onMount, type JSX } from "solid-js";

/** A small popup anchored under a trigger.  Closes on outside click, Escape, or scroll. */
export function Menu(props: { x: number; y: number; onClose: () => void; children: JSX.Element }) {
  let panel: HTMLDivElement | undefined;

  onMount(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (panel && !panel.contains(event.target as Node)) props.onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") props.onClose();
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", props.onClose);
    onCleanup(() => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", props.onClose);
    });
  });

  // Keep the panel on screen when the trigger sits near the right or bottom edge.
  const left = () => Math.min(props.x, window.innerWidth - 190);
  const top = () => Math.min(props.y, window.innerHeight - 130);

  return (
    <div ref={panel} class="menu" role="menu" style={{ left: `${left()}px`, top: `${top()}px` }}>
      {props.children}
    </div>
  );
}
