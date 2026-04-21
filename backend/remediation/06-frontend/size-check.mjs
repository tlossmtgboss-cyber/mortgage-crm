#!/usr/bin/env node
/**
 * 06-frontend/size-check.mjs
 *
 * Enforces bundle size budgets. Fails CI if any chunk exceeds its budget.
 * Run after `vite build`.
 *
 * Drop-in: frontend/scripts/size-check.mjs
 * Add to package.json: "size-check": "node scripts/size-check.mjs"
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

// Budgets in KB (gzipped). Breach = CI fail.
const BUDGETS = {
  // Initial load chunks
  "index": 400,
  "vendor-react": 50,
  "vendor-ui": 120,
  "vendor-data": 80,
  "vendor-misc": 200,

  // Feature chunks (loaded on demand, but still cap)
  "app-pipeline": 500,
  "app-ai": 500,
  "app-voice": 500,
  "app-borrower": 400,
  "app-admin": 400,
  "app-docs": 400,

  // Heavy vendor chunks — used only where needed
  "vendor-three": 800,
  "vendor-charts": 400,
  "vendor-gsap": 300,
  "vendor-pdf": 500,
  "vendor-editor": 800,
};

// Total initial load budget (KB gzipped) — main + vendor-react + vendor-ui + vendor-data
const INITIAL_BUDGET_KB = 800;

const DIST = "./dist/assets";

function gzipSizeKB(path) {
  const raw = readFileSync(path);
  return gzipSync(raw, { level: 9 }).length / 1024;
}

function matchBudget(filename) {
  // filename format: "name-hash.js" — strip hash
  const stem = filename.replace(/-[a-zA-Z0-9_-]+\.js$/, "");
  if (BUDGETS[stem] !== undefined) return { name: stem, budget: BUDGETS[stem] };
  // Fall back to prefix match
  for (const key of Object.keys(BUDGETS)) {
    if (stem.startsWith(key)) return { name: key, budget: BUDGETS[key] };
  }
  return null;
}

function main() {
  let files;
  try {
    files = readdirSync(DIST).filter((f) => f.endsWith(".js"));
  } catch (e) {
    console.error(`!! ${DIST} not found. Did you run \`npm run build\` first?`);
    process.exit(1);
  }

  const results = [];
  let initialSum = 0;
  let violations = 0;

  for (const file of files) {
    const path = join(DIST, file);
    const rawKB = statSync(path).size / 1024;
    const gzipKB = gzipSizeKB(path);
    const match = matchBudget(file);

    const row = {
      file,
      raw: rawKB,
      gzip: gzipKB,
      budget: match?.budget ?? null,
      over: match ? gzipKB - match.budget : null,
    };
    results.push(row);

    // Initial load = main index chunk + core vendor chunks
    if (match && ["index", "vendor-react", "vendor-ui", "vendor-data"].includes(match.name)) {
      initialSum += gzipKB;
    }

    if (match && gzipKB > match.budget) violations++;
  }

  // Print report
  console.log("\n==> Bundle size report");
  console.log(
    `${"file".padEnd(45)} ${"raw".padStart(10)} ${"gzip".padStart(10)} ${"budget".padStart(10)} ${"status".padStart(10)}`,
  );
  console.log("-".repeat(90));
  for (const r of results.sort((a, b) => b.gzip - a.gzip)) {
    const status =
      r.budget === null ? "—" : r.over > 0 ? `+${r.over.toFixed(0)}KB` : "ok";
    console.log(
      `${r.file.padEnd(45)} ${r.raw.toFixed(1).padStart(8)}KB ${r.gzip.toFixed(1).padStart(8)}KB ${
        r.budget ? `${r.budget}KB`.padStart(10) : "—".padStart(10)
      } ${status.padStart(10)}`,
    );
  }

  console.log("-".repeat(90));
  console.log(`Initial load (gzip): ${initialSum.toFixed(1)}KB / ${INITIAL_BUDGET_KB}KB budget`);

  if (initialSum > INITIAL_BUDGET_KB) {
    console.error(`\n!! Initial load exceeds budget by ${(initialSum - INITIAL_BUDGET_KB).toFixed(1)}KB`);
    violations++;
  }

  if (violations > 0) {
    console.error(`\n!! ${violations} budget violation(s). Failing build.`);
    process.exit(1);
  }

  console.log("\n==> All budgets within limits.");
}

main();
