import test from "node:test";
import assert from "node:assert/strict";
import { nf, signed, pct, probText, ordinal, plural, seasonLabel, dateShort, dateLong, weekday, timeOf, relTime, bytes, initials, fold, clamp, int, sureAge } from "../../src/app/web/js/lib/format.js";

test("numbers use a true minus sign and never show negative zero", () => {
  assert.equal(nf(-1.234, 2), "−1.23");
  assert.equal(nf(-0.001, 2), "0.00");
  assert.equal(nf(null), "–");
  assert.equal(nf(NaN), "–");
  assert.equal(signed(2.44, 1), "+2.4");
  assert.equal(signed(-2.44, 1), "−2.4");
  assert.equal(signed(0.04, 1), "0.0");
});

test("probabilities never claim certainty or impossibility", () => {
  assert.equal(probText(0.9993), ">99%");
  assert.equal(probText(0.0002), "<1%");
  assert.equal(probText(0.42), "42%");
  assert.equal(probText(0.034), "3.4%");
  assert.equal(pct(0.5), "50%");
  assert.equal(probText(undefined), "–");
});

test("ordinals, plurals and season labels", () => {
  assert.deepEqual([1, 2, 3, 4, 11, 12, 13, 21, 22, 103].map(ordinal), ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "103rd"]);
  assert.equal(plural(1, "point"), "1 point");
  assert.equal(plural(2, "point"), "2 points");
  assert.equal(plural(2, "match", "matches"), "2 matches");
  assert.equal(seasonLabel(2026), "2026/27");
  assert.equal(seasonLabel(1999), "1999/00");
  assert.equal(int(2425), "2,425");
});

test("dates are formatted without time-zone surprises", () => {
  assert.equal(dateShort("2027-03-07"), "7 Mar");
  assert.equal(dateLong("2027-03-07 20:00:00"), "7 Mar 2027");
  assert.equal(weekday("2027-03-07"), "Sun");
  assert.equal(timeOf("2027-03-07 20:00:00"), "20:00");
  assert.equal(timeOf("2027-03-07"), "");
  assert.equal(relTime(30), "just now");
  assert.equal(relTime(3600 * 5), "5 h ago");
  assert.equal(relTime(null), "never");
});

test("byte sizes switch to MB before they look silly", () => {
  assert.equal(bytes(512), "512 B");
  assert.equal(bytes(90_000), "88 KB");
  assert.equal(bytes(1_500_000), "1.4 MB");
});

test("names fold for search: accents, case and punctuation vanish", () => {
  assert.equal(fold("Luka Milović"), "luka milovic");
  assert.equal(fold("Øyvind  Ødegaard"), "oyvind odegaard");
  assert.equal(fold("Straße"), "strasse");
  assert.equal(initials("Luka Milović"), "LM");
  assert.equal(initials("Kai"), "KA");
  assert.equal(clamp(5, 0, 3), 3);
});

test("sureAge trusts every source except a name-only match", () => {
  assert.equal(sureAge({ age: 24, dob_basis: "roster" }), 24);
  assert.equal(sureAge({ age: 24, dob_basis: "club" }), 24);
  assert.equal(sureAge({ age: 24, dob_basis: "manual" }), 24);
  assert.equal(sureAge({ age: 24, dob_basis: "name" }), null);
  assert.equal(sureAge({ age: null, dob_basis: null }), null);
  assert.equal(sureAge({}), null);
});
