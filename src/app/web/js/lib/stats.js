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
