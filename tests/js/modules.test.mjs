// Static check of the whole browser code base: every module parses, every relative import points at a file that exists, and every named
// import is something that file really exports. The app has no build step, so one mistyped name would otherwise only show up as a blank page.
import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../src/app/web/js");

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : p.endsWith(".js") ? [p] : [];
  });
}

const files = walk(ROOT);
const source = new Map(files.map((f) => [f, readFileSync(f, "utf8")]));

function exportsOf(text) {
  const names = new Set();
  for (const m of text.matchAll(/^export\s+(?:async\s+)?(?:function\*?|const|let|var|class)\s+([A-Za-z0-9_$]+)/gm)) names.add(m[1]);
  for (const m of text.matchAll(/^export\s*\{([^}]*)\}/gm)) {
    for (const part of m[1].split(",")) {
      const name = part.trim().split(/\s+as\s+/).pop();
      if (name) names.add(name);
    }
  }
  if (/^export\s+default\b/m.test(text)) names.add("default");
  return names;
}

function importsOf(text) {
  const out = [];
  for (const m of text.matchAll(/^import\s+([\s\S]*?)\s+from\s+["']([^"']+)["'];?/gm)) {
    const clause = m[1].trim();
    const names = [];
    const braces = /\{([\s\S]*)\}/.exec(clause);
    if (braces) for (const part of braces[1].split(",")) { const n = part.trim().split(/\s+as\s+/)[0]; if (n) names.push(n); }
    const head = clause.replace(/\{[\s\S]*\}/, "").replace(/,/g, "").trim();
    if (head && !head.startsWith("*")) names.push("default");
    out.push({ spec: m[2], names });
  }
  return out;
}

test("every module is syntactically valid", () => {
  for (const f of files) {
    execFileSync(process.execPath, ["--check", f], { stdio: "pipe" });
  }
  assert.ok(files.length > 40);
});

test("every relative import resolves, and every named import exists in that module", () => {
  const problems = [];
  for (const [file, text] of source) {
    for (const { spec, names } of importsOf(text)) {
      if (!spec.startsWith(".")) continue;
      const target = resolve(dirname(file), spec);
      if (target.includes("/vendor/")) continue; // the vendored bundle is minified
      const body = source.get(target);
      if (body === undefined) { problems.push(`${relative(ROOT, file)}: cannot find ${spec}`); continue; }
      const have = exportsOf(body);
      for (const n of names) if (!have.has(n)) problems.push(`${relative(ROOT, file)}: ${spec} does not export ${n}`);
    }
  }
  assert.deepEqual(problems, []);
});

test("no module still reaches for the retired forecast or method pages", () => {
  const stale = [];
  for (const [file, text] of source) {
    if (/pages\/(forecast|method)\.js/.test(text) || /labHref/.test(text)) stale.push(relative(ROOT, file));
  }
  assert.deepEqual(stale, []);
});

test("no module uses a name it never declared or imported, and none imports what it never uses", (t) => {
  // tools/check-modules.mjs reads the code with the parser inside Node, which is only reachable with --expose-internals
  let out = "";
  try {
    out = execFileSync(process.execPath, ["--expose-internals", "--no-warnings", resolve(ROOT, "../../../../tools/check-modules.mjs")], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  } catch (e) {
    assert.fail(String(e.stdout || e.stderr || e.message));
  }
  if (out.startsWith("SKIP")) return t.skip(out.trim());
  assert.equal(out.trim(), "ok");
});
