// One tooltip for the whole app. Charts call show/move/hide; the host renders it.
import { html, useEffect, useLayoutEffect, useRef, useState } from "./html.js";
import { createStore, useStore } from "./store.js";

const tip = createStore({ visible: false, x: 0, y: 0, content: null });

export const tooltip = {
  show(event, content) { tip.set({ visible: true, x: event.clientX, y: event.clientY, content }); },
  move(event, content) { tip.set((s) => ({ visible: true, x: event.clientX, y: event.clientY, content: content !== undefined ? content : s.content })); },
  at(x, y, content) { tip.set({ visible: true, x, y, content }); },
  hide() { tip.set((s) => (s.visible ? { visible: false } : {})); },
};

export function TooltipHost() {
  const s = useStore(tip);
  const ref = useRef(null);
  const [pos, setPos] = useState({ left: 0, top: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !s.visible) return;
    const w = el.offsetWidth, h = el.offsetHeight;
    let left = s.x + 14, top = s.y + 16;
    if (left + w > window.innerWidth - 8) left = s.x - w - 14;
    if (top + h > window.innerHeight - 8) top = s.y - h - 14;
    setPos({ left: Math.max(8, left), top: Math.max(8, top) });
  }, [s.x, s.y, s.visible, s.content]);
  useEffect(() => {
    const off = () => tooltip.hide();
    window.addEventListener("scroll", off, true);
    window.addEventListener("blur", off);
    return () => { window.removeEventListener("scroll", off, true); window.removeEventListener("blur", off); };
  }, []);
  return html`<div class=${"tooltip" + (s.visible ? " on" : "")} ref=${ref} style=${{ left: pos.left + "px", top: pos.top + "px" }} role="tooltip">${s.content}</div>`;
}

// Convenience builders for consistent tooltip content (values lead, labels follow).
export function Tip({ title, sub, rows = [] }) {
  return html`<div>
    ${title ? html`<div class="tt-title">${title}</div>` : null}
    ${sub ? html`<div class="tt-sub">${sub}</div>` : null}
    ${rows.map((r) => html`<div class="tt-row"><span class="k">${r.color ? html`<i class=${r.shape === "dot" ? "dot" : "key"} style=${{ background: r.color }}></i>` : null}${r.label}</span><span class="v">${r.value}</span></div>`)}
  </div>`;
}
