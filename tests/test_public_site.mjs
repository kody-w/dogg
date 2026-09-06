import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { strictJson, canonicalNative, H, validateRoster, validateOrientation, knownDirectory, loadSource, freshness, reconcile,
  publicUrl, readPublicBytes, pool, profile, restoreSelection, saveSelection, LIMITS, STORAGE_KEY } from "../site/data.mjs";
import { fixtureChain, fixtureFetch, NOW } from "./site_fixtures.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const bytes = fs.readFileSync(path.join(ROOT, "subscriptions.json"));
const roster = validateRoster(strictJson(bytes));
const feed = roster.feeds.find(value => value.id === "dogg.ticks");
const options = (files, calls) => ({ clock: () => NOW, fetchImpl: fixtureFetch(feed, files, calls) });
const clone = value => JSON.parse(JSON.stringify(value));

test("one authoritative curated roster binds real local streams and exact public endpoints", () => {
  assert.equal(roster.feeds.length, 7);
  assert.equal(new Set(roster.feeds.map(value => value.publisher)).size, 2);
  for (const value of roster.feeds) {
    if (value.repository === "kody-w/dogg") {
      const head = JSON.parse(fs.readFileSync(path.join(ROOT, value.path, "HEAD.json")));
      assert.equal(value.stream_id, head.stream_id);
    }
  }
  const schema = strictJson(fs.readFileSync(path.join(ROOT, "subscriptions.schema.json")));
  assert.deepEqual(Object.keys(schema.properties).sort(), Object.keys(roster).sort());
  assert.deepEqual(schema.properties.feeds.items.required.sort(), Object.keys(feed).sort());
});

test("unsafe/duplicate roster IDs, URLs, cadence, source kinds and raw-carrier activation refuse", () => {
  const changes = [
    value => value.feeds.push(clone(value.feeds[0])),
    value => value.feeds[0].head_url = "javascript:alert(1)",
    value => value.feeds[0].head_url = "https://raw.githubusercontent.com.evil.invalid/a",
    value => value.feeds[0].head_url += "?token=secret",
    value => value.feeds[0].path = "../private/",
    value => value.feeds[0].publisher = "other",
    value => value.feeds[0].refresh_seconds = 1,
    value => value.feeds[0].stale_after_seconds = null,
    value => value.feeds[0].source_kind = "rapp/1",
    value => value.full_carrier = "download",
    value => value.feeds = [],
  ];
  changes.forEach(change => { const value = clone(roster); change(value); assert.throws(() => validateRoster(value)); });
  for (const url of ["javascript:alert(1)", "http://github.com/a", "https://user:pass@github.com/a",
    "https://github.com/a\" onclick=\"x", "https://github.com/a#script", "https://github.com/a?x=1",
    "https://github.com\\@evil.invalid/a", " https://github.com/a"]) assert.throws(() => publicUrl(url));
});

test("strict native parser rejects duplicates, lost number tokens, malformed/truncated and oversized JSON", () => {
  for (const text of ['{"x":1,"x":2}', '{"x":1,"\\u0078":1}', '{"seq":0.0}', '{"seq":0e0}', '{"seq":-0}',
    '{"seq":9007199254740993}', '{"seq":NaN}', '{"x":1}junk', '{"x":', '{"x":"\\ud800"}',
    '{"x":"a\nb"}', "[".repeat(33) + "0" + "]".repeat(33), "\ufeff{}",
    "[" + "0,".repeat(20001) + "0]"]) assert.throws(() => strictJson(text), text.slice(0, 60));
  assert.throws(() => strictJson(new Uint8Array([255, 123, 125])));
  assert.throws(() => strictJson(" ".repeat(LIMITS.json + 1)));
  const value = strictJson('{"__proto__":{"polluted":true},"x":[null,false,-1]}');
  assert.equal(Object.getPrototypeOf(value), null);
  assert.equal({}.polluted, undefined);
});

test("native code-point canonicalization matches the actual Python native core, not full RAPP1 JCS", async () => {
  const payload = { "\ue000": 1, "😀": 2, z: "quotes \" and \\", a: -3 };
  const python = spawnSync("python3", ["-c",
    "import sys,json;sys.path.insert(0,'tools');import rapp;r=json.load(sys.stdin);print(rapp.canonical(r));print(rapp.H('rapp/1:particle',r))"],
  { cwd: ROOT, input: JSON.stringify(payload), encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  assert.equal(python.status, 0, python.stderr);
  const [canonical, hash] = python.stdout.trimEnd().split("\n");
  assert.equal(canonicalNative(payload), canonical);
  assert.equal(await H("rapp/1:particle", payload), hash);
});

test("derived projection has explicit shape/alignment and does not promote malformed or stale world status", () => {
  const view = strictJson(fs.readFileSync(path.join(ROOT, "orient.json")));
  validateOrientation(view);
  for (const change of [
    value => value.tick.frame_hash = "bad",
    value => value.sources.ticks.count = 0,
    value => value.status.world.state = "fresh",
    value => value.world.tick -= 1,
    value => value.status.registry.dimensions += 1,
    value => value.dimensions.push(value.dimensions[0]),
    value => value.status.world = null,
  ]) {
    const bad = clone(view); change(bad); assert.throws(() => validateOrientation(bad));
  }
});

test("full known directory accounts for all registrations separately from starters and defaults", () => {
  const view = validateOrientation(strictJson(fs.readFileSync(path.join(ROOT, "orient.json"))));
  const directory = knownDirectory(roster, view);
  const registered = new Set(view.dimensions.map(item => item.dimension));
  const expected = new Set([...registered, ...roster.feeds.map(item => item.stream_id)]);
  assert.equal(directory.registered_dimensions, registered.size);
  assert.equal(directory.additional_core_journals, expected.size - registered.size);
  assert.equal(directory.known_sources, expected.size);
  assert.equal(directory.entries.filter(entry => entry.registered).length, registered.size);
  assert.deepEqual(new Set(directory.entries.map(item => item.stream_id)), expected);
  assert.equal(directory.entries.filter(entry => entry.starter_id).length, 7);
  assert.equal(roster.feeds.filter(entry => entry.default).length, 2);
  assert(view.dimensions.every(item => directory.entries.some(entry => entry.stream_id === item.dimension)));
  assert(directory.entries.every(entry => entry.availability === "unmeasured"));
  const unavailable = knownDirectory(roster);
  assert.equal(unavailable.registry_state, "unavailable");
  assert.equal(unavailable.registered_dimensions, null);
  assert.equal(unavailable.known_sources, 7);
});

test("unknown and invalid directory entries remain explicit and never become unsafe links", () => {
  const view = clone(strictJson(fs.readFileSync(path.join(ROOT, "orient.json"))));
  view.dimensions.push({ dimension: "unknown:@example/feed", repo: "example/unknown-feed",
    path: "updates/", outlook: "Availability is not measured." });
  view.dimensions.push({ dimension: "invalid:@example/feed", repo: "javascript:alert(1)",
    path: "../private/", outlook: "<img src=x onerror=alert(1)>" });
  view.status.registry.state = "error";
  const directory = knownDirectory(roster, view);
  const expected = new Set([
    ...view.dimensions.map(item => item.dimension), ...roster.feeds.map(item => item.stream_id),
  ]);
  assert.equal(directory.known_sources, expected.size);
  assert.equal(directory.registry_state, "error");
  const unknown = directory.entries.find(entry => entry.stream_id === "unknown:@example/feed");
  assert.equal(unknown.availability, "unmeasured");
  assert.equal(unknown.starter_id, null);
  const invalid = directory.entries.find(entry => entry.stream_id === "invalid:@example/feed");
  assert.equal(invalid.source_url, null);
  assert.match(invalid.metadata_error, /Invalid/);
  assert.equal(invalid.purpose, "<img src=x onerror=alert(1)>");
});

test("latest plus predecessor reads are bounded, explicit and raw-byte-hashed", async () => {
  const fixture = await fixtureChain(feed.stream_id), calls = [];
  const observation = await loadSource(feed, options(fixture.files, calls));
  assert.equal(observation.latest.seq, 2);
  assert.equal(observation.coverage.frames_checked, 2);
  assert.equal(observation.coverage.total_frames, 3);
  assert.equal(observation.coverage.from_seq, 1);
  assert.equal(calls.length, 3);
  assert.equal(observation.coverage.containers.length, 3);
  assert(observation.coverage.containers.every(value => /^[a-f0-9]{64}$/.test(value.sha256)));
  assert(calls.every(value => value.options.credentials === "omit" && value.options.redirect === "error" &&
    value.options.referrerPolicy === "no-referrer" && !value.url.includes("?")));
});

test("HEAD/epoch/tail boundary works and whole epoch ordering/truncation is checked", async () => {
  const fixture = await fixtureChain(feed.stream_id, { sealed: 1 }), calls = [];
  const observation = await loadSource(feed, options(fixture.files, calls));
  assert.equal(observation.coverage.frames_checked, 2);
  assert(calls.some(value => value.url.endsWith("epochs/0.jsonl")));
  const original = fixture.files.get("epochs/0.jsonl");
  for (const changed of [original.trimEnd().split("\n").reverse().join("\n") + "\n",
    original.trimEnd().split("\n")[0] + "\n", original + "\n", original + "{}\n",
    original.replace('"seq":0', '"seq":0.0'), original.replace('"seq":0', '"seq":0,"seq":0'),
    original.replace('"kind":"tick.anchor"', '"not_kind":"tick.anchor"')]) {
    fixture.files.set("epochs/0.jsonl", changed);
    await assert.rejects(loadSource(feed, options(fixture.files)));
  }
});

test("single genesis has one nonzero checked frame; empty/missing HEAD never passes", async () => {
  const fixture = await fixtureChain(feed.stream_id, { count: 1 });
  assert.equal((await loadSource(feed, options(fixture.files))).coverage.frames_checked, 1);
  fixture.files.set("HEAD.json", JSON.stringify({ ...fixture.head, count: 0 }));
  await assert.rejects(loadSource(feed, options(fixture.files)));
  fixture.files.delete("HEAD.json");
  await assert.rejects(loadSource(feed, options(fixture.files)), /HTTP 404/);
});

test("invalid heads, hashes, streams, signatures, order and missing frames fail closed", async () => {
  const fixture = await fixtureChain(feed.stream_id);
  const originalHead = fixture.files.get("HEAD.json"), originalFrame = fixture.files.get("2.json");
  for (const update of [{ count: true }, { count: 4 }, { stream_id: "other" }, { head_frame: "0".repeat(64) },
    { sealed_epochs: 9 }, { epoch_size: 0 }, { updated: "2030-01-01T00:00:00.000Z" }]) {
    fixture.files.set("HEAD.json", JSON.stringify({ ...fixture.head, ...update }));
    await assert.rejects(loadSource(feed, options(fixture.files)));
  }
  fixture.files.set("HEAD.json", originalHead);
  for (const update of [{ seq: 1 }, { payload_hash: "0".repeat(64) }, { frame_hash: "0".repeat(64) },
    { stream_id: "other" }, { sig: "not-a-signature" }, { prev: "0".repeat(64) }, { utc: "2026-02-30T00:00:00.000Z" }]) {
    fixture.files.set("2.json", JSON.stringify({ ...fixture.frames[2], ...update }));
    await assert.rejects(loadSource(feed, options(fixture.files)));
  }
  fixture.files.set("2.json", originalFrame);
  fixture.files.delete("1.json");
  await assert.rejects(loadSource(feed, options(fixture.files)), /HTTP 404/);
});

test("HTTP partial/error responses, empty bodies, redirects and excessive bodies never prefix-verify", async () => {
  for (const response of [new Response("{}", { status: 206 }), new Response("{}", { status: 500 }),
    new Response("", { status: 200 }), new Response("x".repeat(30), { status: 200 }),
    new Response("{}", { status: 200, headers: { "content-length": "999" } })]) {
    await assert.rejects(readPublicBytes(feed.head_url, { maximum: 16, fetchImpl: async () => response }));
  }
  await assert.rejects(readPublicBytes(feed.head_url, { timeout: 0 }));
  await assert.rejects(readPublicBytes(feed.head_url, { timeout: 10, fetchImpl: (_url, { signal }) =>
    new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(new DOMException("Timed out", "AbortError")))) }));
  const bad = { status: 200, redirected: true, headers: new Headers(), body: new ReadableStream() };
  await assert.rejects(readPublicBytes(feed.head_url, { fetchImpl: async () => bad }));
});

test("fresh, stale, event-driven and partial statuses are separate from integrity coverage", async () => {
  const fixture = await fixtureChain(feed.stream_id);
  const observation = await loadSource(feed, options(fixture.files));
  assert.equal(freshness(feed, observation, NOW).state, "fresh");
  assert.equal(freshness(feed, observation, NOW + 7200000).state, "stale");
  assert.equal(freshness(roster.feeds.find(value => value.id === "dogg.thread"), observation, NOW).state, "event-driven");
  assert.equal(freshness(feed, null, NOW).state, "unmeasured");
  const partial = clone(observation); partial.latest.payload.sources_failed = ["api"];
  assert.equal(freshness(feed, partial, NOW).state, "partial");
});

test("failed refresh preserves last-good, same head is a no-op, rollback/fork is not accepted", async () => {
  const fixture = await fixtureChain(feed.stream_id);
  const observation = await loadSource(feed, options(fixture.files));
  const initial = reconcile(null, { observation });
  const repeated = reconcile(initial, { observation: clone(observation) });
  assert.equal(repeated.changed, false);
  const failure = reconcile(initial, { error: "HTTP 503" });
  assert.equal(failure.status, "error");
  assert.equal(failure.observation, observation);
  const rollback = clone(observation); rollback.latest.seq -= 1;
  assert.equal(reconcile(initial, { observation: rollback }).status, "error");
  const fork = clone(observation); fork.latest.frame_hash = "0".repeat(64);
  assert.equal(reconcile(initial, { observation: fork }).observation, observation);
});

test("private choices are local-only, portable, bounded and explicit when storage is denied", () => {
  const storage = new Map();
  const local = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
  assert.deepEqual(restoreSelection(roster, local).ids, ["dogg.world", "dogg.thread"]);
  assert.equal(saveSelection(roster, ["dogg.planet"], local).persistent, true);
  assert.deepEqual(restoreSelection(roster, local).ids, ["dogg.planet"]);
  const saved = strictJson(storage.get(STORAGE_KEY));
  assert.equal(saved.mode, "read-only");
  assert.equal(saved.roster, roster.canonical_url);
  const denied = { getItem() { throw new DOMException("Denied", "SecurityError"); }, setItem() { throw new Error("Denied"); } };
  assert.deepEqual(restoreSelection(roster, denied).ids, []);
  assert.match(saveSelection(roster, [], denied).notice, /tab only/);
  storage.set(STORAGE_KEY, JSON.stringify({ ...profile(roster, []), feed_ids: ["unknown"] }));
  assert.equal(restoreSelection(roster, local).persistent, false);
  storage.set(STORAGE_KEY, '{"schema":"dogg-following/1","schema":"dogg-following/1"}');
  assert.deepEqual(restoreSelection(roster, local).ids, []);
  assert.throws(() => profile(roster, ["javascript:alert(1)"]));
});

test("source pool limits concurrency and one failure can be recorded without dropping other sources", async () => {
  let active = 0, maximum = 0;
  const seen = [];
  await pool([0, 1, 2, 3, 4, 5, 6], async value => {
    active += 1; maximum = Math.max(maximum, active);
    await new Promise(resolve => setTimeout(resolve, 3));
    seen.push(value); active -= 1;
  });
  assert.equal(maximum, 3);
  assert.equal(seen.length, 7);
});

test("HTML offers all audience paths and never interpolates source HTML or URL markup", () => {
  const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
  for (const label of ["Public change journals", "Read &amp; follow", "Use with my AI", "Technical details",
    "Historical source", "withheld", "No account or API key", "localStorage"]) {
    if (label === "Historical source") assert.match(html, /historical source quotes/);
    else assert(html.includes(label), label);
  }
  const app = fs.readFileSync(path.join(ROOT, "site/app.mjs"), "utf8");
  assert(!/innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(/.test(app));
  assert(app.includes("textContent"));
  assert(!html.includes("https://kody-w.github.io/rapp-organism/"));
});
