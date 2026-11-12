// The players ticked for comparison, in a tray at the foot of the screen, with the button that compares them.
import { html } from "../../lib/html.js";
import { navigate } from "../../lib/router.js";
import { Icon } from "../../lib/icons.js";
import { Button } from "../common.js";

export function CompareTray({ ids, rows, onChange }) {
  if (!ids.length) return null;
  const chosen = ids.map((id) => rows.find((r) => r.id === id)).filter(Boolean);
  return html`<div class="tray" role="region" aria-label="Comparison selection">
    <div class="tray-list">${chosen.map((r) => html`<span class="chip on" key=${r.id}>${r.name}<button type="button" aria-label=${`Remove ${r.name} from the comparison`} onClick=${() => onChange(ids.filter((x) => x !== r.id))}><${Icon} name="x" /></button></span>`)}</div>
    <div class="row" style=${{ gap: "8px" }}>
      <${Button} kind="quiet" size="sm" onClick=${() => onChange([])}>Clear</${Button}>
      <${Button} kind="primary" size="sm" icon="compare" disabled=${ids.length < 2} onClick=${() => navigate("/compare", { ids: ids.join(",") })}>${ids.length < 2 ? "Pick one more" : `Compare ${ids.length}`}</${Button}>
    </div>
  </div>`;
}
