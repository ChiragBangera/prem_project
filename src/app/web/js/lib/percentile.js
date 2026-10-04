// What a percentile bar says, in plain words. One place, so the metric table, the profile card and their tooltips agree.

/** Higher is better (true), lower is better (false) or a style metric where neither is (null). Profile items carry it as `higher_is_better`. */
export const direction = (it) => (it.hib !== undefined ? it.hib : it.higher_is_better ?? true);

/** The whole number a bar is drawn at, kept off 0 and 100 so the sentence never claims to beat "0" or "100" of every 100. */
export const beats = (pct) => Math.max(1, Math.min(99, Math.round(pct)));

/**
 * The sentence behind one bar, for a profile item ({ pct, rank, pool_n, hib }). `who` is the peer group in the plural ("midfielders").
 * Null when he is not ranked on it.
 */
export function readBar(it, who) {
  if (!it || it.pct == null) return null;
  const n = beats(it.pct);
  const dir = direction(it);
  if (dir === null) return `A matter of style, not quality: he is higher than ${n} of every 100 ${who} on this, and neither high nor low is better.`;
  const place = it.rank && it.pool_n ? ` Rank ${it.rank} of ${it.pool_n}.` : "";
  if (dir === false) return `Better than ${n} of every 100 ${who}. Less is better here, so the bar is flipped: a long bar means he does this less than most.${place}`;
  return `Better than ${n} of every 100 ${who}.${place}`;
}

/** The comparison group in words: "the 88 midfielders in the Premier League who have played at least 660 minutes". */
export function peerGroup({ n, who, league, minutes }) {
  return `the ${n} ${who} ${league ? `in the ${league} ` : ""}who have played at least ${minutes} minutes`;
}
