// League + season scope shared by every page (persisted in the ui store).
import { ui, metaStore, useStore } from "./store.js";
import { seasonLabel } from "./format.js";

export function useScope() {
  const { league, season } = useStore(ui, (u) => ({ league: u.league, season: u.season }));
  return { league, season };
}

export function setLeague(league) { ui.set({ league }); }
export function setSeason(season) { ui.set({ season }); }

export function useMeta() {
  return useStore(metaStore);
}

export function leagueName(meta, code) {
  return meta?.leagues?.find((l) => l.code === code)?.name || code;
}

export function seasonOptions(meta) {
  const cur = meta?.current_season;
  const list = (meta?.seasons || []).map((s) => ({ value: String(s.season), label: s.label || seasonLabel(s.season) }));
  return [{ value: "auto", label: cur ? `Latest (${seasonLabel(cur)})` : "Latest" }, ...list];
}
