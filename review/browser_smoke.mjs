// Bounded CDP verification for the locally served review; no third-party modules.
import {writeFile} from "node:fs/promises";
const [debugPort, reviewURL, screenshotPath, annotationMode] = process.argv.slice(2);
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const target = targets.find(item => item.type === "page");
if (!target) throw new Error("No owned browser page is available");
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, {once:true});
  socket.addEventListener("error", reject, {once:true});
});
let sequence = 0;
const pending = new Map(), exceptions = [];
socket.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails.text);
  if (!pending.has(message.id)) return;
  const {resolve, reject, timeout} = pending.get(message.id);
  clearTimeout(timeout);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message)); else resolve(message.result);
});
function command(method, params={}) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {pending.delete(id); reject(new Error(`CDP timeout: ${method}`));}, 8000);
    pending.set(id, {resolve, reject, timeout});
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression, awaitPromise=false) {
  const result = await command("Runtime.evaluate", {expression, returnByValue:true, awaitPromise, userGesture:true});
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}
await command("Runtime.enable");
await command("Page.enable");
await command("Emulation.setDeviceMetricsOverride", {width:1440, height:1250, deviceScaleFactor:1, mobile:false});
await command("Page.navigate", {url:reviewURL});
for (let attempt=0; attempt<30; attempt++) {
  if (await evaluate('typeof session !== "undefined" && session !== null && document.getElementById("notice").textContent.startsWith("Ready")')) break;
  await new Promise(resolve => setTimeout(resolve, 100));
}
const initial = await evaluate(`({ready:document.getElementById("notice").textContent,markers:session?.markers.length,media:Object.keys(session?.media||{}),sourcePathExposed:document.body.textContent.includes("/Users/jess/Documents"),horizontalOverflow:document.documentElement.scrollWidth>innerWidth})`);
const filter = await evaluate(`(() => {const select=document.getElementById("kind-filter");if(select.options.length<2)return {available:false};select.value=select.options[1].value;select.dispatchEvent(new Event("change"));return {available:true,shown:document.querySelectorAll(".candidate").length,total:session.markers.length};})()`);
await evaluate('document.querySelector(".candidate")?.click()');
await new Promise(resolve => setTimeout(resolve, 500));
const navigation = await evaluate('({sourceStart:Number(document.getElementById("note-start").value),sourceEnd:Number(document.getElementById("note-end").value),selected:document.getElementById("selected-proposal").textContent})');
const metadata = await evaluate(`(async()=>{const values=[];for(const player of document.querySelectorAll("video,audio")){player.muted=true;player.load();await new Promise(resolve=>{if(player.readyState>=1)return resolve();player.addEventListener("loadedmetadata",resolve,{once:true});player.addEventListener("error",resolve,{once:true});setTimeout(resolve,2500);});values.push({type:player.tagName.toLowerCase(),duration:Number.isFinite(player.duration)?player.duration:null,readyState:player.readyState,error:player.error?.code||null});}return values;})()`, true);
const playback = await evaluate(`(async()=>{const player=document.querySelector("video")||document.querySelector("audio");if(!player)return {available:false};player.muted=true;player.currentTime=Math.min(10,Math.max(0,(player.duration||10)/2));const before=player.currentTime;try{await player.play();await new Promise(resolve=>setTimeout(resolve,700));player.pause();return {available:true,muted:true,advancedSeconds:player.currentTime-before,decodedVideoFrames:player.getVideoPlaybackQuality?.().totalVideoFrames||null};}catch(error){return {available:true,muted:true,error:error.name};}})()`, true);
let annotations = {state:"not_written_during_actual_take_check"};
if (annotationMode === "synthetic-annotation") {
  annotations = await evaluate(`(async()=>{if(!session.source_name.startsWith("synthetic-"))throw new Error("Annotation smoke requires a synthetic fixture");const before=store.revision;document.getElementById("note-text").value="Automated synthetic UI check; not an operator listening observation.";document.getElementById("annotation-form").requestSubmit();for(let i=0;i<30&&store.revision===before;i++)await new Promise(resolve=>setTimeout(resolve,100));const saved=store.revision===before+1;const record=store.annotations.find(item=>item.note.startsWith("Automated synthetic UI check"));if(record){const article=[...document.querySelectorAll(".saved-note")].find(item=>item.textContent.includes(record.note));[...article.querySelectorAll("button")].find(item=>item.textContent==="Edit note").click();document.getElementById("note-text").value="Automated synthetic UI check updated; no listening acceptance.";document.getElementById("annotation-form").requestSubmit();for(let i=0;i<30&&store.revision===before+1;i++)await new Promise(resolve=>setTimeout(resolve,100));}await refreshNotes();return {state:"synthetic_fixture_only",saved,updated:store.revision===before+2,reloadedNote:store.annotations.find(item=>item.id===record?.id)?.note,acceptance:store.listening_acceptance};})()`, true);
}
const screenshot = await command("Page.captureScreenshot", {format:"png", captureBeyondViewport:false});
await writeFile(screenshotPath, Buffer.from(screenshot.data, "base64"));
await command("Emulation.setDeviceMetricsOverride", {width:390, height:844, deviceScaleFactor:1, mobile:true});
const mobile = await evaluate('({width:innerWidth,documentWidth:document.documentElement.scrollWidth,horizontalOverflow:document.documentElement.scrollWidth>innerWidth})');
const receipt = {initial, filter, navigation, metadata, playback, annotations, mobile, runtimeExceptions:exceptions,
  screenshot:"review-preview.png", evidenceKind:"muted_browser_decode_and_navigation_not_listening_acceptance"};
process.stdout.write(JSON.stringify(receipt)+"\n");
try { await command("Browser.close"); } catch (_) { /* Closing may end the socket before its reply. */ }
socket.close();
