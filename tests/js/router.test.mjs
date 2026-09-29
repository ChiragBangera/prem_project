import test from "node:test";
import assert from "node:assert/strict";
import { compile, match, href } from "../../src/app/web/js/lib/router.js";

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
