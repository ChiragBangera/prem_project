// Team style and maps: where the team touches the ball, how it passes, where it defends and carries, drawn from the stored event data.
import { html, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { Async, Card, Segmented, Select } from "../ui/common.js";
import { MapLab } from "../ui/maplab.js";

const WINDOWS = [{ value: "", label: "Whole season" }, { value: "5", label: "Last 5 matches" }, { value: "10", label: "Last 10 matches" }, { value: "20", label: "Last 20 matches" }];
const VENUES = [{ value: "all", label: "All matches" }, { value: "h", label: "Home" }, { value: "a", label: "Away" }];

export default function StyleMaps({ team, scope }) {
  const [venue, setVenue] = useState("all");
  const [last, setLast] = useState("");
  const params = { team, league: scope.league, season: scope.season, venue: venue === "all" ? undefined : venue, last: last || undefined };
  const q = useApi("/api/maps/team", params);
  const shots = useApi("/api/team/shots", params);
  const sample = shots.data ? { for: shots.data.for, against: shots.data.against } : undefined;
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <${Card} title="Style and maps" sub="Every map is drawn from the stored event data, so it updates by itself as matches are played. Choose a layer, then narrow the matches."
      actions=${html`<div class="row wrap" style=${{ gap: "8px" }}>
        <${Segmented} small label="Which matches" value=${venue} onChange=${setVenue} options=${VENUES} />
        <${Select} compact label="How many matches" value=${last} options=${WINDOWS} onChange=${setLast} />
      </div>`}>
      <${Async} q=${q}>${(d) => html`<${MapLab} data=${d} kind="team" shots=${sample} shotsLoading=${shots.loading} />`}</${Async}>
    </${Card}>
  </div>`;
}
