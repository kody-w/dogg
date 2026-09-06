import { H } from "../site/data.mjs";

export const NOW = Date.parse("2026-09-06T13:10:00.000Z");
export async function fixtureChain(stream, { count = 3, epoch = 2, sealed = 0, kind = "tick.anchor", payload } = {}) {
  const frames = [];
  for (let seq = 0; seq < count; seq += 1) {
    const frame = {
      spec: "rapp/1", kind, stream_id: stream, seq,
      utc: `2026-09-06T13:00:${String(seq).padStart(2, "0")}.000Z`,
      payload: payload ? payload(seq) : { tick: seq, note: "A public observation", value: seq },
      prev: frames.at(-1)?.payload_hash || null, prev_wave: null, sig: null,
    };
    frame.payload_hash = await H("rapp/1:particle", frame.payload);
    frame.frame_hash = await H("rapp/1:wave", Object.fromEntries(Object.entries(frame).filter(([key]) =>
      !["frame_hash", "sig"].includes(key))));
    frames.push(frame);
  }
  const head = { count, stream_id: stream, head_frame: frames.at(-1)?.frame_hash || "0".repeat(64),
    updated: "2026-09-06T13:00:03.000Z", epoch_size: epoch, sealed_epochs: sealed };
  const files = new Map([["HEAD.json", JSON.stringify(head)]]);
  for (let index = 0; index < sealed; index += 1) {
    files.set(`epochs/${index}.jsonl`, frames.slice(index * epoch, (index + 1) * epoch).map(value => JSON.stringify(value)).join("\n") + "\n");
  }
  frames.slice(sealed * epoch).forEach(frame => files.set(`${frame.seq}.json`, JSON.stringify(frame, null, 2) + "\n"));
  return { frames, head, files };
}

export function fixtureFetch(feed, files, calls = []) {
  return async (url, options) => {
    calls.push({ url, options });
    const key = url.slice(feed.records_url.length);
    return files.has(key) ? new Response(files.get(key), { status: 200, headers: { "content-type": "application/json" } }) :
      new Response("missing", { status: 404 });
  };
}
