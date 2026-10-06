// Bounded CDP walkthrough of the S2 practice page; no third-party modules.
// Usage: node browser_smoke_s2.mjs <debugPort> <reviewURL> <outputDir> <synthetic|real>
import {writeFile} from "node:fs/promises";
const [debugPort, reviewURL, outputDir, mode] = process.argv.slice(2);
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const target = targets.find(item => item.type === "page");
if (!target) throw new Error("No owned browser page is available");
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, {once:true});
  socket.addEventListener("error", reject, {once:true});
});
let sequence = 0;
const pending = new Map();
let exceptions = [];
socket.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
  if (message.method === "Page.javascriptDialogOpening") command("Page.handleJavaScriptDialog", {accept:true}).catch(() => {});
  if (!pending.has(message.id)) return;
  const {resolve, reject, timeout} = pending.get(message.id);
  clearTimeout(timeout);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message)); else resolve(message.result);
});
function command(method, params={}) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {pending.delete(id); reject(new Error(`CDP timeout: ${method}`));}, 10000);
    pending.set(id, {resolve, reject, timeout});
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression, awaitPromise=false) {
  const result = await command("Runtime.evaluate", {expression, returnByValue:true, awaitPromise, userGesture:false});
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function key(keyName, {shift=false}={}) {
  const codes = {ArrowRight:["ArrowRight", 39], ArrowLeft:["ArrowLeft", 37]};
  const upper = keyName.length === 1 ? keyName.toUpperCase() : keyName;
  const [code, vk] = codes[keyName] || ["Key" + upper, upper.charCodeAt(0)];
  const keyValue = keyName.length === 1 ? (shift ? upper : keyName.toLowerCase()) : keyName;
  const modifiers = shift ? 8 : 0;
  await command("Input.dispatchKeyEvent", {type:"keyDown", key:keyValue, code, windowsVirtualKeyCode:vk, modifiers});
  await command("Input.dispatchKeyEvent", {type:"keyUp", key:keyValue, code, windowsVirtualKeyCode:vk, modifiers});
}
async function waitFor(expression, attempts=60, delay=100) {
  for (let attempt = 0; attempt < attempts; attempt++) {
    if (await evaluate(expression)) return true;
    await sleep(delay);
  }
  return false;
}
const VERDICT = String.raw`\b(?:rushed|dragged|late|early|mistakes?|errors?|wrong|missed|sloppy|tight)\b`;
const PANELS = ["s2-stages", "s2-ab", "s2-coverage", "s2-flags", "s2-timing", "s2-prototypes"];
const pageState = `(() => {
  const panels = {};
  for (const id of ${JSON.stringify(PANELS)}) {
    const section = document.getElementById(id), body = document.getElementById(id + "-body");
    const rect = section.getBoundingClientRect(), text = body.textContent.trim();
    panels[id] = {visible: rect.height > 0 && getComputedStyle(section).display !== "none", text_length: text.length,
      unavailable: text.startsWith("Unavailable") || text.includes("belongs to another recording") ? text.slice(0, 160) : null};
  }
  const generated = [], upstream = [];
  for (const id of ${JSON.stringify(PANELS)}.concat(["s2-quickmark"])) {
    const clone = document.getElementById(id === "s2-quickmark" ? id : id + "-body").cloneNode(true);
    for (const item of clone.querySelectorAll(".s2-upstream")) { upstream.push(item.textContent); item.remove(); }
    for (const item of clone.querySelectorAll("option")) item.remove();
    generated.push(clone.textContent);
  }
  const verdict = new RegExp(${JSON.stringify(VERDICT)}, "gi");
  const hits = generated.join(" \\n ").match(verdict) || [];
  const media = [...document.querySelectorAll("audio,video")];
  return {innerWidth, scrollWidth: document.documentElement.scrollWidth, horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
    panels, verdictHits: hits, upstreamNodes: upstream.length,
    players: media.map(item => ({tag: item.tagName.toLowerCase(), paused: item.paused, preload: item.preload, autoplay: item.autoplay})),
    s2Ready: typeof s2Ready !== "undefined" ? s2Ready : null};
})()`;
async function load() {
  await command("Page.navigate", {url:reviewURL});
  await waitFor('typeof session !== "undefined" && session !== null && document.getElementById("notice").textContent.startsWith("Ready")', 80);
  await waitFor('typeof s2Initialized !== "undefined" && s2Initialized && !document.getElementById("s2-ab-body").textContent.startsWith("Loading")', 80);
}
async function screenshot(name, elementId) {
  if (elementId) await evaluate(`document.getElementById(${JSON.stringify(elementId)}).scrollIntoView()`);
  await sleep(150);
  const shot = await command("Page.captureScreenshot", {format:"png", captureBeyondViewport:false});
  const path = `${outputDir}/${name}.png`;
  await writeFile(path, Buffer.from(shot.data, "base64"));
  return `${name}.png`;
}
async function keyActions() {
  // Navigation keys only (read-only): labelling session on, N/P and Shift+N/P, then arrows.
  await evaluate('document.getElementById("s2-session").click(); document.getElementById("source-transport").focus(); true');
  const before = await evaluate('Number(document.getElementById("position").value)');
  for (const [name, shift] of [["n", false], ["n", false], ["p", false], ["n", true], ["p", true], ["ArrowRight", false]]) { await key(name, {shift}); await sleep(120); }
  const after = await evaluate('({position:Number(document.getElementById("position").value), status:document.getElementById("s2-queue-status").textContent, queue:s2State.queue.length})');
  await evaluate('document.getElementById("s2-session").click(); true');
  return {before, after, keys:["N", "N", "P", "Shift+N", "Shift+P", "ArrowRight"]};
}
async function triageCounts() {
  return evaluate(`(() => {
    const result = {};
    for (const id of ["s2-show-navigation", "s2-show-suppressed"]) { const box = document.getElementById(id); if (box && !box.checked) box.click(); }
    for (const group of ["shown", "navigation", "suppressed"]) { const list = document.getElementById("s2-flags-" + group); result[group] = list ? list.querySelectorAll(".s2-flag").length : null; }
    const den = s2Bundle?.layers?.flags_triage?.document?.denominators || null;
    for (const id of ["s2-show-navigation", "s2-show-suppressed"]) { const box = document.getElementById(id); if (box && box.checked) box.click(); }
    result.denominators = den;
    result.matches = den ? result.shown === den.shown && result.navigation === den.navigation_hidden && result.suppressed === den.suppressed_lower_priority : null;
    return result;
  })()`);
}
async function revealCheck() {
  const first = await evaluate(`(() => { const button = [...document.querySelectorAll("#s2-ab-body button")].find(item => item.textContent === "Reveal which is FULLER"); if (!button) return null; button.click(); return document.querySelector("#s2-ab-body .s2-mapping").textContent; })()`);
  await load();
  const afterReload = await evaluate('document.querySelector("#s2-ab-body .s2-mapping")?.textContent || null');
  return {revealedText:first, afterReload, persisted: afterReload !== null && afterReload === first};
}
async function labellingSession() {
  if (!(await evaluate('session.source_name.startsWith("synthetic-")'))) throw new Error("Quick-mark smoke requires a synthetic fixture");
  const started = Date.now();
  await evaluate(`(() => { const box = document.getElementById("s2-session"); if (!box.checked) box.click();
    const input = document.getElementById("s2-template"); input.value = "synthetic walkthrough boundary (automated; not an operator mark)";
    seekSource(session.timeline.source_min_seconds); document.getElementById("source-transport").focus(); return true; })()`);
  await waitFor('Math.abs(currentSource() - Number(document.getElementById("position").value)) < 0.02', 60, 50);
  const times = [], navigation = [];
  let queueKeys = 0;
  for (let index = 0; index < 12; index++) {
    if (index > 0 && index < 11) {
      const before = await evaluate("currentSource()");
      await key("ArrowRight"); navigation.push("ArrowRight");
      await waitFor(`Math.abs(currentSource() - ${before + 1}) < 0.02 || currentSource() >= session.timeline.source_max_seconds - 0.02`, 40, 50);
    } else if (index === 11) {
      await key("p"); navigation.push("P");
      await waitFor('Math.abs(currentSource() - Number(document.getElementById("position").value)) < 0.02', 40, 50);
    }
    await key("b"); queueKeys += 1;
    times.push(await evaluate("s2State.queue.at(-1)?.annotation.source_span.start_seconds ?? null"));
  }
  const queued = await evaluate("s2State.queue.length");
  const revisionBefore = await evaluate("issueStore.revision");
  await evaluate('document.getElementById("s2-save").click(); true');
  await waitFor("s2State.queue.length === 0 && !s2State.busy", 100, 100);
  const wallSeconds = (Date.now() - started) / 1000;
  const status = await evaluate('document.getElementById("s2-queue-status").textContent');
  await load();
  const readBack = await evaluate(`(async () => { const value = await (await fetch("/api/annotations-v2", {cache:"no-store"})).json();
    const marks = value.annotations.filter(item => item.note.startsWith("quick mark (key B)"));
    return {revision:value.revision, count:marks.length, distinctTimes:new Set(marks.map(item => item.source_span.start_seconds)).size,
      claimLabels:[...new Set(marks.map(item => item.claim_label))], bases:[...new Set(marks.map(item => item.basis))], verdicts:[...new Set(marks.map(item => item.musical_verdict))],
      userLaneMarks:document.querySelectorAll(".s2-user").length}; })()`, true);
  return {state:"synthetic_fixture_only", queued, queueKeystrokes:queueKeys, saveActions:1, navigationKeystrokes:navigation,
    markTimes:times, distinctQueuedTimes:new Set(times).size, revisionBefore, status, readBack, wallSeconds,
    note:"wall time of an automated run; no operator-speed claim"};
}
const configs = [
  {name:"desktop-1440", width:1440, height:1000, deviceScaleFactor:1, mobile:false},
  {name:"mobile-375", width:375, height:812, deviceScaleFactor:3, mobile:true},
  {name:"mobile-390", width:390, height:844, deviceScaleFactor:3, mobile:true},
  {name:"zoom-200", width:720, height:1000, deviceScaleFactor:2, mobile:false, note:"200% zoom of a 1440 px window as 720 CSS px at DPR 2"},
];
await command("Runtime.enable");
await command("Page.enable");
const results = [];
let labelling = {state:"not_written_during_real_take_check"}, reveal = null;
for (const config of configs) {
  exceptions = [];
  await command("Emulation.setDeviceMetricsOverride", {width:config.width, height:config.height, deviceScaleFactor:config.deviceScaleFactor, mobile:config.mobile});
  await load();
  const afterLoad = await evaluate(pageState);
  const shots = [await screenshot(`${config.name}-top`, null), await screenshot(`${config.name}-ab`, "s2-ab"), await screenshot(`${config.name}-coverage`, "s2-coverage"), await screenshot(`${config.name}-flags`, "s2-flags")];
  const keys = await keyActions();
  const triage = await triageCounts();
  if (config.name === "desktop-1440") {
    if (mode === "synthetic") labelling = await labellingSession();
    reveal = await revealCheck();
  }
  const afterKeys = await evaluate(pageState);
  if (mode === "synthetic" && config.name === "desktop-1440") shots.push(await screenshot(`${config.name}-coverage-after-marks`, "s2-coverage"));
  results.push({...config, afterLoad, afterKeys, keys, triage, screenshots:shots, exceptions:[...exceptions], exceptionCount:exceptions.length,
    allPlayersPaused: afterLoad.players.every(item => item.paused) && afterKeys.players.every(item => item.paused)});
}
const source = await evaluate("({source_name:session.source_name, source_sha256:session.source_sha256})");
process.stdout.write(JSON.stringify({mode, source, configs:results, labelling, reveal,
  summary:{noOverflow:results.filter(item => !item.afterLoad.horizontalOverflow && !item.afterKeys.horizontalOverflow).length,
    configs:results.length, playersChecked:results.reduce((total, item) => total + item.afterLoad.players.length + item.afterKeys.players.length, 0),
    allPaused:results.every(item => item.allPlayersPaused), verdictHits:results.reduce((total, item) => total + item.afterLoad.verdictHits.length + item.afterKeys.verdictHits.length, 0),
    exceptions:results.reduce((total, item) => total + item.exceptionCount, 0)},
  evidenceKind:"muted_browser_render_and_navigation_not_listening_acceptance"}) + "\n");
try { await command("Browser.close"); } catch (_) { /* Closing may end the socket before its reply. */ }
socket.close();
