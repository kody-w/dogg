#!/usr/bin/env node
// Existing Chrome + Node built-ins only. Isolated profile, deterministic HTTP fixtures.
import fs from "node:fs";
import path from "node:path";
import { createServer } from "node:http";
import { once } from "node:events";
import { spawn, execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { fixtureChain, NOW } from "./site_fixtures.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.resolve(process.env.DOGG_BROWSER_EVIDENCE || path.join(ROOT, ".site-browser-evidence"));
const CHROME = process.env.CHROME_BIN || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
fs.mkdirSync(OUT, { recursive: true });
const profileDirectory = path.join(OUT, `isolated-chrome-${process.pid}`);
fs.mkdirSync(profileDirectory);
const downloads = path.join(OUT, `downloads-${process.pid}`);
fs.mkdirSync(downloads);
const roster = JSON.parse(fs.readFileSync(path.join(ROOT, "subscriptions.json")));
const fixtures = new Map(), calls = [], assertions = [], errors = [], failed = new Set();
let malformedRoster = false;
for (const feed of roster.feeds) {
  const chain = await fixtureChain(feed.stream_id, {
    count: feed.id === "dogg.thread" ? 6 : 3,
    kind: feed.id === "dogg.world" ? "world.snapshot" : "dogg.observation",
    payload: seq => feed.id === "dogg.world" ? {
      tick: seq, world: { btc_usd: { spot: "79969.955" }, earthquakes_past_hour: { count: seq + 10 } }, sources_failed: [],
    } : {
      tick: seq, note: seq === 0 ? "Historical quote: signed-by-math; full rapp/1; one global chain." :
        'Literal source text: <img src=x onerror="globalThis.__injected=true"> and javascript:alert(1).',
    },
  });
  fixtures.set(feed.id, chain);
}
const orientation = {
  schema: "dogg/0-orient", projection_version: 1, generated_utc: "2026-09-06T13:01:00.000Z",
  subscriptions_url: roster.canonical_url, input_fingerprint: "1".repeat(64),
  tick: { seq: 2, utc: "2026-09-06T13:00:02.000Z", frame_hash: "2".repeat(64) },
  dimensions: [
    ...roster.feeds.filter(feed => ["dogg.world", "dogg.markets", "dogg.planet", "dogg.attention"].includes(feed.id))
      .map(feed => ({ dimension: feed.stream_id, repo: feed.repository, path: feed.path, outlook: feed.purpose })),
    ...Array.from({ length: 16 }, (_, n) => ({ dimension: `fixture-${n}:@kody-w/registered-fixture-${n}`,
      repo: n === 15 ? "javascript:alert(1)" : `kody-w/registered-fixture-${n}`, path: "updates/",
      outlook: "A registered metadata-only fixture. Public availability is unmeasured." })),
  ],
  world: { seq: 2, utc: "2026-09-06T13:00:02.000Z", frame_hash: "3".repeat(64), tick: 2, tick_frame: "2".repeat(64), data: {} },
  sources: { ticks: { count: 3, head_frame: "2".repeat(64) }, world: { count: 3, head_frame: "3".repeat(64) },
    registry: { count: 21, head_frame: "4".repeat(64) } },
  status: { world: { state: "current", last_refresh: "ok", ticks_behind: 0, sources_failed: [] },
    registry: { state: "current", records: 21, dimensions: 20 } },
};
const allowed = new Set(["index.html", "subscriptions.json", "site/app.mjs", "site/data.mjs", "site/style.css"]);
const server = createServer((request, response) => {
  const name = new URL(request.url, "http://localhost").pathname.slice(1) || "index.html";
  if (name === "favicon.ico") { response.writeHead(204); response.end(); return; }
  if (!allowed.has(name)) { response.writeHead(404); response.end("not a test resource"); return; }
  const raw = name === "subscriptions.json" && malformedRoster ? '{"schema":"dogg-subscriptions/1","schema":"dogg-subscriptions/1"}' :
    fs.readFileSync(path.join(ROOT, name));
  response.writeHead(200, { "content-type": name.endsWith(".mjs") ? "text/javascript" :
    name.endsWith(".css") ? "text/css" : name.endsWith(".json") ? "application/json" : "text/html" });
  response.end(raw);
});
server.listen(0, "127.0.0.1");
await once(server, "listening");
const base = `http://127.0.0.1:${server.address().port}`;
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const owned = new Set();
let chrome, socket, session, serial = 0, closing = false;
const waiting = new Map();

function collectDescendants() {
  if (!chrome?.pid) return;
  const rows = execFileSync("ps", ["-A", "-o", "pid=,ppid="], { encoding: "utf8" })
    .trim().split("\n").map(line => line.trim().split(/\s+/).map(Number));
  owned.add(chrome.pid);
  for (let pass = 0; pass < 5; pass += 1) for (const [pid, ppid] of rows) if (owned.has(ppid)) owned.add(pid);
}
function send(method, params = {}, target = session) {
  const id = ++serial;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { waiting.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 20000);
    waiting.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params, ...(target ? { sessionId: target } : {}) }));
  });
}
async function evaluate(expression) {
  const answer = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true, userGesture: true });
  if (answer.exceptionDetails) throw new Error(answer.exceptionDetails.exception?.description || answer.exceptionDetails.text);
  return answer.result.value;
}
async function wait(expression, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await evaluate(expression)) return; await sleep(75); }
  throw new Error(`DOM timeout: ${expression}\n${await evaluate("document.body.innerText.slice(0,5000)")}`);
}
async function navigate(theme = "light") {
  await send("Page.navigate", { url: `${base}/index.html?scoutTheme=${theme}` });
  await wait("document.querySelectorAll('.feed').length===7 && !document.getElementById('refresh').disabled && !document.getElementById('load-history').disabled");
}
async function click(selector) {
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
}
async function idle() { await wait("!document.getElementById('refresh').disabled && !document.getElementById('load-history').disabled"); }
function passed(name) { assertions.push(name); console.log("PASS", name); }

const clockScript = `
  (() => {
    const OriginalDate = Date; let now = ${NOW};
    globalThis.Date = class extends OriginalDate {
      constructor(...args) { super(...(args.length ? args : [now])); }
      static now() { return now; }
    };
    window.__advanceTime = value => { now += value; };
    const interval = window.setInterval, callbacks = [];
    window.setInterval = (fn, ms, ...args) => { callbacks.push(fn); return interval(fn, ms, ...args); };
    window.__runTimers = () => callbacks.forEach(fn => fn());
    window.__testVisibility = "visible";
    Object.defineProperty(document, "visibilityState", { get: () => window.__testVisibility });
  })();
`;
const stopTracking = setInterval(collectDescendants, 500);
let primaryFailure = null;
try {
  chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profileDirectory}`,
    `--disk-cache-dir=${path.join(profileDirectory, "cache")}`, `--crash-dumps-dir=${profileDirectory}`,
    "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update",
    "--disable-sync", "--disable-default-apps", "--no-pings", "about:blank"],
  { stdio: "ignore", env: { ...process.env, TMPDIR: profileDirectory } });
  chrome.on("error", error => errors.push(error.message));
  const portFile = path.join(profileDirectory, "DevToolsActivePort");
  for (let tries = 0; tries < 200 && !fs.existsSync(portFile); tries += 1) {
    if (chrome.exitCode !== null) throw new Error(`Chrome exited ${chrome.exitCode}`);
    await sleep(50);
  }
  assert(fs.existsSync(portFile), "isolated Chrome debug endpoint not ready");
  const [port, endpoint] = fs.readFileSync(portFile, "utf8").trim().split("\n");
  socket = new WebSocket(`ws://127.0.0.1:${port}${endpoint}`);
  socket.addEventListener("message", async event => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const pending = waiting.get(message.id);
      if (!pending) return;
      waiting.delete(message.id); clearTimeout(pending.timer);
      if (message.error) pending.reject(new Error(message.error.message)); else pending.resolve(message.result);
    } else if (message.method === "Runtime.exceptionThrown") {
      errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
    } else if (message.method === "Fetch.requestPaused") {
      const { requestId, request } = message.params;
      calls.push({ url: request.url, method: request.method });
      let code = 200, raw;
      if (request.url === roster.orientation_url) raw = JSON.stringify(orientation);
      else {
        const feed = roster.feeds.find(value => request.url.startsWith(value.records_url));
        if (!feed || failed.has(feed.id)) { code = 503; raw = "fixture unavailable"; }
        else {
          const key = request.url.slice(feed.records_url.length);
          raw = fixtures.get(feed.id).files.get(key);
          if (raw === undefined) { code = 404; raw = "missing fixture"; }
        }
      }
      try {
        await send("Fetch.fulfillRequest", { requestId, responseCode: code,
          responseHeaders: [{ name: "Content-Type", value: "application/json" }, { name: "Access-Control-Allow-Origin", value: "*" }],
          body: Buffer.from(raw).toString("base64") });
      } catch (error) { if (!closing) errors.push(error.message); }
    }
  });
  await new Promise((resolve, reject) => { socket.addEventListener("open", resolve, { once: true }); socket.addEventListener("error", reject, { once: true }); });
  const target = await send("Target.createTarget", { url: "about:blank" }, null);
  session = (await send("Target.attachToTarget", { targetId: target.targetId, flatten: true }, null)).sessionId;
  await send("Page.enable"); await send("Runtime.enable");
  await send("Fetch.enable", { patterns: [{ urlPattern: "https://raw.githubusercontent.com/*" }] });
  await send("Page.addScriptToEvaluateOnNewDocument", { source: clockScript });
  await send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads }, null);
  await send("Emulation.setDeviceMetricsOverride", { width: 1100, height: 900, deviceScaleFactor: 1, mobile: false });
  await navigate();
  assert.equal(errors.length, 0, errors.join("\n"));
  assert.equal(await evaluate("document.getElementById('following-count').textContent"), "2 following");
  assert.equal(await evaluate("document.querySelectorAll('.feed img').length"), 0);
  assert.equal(await evaluate("typeof globalThis.__injected"), "undefined");
  assert.equal(await evaluate("document.querySelector('[href^=\"javascript:\"]')===null"), true);
  passed("cold rendered page: seven feeds, two default follows, no page errors or source markup execution");

  const beforeDirectory = calls.length;
  await click('[data-open="directory"]');
  assert.equal(await evaluate("document.querySelectorAll('.directory-entry').length"), 23);
  assert.match(await evaluate("document.getElementById('directory-status').innerText"), /20 registered dimensions plus 3 core journals/);
  assert.match(await evaluate("document.getElementById('directory-entries').innerText"), /Invalid or incomplete/);
  assert.equal(await evaluate("document.querySelectorAll('#directory-entries a[href^=\"javascript:\"]').length"), 0);
  const directoryTop = await evaluate("document.getElementById('directory').getBoundingClientRect().top + window.scrollY");
  const directoryImage = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
    clip: { x: 0, y: directoryTop, width: 1100, height: 900, scale: 1 } });
  fs.writeFileSync(path.join(OUT, "full-directory-desktop.png"), Buffer.from(directoryImage.data, "base64"));
  await evaluate("document.getElementById('directory-search').value='registered-fixture-15';document.getElementById('directory-search').dispatchEvent(new Event('input'))");
  assert.equal(await evaluate("document.querySelectorAll('.directory-entry').length"), 1);
  await evaluate("document.getElementById('directory-search').value='';document.getElementById('directory-search').dispatchEvent(new Event('input'))");
  assert.equal(calls.length, beforeDirectory, "browsing directory triggered remote record polling");
  await click('[data-directory-feed="dogg.world"]');
  assert.equal(await evaluate("document.getElementById('following-count').textContent"), "1 following");
  await click('[data-directory-feed="dogg.world"]'); await idle();
  assert.equal(await evaluate("document.getElementById('following-count').textContent"), "2 following");
  await click("#directory > summary");
  passed("full 23-source directory keeps 20 registrations visible without polling; starter follow controls stay local");

  await click('[data-feed-id="dogg.planet"] input[type="checkbox"]'); await idle();
  assert.equal(await evaluate("document.getElementById('following-count').textContent"), "3 following");
  await navigate();
  assert.equal(await evaluate("document.getElementById('following-count').textContent"), "3 following");
  await click('[data-feed-id="dogg.planet"] input[type="checkbox"]');
  await click('[data-feed-id="dogg.planet"] input[type="checkbox"]'); await idle();
  assert.equal(await evaluate("JSON.parse(localStorage.getItem('dogg.following.v1')).feed_ids.includes('dogg.planet')"), true);
  passed("follow/unfollow repeated, real localStorage persistence, reload restores private choices");

  await evaluate("document.getElementById('search').value='no-such-feed';document.getElementById('search').dispatchEvent(new Event('input'))");
  assert.equal(await evaluate("document.getElementById('empty').hidden"), false);
  await evaluate("document.getElementById('search').value='';document.getElementById('search').dispatchEvent(new Event('input'))");
  await click("#only-following");
  assert.equal(await evaluate("document.querySelectorAll('.feed:not([hidden])').length"), 3);
  await click("#only-following");
  passed("search empty state and following-only filter work in rendered DOM");

  await click('[data-open="ai"]');
  await evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new Error('denied')}}})");
  await click("#copy-profile");
  await wait("document.getElementById('profile-status').textContent.includes('copy it manually')");
  await evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.__copied=text}}})");
  await click("#copy-profile");
  await wait("document.getElementById('profile-status').textContent.includes('copied locally')");
  assert.equal(await evaluate("JSON.parse(window.__copied).feed_ids.length"), 3);
  await click("#download-profile");
  for (let tries = 0; tries < 100 && !fs.readdirSync(downloads).some(name => name.endsWith(".json")); tries += 1) await sleep(50);
  const download = fs.readdirSync(downloads).find(name => name.endsWith(".json"));
  assert(download, "profile download missing");
  assert.equal(JSON.parse(fs.readFileSync(path.join(downloads, download))).mode, "read-only");
  passed("AI path copy success/denial fallback and real JSON download; no profile upload");

  failed.add("dogg.world");
  await click("#refresh"); await idle();
  assert.match(await evaluate("document.querySelector('[data-feed-id=\"dogg.world\"]').innerText"), /last good shown/);
  assert.equal(await evaluate("document.querySelector('[data-feed-id=\"dogg.world\"] .badge').dataset.state"), "error");
  assert.match(await evaluate("document.querySelector('[data-feed-id=\"dogg.world\"]').innerText"), /79969/);
  failed.clear();
  await click("#refresh"); await idle();
  assert.equal(await evaluate("document.querySelector('[data-feed-id=\"dogg.world\"] .badge').dataset.state"), "fresh");
  assert.equal(await evaluate("document.querySelector('[data-feed-id=\"dogg.world\"]').innerText.includes('A new record arrived')"), false);
  passed("failed refresh retains last-good with error; repeated unchanged source is not a phantom new record");

  const beforeHidden = calls.length;
  await evaluate("window.__testVisibility='hidden';window.__advanceTime(7200000);window.__runTimers()");
  await sleep(150);
  assert.equal(calls.length, beforeHidden);
  await evaluate("window.__testVisibility='visible';window.__runTimers()");
  await idle();
  assert.equal(await evaluate("document.querySelector('[data-feed-id=\"dogg.world\"] .badge').dataset.state"), "stale");
  passed("simulated hidden-page refresh pauses; visible refresh marks aged source stale, not verified green");

  await click("#history > summary"); await click("#load-history");
  await wait("document.querySelectorAll('.history-record').length===6 && !document.getElementById('load-history').disabled");
  assert.match(await evaluate("document.getElementById('history').innerText"), /not current claims/);
  assert.match(await evaluate("document.getElementById('history-records').innerText"), /signed-by-math/);
  assert.equal(await evaluate("document.querySelectorAll('#history-records img').length"), 0);
  await click('[data-open="technical"]');
  assert.equal(await evaluate("document.getElementById('technical').open"), true);
  passed("historical quotes remain verbatim/contextualized; technical path opens; source HTML stays text");

  const screenshots = [];
  for (const theme of ["light", "dark"]) {
    for (const [label, width, height] of [["desktop", 1100, 900], ["mobile", 390, 844]]) {
      await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: label === "mobile" });
      await navigate(theme);
      assert.equal(await evaluate("document.documentElement.dataset.theme"), theme);
      assert(await evaluate("document.documentElement.scrollWidth<=window.innerWidth"), `${theme}/${label} horizontal overflow`);
      const minimumContrast = await evaluate(`(() => {
        const luminance = rgb => {
          const values = rgb.match(/[\\d.]+/g).slice(0,3).map(Number).map(n => {
            const s=n/255;return s<=0.04045?s/12.92:((s+0.055)/1.055)**2.4;
          });return values[0]*0.2126+values[1]*0.7152+values[2]*0.0722;
        };
        return Math.min(...[...document.querySelectorAll('.muted,.metadata,.purpose,.privacy-line,footer')]
          .filter(node=>node.offsetParent!==null).map(node=>{
            let parent=node,background;
            do {background=getComputedStyle(parent).backgroundColor;parent=parent.parentElement;}
            while(parent&&(background==='rgba(0, 0, 0, 0)'||background==='transparent'));
            const a=luminance(getComputedStyle(node).color),b=luminance(background);
            return (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
          }));
      })()`);
      assert(minimumContrast >= 4.5, `${theme}/${label} small-text contrast ${minimumContrast}`);
      const metrics = await send("Page.getLayoutMetrics");
      const name = `${theme}-${label}.png`;
      const image = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
        clip: { x: 0, y: 0, width, height: Math.min(metrics.cssContentSize.height, 8000), scale: 1 } });
      fs.writeFileSync(path.join(OUT, name), Buffer.from(image.data, "base64"));
      screenshots.push(name);
    }
  }
  await evaluate("document.getElementById('refresh').focus()");
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
  assert.equal(await evaluate("document.activeElement.getAttribute('href')"), "#directory");
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
  assert.equal(await evaluate("document.activeElement.id"), "search");
  await evaluate("document.querySelector('[data-feed-id=\"dogg.planet\"] input').focus()");
  for (const expected of [false, true]) {
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
    await idle();
    assert.equal(await evaluate("document.querySelector('[data-feed-id=\"dogg.planet\"] input').checked"), expected);
  }
  passed("light/dark desktop/mobile render without overflow; small text meets 4.5:1; keyboard search/follow work");

  await send("Page.addScriptToEvaluateOnNewDocument", { source: "Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Denied','SecurityError')}})" });
  await navigate();
  assert.equal(await evaluate("document.getElementById('following-count').textContent"), "0 following");
  assert.match(await evaluate("document.getElementById('storage-status').innerText"), /storage unavailable/);
  await click('[data-feed-id="dogg.world"] input[type="checkbox"]'); await idle();
  assert.match(await evaluate("document.getElementById('storage-status').innerText"), /tab only/);
  await navigate();
  assert.equal(await evaluate("document.getElementById('following-count').textContent"), "0 following");
  passed("denied storage is explicit; tab-only following works and is not falsely restored after reload");

  malformedRoster = true;
  await send("Page.navigate", { url: `${base}/index.html` });
  await wait("!document.getElementById('load-error').hidden");
  assert.equal(await evaluate("document.querySelectorAll('.feed').length"), 0);
  assert.match(await evaluate("document.getElementById('load-error').textContent"), /No sources were silently followed/);
  assert(calls.every(call => call.method === "GET"), "non-read source request found");
  assert.equal(errors.length, 0, errors.join("\n"));
  fs.writeFileSync(path.join(OUT, "rendered-error-dom.html"), await evaluate("document.documentElement.outerHTML"));
  passed("malformed roster fails visibly; no empty-source green or uncaught page errors");
  const report = { browser: await send("Browser.getVersion", {}, null), node: process.version,
    scope: "isolated Chrome profile; deterministic intercepted public HTTP fixtures; not user-session or live deployment evidence",
    assertions, screenshots, uncaught_page_errors: errors, source_requests: calls.length, all_source_requests_read_only: true,
    directory_screenshot: "full-directory-desktop.png",
    owned_browser_pids: [...owned] };
  fs.writeFileSync(path.join(OUT, "browser-results.json"), JSON.stringify(report, null, 2) + "\n");
} catch (error) {
  primaryFailure = error;
  fs.writeFileSync(path.join(OUT, "browser-failure.json"), JSON.stringify({
    message: error.message, stack: error.stack, assertions, uncaught_page_errors: errors,
  }, null, 2) + "\n");
  throw error;
} finally {
  closing = true;
  clearInterval(stopTracking);
  collectDescendants();
  if (socket?.readyState === WebSocket.OPEN) {
    await send("Browser.close", {}, null).catch(() => {});
  }
  await sleep(700);
  for (const pid of owned) {
    try { process.kill(pid, 0); process.kill(pid, "SIGTERM"); }
    catch (error) { if (error.code !== "ESRCH") throw error; }
  }
  socket?.close();
  for (const pending of waiting.values()) { clearTimeout(pending.timer); pending.reject(new Error("browser closed")); }
  waiting.clear();
  await new Promise(resolve => server.close(resolve));
  const liveOwned = () => [...owned].filter(pid => {
    try { process.kill(pid, 0); return true; }
    catch (error) { if (error.code === "ESRCH") return false; throw error; }
  });
  let alive = liveOwned();
  const deadline = Date.now() + 5000;
  while (alive.length && Date.now() < deadline) { await sleep(100); alive = liveOwned(); }
  fs.writeFileSync(path.join(OUT, "owned-process-cleanup.json"), JSON.stringify({ owned_pids: [...owned], still_running: alive }, null, 2));
  if (!alive.length) fs.rmSync(profileDirectory, { recursive: true });
  if (!primaryFailure) assert.equal(alive.length, 0, "an owned browser descendant is still running");
  else if (alive.length) console.error("Additional cleanup failure: owned browser descendants", alive);
}
