// Small numeric helpers used by charts (pure functions, unit-tested in web/tests).

/** Exact distribution of the number of successes over independent trials with probabilities ps. */
export function poissonBinomial(ps) {
  let pmf = [1];
  for (const p of ps) {
    const q = Math.min(1, Math.max(0, p));
    const next = new Array(pmf.length + 1).fill(0);
    for (let k = 0; k < pmf.length; k++) {
      next[k] += pmf[k] * (1 - q);
      next[k + 1] += pmf[k] * q;
    }
    pmf = next;
  }
  return pmf;
}

export const sum = (xs) => xs.reduce((a, b) => a + b, 0);

/** P(X >= k) and P(X <= k) from a pmf. */
export function tails(pmf, k) {
  const atLeast = sum(pmf.slice(Math.max(0, k)));
  const atMost = sum(pmf.slice(0, k + 1));
  return { atLeast: Math.min(1, atLeast), atMost: Math.min(1, atMost) };
}

export function mean(xs) {
  return xs.length ? sum(xs) / xs.length : NaN;
}

export function quantile(sorted, q) {
  if (!sorted.length) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

/** P(home win, draw, away win) if goals are Poisson with the given means (a fair read of a result from its xG). */
export function poissonOutcome(muHome, muAway, maxGoals = 10) {
  const pmf = (mu) => {
    const out = [Math.exp(-mu)];
    for (let k = 1; k <= maxGoals; k++) out.push((out[k - 1] * mu) / k);
    return out;
  };
  const h = pmf(Math.max(muHome, 1e-9)), a = pmf(Math.max(muAway, 1e-9));
  let home = 0, draw = 0, away = 0;
  for (let i = 0; i <= maxGoals; i++) {
    for (let j = 0; j <= maxGoals; j++) {
      const p = h[i] * a[j];
      if (i > j) home += p; else if (i === j) draw += p; else away += p;
    }
  }
  const total = home + draw + away;
  return { home: home / total, draw: draw / total, away: away / total };
}

/**
 * The straight line that fits the points best (least squares): ``y = a + b·x``, with ``sd`` the typical distance of a point from it.
 * Null with fewer than eight points or no spread across: a line through a handful of dots says nothing.
 */
export const fitLine = (points) => {
  const n = points.length;
  if (n < 8) return null;
  const mx = sum(points.map((p) => p.x)) / n, my = sum(points.map((p) => p.y)) / n;
  const sxx = sum(points.map((p) => (p.x - mx) ** 2)), sxy = sum(points.map((p) => (p.x - mx) * (p.y - my)));
  if (!(sxx > 0)) return null;
  const b = sxy / sxx, a = my - b * mx;
  const sd = Math.sqrt(sum(points.map((p) => (p.y - a - b * p.x) ** 2)) / (n - 2));
  return { a, b, sd };
};

/**
 * Who stands furthest from the line: ``below`` and ``above``, each the ``count`` points with the largest gap, counting only points at
 * or beyond ``fromX`` across (a gap at low volume is noise). Each is ``{ id, gap }`` with the gap in units of ``sd``.
 */
export const offTheLine = (points, line, { count = 6, fromX = -Infinity } = {}) => {
  if (!line || !(line.sd > 0)) return { below: [], above: [] };
  const gaps = points.filter((p) => p.x >= fromX).map((p) => ({ id: p.id, gap: (p.y - line.a - line.b * p.x) / line.sd }));
  const sorted = [...gaps].sort((p, q) => p.gap - q.gap);
  return { below: sorted.filter((p) => p.gap < -0.5).slice(0, count), above: sorted.filter((p) => p.gap > 0.5).slice(-count).reverse() };
};

/**
 * Where each value ranks among the others, as a share from 0 to 100: the share of the others it beats, a tie counting half. ``hib`` false
 * turns it round (fewer is better), so a high number always reads as good; ``null`` (style, not quality) keeps it as "higher than". A blank
 * value has no rank, and with fewer than two values nobody is ranked.
 */
export const rankShares = (values, hib = true) => {
  const known = values.filter((v) => v != null && Number.isFinite(v));
  const n = known.length;
  return values.map((v) => {
    if (n < 2 || v == null || !Number.isFinite(v)) return null;
    let below = 0, same = -1;  // the value itself is one of the equal ones
    for (const x of known) { if (x < v) below += 1; else if (x === v) same += 1; }
    const share = (100 * (below + same / 2)) / (n - 1);
    return hib === false ? 100 - share : share;
  });
};
