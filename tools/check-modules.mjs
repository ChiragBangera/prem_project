#!/usr/bin/env node
// Static lint for the browser code, which has no build step and so no compiler to catch a typo:
//   * every identifier a module uses is declared in it, imported, or a browser global (a deleted import would otherwise be a blank page);
//   * every import is used.
// It reads the code with the JavaScript parser that ships inside Node, so it needs `node --expose-internals` (the test that runs it does that).
//
//   node --expose-internals --no-warnings tools/check-modules.mjs
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../src/app/web/js");
const require = createRequire(import.meta.url);
let acorn, walk;
try {
  acorn = require("internal/deps/acorn/acorn/dist/acorn");
  walk = require("internal/deps/acorn/acorn-walk/dist/walk");
} catch (_) {
  console.log("SKIP: this Node does not expose its parser (run with --expose-internals)");
  process.exit(0);
}

const GLOBALS = new Set(`window document console navigator location history localStorage sessionStorage indexedDB setTimeout clearTimeout setInterval clearInterval
  requestAnimationFrame cancelAnimationFrame fetch URL URLSearchParams Promise Math JSON Object Array Set Map WeakMap WeakSet Number String Boolean Date RegExp Error TypeError
  Symbol Infinity NaN undefined parseInt parseFloat isNaN isFinite encodeURIComponent decodeURIComponent decodeURI encodeURI Intl AbortController Blob FormData Event CustomEvent
  HashChangeEvent ResizeObserver IntersectionObserver MutationObserver matchMedia getComputedStyle performance structuredClone queueMicrotask TextEncoder TextDecoder
  Uint8Array Float32Array Float64Array Int32Array Uint16Array Int16Array Uint32Array BigInt arguments globalThis Response Request Headers alert confirm prompt CSS DOMParser Image
  Node Element HTMLElement SVGElement KeyboardEvent MouseEvent Reflect Proxy atob btoa CompressionStream DecompressionStream ReadableStream requestIdleCallback
  cancelIdleCallback BroadcastChannel caches crypto screen customElements DOMRect File FileReader IDBKeyRange XMLSerializer Worker AggregateError WebSocket EventSource`.split(/\s+/));

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? (name === "vendor" || name === "fonts" ? [] : files(p)) : p.endsWith(".js") ? [p] : [];
  });
}

function check(file) {
  const problems = [];
  const where = relative(ROOT, file);
  let ast;
  try { ast = acorn.parse(readFileSync(file, "utf8"), { ecmaVersion: "latest", sourceType: "module", allowHashBang: true }); } catch (e) { return [`${where}: ${e.message}`]; }

  const declared = new Set();
  const imports = new Map();
  const declare = (n) => {
    if (!n) return;
    switch (n.type) {
      case "Identifier": declared.add(n.name); break;
      case "ObjectPattern": n.properties.forEach((p) => declare(p.type === "RestElement" ? p.argument : p.value)); break;
      case "ArrayPattern": n.elements.forEach(declare); break;
      case "RestElement": declare(n.argument); break;
      case "AssignmentPattern": declare(n.left); break;
      default: break;
    }
  };
  walk.full(ast, (n) => {
    if (n.type === "ImportSpecifier" || n.type === "ImportDefaultSpecifier" || n.type === "ImportNamespaceSpecifier") { declared.add(n.local.name); imports.set(n.local.name, 0); }
    else if (n.type === "VariableDeclarator") declare(n.id);
    else if ((n.type === "FunctionDeclaration" || n.type === "ClassDeclaration") && n.id) declared.add(n.id.name);
    if (n.type === "FunctionDeclaration" || n.type === "FunctionExpression" || n.type === "ArrowFunctionExpression") {
      n.params.forEach(declare);
      if (n.type === "FunctionExpression" && n.id) declared.add(n.id.name);
    }
    if (n.type === "ClassExpression" && n.id) declared.add(n.id.name);
    if (n.type === "CatchClause") declare(n.param);
  });

  const used = new Map();
  walk.full(ast, (n) => {   // `export { a, b }` re-exports local bindings; the walker does not descend into the specifiers
    if (n.type === "ExportNamedDeclaration" && !n.source) for (const spec of n.specifiers) used.set(spec.local.name, (used.get(spec.local.name) || 0) + 1);
  });
  walk.fullAncestor(ast, (n, _state, ancestors) => {
    if (n.type !== "Identifier") return;
    const parent = ancestors[ancestors.length - 2];
    if (!parent) return;
    if (parent.type === "MemberExpression" && parent.property === n && !parent.computed) return;
    if ((parent.type === "Property" || parent.type === "PropertyDefinition" || parent.type === "MethodDefinition") && parent.key === n && !parent.computed && !(parent.type === "Property" && parent.shorthand)) return;
    if (parent.type === "ImportSpecifier" || parent.type === "ImportDefaultSpecifier" || parent.type === "ImportNamespaceSpecifier" || parent.type === "LabeledStatement" || parent.type === "BreakStatement" || parent.type === "ContinueStatement") return;
    if ((parent.type === "FunctionDeclaration" || parent.type === "FunctionExpression" || parent.type === "ClassDeclaration" || parent.type === "ClassExpression") && parent.id === n) return;
    if (parent.type === "VariableDeclarator" && parent.id === n) return;
    if (parent.type === "CatchClause" && parent.param === n) return;
    if ((parent.type === "FunctionDeclaration" || parent.type === "FunctionExpression" || parent.type === "ArrowFunctionExpression") && parent.params.includes(n)) return;
    if (/Pattern$/.test(parent.type) || parent.type === "RestElement") {
      // a name being bound is not a use; the default value in `{ a = b }` and a computed key are
      if (!(parent.type === "AssignmentPattern" && parent.right === n)) return;
    }
    used.set(n.name, (used.get(n.name) || 0) + 1);
  });

  for (const [name, count] of used) if (!declared.has(name) && !GLOBALS.has(name)) problems.push(`${where}: "${name}" is used ${count}x but is neither declared nor imported`);
  for (const name of imports.keys()) if (!used.has(name)) problems.push(`${where}: "${name}" is imported but never used`);
  return problems;
}

const problems = files(ROOT).flatMap(check);
if (problems.length) {
  console.log(problems.join("\n"));
  process.exit(1);
}
console.log("ok");
