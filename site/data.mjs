// Bounded native DOGG observation, not a general RAPP/1 Consumer or trust engine.
export const LIMITS = Object.freeze({ json: 262144, head: 16384, epoch: 4194304, total: 8388608,
  depth: 32, values: 20000, feeds: 12, parallel: 3, history: 6, timeout: 8000, sourceTime: 25000 });
export const ROSTER_URL = "https://kody-w.github.io/dogg/subscriptions.json";
export const STORAGE_KEY = "dogg.following.v1";
const FRAME_KEYS = ["spec", "kind", "stream_id", "seq", "utc", "payload", "payload_hash", "frame_hash", "prev", "prev_wave", "sig"];
const FEED_KEYS = ["id", "title", "purpose", "publisher", "repository", "path", "source_kind", "stream_id",
  "head_url", "records_url", "source_url", "default", "audiences", "topics", "refresh_seconds",
  "expected_update_seconds", "stale_after_seconds"];
const HEX = /^[0-9a-f]{64}$/;
const encoder = new TextEncoder();

function need(value, message) { if (!value) throw new Error(message); }
function object(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
function keys(value, expected, label) {
  need(object(value) && Object.keys(value).sort().join("\0") === [...expected].sort().join("\0"), `${label} fields invalid`);
}
function uint(value, min = 0, max = Number.MAX_SAFE_INTEGER) { return Number.isSafeInteger(value) && value >= min && value <= max; }
function text(value, maximum = 512) {
  return typeof value === "string" && value.length > 0 && value.length <= maximum && !/[\u0000-\u001f\u007f]/.test(value);
}
function scalarString(value) {
  for (const char of value) {
    const point = char.codePointAt(0);
    need(point < 0xd800 || point > 0xdfff, "unpaired Unicode surrogate");
  }
}

export function strictJson(input, maximum = LIMITS.json) {
  const bytes = typeof input === "string" ? encoder.encode(input) : new Uint8Array(input);
  need(bytes.length > 0 && bytes.length <= maximum, "JSON empty or exceeds byte limit");
  const source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  need(bytes[0] !== 239, "JSON BOM unsupported");
  let at = 0, values = 0;
  const whitespace = () => { while (/[ \t\r\n]/.test(source[at] || "\0")) at += 1; };
  function string() {
    const start = at++;
    while (at < source.length) {
      const char = source[at++];
      if (char === "\\") { at += 1; continue; }
      if (char === '"') {
        const result = JSON.parse(source.slice(start, at));
        scalarString(result);
        need(encoder.encode(result).length <= 65536, "JSON string exceeds limit");
        return result;
      }
      need(char.charCodeAt(0) >= 32, "invalid JSON string control");
    }
    throw new Error("unterminated JSON string");
  }
  function value(depth) {
    whitespace();
    need(depth <= LIMITS.depth && ++values <= LIMITS.values, "JSON depth/value limit");
    const char = source[at];
    if (char === '"') return string();
    if (char === "{") {
      at += 1; whitespace();
      const result = Object.create(null);
      if (source[at] === "}") { at += 1; return result; }
      for (;;) {
        whitespace();
        need(source[at] === '"' && ++values <= LIMITS.values, "invalid object member");
        const key = string();
        need(!Object.hasOwn(result, key), "duplicate JSON member");
        whitespace(); need(source[at++] === ":", "missing member colon");
        result[key] = value(depth + 1);
        whitespace();
        if (source[at] === "}") { at += 1; return result; }
        need(source[at++] === ",", "invalid object separator");
      }
    }
    if (char === "[") {
      at += 1; whitespace();
      const result = [];
      if (source[at] === "]") { at += 1; return result; }
      for (;;) {
        result.push(value(depth + 1)); whitespace();
        if (source[at] === "]") { at += 1; return result; }
        need(source[at++] === ",", "invalid array separator");
      }
    }
    for (const [literal, result] of [["true", true], ["false", false], ["null", null]]) {
      if (source.startsWith(literal, at)) { at += literal.length; return result; }
    }
    const start = at;
    if (source[at] === "-") at += 1;
    while (/[0-9]/.test(source[at] || "x")) at += 1;
    const token = source.slice(start, at);
    need(token.length <= 17 && /^-?(0|[1-9][0-9]*)$/.test(token) && token !== "-0" &&
      !/[.eE]/.test(source[at] || "x"), "unsupported number token: safe integers only");
    const result = Number(token);
    need(Number.isSafeInteger(result), "integer outside safe profile");
    return result;
  }
  const result = value(1);
  whitespace(); need(at === source.length, "trailing or truncated JSON input");
  return result;
}

function codepointOrder(a, b) {
  const x = [...a], y = [...b];
  for (let i = 0; i < Math.min(x.length, y.length); i += 1) {
    const difference = x[i].codePointAt(0) - y[i].codePointAt(0);
    if (difference) return difference;
  }
  return x.length - y.length;
}

export function canonicalNative(value) {
  if (value === null || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") { need(Number.isSafeInteger(value), "unsupported native number"); return JSON.stringify(value); }
  if (typeof value === "string") { scalarString(value); return JSON.stringify(value); }
  if (Array.isArray(value)) return "[" + value.map(canonicalNative).join(",") + "]";
  need(object(value), "unsupported native value");
  // Native tools/rapp.py sorts Unicode code points, not frozen RAPP/1 UTF-16 JCS.
  return "{" + Object.keys(value).sort(codepointOrder).map(key =>
    JSON.stringify(key) + ":" + canonicalNative(value[key])).join(",") + "}";
}

export async function sha256(bytes) {
  const raw = typeof bytes === "string" ? encoder.encode(bytes) : bytes;
  return [...new Uint8Array(await globalThis.crypto.subtle.digest("SHA-256", raw))]
    .map(byte => byte.toString(16).padStart(2, "0")).join("");
}
export async function H(domain, value) { return sha256(domain + "\n" + canonicalNative(value)); }

export function publicUrl(value) {
  need(typeof value === "string" && value.length <= 1024 && !/[\s\\]/.test(value), "unsafe public URL");
  const url = new URL(value);
  need(url.protocol === "https:" && !url.username && !url.password && !url.port &&
    !url.hash && !url.search && url.href === value &&
    ["raw.githubusercontent.com", "github.com", "kody-w.github.io"].includes(url.hostname),
  "unsupported public URL");
  return value;
}

export function validateRoster(roster) {
  keys(roster, ["schema", "version", "title", "purpose", "canonical_url", "orientation_url", "catalog_code_url", "full_carrier", "feeds"], "roster");
  need(roster.schema === "dogg-subscriptions/1" && uint(roster.version, 1) &&
    text(roster.title, 100) && text(roster.purpose, 500), "unsupported roster");
  need(roster.canonical_url === ROSTER_URL &&
    roster.orientation_url === "https://raw.githubusercontent.com/kody-w/dogg/main/orient.json" &&
    roster.catalog_code_url === "https://github.com/kody-w/rapp-organism" &&
    roster.full_carrier === "withheld", "roster authority/disclosure boundary mismatch");
  need(Array.isArray(roster.feeds) && roster.feeds.length > 0 && roster.feeds.length <= LIMITS.feeds, "roster size limit");
  const ids = new Set();
  for (const feed of roster.feeds) {
    keys(feed, FEED_KEYS, "feed");
    need(text(feed.id, 64) && /^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$/.test(feed.id) && !ids.has(feed.id), "invalid/duplicate feed id");
    ids.add(feed.id);
    need(text(feed.title, 100) && text(feed.purpose, 500) && text(feed.stream_id, 256), "invalid feed description");
    need(typeof feed.repository === "string" && /^[a-z0-9][a-z0-9-]{0,38}\/[a-z0-9][a-z0-9._-]{0,99}$/.test(feed.repository) &&
      feed.publisher === feed.repository.split("/")[0] && typeof feed.path === "string" &&
      /^[a-z][a-z0-9-]*\/$/.test(feed.path), "invalid feed repository/path");
    const base = `https://raw.githubusercontent.com/${feed.repository}/main/${feed.path}`;
    need(publicUrl(feed.head_url) === base + "HEAD.json" && publicUrl(feed.records_url) === base &&
      publicUrl(feed.source_url) === `https://github.com/${feed.repository}/tree/main/${feed.path.slice(0, -1)}`,
    "feed URLs do not bind repository/path");
    need(feed.source_kind === "native-dogg/0" && typeof feed.default === "boolean", "unsupported source kind/default");
    need(Array.isArray(feed.audiences) && feed.audiences.length > 0 && feed.audiences.length <= 3 &&
      new Set(feed.audiences).size === feed.audiences.length &&
      feed.audiences.every(item => ["people", "ai", "developers"].includes(item)), "invalid audience");
    need(Array.isArray(feed.topics) && feed.topics.length > 0 && feed.topics.length <= 6 &&
      new Set(feed.topics).size === feed.topics.length &&
      feed.topics.every(item => text(item, 40) && /^[a-z][a-z0-9-]*$/.test(item)), "invalid topics");
    need(uint(feed.refresh_seconds, 300, 3600), "refresh cadence too fast or invalid");
    need((feed.expected_update_seconds === null && feed.stale_after_seconds === null) ||
      (uint(feed.expected_update_seconds, 60, 604800) && uint(feed.stale_after_seconds, feed.expected_update_seconds, 2592000)),
    "invalid freshness expectations");
  }
  return roster;
}

export function validUtc(value) {
  return typeof value === "string" && /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$/.test(value) &&
    value.slice(0, 4) !== "0000" && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
}

export function validateHead(value, stream) {
  need(object(value) && uint(value.count, 1) && value.stream_id === stream &&
    HEX.test(value.head_frame) && validUtc(value.updated), "missing/empty/invalid source HEAD");
  const epoch = value.epoch_size ?? 288, sealed = value.sealed_epochs ?? 0;
  need(uint(epoch, 1, 512) && uint(sealed, 0, Math.floor(Number.MAX_SAFE_INTEGER / epoch)) &&
    sealed * epoch <= value.count, "invalid epoch layout");
  return { ...value, epoch_size: epoch, sealed_epochs: sealed };
}

function frameShape(frame, seq, stream) {
  keys(frame, FRAME_KEYS, "native frame");
  need(frame.spec === "rapp/1" && uint(frame.seq) && frame.seq === seq && frame.stream_id === stream &&
    text(frame.kind, 129) && /^[a-z0-9]+(?:-[a-z0-9]+)*\.[a-z0-9]+(?:-[a-z0-9]+)*$/.test(frame.kind) &&
    validUtc(frame.utc) && object(frame.payload), "native frame shape/order/stream invalid");
  need(typeof frame.payload_hash === "string" && HEX.test(frame.payload_hash) &&
    typeof frame.frame_hash === "string" && HEX.test(frame.frame_hash) &&
    (frame.prev === null || typeof frame.prev === "string" && HEX.test(frame.prev)), "native hash fields invalid");
  need(frame.prev_wave === null && frame.sig === null, "signed/swarm sources unsupported by this reader");
  need(seq !== 0 || frame.prev === null, "invalid native genesis link");
}

export async function checkFrame(frame, seq, stream) {
  frameShape(frame, seq, stream);
  need(frame.payload_hash === await H("rapp/1:particle", frame.payload), "native payload hash mismatch");
  const preimage = Object.fromEntries(Object.entries(frame).filter(([key]) => !["frame_hash", "sig"].includes(key)));
  need(frame.frame_hash === await H("rapp/1:wave", preimage), "native frame hash mismatch");
}

export async function readPublicBytes(url, { maximum = LIMITS.json, timeout = LIMITS.timeout, fetchImpl = fetch } = {}) {
  need(timeout > 0, "source time budget exceeded");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetchImpl(url, { signal: controller.signal, cache: "no-store",
      credentials: "omit", referrerPolicy: "no-referrer", redirect: "error" });
    need(response.status === 200 && !response.redirected, `source HTTP ${response.status}; full 200 response required`);
    const declared = response.headers.get("content-length");
    need(declared === null || /^[0-9]+$/.test(declared) && Number(declared) <= maximum, "source exceeds declared byte limit");
    need(response.body, "empty response body");
    const reader = response.body.getReader();
    const buffer = new Uint8Array(maximum);
    let size = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        need(size <= maximum, "source exceeds byte limit");
        buffer.set(value, size - value.byteLength);
      }
    } catch (error) {
      await reader.cancel().catch(() => {});
      throw error;
    } finally { reader.releaseLock(); }
    need(size > 0, "empty source response");
    return buffer.slice(0, size);
  } finally { clearTimeout(timer); }
}

export async function loadSource(feed, { fetchImpl = fetch, clock = () => Date.now(), limit = 2 } = {}) {
  need(feed.source_kind === "native-dogg/0" && uint(limit, 1, LIMITS.history), "unsupported read request");
  const deadline = Date.now() + LIMITS.sourceTime;
  let total = 0, requests = 0;
  const containers = [];
  async function read(url, maximum) {
    publicUrl(url);
    need(++requests <= limit + 1, "source request budget exceeded");
    const raw = await readPublicBytes(url, { maximum, fetchImpl, timeout: Math.min(LIMITS.timeout, deadline - Date.now()) });
    total += raw.length; need(total <= LIMITS.total, "source total byte budget exceeded");
    containers.push({ url, bytes: raw.length, sha256: await sha256(raw) });
    return raw;
  }
  const head = validateHead(strictJson(await read(feed.head_url, LIMITS.head)), feed.stream_id);
  const cache = new Map();
  async function record(seq) {
    if (seq < head.sealed_epochs * head.epoch_size) {
      const index = Math.floor(seq / head.epoch_size);
      const url = feed.records_url + `epochs/${index}.jsonl`;
      if (!cache.has(index)) {
        const raw = await read(url, LIMITS.epoch);
        const body = new TextDecoder("utf-8", { fatal: true }).decode(raw);
        const lines = body.split("\n");
        if (lines.at(-1) === "") lines.pop();
        need(lines.length === head.epoch_size && lines.every(line => line.trim().length > 0), "incomplete/extra epoch records");
        const parsed = lines.map(line => strictJson(line));
        parsed.forEach((value, offset) => frameShape(value, index * head.epoch_size + offset, feed.stream_id));
        cache.set(index, parsed);
      }
      return { frame: cache.get(index)[seq % head.epoch_size], url };
    }
    const url = feed.records_url + `${seq}.json`;
    return { frame: strictJson(await read(url, LIMITS.json)), url };
  }
  const start = Math.max(0, head.count - limit), frames = [];
  let latestUrl;
  for (let seq = start; seq < head.count; seq += 1) {
    const { frame, url } = await record(seq);
    await checkFrame(frame, seq, feed.stream_id);
    const previous = frames.at(-1);
    need(!previous || frame.prev === previous.payload_hash && frame.utc >= previous.utc, "native predecessor link mismatch");
    frames.push(frame); latestUrl = url;
  }
  const latest = frames.at(-1);
  need(latest && latest.frame_hash === head.head_frame, "HEAD/latest mismatch; no empty verification");
  need(Date.parse(latest.utc) <= clock() + 120000 && Date.parse(head.updated) <= clock() + 120000,
    "source timestamp is ahead of observer clock");
  need(Date.now() <= deadline, "source time budget exceeded");
  return { head, frames, latest, latest_url: latestUrl, checked_utc: new Date(clock()).toISOString(),
    coverage: { profile: "native-safe-integer/1", frames_checked: frames.length, from_seq: start,
      total_frames: head.count, claim: "bounded-record-hashes-and-adjacent-links; not authenticated full-chain verification",
      containers_fully_read: containers.length, containers } };
}

export function freshness(feed, observation, clock = Date.now()) {
  if (!observation) return { state: "unmeasured", label: "Not checked yet" };
  const seconds = Math.max(0, Math.floor((clock - Date.parse(observation.latest.utc)) / 1000));
  if (feed.stale_after_seconds === null) return { state: "event-driven", label: "Event-driven · no freshness promise", age_seconds: seconds };
  if (seconds <= feed.stale_after_seconds && Array.isArray(observation.latest.payload.sources_failed) &&
    observation.latest.payload.sources_failed.length) {
    return { state: "partial", label: "Partial · some upstream readings unavailable", age_seconds: seconds };
  }
  return { state: seconds > feed.stale_after_seconds ? "stale" : "fresh",
    label: seconds > feed.stale_after_seconds ? "Stale · update overdue" : "Fresh within this feed's target", age_seconds: seconds };
}

export function validateOrientation(value, clock = Date.now()) {
  need(object(value) && value.schema === "dogg/0-orient" && value.projection_version === 1 &&
    value.subscriptions_url === ROSTER_URL && validUtc(value.generated_utc) &&
    typeof value.input_fingerprint === "string" && HEX.test(value.input_fingerprint), "unsupported derived view");
  need(object(value.tick) && uint(value.tick.seq) && validUtc(value.tick.utc) &&
    typeof value.tick.frame_hash === "string" && HEX.test(value.tick.frame_hash) &&
    Date.parse(value.tick.utc) <= clock + 120000, "invalid derived tick");
  need(object(value.sources?.ticks) && uint(value.sources.ticks.count, 1) &&
    value.sources.ticks.count === value.tick.seq + 1 && value.sources.ticks.head_frame === value.tick.frame_hash, "derived tick/head mismatch");
  need(Array.isArray(value.dimensions) && value.dimensions.length <= 4096 &&
    value.dimensions.every(item => object(item) && text(item.dimension, 256)) &&
    new Set(value.dimensions.map(item => item.dimension)).size === value.dimensions.length, "invalid derived dimensions");
  const world = value.status?.world, registry = value.status?.registry;
  need(object(world) && ["current", "stale", "partial", "error"].includes(world.state) &&
    ["not-attempted", "ok", "failed"].includes(world.last_refresh), "invalid derived world status");
  need(object(registry) && ["current", "error"].includes(registry.state), "invalid derived registry status");
  if (registry.state === "current") {
    need(uint(registry.records, 1, 4096) && registry.dimensions === value.dimensions.length &&
      object(value.sources.registry) && value.sources.registry.count === registry.records &&
      typeof value.sources.registry.head_frame === "string" && HEX.test(value.sources.registry.head_frame), "derived registry/head mismatch");
  }
  if (world.state !== "error") {
    const record = value.world;
    need(object(record) && uint(record.seq) && uint(record.tick, 0, value.tick.seq) && validUtc(record.utc) &&
      object(record.data) && typeof record.frame_hash === "string" && HEX.test(record.frame_hash) &&
      typeof record.tick_frame === "string" && HEX.test(record.tick_frame) &&
      object(value.sources.world) && value.sources.world.count === record.seq + 1 &&
      value.sources.world.head_frame === record.frame_hash, "invalid derived world/head");
    need(world.ticks_behind === value.tick.seq - record.tick && Array.isArray(world.sources_failed) &&
      world.sources_failed.length <= 128 && world.sources_failed.every(item => text(item, 100)), "invalid derived world coverage");
    if (record.tick === value.tick.seq) {
      need(record.tick_frame === value.tick.frame_hash &&
        world.state === (world.sources_failed.length ? "partial" : "current"), "invalid world alignment status");
    } else need(world.state === "stale", "old world must be marked stale");
  }
  return value;
}

export function knownDirectory(roster, orientation = null) {
  const entries = new Map();
  for (const item of orientation?.dimensions || []) {
    const starter = roster.feeds.find(feed => feed.stream_id === item.dimension);
    let sourceUrl = null, metadataError = null;
    const repository = typeof item.repo === "string" ? item.repo : "";
    const sourcePath = typeof item.path === "string" ? item.path : "";
    try {
      need(/^[a-z0-9][a-z0-9-]{0,38}\/[a-z0-9][a-z0-9._-]{0,99}$/.test(repository) &&
        /^[a-z][a-z0-9-]*\/$/.test(sourcePath), "invalid registered repository/path");
      sourceUrl = publicUrl(`https://github.com/${repository}/tree/main/${sourcePath.slice(0, -1)}`);
    } catch { metadataError = "Invalid or incomplete registry source metadata; no navigation or record fetch enabled."; }
    if (starter && (repository !== starter.repository || sourcePath !== starter.path)) {
      metadataError = "Registry target differs from the curated source. The starter source remains separate; no automatic adoption.";
    }
    entries.set(item.dimension, {
      stream_id: item.dimension, title: starter?.title || repository || item.dimension,
      purpose: starter?.purpose || (typeof item.outlook === "string" ? item.outlook.slice(0, 500) : "No purpose declared in this registration."),
      publisher: starter?.publisher || (sourceUrl ? repository.split("/")[0] : "unmeasured"),
      repository: starter?.repository || repository, path: starter?.path || sourcePath,
      registry_target: { repository, path: sourcePath }, source_url: starter?.source_url || sourceUrl,
      source_kind: starter?.source_kind || "unmeasured; registry listing only",
      starter_id: starter?.id || null, registered: true, core_journal: false, metadata_error: metadataError,
      availability: "unmeasured",
    });
  }
  for (const feed of roster.feeds) {
    if (entries.has(feed.stream_id)) continue;
    entries.set(feed.stream_id, {
      stream_id: feed.stream_id, title: feed.title, purpose: feed.purpose, publisher: feed.publisher,
      repository: feed.repository, path: feed.path, source_url: feed.source_url, source_kind: feed.source_kind,
      starter_id: feed.id, registered: false,
      core_journal: feed.repository === "kody-w/dogg" && ["ticks/", "frames/", "notary/"].includes(feed.path),
      metadata_error: null, availability: "unmeasured",
    });
  }
  return {
    scope: "metadata directory from the public registry snapshot plus canonical starter roster; not availability or trust",
    registered_dimensions: orientation ? orientation.dimensions.length : null,
    registry_state: orientation?.status.registry.state || "unavailable",
    registry_source: orientation?.sources.registry || null,
    additional_core_journals: [...entries.values()].filter(entry => entry.core_journal).length,
    additional_curated_sources: [...entries.values()].filter(entry => !entry.registered && !entry.core_journal).length,
    starter_feeds: roster.feeds.length, known_sources: entries.size,
    entries: [...entries.values()].sort((a, b) => a.title.localeCompare(b.title)),
  };
}

export function reconcile(previous, { observation, error, attempted = new Date().toISOString() }) {
  const old = previous?.observation;
  if (observation && old) {
    const before = old.latest, after = observation.latest;
    if (after.seq < before.seq || (after.seq === before.seq && after.frame_hash !== before.frame_hash)) {
      error = "Source head rolled back or changed at the same sequence"; observation = null;
    } else if (after.seq === before.seq + 1 &&
      (after.prev !== before.payload_hash || observation.frames[0]?.frame_hash !== before.frame_hash)) {
      error = "New record does not continue the last observed head"; observation = null;
    }
  }
  if (error || !observation) return { ...previous, status: "error", error: error || "Source unavailable",
    attempted_utc: attempted, changed: false, observation: old || null };
  return { status: "ok", observation, attempted_utc: attempted, error: null,
    changed: Boolean(old && old.latest.frame_hash !== observation.latest.frame_hash),
    gap_unchecked: old ? Math.max(0, observation.latest.seq - old.latest.seq - 1) : 0 };
}

export async function pool(items, worker, concurrency = LIMITS.parallel) {
  need(uint(concurrency, 1, LIMITS.parallel), "concurrency limit");
  let cursor = 0;
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    for (;;) {
      const index = cursor++;
      if (index >= items.length) return;
      await worker(items[index], index);
    }
  }));
}

export function profile(roster, ids) {
  const chosen = new Set(ids);
  need([...chosen].every(id => roster.feeds.some(feed => feed.id === id)), "unknown selected feed");
  return { schema: "dogg-following/1", roster: ROSTER_URL, roster_version: roster.version,
    feed_ids: roster.feeds.filter(feed => chosen.has(feed.id)).map(feed => feed.id), mode: "read-only" };
}

export function restoreSelection(roster, storage) {
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (raw === null) return { ids: roster.feeds.filter(feed => feed.default).map(feed => feed.id), persistent: true, notice: "Choices stay in this browser. Nothing is uploaded." };
    const value = strictJson(raw, 4096);
    keys(value, ["schema", "roster", "roster_version", "feed_ids", "mode"], "saved profile");
    need(value.schema === "dogg-following/1" && value.roster === ROSTER_URL && uint(value.roster_version, 1) &&
      value.mode === "read-only" && Array.isArray(value.feed_ids) && value.feed_ids.length <= LIMITS.feeds &&
      new Set(value.feed_ids).size === value.feed_ids.length, "invalid saved profile");
    profile(roster, value.feed_ids);
    return { ids: value.feed_ids, persistent: true, notice: "Restored your browser-only choices. Nothing is uploaded." };
  } catch (error) {
    const unavailable = error?.name === "SecurityError" || error?.name === "QuotaExceededError";
    return { ids: [], persistent: false, notice: unavailable
      ? "Browser storage unavailable. Following works for this tab only; nothing is uploaded."
      : "Saved choices could not be read. No feeds were followed automatically; choose again for this tab." };
  }
}

export function saveSelection(roster, ids, storage) {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(profile(roster, ids)));
    return { persistent: true, notice: "Choices saved only in this browser. Nothing is uploaded." };
  } catch {
    return { persistent: false, notice: "Browser storage unavailable. Choices last for this tab only; nothing is uploaded." };
  }
}

export function summary(observation) {
  const payload = observation.latest.payload;
  if (object(payload.world)) {
    const facts = [];
    if (typeof payload.world.btc_usd?.spot === "string") facts.push("Bitcoin USD " + payload.world.btc_usd.spot.slice(0, 40));
    if (uint(payload.world.earthquakes_past_hour?.count)) facts.push(payload.world.earthquakes_past_hour.count + " earthquakes in the source's past-hour window");
    if (facts.length) return facts.join(" · ");
  }
  for (const key of ["summary", "note", "text", "title", "outlook", "message"]) {
    if (typeof payload[key] === "string") return payload[key].slice(0, 240);
  }
  return `Latest ${observation.latest.kind} record. Open the record for the publisher's full observations.`;
}

export function changeSummary(observation) {
  const previous = observation.frames.at(-2), current = observation.latest;
  if (!previous) return "First recorded entry; no predecessor is available.";
  const a = object(previous.payload.world) ? previous.payload.world : previous.payload;
  const b = object(current.payload.world) ? current.payload.world : current.payload;
  const ignored = new Set(["tick", "tick_frame", "beat_utc", "fetched_utc", "utc", "minted_by"]);
  const changed = [...new Set([...Object.keys(a), ...Object.keys(b)])].filter(key =>
    !ignored.has(key) && canonicalNative(a[key] ?? null) !== canonicalNative(b[key] ?? null));
  return changed.length ? `${changed.length} observation field${changed.length === 1 ? "" : "s"} changed since the previous record.`
    : "No non-clock observation fields changed since the previous record.";
}
