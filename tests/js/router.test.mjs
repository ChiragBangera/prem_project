import test from "node:test";
import assert from "node:assert/strict";
import { compile, match, href, parseHash } from "../../src/app/web/js/lib/router.js";

const routes = compile([
  { path: "/", name: "home" },
  { path: "/team/:team", name: "team" },
  { path: "/player/:id", name: "player" },
]);

test("routes match with decoded params", () => {
  assert.equal(match(routes, "/").route.name, "home");
  const m = match(routes, "/team/Manchester%20United");
  assert.equal(m.route.name, "team");
  assert.equal(m.params.team, "Manchester United");
  assert.equal(match(routes, "/player/100844/").params.id, "100844");
  assert.equal(match(routes, "/nowhere"), null);
});

test("href builds hash links and drops empty query values", () => {
  assert.equal(href("/scout"), "#/scout");
  assert.equal(href("/scout", { groups: "ATT", q: "", min: null, view: undefined }), "#/scout?groups=ATT");
  assert.equal(href("/team/" + encodeURIComponent("Borussia M.Gladbach")), "#/team/Borussia%20M.Gladbach");
  assert.equal(href("/compare", { ids: "1,2" }), "#/compare?ids=1%2C2");
});

test("a hash is split into a path and a query, each decoded once", () => {
  assert.deepEqual(parseHash(""), { path: "/", query: {} });
  assert.deepEqual(parseHash("#/scout"), { path: "/scout", query: {} });
  assert.deepEqual(parseHash("#/team/Manchester%20United?tab=maps"), { path: "/team/Manchester United", query: { tab: "maps" } });
  assert.deepEqual(parseHash("#/scout?f=npxg90%3E%3Dp80&r=ATT%2CMID").query, { f: "npxg90>=p80", r: "ATT,MID" });
  assert.deepEqual(parseHash("#/scout?q=100%2541").query, { q: "100%41" });                // a literal percent sign survives: decoded once, not twice
  assert.deepEqual(parseHash("#/scout?q=a?b&r=ATT").query, { q: "a?b", r: "ATT" });        // a second "?" belongs to the value
  assert.equal(parseHash("#scout").path, "/scout");
});

test("a malformed percent-escape never throws and never takes the app down", () => {
  assert.doesNotThrow(() => parseHash("#/scout?q=%E0%A4%A"));
  assert.equal(parseHash("#/scout?q=%E0%A4%A").path, "/scout");
  assert.equal(parseHash("#/team/%E0%A4%A").path, "/team/%E0%A4%A");                      // left as typed
  assert.equal(match(routes, "/team/%E0%A4%A").params.team, "%E0%A4%A");
});
