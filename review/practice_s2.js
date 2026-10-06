"use strict";
// S2 practice panels: stage identities, matched A/B, intended-vs-observed coverage,
// triaged flags, phrase timing measurements and a quick-mark labelling session.
// Evidence display only: text via textContent; nothing starts playback automatically or from code.
let s2Bundle = null, s2Ready = false, s2Initialized = false, s2PairBox = null, s2CoverageBox = null;
const s2State = {pair:0, reveal:new Set(), anchor:null, session:false, queue:[], frozen:null, busy:false, uncertain:false, lastFlag:null, wired:false};
const s2Players = [];
const S2_PANELS = ["s2-stages", "s2-ab", "s2-coverage", "s2-flags", "s2-timing"];
const S2_KINDS = ["phrase_duration", "phrase_omission", "rhythm_timing", "rhythm_pattern", "melodic_pitch", "articulation", "rest_execution", "meter_mismatch", "tone", "noise", "other"];
const S2_BASIS = {
  operator_assertion:{label:"USER REPORTED", shape:"solid"},
  operator_context:{label:"INTENT", shape:"bracket"},
  detector_hypothesis:{label:"REVIEW", shape:"dashed", subtitle:"detector hypothesis"},
  reference_comparison:{label:"REFERENCE REVIEW", shape:"double"},
};
// Display names that keep generated text free of verdict wording.
const S2_KEY_LABELS = {missed_or_extra_notes:"note-level comparison", "phrase_timing.real_take_status":"phrase timing real-take status"};
const S2_TENDENCY = {within_5_ms:"within ±5 ms of modelled click", ahead_of_click:"ahead of modelled click", behind_click:"behind modelled click"};
const S2_PROTOTYPES = [
  ["Compact overlay preview", "section label, BPM and issue badges; not rendered"],
  ["Operator preference capture", "not stored; preference stays not recorded"],
  ["Editor marker export from this page", "use the existing marker tools"],
  ["Staff or tab view", "no notation is derived"],
  ["Click-drift timeline", "not drawn"],
];

function s2el(tag, text, cls) {
  const item = document.createElement(tag);
  if(text !== undefined && text !== null) item.textContent = String(text);
  if(cls) item.className = cls;
  return item;
}
function s2Human(value) { return String(value).replaceAll("_", " "); }
function s2Key(key) { return S2_KEY_LABELS[key] || s2Human(key); }
function s2Short(hash) { return typeof hash === "string" && /^[a-f0-9]{64}$/.test(hash) ? hash.slice(0, 12) : "unknown"; }
function s2Fixed(value, digits) { return Number.isFinite(value) ? value.toFixed(digits) : "unknown"; }
function s2Signed(value, digits) {
  if(!Number.isFinite(value)) return "unknown";
  const fixed = Math.abs(value).toFixed(digits);
  return (Number(fixed) === 0 ? "±" : value < 0 ? "−" : "+") + fixed;
}
function s2Clock(value) { return typeof clock === "function" ? clock(value) : s2Fixed(value, 3) + " s"; }
function s2Body(id) { return byId(id + "-body"); }
function s2Upstream(tag, text) { return s2el(tag, text, "s2-upstream"); }

function s2Badge(record) {
  if(record && record.store) {
    const known = S2_BASIS[record.basis];
    if(!known) return {text:"UNKNOWN BASIS", subtitle:null, shape:"plain"};
    const label = typeof record.claim_label === "string" && record.claim_label ? record.claim_label : known.label;
    return {text:label, subtitle:known.subtitle || null, shape:known.shape};
  }
  if(record && record.origin === "intent") return {text:"INTENT · projected", subtitle:null, shape:"bracket"};
  if(record && record.origin === "detector") return {text:"DETECTOR HYPOTHESIS", subtitle:null, shape:"dotted"};
  return {text:"UNKNOWN BASIS", subtitle:null, shape:"plain"};
}
function s2BadgeNode(record) {
  const badge = s2Badge(record), item = s2el("span", badge.text, "s2-badge s2-shape-" + badge.shape);
  if(badge.subtitle) item.append(s2el("small", " · " + badge.subtitle, "s2-badge-sub"));
  return item;
}
function s2Unavailable(id, reason, message) {
  const body = s2Body(id);
  body.replaceChildren(s2el("p", message || "Unavailable: " + s2Human(reason || "unknown"), "s2-unavailable"));
}
function s2AllUnavailable(reason, message) {
  for(const id of S2_PANELS) s2Unavailable(id, reason, message);
}

// ----- stage identity strip ---------------------------------------------------
function s2StageRow(label, hash, role, status, details) {
  const row = s2el("div", undefined, "s2-stage-row");
  const code = s2el("code", s2Short(hash), "s2-hash");
  code.setAttribute("aria-label", label + " SHA-256 " + (hash || "unknown"));
  code.title = hash || "unknown";
  row.append(s2el("strong", label, "s2-stage-label"), code, s2el("span", role, "s2-stage-role"), s2el("span", status, "s2-stage-status"));
  const inspector = s2el("details", undefined, "s2-inspector");
  inspector.append(s2el("summary", "Full hashes"));
  for(const [name, value] of details) inspector.append(s2el("p", name + ": " + (value || "unknown")));
  row.append(inspector);
  return row;
}
function s2RenderStages() {
  const body = s2Body("s2-stages"), stages = s2Bundle.stages || {};
  body.replaceChildren();
  const source = stages.source || {}, tone = stages.tone || {}, arrangement = stages.arrangement || {};
  body.append(s2StageRow("Source", source.original_sha256, "original recording identity", "bound to this session",
    [["original source", source.original_sha256], ["source.wav", source.source_wav_sha256]]));
  body.append(s2StageRow("Tone (FULLER)", tone.cleaned_sha256, "delivery master · profile " + (tone.profile_name || "unknown"), "run " + (tone.run_id || "unknown"),
    [["denoised.wav", tone.denoised_sha256], ["processed.wav", tone.processed_sha256], ["cleaned.wav", tone.cleaned_sha256], ["applied-profile.json", tone.applied_profile_sha256]]));
  const spans = Array.isArray(arrangement.spans) ? arrangement.spans : [];
  body.append(s2StageRow("Arrangement intent", arrangement.arrangement_sha256, "operator arrangement · " + spans.length + " projected anchor files", "anchor not adopted",
    [["arrangement", arrangement.arrangement_sha256]].concat(spans.map(item => ["spans k" + item.k0 + " (" + item.file + ")", item.sha256]))));
  const groups = new Map();
  for(const item of Array.isArray(stages.analysis) ? stages.analysis : []) {
    if(item.layer === "tone_ab") continue;
    const key = item.analyzed_input_sha256 || "unrecorded";
    if(!groups.has(key)) groups.set(key, {layers:[], noStretch:new Set(), matches:item.matches_tone_denoised});
    groups.get(key).layers.push(item.layer);
    groups.get(key).noStretch.add(item.timeline_no_stretch_verified === true ? "true" : item.timeline_no_stretch_verified === false ? "false" : "unknown");
  }
  for(const [hash, group] of groups) {
    const noStretch = "no-stretch: " + [...group.noStretch].join(" / ");
    const status = hash === "unrecorded" ? "analyzed input not recorded by this layer — bound by original source only"
      : group.matches ? "same as tone denoised stage · " + noStretch
      : "analysis input differs from tone stage — bound by original source only · " + noStretch;
    body.append(s2StageRow("Analysis input", hash === "unrecorded" ? null : hash, group.layers.join(", "), status, [["analyzed input", hash]]));
  }
  const unknown = s2el("details", undefined, "s2-inspector s2-unknowns");
  const fields = s2Bundle.unknown_fields || {};
  unknown.append(s2el("summary", "Unknown and not-established fields (" + Object.keys(fields).length + ")"));
  for(const [key, item] of Object.entries(fields)) {
    const value = item && typeof item.value === "object" && item.value !== null ? JSON.stringify(item.value) : String(item ? item.value : "unknown");
    unknown.append(s2el("p", s2Key(key) + ": " + s2Human(value) + " — " + (item && item.reason ? item.reason : "")));
  }
  const boundary = s2Bundle.claim_boundary || {};
  for(const [key, value] of Object.entries(boundary)) unknown.append(s2el("p", "claim boundary · " + s2Key(key) + ": " + s2Human(value)));
  body.append(unknown);
}

// ----- matched A/B -------------------------------------------------------------
function s2Exclusive(current) {
  for(const player of s2Players) if(player !== current && !player.paused) player.pause();
  if(typeof players !== "undefined" && players) for(const player of players.values()) if(player !== current && !player.paused) player.pause();
}
function s2Player(url, label) {
  const audio = document.createElement("audio");
  audio.controls = true;
  audio.preload = "none";
  audio.src = url;
  audio.className = "s2-player";
  audio.setAttribute("aria-label", label);
  audio.addEventListener("play", () => s2Exclusive(audio));
  s2Players.push(audio);
  return audio;
}
function s2ReleasePlayers() {
  for(const player of s2Players) if(!player.paused) player.pause();
  s2Players.length = 0;
}
function s2Urls() { return (s2Bundle.served && s2Bundle.served.media_urls) || {}; }
function s2RenderAB() {
  const layer = s2Bundle.layers && s2Bundle.layers.tone_ab;
  s2ReleasePlayers();
  if(!layer || layer.status !== "available") return s2Unavailable("s2-ab", layer ? layer.reason : "layer_missing");
  const body = s2Body("s2-ab"), match = layer.loudness_match || {}, region = layer.region || {};
  body.replaceChildren();
  body.append(s2el("p", "region match: ±" + s2Fixed(match.match_lu_delta, 2) + " LU over " + s2Fixed(region.start_seconds, 1) + "–" + s2Fixed(region.end_seconds, 1) + " s (measured, BS.1770 via FFmpeg loudnorm)", "s2-measure"));
  body.append(s2el("p", "operator_preference: not recorded", "s2-claim"), s2el("p", "listening acceptance: not established", "s2-claim"));
  body.append(s2el("p", "Excerpt files are pre-gained by tone_ab; this page applies no gain. Browser output level and device are unmeasured.", "muted"));
  const pairs = layer.excerpts && Array.isArray(layer.excerpts.pairs) ? layer.excerpts.pairs : [];
  const selector = s2el("div", undefined, "tabs s2-pairs");
  selector.setAttribute("role", "group");
  selector.setAttribute("aria-label", "Excerpt pair");
  pairs.forEach((pair, index) => {
    const button = s2el("button", "Pair " + pair.pair);
    button.type = "button";
    button.setAttribute("aria-pressed", String(index === s2State.pair));
    button.addEventListener("click", () => { s2State.pair = index; s2RenderAB(); });
    selector.append(button);
  });
  body.append(selector);
  s2PairBox = s2el("div", undefined, "s2-pair");
  body.append(s2PairBox);
  if(!pairs.length) { s2PairBox.append(s2el("p", "No excerpt pairs in tone-ab.json.", "s2-unavailable")); return; }
  s2State.pair = Math.min(s2State.pair, pairs.length - 1);
  s2RenderPair(layer, pairs[s2State.pair], s2State.pair);
  if(Array.isArray(layer.limitations)) {
    const limits = s2el("details", undefined, "s2-inspector");
    limits.append(s2el("summary", "tone_ab limitations (verbatim)"));
    for(const text of layer.limitations) limits.append(s2Upstream("p", text));
    body.append(limits);
  }
}
function s2RenderPair(layer, pair, index) {
  const media = (layer.pair_media || [])[index] || {}, urls = s2Urls();
  s2PairBox.append(s2el("p", "Pair " + pair.pair + " · native samples " + pair.start_sample + "–" + pair.end_sample_exclusive + " (" + s2Fixed(pair.start_seconds, 3) + " s start, source audio clock)", "muted"));
  const grid = s2el("div", undefined, "s2-players");
  for(const side of ["X", "Y"]) {
    const figure = s2el("figure", undefined, "s2-figure");
    figure.append(s2el("figcaption", side));
    const url = urls[media[side]];
    figure.append(url ? s2Player(url, "Excerpt pair " + pair.pair + " player " + side) : s2el("p", "Media not served: " + s2Human((s2Bundle.served && s2Bundle.served.media_status || {})[media[side]] || "missing"), "s2-unavailable"));
    grid.append(figure);
  }
  s2PairBox.append(grid);
  const revealed = s2State.reveal.has(index), key = ((layer.excerpts || {}).blind_key || []).find(item => item.pair === pair.pair);
  const reveal = s2el("button", revealed ? "Hide mapping" : "Reveal which is FULLER", "quiet");
  reveal.type = "button";
  reveal.setAttribute("aria-pressed", String(revealed));
  reveal.addEventListener("click", () => { if(s2State.reveal.has(index)) s2State.reveal.delete(index); else s2State.reveal.add(index); s2RenderAB(); });
  s2PairBox.append(reveal);
  const name = arm => arm === "delivery_master" ? "FULLER delivery master" : arm === "source" ? "source" : s2Human(arm || "unknown");
  s2PairBox.append(s2el("p", revealed && key ? "X = " + name(key.X) + " · Y = " + name(key.Y) + " (display only; not saved, not a preference)" : "Mapping hidden. Revealing is a local display toggle; it is never saved.", "s2-mapping"));
  const levels = s2el("details", undefined, "s2-inspector");
  levels.append(s2el("summary", "Per-file level measurements (measured; gains can hint at the mapping)"));
  for(const side of ["X", "Y"]) {
    const file = (pair.files || {})[side] || {};
    levels.append(s2el("p", side + ": static gain " + s2Signed(file.static_gain_db, 2) + " dB · excerpt LUFS " + s2Fixed(file.excerpt_lufs_informational, 2) + " (informational) · sample peak " + s2Fixed(file.sample_peak_dbfs, 2) + " dBFS · true peak " + (Number.isFinite(file.true_peak_dbtp) ? s2Fixed(file.true_peak_dbtp, 2) + " dBTP" : "not measured")));
  }
  s2PairBox.append(levels);
  const trial = layer.trial || {status:"unavailable", reason:"trial_missing"};
  const box = s2el("div", undefined, "s2-trial");
  if(trial.status === "available") {
    const controls = trial.controls || {}, item = (trial.pairs || []).find(entry => entry.pair === pair.pair), url = item && urls[item.media];
    const label = "TRIAL · " + s2Human(controls.type || "lowshelf") + " " + s2Fixed(controls.frequency_hz, 0) + " Hz " + s2Signed(controls.gain_db, 1) + " dB · unreviewed experiment · not adopted";
    const figure = s2el("figure", undefined, "s2-figure s2-trial-figure");
    figure.append(s2el("figcaption", label));
    figure.append(url ? s2Player(url, label) : s2el("p", "Trial excerpt not served for this pair.", "s2-unavailable"));
    box.append(figure, s2el("p", "Unblinded. Cut at the same native samples from the trial file; static gain " + s2Signed(trial.gain_db, 2) + " dB from the tone_ab region match.", "muted"));
  } else {
    box.append(s2el("p", "TRIAL excerpt unavailable: " + s2Human(trial.reason || "unknown") + " · unreviewed experiment · not adopted", "s2-unavailable"));
  }
  s2PairBox.append(box);
}

// ----- coverage strip ----------------------------------------------------------
function s2Intent() {
  if(!s2Ready || !s2Bundle || !s2Bundle.layers) return null;
  const coverage = s2Bundle.layers.coverage || {}, files = coverage.intent && Array.isArray(coverage.intent.files) ? coverage.intent.files : [];
  // Default view: the middle anchor candidate, so ±1 click alternatives sit on either side. Nothing is adopted.
  if(s2State.anchor === null) s2State.anchor = Math.floor(Math.max(0, files.length - 1) / 2);
  return files[Math.min(s2State.anchor, Math.max(0, files.length - 1))] || null;
}
function s2Boundaries() {
  const intent = s2Intent();
  return intent ? intent.boundaries.map(item => item.source_seconds).filter(Number.isFinite).sort((a, b) => a - b) : [];
}
function s2Breakdown(row) {
  return (row.structural_status || []).some(item => item === "breakdown_execution_uncertain" || item === "uncertain_upstream_breakdown");
}
function s2JoinNode(row, left) {
  const join = ["supported", "weak", "uncertain"].includes(row.join_confidence) ? row.join_confidence : "unknown";
  const tick = s2el("span", undefined, "s2-tick s2-join-" + join);
  tick.style.left = left + "%";
  let glyph = join === "weak" ? "~" : join === "uncertain" ? "?" : join === "unknown" ? "?" : "";
  if(s2Breakdown(row)) glyph += "≈";
  if(glyph) tick.append(s2el("span", glyph, "s2-glyph"));
  tick.setAttribute("role", "img");
  tick.setAttribute("aria-label", join === "uncertain" ? "uncertain join" : join === "weak" ? "weak join" : join === "supported" ? "supported join" : "join confidence unknown");
  tick.title = row.id + " · " + s2Clock(row.source_seconds) + " · " + join + " join" + (s2Breakdown(row) ? " · breakdown execution uncertain" : "");
  return tick;
}
function s2Lane(label, badge) {
  const lane = s2el("div", undefined, "s2-lane"), name = s2el("div", undefined, "s2-lane-label");
  name.append(s2el("strong", label), s2BadgeNode(badge));
  const track = s2el("div", undefined, "s2-track");
  lane.append(name, track);
  return [lane, track];
}
function s2Place(item, start, end, min, span) {
  const left = Math.max(0, Math.min(100, 100 * (start - min) / span));
  const right = Math.max(0, Math.min(100, 100 * (end - min) / span));
  item.style.left = left + "%";
  item.style.width = Math.max(0.4, right - left) + "%";
}
function s2RenderCoverage() {
  const layer = s2Bundle.layers && s2Bundle.layers.coverage;
  if(!layer || layer.status !== "available") return s2Unavailable("s2-coverage", layer ? layer.reason : "layer_missing");
  const body = s2Body("s2-coverage"), files = layer.intent && Array.isArray(layer.intent.files) ? layer.intent.files : [];
  body.replaceChildren();
  const min = Number(layer.source_min_seconds) || 0, max = Number(layer.source_max_seconds), span = Number.isFinite(max) && max > min ? max - min : 1;
  if(files.length) {
    const label = s2el("label", "Arrangement anchor");
    const select = s2el("select");
    select.id = "s2-anchor";
    files.forEach((file, index) => { const option = s2el("option", "k" + file.k0 + " · anchor review candidate"); option.value = String(index); select.append(option); });
    s2Intent();
    select.value = String(Math.min(s2State.anchor, files.length - 1));
    select.addEventListener("change", () => { s2State.anchor = Number(select.value) || 0; s2RenderCoverage(); });
    label.append(select);
    body.append(label, s2el("p", "anchor review candidate · not adopted · ±1 click alternatives", "s2-claim"));
  } else {
    body.append(s2el("p", "INTENT lane unavailable: " + s2Human(layer.intent && layer.intent.reason || "input_not_supplied"), "s2-unavailable"));
  }
  const intent = s2Intent(), detector = layer.detector || {}, spans = detector.status === "available" && Array.isArray(detector.proposed_review_spans) ? detector.proposed_review_spans : [];
  const summary = s2el("div", undefined, "s2-summary");
  if(intent) {
    const within = intent.units.filter(unit => unit.coverage === "within_source").length;
    const counts = {supported:0, weak:0, uncertain:0, other:0};
    for(const row of intent.boundaries) counts[["supported", "weak", "uncertain"].includes(row.join_confidence) ? row.join_confidence : "other"] += 1;
    summary.append(s2el("p", "intent units within source: " + within + "/" + intent.units.length));
    summary.append(s2el("p", "boundaries by join confidence: supported " + counts.supported + ", weak " + counts.weak + ", uncertain " + counts.uncertain + (counts.other ? ", other " + counts.other : "") + " (of " + intent.boundaries.length + ")"));
  }
  summary.append(s2el("p", detector.status === "available" ? "detector review spans: " + spans.length : "detector review spans: unavailable (" + s2Human(detector.reason || "unknown") + ")"));
  body.append(summary);
  const strip = s2el("div", undefined, "s2-strip");
  strip.setAttribute("aria-label", "Source timeline " + s2Fixed(min, 1) + " to " + s2Fixed(max, 1) + " seconds");
  const [intentLane, intentTrack] = s2Lane("INTENT", {origin:"intent"});
  intentTrack.classList.add("s2-track-intent");
  if(intent) {
    for(const unit of intent.units) {
      const button = s2el("button", unit.id, "s2-unit s2-unit-" + s2Human(unit.kind || "unit").replaceAll(" ", "-"));
      button.type = "button";
      s2Place(button, unit.start_source_seconds, unit.end_source_seconds, min, span);
      const outside = unit.coverage !== "within_source";
      if(outside) { button.classList.add("s2-outside"); button.append(s2el("span", " outside source", "s2-outside-label")); }
      button.setAttribute("aria-label", "INTENT · projected unit " + unit.id + " · " + s2Clock(unit.start_source_seconds) + " to " + s2Clock(unit.end_source_seconds) + (outside ? " · outside source" : ""));
      button.addEventListener("click", () => seekSource(Math.max(min, unit.start_source_seconds)));
      intentTrack.append(button);
    }
    for(const row of intent.boundaries) intentTrack.append(s2JoinNode(row, Math.max(0, Math.min(100, 100 * (row.source_seconds - min) / span))));
  }
  const [detectorLane, detectorTrack] = s2Lane("DETECTOR HYPOTHESIS", {origin:"detector"});
  for(const item of spans) {
    const start = Number(item.source_start_seconds), end = Number(item.source_end_seconds);
    if(!Number.isFinite(start) || !Number.isFinite(end)) continue;
    const button = s2el("button", undefined, "s2-span");
    button.type = "button";
    s2Place(button, start, end, min, span);
    button.setAttribute("aria-label", "DETECTOR HYPOTHESIS · " + s2Human(item.kind || "span") + " · " + s2Clock(start) + " to " + s2Clock(end));
    button.title = s2Human(item.kind || "span") + " · " + s2Clock(start);
    button.addEventListener("click", () => seekSource(start));
    detectorTrack.append(button);
  }
  const [userLane, userTrack] = s2Lane("USER REPORTED", {store:true, basis:"operator_assertion"});
  s2CoverageBox = {track:userTrack, min, span};
  strip.append(intentLane, detectorLane, userLane);
  body.append(strip);
  s2RenderUserLane();
  body.append(s2el("p", "Ticks: solid = supported join; dashed with ~ = weak join; hatched with ? = uncertain join; ≈ = breakdown execution uncertain. Overlap between lanes is not agreement, accuracy or correctness. Selecting a unit seeks without playing.", "muted"));
  if(intent) {
    const list = s2el("details", undefined, "s2-inspector");
    list.append(s2el("summary", "Boundary list (" + intent.boundaries.length + ") · k" + intent.k0 + " · " + s2Human(intent.anchor_status || "unknown")));
    for(const row of intent.boundaries) {
      list.append(s2el("p", row.id + " · " + s2Clock(row.source_seconds) + " · " + s2Human(row.join_confidence || "unknown") + " join" +
        (row.join_confidence === "uncertain" ? " ?" : row.join_confidence === "weak" ? " ~" : "") + (s2Breakdown(row) ? " ≈" : "") +
        " · " + (row.structural_status || []).map(s2Human).join(", ") + " · " + s2Human(row.grid_label || "grid unknown") +
        (row.on_interpolated_half_period ? " · on interpolated half period" : "") + (row.coverage && row.coverage !== "within_source" ? " · outside source" : "")));
    }
    body.append(list);
  }
}
function s2RenderUserLane() {
  if(!s2CoverageBox) return;
  const {track, min, span} = s2CoverageBox;
  track.replaceChildren();
  const records = typeof issueStore !== "undefined" && issueStore && Array.isArray(issueStore.annotations) ? issueStore.annotations : [];
  for(const item of records) {
    if(item.basis !== "operator_assertion" || !item.source_span) continue;
    const start = item.source_span.start_seconds, end = item.source_span.end_seconds;
    const mark = s2el("span", undefined, "s2-user" + (item.source_span.extent_known && end > start ? " s2-user-span" : " s2-user-point"));
    if(item.source_span.extent_known && end > start) s2Place(mark, start, end, min, span);
    else mark.style.left = Math.max(0, Math.min(100, 100 * (start - min) / span)) + "%";
    mark.setAttribute("role", "img");
    mark.setAttribute("aria-label", "USER REPORTED · " + s2Human(item.kind) + " · " + s2Clock(start));
    track.append(mark);
  }
}

// ----- triaged flags -------------------------------------------------------------
function s2FlagRow(item, group) {
  const flag = item.flag || {}, start = Number(flag.source_time_seconds), end = Number.isFinite(Number(flag.end_seconds)) ? Number(flag.end_seconds) : start;
  const row = s2el("article", undefined, "s2-flag s2-flag-" + group);
  const head = s2el("p", (group === "navigation" ? "navigation proxy" : item.window_id || "window unknown") + " · " + s2Human(flag.kind || "unknown kind"), "s2-flag-head");
  row.append(head, s2BadgeNode({origin:"detector"}));
  row.append(s2el("p", s2Clock(start) + " → " + s2Clock(end) + (item.tier ? " · tier " + item.tier + " " + s2Human(item.tier_name || "") : "") + (item.crosses_window_boundary ? " · crosses window boundary" : ""), "s2-flag-meta"));
  if(group === "suppressed") row.append(s2el("p", "lower priority in window; shown instead: " + (item.winner_flag_id || "unknown"), "muted"));
  if(group === "navigation") row.append(s2el("p", s2Human(item.reason || "navigation proxy hidden by default"), "muted"));
  const seek = s2el("button", "Seek", "quiet");
  seek.type = "button";
  seek.addEventListener("click", () => { s2State.lastFlag = item; seekSource(start); });
  row.append(seek);
  const record = s2el("details", undefined, "s2-inspector");
  record.append(s2el("summary", "Retained record (verbatim)"), s2Upstream("pre", JSON.stringify(flag, null, 1)));
  row.append(record);
  return row;
}
function s2Shown() {
  const layer = s2Ready && s2Bundle && s2Bundle.layers && s2Bundle.layers.flags_triage;
  return layer && layer.status === "available" && Array.isArray(layer.document.shown) ? layer.document.shown : [];
}
function s2RenderFlagList(list, items, group, visible) {
  list.replaceChildren();
  list.hidden = !visible;
  if(visible) for(const item of items) list.append(s2FlagRow(item, group));
}
function s2RenderFlags() {
  const layer = s2Bundle.layers && s2Bundle.layers.flags_triage;
  if(!layer || layer.status !== "available") return s2Unavailable("s2-flags", layer ? layer.reason : "layer_missing");
  const body = s2Body("s2-flags"), doc = layer.document, den = doc.denominators || {}, basis = doc.window_basis || {};
  body.replaceChildren();
  body.append(s2el("p", "shown " + den.shown + " of " + den.total_flags + " flags · navigation hidden " + den.navigation_hidden + " · suppressed " + den.suppressed_lower_priority, "s2-measure"));
  const kind = String(basis.kind || "unknown");
  const phrase = kind === "phrase_spans";
  body.append(s2el("p", "window basis: " + (kind.startsWith("click_grid") ? "click-grid navigation window — not bar, phrase or meter" : phrase ? "phrase spans" : s2Human(kind)) + " (" + kind + ")"));
  body.append(s2el("p", phrase ? "Default view: at most one per phrase span." : "Default view: at most one per navigation window.", "s2-claim"));
  body.append(s2el("p", "Ordering is the triage file's own rule; numeric confidence is uncalibrated and never shown as a probability or used for ordering.", "muted"));
  const lists = {};
  for(const group of ["shown", "navigation", "suppressed"]) { lists[group] = s2el("div", undefined, "s2-flag-list"); lists[group].id = "s2-flags-" + group; }
  body.append(lists.shown);
  const toggles = s2el("div", undefined, "s2-toggles");
  for(const [id, label, count, group, items] of [["s2-show-navigation", "Show navigation proxies", den.navigation_hidden, "navigation", doc.hidden_navigation],
    ["s2-show-suppressed", "Show suppressed", den.suppressed_lower_priority, "suppressed", doc.suppressed]]) {
    const wrap = s2el("label", undefined, "checkbox"), input = s2el("input");
    input.type = "checkbox";
    input.id = id;
    input.checked = false;
    input.addEventListener("change", () => s2RenderFlagList(lists[group], items, group, input.checked));
    wrap.append(input, s2el("span", label + " (" + count + ")"));
    toggles.append(wrap);
  }
  body.append(toggles, lists.navigation, lists.suppressed);
  s2RenderFlagList(lists.shown, doc.shown, "shown", true);
  s2RenderFlagList(lists.navigation, doc.hidden_navigation, "navigation", false);
  s2RenderFlagList(lists.suppressed, doc.suppressed, "suppressed", false);
}

// ----- phrase timing -----------------------------------------------------------
function s2TimingRow(row, delay) {
  const tr = s2el("tr");
  const measured = row.status === "measured";
  const compensated = Number.isFinite(row.median_offset_ms_delay_compensated);
  const median = compensated ? row.median_offset_ms_delay_compensated : row.median_offset_ms;
  const iqr = compensated ? row.iqr_ms_delay_compensated : row.iqr_ms;
  const label = s2el("td");
  label.append(s2Upstream("span", row.label === null || row.label === undefined ? "(unlabelled " + row.phrase_id + ")" : row.label));
  const span = Array.isArray(row.span_source_seconds) ? row.span_source_seconds : [];
  tr.append(label, s2el("td", s2Human(row.label_basis || "unknown")), s2el("td", s2Clock(span[0]) + " → " + s2Clock(span[1])), s2el("td", s2Human(row.status || "unknown")));
  if(measured && Number.isFinite(median)) {
    tr.append(s2el("td", "median offset " + s2Signed(median, 1) + " ms" + (compensated ? " (delay-compensated: " + s2Human(delay || "detector delay") + ")" : " (not delay-compensated)")));
    tr.append(s2el("td", Array.isArray(iqr) ? "IQR " + s2Signed(iqr[0], 1) + " … " + s2Signed(iqr[1], 1) + " ms" : "IQR unknown"));
    tr.append(s2el("td", "click-proximal n " + row.click_proximal_onset_count));
    tr.append(s2el("td", S2_TENDENCY[row.tendency_label] || "descriptive sign unknown"));
  } else {
    tr.append(s2el("td", "—"), s2el("td", "—"), s2el("td", "click-proximal n " + (Number.isFinite(row.click_proximal_onset_count) ? row.click_proximal_onset_count : "unknown")));
    tr.append(s2el("td", "abstained: " + s2Human(row.abstain_reason || "reason not recorded")));
  }
  return tr;
}
function s2RenderTiming() {
  const layer = s2Bundle.layers && s2Bundle.layers.phrase_timing;
  if(!layer || layer.status !== "available") return s2Unavailable("s2-timing", layer ? layer.reason : "layer_missing");
  const body = s2Body("s2-timing");
  body.replaceChildren();
  body.append(s2el("p", "MEASUREMENT · unvalidated until operator spot check · click identity unverified · capture latency uncalibrated", "s2-measure"));
  body.append(s2el("p", "Offsets are onset minus modelled click (negative = before the modelled click). They describe timing evidence only and never grade the performance.", "muted"));
  (layer.files || []).forEach((file, index) => {
    const doc = file.document || {}, rows = Array.isArray(doc.phrases) ? doc.phrases : [], delay = doc.detector_delay || {};
    const section = s2el("details", undefined, "s2-timing-file");
    section.open = index === 0;
    const summary = doc.summary || {};
    section.append(s2el("summary", s2Human(doc.phrase_basis || "phrase basis unknown") + " · measured " + (summary.measured_count ?? rows.filter(row => row.status === "measured").length) + " of " + rows.length + " · " + file.file + " " + s2Short(file.sha256)));
    section.append(s2el("p", "real-take status: " + s2Human(doc.real_take_status || "unknown") + " · detector delay: " + s2Human(delay.status || "uncalibrated") + " · physical capture latency: " + s2Human(doc.physical_capture_latency || "uncalibrated"), "muted"));
    const wrap = s2el("div", undefined, "s2-table-wrap"), table = s2el("table", undefined, "s2-table"), head = s2el("tr");
    for(const title of ["Phrase", "Label basis", "Span", "Status", "Median offset", "IQR", "Count", "Description"]) head.append(s2el("th", title));
    const thead = s2el("thead"), tbody = s2el("tbody");
    thead.append(head);
    for(const row of rows) tbody.append(s2TimingRow(row, delay.status));
    table.append(thead, tbody);
    wrap.append(table);
    section.append(wrap);
    body.append(section);
  });
  for(const refusal of layer.refused || []) body.append(s2el("p", "Timing file " + refusal.file + " unavailable: " + s2Human(refusal.reason), "s2-unavailable"));
}

// ----- prototypes --------------------------------------------------------------
function s2RenderPrototypes() {
  const body = s2Body("s2-prototypes");
  if(!body) return;
  body.replaceChildren();
  for(const [title, detail] of S2_PROTOTYPES) {
    const item = s2el("div", undefined, "s2-prototype");
    item.append(s2el("span", "PROTOTYPE · not implemented", "s2-badge s2-shape-plain s2-prototype-badge"), s2el("strong", title), s2el("span", " — " + detail, "muted"));
    body.append(item);
  }
}

// ----- labelling session -------------------------------------------------------
function s2QueueNotice(text, warn=false) {
  const target = byId("s2-queue-status");
  target.textContent = text;
  target.classList.toggle("s2-warn", warn);
}
function s2S1Locked() { return typeof issueBusy !== "undefined" && (issueBusy || issueUncertain); }
function s2Locked() { return s2State.busy || s2State.uncertain; }
function s2Controls() {
  const blocked = s2S1Locked();
  byId("s2-save").disabled = !s2State.session || s2State.busy || blocked || !s2State.queue.length;
  byId("s2-retry").hidden = !s2State.uncertain;
  byId("s2-retry").disabled = s2State.busy || blocked;
  byId("s2-undo").disabled = !s2State.session || s2Locked() || !s2State.queue.length;
  for(const id of ["s2-template", "s2-kind", "s2-certainty"]) byId(id).disabled = s2Locked();
  if(typeof issueBusy !== "undefined") {
    const save = byId("issue-save");
    if(s2Locked()) save.disabled = true;
    else if(!issueBusy && typeof issueStore !== "undefined" && issueStore) save.disabled = false;
  }
}
function s2RenderQueue() {
  const list = byId("s2-queue");
  list.replaceChildren();
  s2State.queue.forEach((item, index) => {
    const span = item.annotation.source_span;
    const entry = s2el("li", undefined, "s2-queued");
    entry.append(s2BadgeNode({store:true, basis:"operator_assertion"}), s2el("span", " " + s2Clock(span.start_seconds) + " · " + s2Human(item.annotation.kind) + " · point (extent unknown) · " + s2Human(item.annotation.operator_certainty) + " · key " + item.trigger + " · "));
    entry.append(s2Upstream("q", item.annotation.operator_quote));
    if(index === 0 && s2State.uncertain) entry.append(s2el("span", " · held for retry with its original key", "s2-warn"));
    if(item.error) entry.append(s2el("span", " · refused: " + s2Human(item.error), "s2-warn"));
    list.append(entry);
  });
  byId("s2-queue-count").textContent = s2State.queue.length + " queued";
  s2Controls();
}
function s2Now() { return Number(currentSource().toFixed(3)); }
function s2QueueMark(trigger) {
  if(!s2State.session) return false;
  if(s2Locked() || s2S1Locked()) { s2QueueNotice("A save is in progress or awaiting a retry; finish it before queueing more marks.", true); return false; }
  const quote = byId("s2-template").value;
  if(!quote.trim()) { s2QueueNotice("Type your template text first; it is saved verbatim as your words.", true); return false; }
  const time = s2Now(), timeline = session.timeline;
  if(!(Number.isFinite(time) && time >= timeline.source_min_seconds && time <= timeline.source_max_seconds)) { s2QueueNotice("The current position is outside the original recording.", true); return false; }
  const kind = trigger === "B" ? "phrase_duration" : byId("s2-kind").value;
  let note = "quick mark (key " + trigger + ") at " + s2Clock(time) + "; template text";
  const flag = s2State.lastFlag && s2State.lastFlag.flag;
  if(flag && time >= Number(flag.source_time_seconds) - 0.001 && time <= Number(flag.end_seconds ?? flag.source_time_seconds) + 0.001) note += "; near triaged flag " + s2State.lastFlag.flag_id + " (detector hypothesis)";
  const annotation = {kind, basis:"operator_assertion", status:"needs_review", source_span:{start_seconds:time, end_seconds:time, extent_known:false},
    reported_by:{actor:"operator", via:"browser"}, operator_certainty:byId("s2-certainty").value, operator_quote:quote, note};
  s2State.queue.push({annotation, trigger, error:null});
  s2QueueNotice("Queued " + s2State.queue.length + " unsaved mark" + (s2State.queue.length === 1 ? "" : "s") + ". Save queued marks when ready.");
  s2RenderQueue();
  return true;
}
function s2Undo() {
  if(s2Locked() || !s2State.queue.length) return false;
  s2State.queue.pop();
  s2QueueNotice("Removed the last unsaved mark.");
  s2RenderQueue();
  return true;
}
function s2SeekBoundary(direction) {
  const marks = s2Boundaries();
  if(!marks.length) { s2QueueNotice("No intent boundaries are available.", true); return null; }
  const now = Number(byId("position").value), reference = Number.isFinite(now) ? now : currentSource();
  const target = direction > 0 ? marks.find(value => value > reference + 0.01) : [...marks].reverse().find(value => value < reference - 0.01);
  if(target === undefined) { s2QueueNotice(direction > 0 ? "No later intent boundary." : "No earlier intent boundary."); return null; }
  seekSource(target);
  s2QueueNotice("At intent boundary " + s2Clock(target) + " (projected; not detected).");
  return target;
}
function s2SeekFlag(direction) {
  const flags = s2Shown().slice().sort((a, b) => a.flag.source_time_seconds - b.flag.source_time_seconds);
  if(!flags.length) { s2QueueNotice("No shown triaged flags are available.", true); return null; }
  const now = Number(byId("position").value), reference = Number.isFinite(now) ? now : currentSource();
  const item = direction > 0 ? flags.find(entry => entry.flag.source_time_seconds > reference + 0.01) : [...flags].reverse().find(entry => entry.flag.source_time_seconds < reference - 0.01);
  if(!item) { s2QueueNotice(direction > 0 ? "No later shown flag." : "No earlier shown flag."); return null; }
  s2State.lastFlag = item;
  seekSource(item.flag.source_time_seconds);
  s2QueueNotice("At " + item.flag_id + " · " + s2Human(item.flag.kind) + " (detector hypothesis).");
  return item.flag.source_time_seconds;
}
function s2KeyHandler(event) {
  if(!s2State.session) return;
  if(event.target && typeof event.target.matches === "function" && event.target.matches("input,select,textarea")) return;
  if(event.altKey || event.ctrlKey || event.metaKey || typeof event.key !== "string") return;
  const key = event.key.toLowerCase();
  if(event.shiftKey) {
    if(key === "n" || key === "p") { event.preventDefault(); s2SeekFlag(key === "n" ? 1 : -1); }
    return;
  }
  if(key === "b") { event.preventDefault(); s2QueueMark("B"); }
  else if(key === "i") { event.preventDefault(); s2QueueMark("I"); }
  else if(key === "n" || key === "p") { event.preventDefault(); s2SeekBoundary(key === "n" ? 1 : -1); }
  else if(key === "u") { event.preventDefault(); s2Undo(); }
}
function s2BarKey(event) {
  s2KeyHandler(event);
  if(!event.defaultPrevented && typeof transportKey === "function") transportKey(event);
}
function s2BuildRequest(annotation) {
  return JSON.stringify({schema_version:2, expected_revision:issueStore.revision, idempotency_key:"browser-" + crypto.randomUUID(),
    source_sha256:session.source_sha256, manifest_sha256:session.manifest_sha256, annotation});
}
async function s2SaveQueue() {
  if(s2State.busy || !s2State.queue.length) return;
  if(s2S1Locked()) { s2QueueNotice("The issue form above is saving or awaiting its retry; finish it first.", true); return; }
  if(typeof issueStore === "undefined" || !issueStore) { s2QueueNotice("Structured annotation saving is unavailable for this session.", true); return; }
  s2State.busy = true;
  s2Controls();
  let saved = 0, replayed = 0;
  try {
    while(s2State.queue.length) {
      const head = s2State.queue[0];
      if(!s2State.frozen) s2State.frozen = s2BuildRequest(head.annotation);
      let response, value;
      try {
        response = await fetch("/api/annotations-v2", {method:"POST", headers:{"Content-Type":"application/json", "X-Review-Token":session.token}, body:s2State.frozen});
        value = await response.json();
      } catch(_) {
        s2State.uncertain = true;
        s2QueueNotice("Save outcome unclear for the first queued mark. Retry the same mark to reconcile it; its bytes and key are held.", true);
        return;
      }
      if(response.status >= 500) {
        s2State.uncertain = true;
        s2QueueNotice("Server response leaves the save outcome unclear (" + s2Human(value && value.error || "status " + response.status) + "). Retry the same mark.", true);
        return;
      }
      if(!response.ok) {
        s2State.frozen = null;
        s2State.uncertain = false;
        if(value && value.error === "stale_annotation_revision") {
          try { await refreshIssues(); } catch(_) { /* The refreshed store stays unavailable; the queue is kept. */ }
          s2QueueNotice("Saved reports changed in another window. The remaining queue is kept with fresh keys; press Save queued marks again.", true);
          return;
        }
        head.error = String(value && value.error || "save_refused_status_" + response.status);
        s2QueueNotice("The first queued mark was refused (" + s2Human(head.error) + "); it stays in the queue and saving stopped.", true);
        return;
      }
      if(!value || value.schema_version !== 2 || value.source_sha256 !== session.source_sha256 || value.manifest_sha256 !== session.manifest_sha256 || !value.mutation || !value.mutation.annotation_id) {
        s2State.uncertain = true;
        s2QueueNotice("Save receipt identity is unclear. Retry the same mark to reconcile it.", true);
        return;
      }
      issueStore = value;
      s2State.frozen = null;
      s2State.uncertain = false;
      s2State.queue.shift();
      if(value.mutation.outcome === "replayed") replayed += 1; else saved += 1;
    }
    s2QueueNotice("Saved " + saved + " new mark" + (saved === 1 ? "" : "s") + (replayed ? " and reconciled " + replayed + " replay" + (replayed === 1 ? "" : "s") + " without duplicates" : "") + ". Musical verdict remains unestablished.");
  } finally {
    s2State.busy = false;
    s2RenderQueue();
    if(typeof renderIssues === "function") renderIssues();
    if(typeof renderCallouts === "function") renderCallouts();
    s2RenderUserLane();
  }
}
function s2SetSession(enabled) {
  s2State.session = !!enabled;
  byId("s2-session").checked = s2State.session;
  byId("s2-quickmark").hidden = !s2State.session;
  s2Controls();
}
function s2Wire() {
  if(s2State.wired) return;
  s2State.wired = true;
  const kinds = byId("s2-kind");
  if(kinds && !kinds.children.length) for(const kind of S2_KINDS) { const option = s2el("option", s2Human(kind)); option.value = kind; kinds.append(option); }
  kinds.value = "phrase_duration";
  byId("s2-certainty").value = "uncertain";
  byId("s2-session").addEventListener("change", event => s2SetSession(event.target.checked));
  byId("source-transport").addEventListener("keydown", s2KeyHandler);
  byId("s2-quickmark").addEventListener("keydown", s2BarKey);
  byId("s2-save").addEventListener("click", s2SaveQueue);
  byId("s2-retry").addEventListener("click", s2SaveQueue);
  byId("s2-undo").addEventListener("click", s2Undo);
  // The S1 issue form waits while a quick-mark save is busy or awaiting its retry.
  document.addEventListener("submit", event => {
    if(event.target && event.target.id === "issue-form" && s2Locked()) {
      event.preventDefault();
      event.stopImmediatePropagation();
      byId("issue-notice").textContent = "Quick-mark save in progress or awaiting its retry; finish it first.";
    }
  }, true);
  if(typeof window !== "undefined" && window.addEventListener) window.addEventListener("beforeunload", event => {
    if(s2State.queue.length) { event.preventDefault(); event.returnValue = ""; }
  });
  if(typeof players !== "undefined" && players) for(const player of players.values()) player.addEventListener("play", () => s2Exclusive(player));
  if(typeof MutationObserver !== "undefined") new MutationObserver(() => s2RenderUserLane()).observe(byId("saved-issues"), {childList:true});
  s2SetSession(false);
  s2RenderQueue();
}
function s2RenderAll() {
  s2RenderStages();
  s2RenderAB();
  s2RenderCoverage();
  s2RenderFlags();
  s2RenderTiming();
}
async function s2Init() {
  if(s2Initialized) return;
  s2Initialized = true;
  s2RenderPrototypes();
  s2Wire();
  let response, value;
  try {
    response = await fetch("/api/practice-s2", {cache:"no-store"});
    value = await response.json();
  } catch(_) {
    return s2AllUnavailable("practice_s2_route_unreachable");
  }
  if(!response.ok) return s2AllUnavailable(value && value.error || "practice_s2_bundle_not_configured");
  const binding = value && value.session_binding;
  if(!binding || binding.original_source_sha256 !== session.source_sha256 || binding.manifest_sha256 !== session.manifest_sha256)
    return s2AllUnavailable("foreign_recording", "S2 evidence belongs to another recording");
  s2Bundle = value;
  s2Ready = true;
  s2RenderAll();
}
document.addEventListener("review-ready", s2Init, {once:true});
if(typeof session !== "undefined" && session && typeof store !== "undefined" && store) s2Init();
