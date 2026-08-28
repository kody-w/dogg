#!/usr/bin/env node
// Conformance test for recite.html's in-browser decoder + wear path.
// Run with: NODE_PATH=$HOME/Documents/GitHub/aaa-fps/node_modules node tests/test_recite_js.mjs
//
// 1. Serves the repo (recite.html fetches chants/*.json relatively) with a tiny http
//    server, opens recite.html#selftest and asserts it renders PASS.
// 2. Mints a SEED chant for the markets dimension via `python3 tools/dogg.py seed`,
//    pastes the fixture frame into the page's wear input, and asserts the JS `wear`
//    results equal `python3 tools/dogg.py wear`'s own output for the same chant + frame.

import { spawn, execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const PORT = 8743;
const BASE = `http://127.0.0.1:${PORT}`;

function py(...args) {
  return execFileSync("python3", args, { cwd: ROOT, encoding: "utf8" }).trim();
}

function startServer() {
  const srv = spawn("python3", ["-m", "http.server", String(PORT)], { cwd: ROOT, stdio: "ignore" });
  return srv;
}

async function waitForServer() {
  for (let i = 0; i < 50; i++) {
    try {
      const res = await fetch(`${BASE}/recite.html`);
      if (res.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("http.server never came up");
}

async function main() {
  const srv = startServer();
  let browser;
  try {
    await waitForServer();
    browser = await chromium.launch();
    const page = await browser.newPage();

    // ── 1. self-test ────────────────────────────────────────────────────────
    await page.goto(`${BASE}/recite.html#selftest`);
    await page.waitForFunction(() => document.getElementById("out").dataset.ok !== undefined, null, { timeout: 10000 });
    const selftestOk = await page.getAttribute("#out", "data-ok");
    const selftestHtml = await page.innerHTML("#out");
    assert.equal(selftestOk, "1", `selftest did not PASS:\n${selftestHtml}`);
    console.log("PASS: recite.html#selftest reproduces chants/VECTORS.json");

    // ── 2. wear: seed chant minted via python3, compared against python's own wear ──
    const DIM = "markets:@kody-w/dogg-markets";
    const seedWords = py(
      "tools/dogg.py", "seed", DIM,
      "select", "btc_usd",
      "ratio", "btc_usd", "eth_usd",
      "above", "btc_usd=70000",
      "below", "btc_usd=50000",
      "sum", "btc_usd", "eth_usd",
      "max_of", "btc_usd", "eth_usd",
    ).split(/\s+/);

    const pyWearOut = JSON.parse(
      py("tools/dogg.py", "wear", ...seedWords, "tests/fixture_markets_frame.json")
    );

    await page.goto(`${BASE}/recite.html`);
    await page.fill("#in", seedWords.join(" "));
    await page.dispatchEvent("#in", "change");
    await page.waitForFunction(() => document.getElementById("out").dataset.ok !== undefined, null, { timeout: 10000 });
    const chantOk = await page.getAttribute("#out", "data-ok");
    assert.equal(chantOk, "1", "seed chant failed to decode in the page");

    const frameJson = await execFileSync("cat", [path.join(ROOT, "tests", "fixture_markets_frame.json")], { encoding: "utf8" });
    await page.fill("#frameIn", frameJson);
    await page.dispatchEvent("#frameIn", "input");
    await page.waitForFunction(() => document.getElementById("wearOut").dataset.ok !== undefined, null, { timeout: 10000 });
    const wearOk = await page.getAttribute("#wearOut", "data-ok");
    const wearTileRaw = await page.getAttribute("#wearOut", "data-tile");
    assert.equal(wearOk, "1", `JS wear failed: ${wearTileRaw}`);
    const jsWearOut = JSON.parse(wearTileRaw);

    assert.equal(jsWearOut.dimension, pyWearOut.dimension, "dimension mismatch");
    assert.equal(jsWearOut.tick, pyWearOut.tick, "tick mismatch");
    assert.equal(jsWearOut.frame_hash, pyWearOut.frame_hash, "frame_hash mismatch");
    assert.deepEqual(jsWearOut.program, pyWearOut.program, "program listing mismatch");
    assert.deepEqual(
      Object.keys(jsWearOut.results).sort(),
      Object.keys(pyWearOut.results).sort(),
      "result key set mismatch"
    );
    for (const k of Object.keys(pyWearOut.results)) {
      const want = pyWearOut.results[k];
      const got = jsWearOut.results[k];
      if (typeof want === "number") {
        assert.ok(
          Math.abs(got - want) < 1e-9 * Math.max(1, Math.abs(want)),
          `results[${k}]: got ${got}, want ${want}`
        );
      } else {
        assert.deepEqual(got, want, `results[${k}]: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
      }
    }
    console.log("PASS: JS wear(seed, fixture frame) equals `python3 tools/dogg.py wear`");

    // ── 3. dimension-id refusal: a seed cut for markets refuses a foreign frame ────
    const foreignFrame = JSON.parse(frameJson);
    foreignFrame.stream_id = "world:@kody-w/dogg";
    await page.fill("#frameIn", JSON.stringify(foreignFrame));
    await page.dispatchEvent("#frameIn", "input");
    await page.waitForFunction(
      (prev) => document.getElementById("wearOut").dataset.tile !== prev,
      wearTileRaw,
      { timeout: 10000 }
    );
    const refusalOk = await page.getAttribute("#wearOut", "data-ok");
    const refusalTile = await page.getAttribute("#wearOut", "data-tile");
    assert.equal(refusalOk, "0", `expected the wrong-dimension frame to be refused, got: ${refusalTile}`);
    assert.match(JSON.parse(refusalTile).error, /not for a world:@kody-w\/dogg frame/);
    console.log("PASS: wear refuses a seed worn on the wrong dimension");

    await browser.close();
    srv.kill();
    console.log("\nALL PASS");
  } catch (err) {
    if (browser) await browser.close();
    srv.kill();
    console.error("FAIL:", err.message);
    process.exit(1);
  }
}

main();
