#!/usr/bin/env node
// Read-only CLI projection of the same authoritative roster and browser data contracts.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { strictJson, validateRoster, validateOrientation, knownDirectory, loadSource, freshness, pool, profile, restoreSelection, STORAGE_KEY } from "../site/data.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
function file(location, maximum) {
  const stat = fs.statSync(location);
  if (!stat.isFile() || stat.size > maximum) throw new Error("input file type/size limit");
  const raw = fs.readFileSync(location);
  if (raw.length > maximum) throw new Error("input file size limit");
  return raw;
}

try {
  const roster = validateRoster(strictJson(file(path.join(ROOT, "subscriptions.json"), 262144)));
  const args = process.argv.slice(2);
  if (args.length === 1 && args[0] === "--list") {
    console.log(JSON.stringify({ scope: "roster configuration only; no source observations", roster }, null, 2));
  } else if (args.length === 1 && args[0] === "--directory") {
    const orientation = validateOrientation(strictJson(file(path.join(ROOT, "orient.json"), 262144)));
    console.log(JSON.stringify({ schema: "dogg-directory-view/1",
      source: "checked-out orient.json plus canonical subscriptions.json; no network availability scan",
      roster: roster.canonical_url, roster_version: roster.version, generated_utc: orientation.generated_utc,
      ...knownDirectory(roster, orientation) }, null, 2));
  } else {
    let ids = roster.feeds.filter(feed => feed.default).map(feed => feed.id);
    if (args.length === 2 && args[0] === "--feed") {
      ids = [args[1]];
    } else if (args.length === 2 && args[0] === "--profile") {
      const raw = new TextDecoder("utf-8", { fatal: true }).decode(file(args[1], 4096));
      const restored = restoreSelection(roster, { getItem(key) { return key === STORAGE_KEY ? raw : null; } });
      if (!restored.persistent) throw new Error(restored.notice);
      ids = restored.ids;
    } else if (args.length) {
      throw new Error("usage: node tools/follow.mjs [--list | --directory | --feed ID | --profile FILE]");
    }
    profile(roster, ids);
    if (!ids.length) throw new Error("empty profile: no sources observed");
    const observations = new Array(ids.length);
    await pool(ids, async (id, index) => {
      const feed = roster.feeds.find(item => item.id === id);
      const checked = new Date().toISOString();
      try {
        const observation = await loadSource(feed);
        observations[index] = { id, ...freshness(feed, observation), checked_utc: observation.checked_utc,
          record_utc: observation.latest.utc, seq: observation.latest.seq, frame_hash: observation.latest.frame_hash,
          stream_id: feed.stream_id, source_kind: feed.source_kind, source_url: observation.latest_url,
          coverage: observation.coverage, signature_authority: "not-checked" };
      } catch (error) {
        observations[index] = { id, state: "error", checked_utc: checked, record_utc: null,
          error: error.message, source_url: feed.head_url, frames_checked: 0 };
        process.exitCode = 1;
      }
    });
    console.log(JSON.stringify({ schema: "dogg-observations/1", roster: roster.canonical_url,
      roster_version: roster.version, scope: "read-only bounded native observations; not authenticated full-chain verification",
      observations }, null, 2));
  }
} catch (error) {
  console.error(`following refused: ${error.message}`);
  process.exitCode = 1;
}
