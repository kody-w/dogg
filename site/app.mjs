import { strictJson, validateRoster, validateOrientation, knownDirectory, readPublicBytes, loadSource, freshness, reconcile,
  restoreSelection, saveSelection, profile, summary, changeSummary, validUtc, publicUrl } from "./data.mjs";

const $ = id => document.getElementById(id);
const cards = new Map(), states = new Map(), pending = new Set(), active = new Set();
let roster, selected = new Set(), orientation, orientationError, orientationBusy = false, historyBusy = false, orientationAttempt = 0;
let directoryLimit = 50;
let storage;
try { storage = window.localStorage; } catch {
  storage = { getItem() { throw new DOMException("Unavailable", "SecurityError"); }, setItem() { throw new DOMException("Unavailable", "SecurityError"); } };
}

function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (className) node.className = className;
  return node;
}
function link(label, url) {
  const node = element("a", label);
  node.href = publicUrl(url);
  node.rel = "noopener noreferrer";
  return node;
}
function date(value) {
  return validUtc(value) ? new Date(value).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
  }) : "Not measured";
}

function updateProfile() {
  $("following-count").textContent = selected.size + " following";
  $("profile").value = JSON.stringify(profile(roster, selected), null, 2);
  $("copy-profile").disabled = $("download-profile").disabled = false;
  applyFilter();
  drawDirectory();
}

function setFollowing(id, follow) {
  if (follow) selected.add(id); else selected.delete(id);
  $("storage-status").textContent = saveSelection(roster, selected, storage).notice;
  updateProfile();
  draw(roster.feeds.find(feed => feed.id === id));
  if (follow) request(id);
}

function drawDirectory() {
  if (!roster) return;
  const directory = knownDirectory(roster, orientation);
  const query = $("directory-search").value.trim().toLowerCase();
  const matches = directory.entries.filter(entry =>
    [entry.title, entry.purpose, entry.publisher, entry.repository, entry.stream_id].join(" ").toLowerCase().includes(query));
  const focused = document.activeElement?.dataset.directoryFeed;
  const rows = [];
  for (const entry of matches.slice(0, directoryLimit)) {
    const row = element("article", undefined, "directory-entry");
    row.dataset.directoryStream = entry.stream_id;
    row.append(element("h3", entry.title), element("p", entry.purpose));
    row.append(element("p", `${entry.stream_id} · ${entry.registered ? "Public registry listing" : entry.core_journal ? "Additional core journal" : "Additional curated source"} · ` +
      `${entry.starter_id ? "In the curated starter set" : "Outside the starter set"}`, "metadata"));
    const state = entry.starter_id ? states.get(entry.starter_id) : null;
    if (entry.metadata_error) row.append(element("p", entry.metadata_error, "notice"));
    if (state?.observation) {
      const feed = roster.feeds.find(item => item.id === entry.starter_id);
      const status = state.status === "error" ? "Read failed; last-good observation retained" : freshness(feed, state.observation).label;
      row.append(element("p", `${status}. Record ${date(state.observation.latest.utc)}; ` +
        `last successful check ${date(state.observation.checked_utc)}.`, "metadata"));
    } else {
      row.append(element("p", state?.status === "error"
        ? `Read failed. No successful observation; last attempt ${date(state.attempted_utc)}.`
        : "Availability and record/check times are unmeasured. No remote records were polled for this directory entry.", "metadata"));
    }
    const actions = element("div", undefined, "actions");
    if (entry.source_url) actions.append(link("Inspect reported public source", entry.source_url));
    if (entry.starter_id) {
      const button = element("button", selected.has(entry.starter_id) ? "Unfollow starter feed" : "Follow starter feed");
      button.type = "button"; button.dataset.directoryFeed = entry.starter_id;
      button.setAttribute("aria-label", `${selected.has(entry.starter_id) ? "Unfollow" : "Follow"} ${entry.title} from directory`);
      button.addEventListener("click", () => setFollowing(entry.starter_id, !selected.has(entry.starter_id)));
      actions.append(button);
    }
    row.append(actions); rows.push(row);
  }
  $("directory-entries").replaceChildren(...rows);
  $("directory-count").textContent = `Showing ${rows.length} of ${matches.length} matching known sources; ${directory.known_sources} total.`;
  $("directory-more").hidden = matches.length <= directoryLimit;
  $("directory-status").textContent = orientation
    ? `${directory.known_sources} known sources: ${directory.registered_dimensions} registered dimensions plus ` +
      `${directory.additional_core_journals} core journals` +
      (directory.additional_curated_sources ? ` and ${directory.additional_curated_sources} additional curated sources` : "") +
      `. ${directory.starter_feeds} curated starter feeds; ` +
      `${roster.feeds.filter(feed => feed.default).length} fresh-browser default follows. ` +
      (orientationError || directory.registry_state !== "current" ? "Registry view is retained or failed, not a complete current directory." :
        "Registry metadata coverage is complete for the reported head; source availability is not.")
    : `Full directory unavailable or not loaded. Showing only ${directory.starter_feeds} starter feeds, not the whole network.`;
  if (focused) [...$("directory-entries").querySelectorAll("[data-directory-feed]")]
    .find(button => button.dataset.directoryFeed === focused)?.focus({ preventScroll: true });
}

function applyFilter() {
  const query = $("search").value.toLowerCase().trim(), only = $("only-following").checked;
  let shown = 0;
  for (const feed of roster?.feeds || []) {
    const card = cards.get(feed.id);
    card.root.hidden = Boolean((only && !selected.has(feed.id)) ||
      ![feed.title, feed.purpose, feed.publisher, ...feed.topics].join(" ").toLowerCase().includes(query));
    if (!card.root.hidden) shown += 1;
  }
  $("empty").hidden = shown !== 0 || !roster;
}

function draw(feed) {
  const card = cards.get(feed.id), state = states.get(feed.id), observation = state?.observation;
  card.follow.checked = selected.has(feed.id);
  card.body.replaceChildren();
  const status = state?.status === "error" ? { state: "error", label: observation ? "Refresh failed · last good shown" : "Source check failed" } :
    freshness(feed, observation);
  const badge = element("span", active.has(feed.id) ? "Checking public source…" : status.label, "badge");
  badge.dataset.state = status.state;
  card.body.append(badge);
  if (state?.error) card.body.append(element("p", state.error, "notice"));
  if (observation) {
    card.body.append(element("p", summary(observation), "summary"));
    card.body.append(element("p", changeSummary(observation)));
    if (state.changed) card.body.append(element("p", "A new record arrived since your previous check."));
    if (state.gap_unchecked) card.body.append(element("p", `${state.gap_unchecked} intervening records were not checked.`, "notice"));
    const failed = observation.latest.payload.sources_failed;
    if (Array.isArray(failed) && failed.length) card.body.append(element("p",
      `Partial observation: ${failed.length} upstream source${failed.length === 1 ? "" : "s"} failed. See the raw record.`, "notice"));
    card.body.append(element("p", `Record ${observation.latest.seq} · recorded ${date(observation.latest.utc)}`, "metadata"));
    card.body.append(element("p", `Last successful check ${date(observation.checked_utc)}`, "metadata"));
    if (state.status === "error") card.body.append(element("p", `Last attempt ${date(state.attempted_utc)}`, "metadata"));
    const coverage = observation.coverage;
    card.body.append(element("p", `${coverage.frames_checked} of ${coverage.total_frames} records hash/link checked · limited native profile, not whole-chain or signature verification.`, "metadata"));
    card.body.append(link("Open the exact source record/container", observation.latest_url));
    const details = element("details");
    details.append(element("summary", "Source hashes & raw observation"));
    details.append(element("pre", JSON.stringify({ stream_id: observation.latest.stream_id,
      record_utc: observation.latest.utc, checked_utc: observation.checked_utc,
      frame_hash: observation.latest.frame_hash, coverage, payload: observation.latest.payload }, null, 2)));
    card.body.append(details);
  } else {
    card.body.append(element("p", selected.has(feed.id) ? "No successful observation yet. A failed read is never marked fresh." :
      "Not measured in this tab. Follow or check once to read the public source.", "metadata"));
    if (state?.attempted_utc) card.body.append(element("p", `Last attempt ${date(state.attempted_utc)}`, "metadata"));
  }
  card.check.disabled = active.has(feed.id) || pending.has(feed.id);
}

function makeCard(feed) {
  const root = element("article", undefined, "feed");
  root.dataset.feedId = feed.id;
  const heading = element("div", undefined, "feed-head"), title = element("h3", feed.title);
  title.id = "title-" + feed.id; root.setAttribute("aria-labelledby", title.id);
  const follow = element("input");
  follow.type = "checkbox"; follow.setAttribute("aria-label", `Follow ${feed.title}`);
  const followLabel = element("label", undefined, "follow");
  followLabel.append(follow, document.createTextNode("Follow"));
  heading.append(title, followLabel);
  root.append(heading, element("p", feed.purpose, "purpose"));
  const source = element("p", undefined, "source");
  source.append(document.createTextNode(`By ${feed.publisher} · `), link("Public source", feed.source_url),
    document.createTextNode(" · native DOGG"));
  root.append(source);
  const body = element("div", undefined, "observation");
  root.append(body);
  const controls = element("div", undefined, "feed-actions"), check = element("button", "Check once");
  check.type = "button"; check.setAttribute("aria-label", `Check ${feed.title} once`);
  controls.append(check, element("span", feed.expected_update_seconds === null ? "When the publisher adds an entry" :
    `Target update: ${Math.round(feed.expected_update_seconds / 60)} min`, "metadata"));
  root.append(controls);
  cards.set(feed.id, { root, body, follow, check });
  follow.addEventListener("change", () => {
    setFollowing(feed.id, follow.checked);
  });
  check.addEventListener("click", () => request(feed.id));
  $("feeds").append(root);
  draw(feed);
}

function updateBusy() {
  $("refresh").disabled = active.size > 0 || pending.size > 0 || historyBusy;
  $("load-history").disabled = active.size > 0 || pending.size > 0 || historyBusy || orientationBusy;
  $("refresh-status").textContent = active.size || pending.size
    ? `Reading ${active.size} source${active.size === 1 ? "" : "s"} · ${pending.size} queued.`
    : "Read-only checks. Automatic refresh pauses when this page is hidden.";
}

function request(id) {
  if (!active.has(id) && !pending.has(id)) pending.add(id);
  drain();
}

function drain() {
  if (historyBusy) { updateBusy(); return; }
  while (active.size < 2 && pending.size) {
    const id = pending.values().next().value;
    pending.delete(id); active.add(id);
    const feed = roster.feeds.find(item => item.id === id);
    draw(feed);
    loadSource(feed).then(observation => {
      states.set(id, reconcile(states.get(id), { observation }));
    }).catch(error => {
      states.set(id, reconcile(states.get(id), { error: error.name === "AbortError" ? "Source timed out. Try again later." : error.message }));
    }).finally(() => {
      active.delete(id); draw(feed); drawOrientation(); drain();
    });
  }
  updateBusy();
}

function drawOrientation() {
  drawDirectory();
  if (!orientation) {
    $("network-status").textContent = orientationError ? "Derived view unavailable. Individual feed checks still work." : "Derived view has not been checked yet.";
    return;
  }
  const newestObserved = Math.max(orientation.tick.seq, ...[...states.values()].map(state => {
    const payload = state.observation?.latest.payload;
    return Number.isSafeInteger(payload?.tick) ? payload.tick : 0;
  }));
  const age = Date.now() - Date.parse(orientation.tick.utc);
  const notes = [];
  if (orientationError) notes.push("refresh failed; last good derived view shown");
  if (newestObserved > orientation.tick.seq) notes.push(`behind a feed reporting tick ${newestObserved}`);
  if (age > 3600000) notes.push("source clock is stale");
  if (orientation.projection_version !== 1) notes.push("legacy view awaiting regeneration");
  if (orientation.status?.world?.state && orientation.status.world.state !== "current") notes.push(`world ${orientation.status.world.state}`);
  if (orientation.status?.world?.last_refresh === "failed") notes.push("last world refresh failed");
  if (orientation.status?.registry?.state === "error") notes.push("registry refresh failed; discovery may be old");
  $("network-status").textContent = `Derived tick ${orientation.tick.seq} · source recorded ${date(orientation.tick.utc)} · ` +
    `${orientation.dimensions.length} discovered dimensions (not auto-followed or trusted).` +
    (notes.length ? " " + notes.join("; ") + "." : " Derived from public records, not an authentication service.");
}

async function refreshOrientation() {
  if (orientationBusy || historyBusy) return;
  orientationBusy = true;
  orientationAttempt = Date.now();
  updateBusy();
  try {
    const value = validateOrientation(strictJson(await readPublicBytes(roster.orientation_url)));
    if (orientation && value.tick.seq < orientation.tick.seq) throw new Error("derived view rolled back");
    orientation = value; orientationError = null;
  } catch { orientationError = true; }
  finally { orientationBusy = false; drawOrientation(); updateBusy(); }
}

function refreshFollowed() {
  for (const id of selected) request(id);
  refreshOrientation();
  if (!selected.size) $("refresh-status").textContent = "No feeds followed yet. Choose a feed or use Check once.";
}

$("search").addEventListener("input", applyFilter);
$("only-following").addEventListener("change", applyFilter);
$("directory-search").addEventListener("input", () => { directoryLimit = 50; drawDirectory(); });
$("directory-more").addEventListener("click", () => { directoryLimit += 50; drawDirectory(); });
$("refresh").addEventListener("click", refreshFollowed);
for (const node of document.querySelectorAll("[data-open]")) {
  node.addEventListener("click", () => { $(node.dataset.open).open = true; });
}
if (["#ai", "#technical", "#history", "#directory"].includes(location.hash)) $(location.hash.slice(1)).open = true;

$("copy-profile").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("profile").value);
    $("profile-status").textContent = "Profile copied locally. Share it only where you choose.";
  } catch {
    $("profile").focus(); $("profile").select();
    $("profile-status").textContent = "Clipboard unavailable. The profile is selected; copy it manually.";
  }
});
$("download-profile").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([$("profile").value + "\n"], { type: "application/json" }));
  const anchor = element("a"); anchor.href = url; anchor.download = "dogg-following.json";
  document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  $("profile-status").textContent = "Read-only profile downloaded on this device. Nothing was uploaded.";
});
$("load-history").addEventListener("click", async () => {
  const button = $("load-history"), feed = roster.feeds.find(item => item.id === "dogg.thread");
  if (!feed || active.size || orientationBusy || historyBusy) return;
  historyBusy = true;
  updateBusy();
  button.disabled = true;
  $("history-status").textContent = "Reading up to six complete historical records…";
  try {
    const observation = await loadSource(feed, { limit: 6 });
    const list = [];
    for (const frame of observation.frames) {
      const card = element("article", undefined, "history-record");
      card.append(element("h3", `Historical source quote · record ${frame.seq} · ${frame.kind}`),
        element("p", date(frame.utc), "metadata"), element("pre", JSON.stringify(frame.payload, null, 2)));
      list.push(card);
    }
    $("history-records").replaceChildren(...list);
    $("history-status").textContent = `${observation.frames.length} of ${observation.head.count} historical records checked and quoted unchanged. ` +
      "These are source claims, not current product promises or signature proofs.";
  } catch (error) {
    $("history-status").textContent = "History refresh failed: " + error.message + ". Any last-good quotes remain below.";
  } finally { historyBusy = false; button.disabled = false; drain(); }
});

try {
  roster = validateRoster(strictJson(await readPublicBytes(new URL("../subscriptions.json", import.meta.url).href)));
  const restored = restoreSelection(roster, storage);
  selected = new Set(restored.ids);
  $("storage-status").textContent = restored.notice;
  $("roster-status").textContent = `${roster.feeds.length} curated feeds · ${new Set(roster.feeds.map(feed => feed.publisher)).size} publishers · starter roster v${roster.version}`;
  roster.feeds.forEach(makeCard);
  updateProfile();
  $("refresh").disabled = $("load-history").disabled = false;
  refreshFollowed();
  setInterval(() => {
    if (document.visibilityState !== "visible") return;
    if (historyBusy) return;
    if (Date.now() - orientationAttempt >= 300000) refreshOrientation();
    for (const feed of roster.feeds) {
      if (selected.has(feed.id) && Date.now() - Date.parse(states.get(feed.id)?.attempted_utc || "1970-01-01") >= feed.refresh_seconds * 1000) request(feed.id);
      if (states.has(feed.id)) draw(feed);
    }
  }, 30000);
} catch (error) {
  $("load-error").hidden = false;
  $("load-error").textContent = "The public starter roster could not be loaded: " + error.message +
    ". No sources were silently followed. Reload to retry, or open subscriptions.json.";
  $("roster-status").textContent = "Starter roster unavailable · no successful source checks yet.";
}
