// WCAG contrast check for every theme in src/App.css.
//
//   npm run check:contrast
//
// Reads the [data-theme] palette blocks straight from the CSS (so a new theme
// cannot ship unchecked), and fails if text falls under 4.5:1 on any surface it
// is drawn on, or the moon/ring graphics under 3:1. Control borders
// (--border-light) are held to the same 3:1 bar but only warn: no theme has
// ever met it.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const css = readFileSync(join(root, "App.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const themeTs = readFileSync(join(root, "theme.ts"), "utf8");

// ── Parse palettes ──────────────────────────────────────────────────────────
const palettes = new Map();
for (const [, selector, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
  const ids = selector
    .split(",")
    .map((s) => s.trim().match(/^\[data-theme="([\w-]+)"\]$/)?.[1])
    .filter(Boolean);
  if (ids.length === 0) continue;
  const tokens = {};
  for (const [, name, value] of body.matchAll(/--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;/g)) {
    tokens[name] = value;
  }
  for (const id of ids) palettes.set(id, { ...(palettes.get(id) ?? {}), ...tokens });
}

const registered = [...themeTs.matchAll(/\{\s*id:\s*"([\w-]+)"/g)].map((m) => m[1]);
let failures = 0;
for (const id of registered) {
  if (!palettes.has(id)) {
    console.error(`FAIL  ${id}: listed in theme.ts but has no [data-theme="${id}"] block in App.css`);
    failures++;
  }
}
for (const id of palettes.keys()) {
  if (!registered.includes(id)) {
    console.error(`FAIL  ${id}: has a CSS block but is not listed in THEMES (theme.ts)`);
    failures++;
  }
}

// ── Contrast maths (WCAG 2.x) ──────────────────────────────────────────────
function luminance(hex) {
  let h = hex.slice(1);
  if (h.length === 3) h = [...h].map((c) => c + c).join("");
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const SURFACES = ["bg", "bg-elevated", "bg-panel", "bg-hover", "bg-input"];
const TEXT_CHECKS = [
  // body copy, labels, hints — on every surface
  ...["text", "text-muted", "text-dim"].map((fg) => [fg, SURFACES]),
  // accent as text: links, list markers, active labels
  ["accent-bright", ["bg", "bg-elevated", "bg-panel", "bg-input"]],
  // syntax colours: only ever text inside code blocks, which sit on --bg-input
  ["accent-warm", ["bg-input"]],
  ["aura-1", ["bg-input"]],
  // status words (never colour alone, but the word must still be legible)
  ...["safe", "scoped", "armed"].map((fg) => [fg, ["bg", "bg-elevated", "bg-panel", "bg-hover"]]),
];

// Graphics (3:1, WCAG 1.4.11): the moon is drawn in --accent-warm, and the
// push-to-talk ring uses it on --bg-hover.
const GRAPHIC_CHECKS = [["accent-warm", ["bg", "bg-elevated", "bg-panel", "bg-hover"]]];

const warnings = [];
for (const [id, p] of palettes) {
  const need = (name) => {
    if (!p[name]) {
      console.error(`FAIL  ${id}: missing --${name}`);
      failures++;
      return false;
    }
    return true;
  };
  for (const [fg, surfaces] of TEXT_CHECKS) {
    for (const bg of surfaces) {
      if (!need(fg) || !need(bg)) continue;
      const r = ratio(p[fg], p[bg]);
      if (r < 4.5) {
        console.error(`FAIL  ${id}: --${fg} on --${bg} is ${r.toFixed(2)}:1 (needs 4.5:1)`);
        failures++;
      }
    }
  }
  for (const [fg, surfaces] of GRAPHIC_CHECKS) {
    for (const bg of surfaces) {
      if (!need(fg) || !need(bg)) continue;
      const r = ratio(p[fg], p[bg]);
      if (r < 3) {
        console.error(`FAIL  ${id}: --${fg} on --${bg} is ${r.toFixed(2)}:1 (graphics need 3:1)`);
        failures++;
      }
    }
  }
  if (need("on-accent") && need("accent-bright")) {
    const r = ratio(p["on-accent"], p["accent-bright"]);
    if (r < 4.5) {
      console.error(`FAIL  ${id}: --on-accent on --accent-bright is ${r.toFixed(2)}:1 (needs 4.5:1)`);
      failures++;
    }
  }
  for (const bg of ["bg", "bg-panel", "bg-elevated"]) {
    if (!p["border-light"] || !p[bg]) continue;
    const r = ratio(p["border-light"], p[bg]);
    if (r < 3) warnings.push(`${id}: --border-light on --${bg} is ${r.toFixed(2)}:1 (3:1 for control edges)`);
  }
}

if (warnings.length) {
  console.warn(`\n${warnings.length} control-border warning(s) (not failing):`);
  for (const w of warnings) console.warn(`  warn  ${w}`);
}
console.log(
  `\n${palettes.size} theme(s) checked: ${[...palettes.keys()].join(", ")}` +
    (failures ? `\n${failures} failure(s).` : "\nAll text pairs meet 4.5:1."),
);
process.exit(failures ? 1 : 0);
