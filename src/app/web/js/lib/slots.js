// Colour follows the entity, never its position: an entity keeps the slot it first received,
// so removing one series never repaints the others (dataviz rule).
import { useRef } from "./html.js";

export function useStableSlots(keys, max = 8) {
  const ref = useRef(new Map());
  const map = ref.current;
  for (const k of [...map.keys()]) if (!keys.includes(k)) map.delete(k);
  const used = new Set(map.values());
  for (const k of keys) {
    if (map.has(k)) continue;
    let slot = 0;
    while (used.has(slot) && slot < max - 1) slot += 1;
    map.set(k, slot);
    used.add(slot);
  }
  return (k) => map.get(k) ?? 0;
}
