"use strict";
// Local source-clock controls and user assertions. No playback or remote service.
let issueStore = null, issueEditId = null, issueEditItem = null, pendingIssue = null;
let issueBusy = false, issueUncertain = false, practiceInitialized = false, lastCalloutSignature = null;
const issueFields = ["issue-start", "issue-end", "issue-span", "issue-kind", "issue-certainty", "issue-status", "issue-quote", "issue-note"];
function issueNotice(message, error=false) {
  byId("issue-notice").textContent=message;
  byId("issue-notice").classList.toggle("error",error);
}
function validSourceSpan(start, end, known, timeline) {
  return Number.isFinite(start)&&Number.isFinite(end)&&start>=timeline.source_min_seconds&&end<=timeline.source_max_seconds&&end>=start&&(known||end===start);
}
function updateLoopStatus() {
  const start=Number(byId("note-start").value),end=Number(byId("note-end").value);
  const enabled=byId("loop-span").checked;
  if(enabled&&(!validSourceSpan(start,end,true,session.timeline)||end<=start)) {
    byId("loop-span").checked=false;
    byId("loop-status").textContent="Choose a nonzero ordered source span before looping.";
    return false;
  }
  if(enabled) {
    const player=players.get(activeRole);
    const origin=activeRole==="video"?session.timeline.format_start_seconds:session.timeline.audio_start_seconds;
    if(!player||player.readyState<1||!Number.isFinite(player.duration)) {
      byId("loop-span").checked=false;
      byId("loop-status").textContent="Loop unavailable until this player's duration is known. Load or seek the player, then arm the loop.";
      return false;
    }
    if(start<origin||end>origin+player.duration) {
      byId("loop-span").checked=false;
      byId("loop-status").textContent="Loop span exceeds this player's source coverage: "+clock(origin)+" → "+clock(origin+player.duration)+". Choose a covered span or another player.";
      return false;
    }
  }
  byId("loop-status").textContent=enabled?"Loop armed: "+clock(start)+" → "+clock(end)+". Press play in the selected player.":"Loop off.";
  return enabled;
}
function transportKey(event) {
  // Native range arrows remain native; typing in form fields never seeks.
  if(event.target.matches("input,select,textarea")||event.altKey||event.ctrlKey||event.metaKey)return;
  if(event.key==="ArrowLeft"||event.key==="ArrowRight") {
    event.preventDefault();
    seekSource(currentSource()+(event.key==="ArrowLeft"?-1:1)*(event.shiftKey?5:1));
  } else if(event.key==="["||event.key==="]") {
    event.preventDefault();byId(event.key==="["?"span-start":"span-end").click();updateLoopStatus();
  } else if(event.key.toLowerCase()==="l") {
    event.preventDefault();byId("loop-span").checked=!byId("loop-span").checked;updateLoopStatus();
  }
}
function syncIssueExtent() {
  byId("issue-end").disabled=!byId("issue-span").checked;
  if(!byId("issue-span").checked)byId("issue-end").value=byId("issue-start").value;
}
function setIssueFieldsLocked(locked) {
  for(const id of issueFields)byId(id).disabled=locked||(id==="issue-end"&&!byId("issue-span").checked);
  for(const id of ["issue-capture","issue-now","issue-new"])byId(id).disabled=locked;
}
function resetIssue() {
  if(issueBusy||issueUncertain)return;
  issueEditId=null;issueEditItem=null;pendingIssue=null;
  byId("issue-start").value=currentSource().toFixed(3);
  byId("issue-end").value=byId("issue-start").value;
  byId("issue-span").checked=false;
  byId("issue-kind").value="rhythm_timing";
  byId("issue-certainty").value="uncertain";byId("issue-status").value="needs_review";
  byId("issue-quote").value="";byId("issue-note").value="";
  syncIssueExtent();issueNotice("Point timestamp; extent unknown. Your description stays verbatim.");
}
function evidenceLabel(basis) {
  return {operator_assertion:"USER REPORTED",operator_context:"INTENT",detector_hypothesis:"DETECTOR HYPOTHESIS",reference_comparison:"REFERENCE COMPARISON"}[basis]||"UNKNOWN BASIS";
}
function activeReviewBadge(source,start,end,known) {
  // Point cues dwell for0.75s after their timestamp; this is display behavior only.
  return known&&end>start?source>=start&&source<end:source>=start&&source<start+0.75;
}
function renderCallouts(source=currentSource()) {
  const target=byId("review-callouts");
  const active=[];
  for(const item of issueStore?.annotations||[]) {
    const span=item.source_span;
    if(activeReviewBadge(source,span.start_seconds,span.end_seconds,span.extent_known))active.push({label:evidenceLabel(item.basis),kind:item.kind,start:span.start_seconds,end:span.end_seconds,known:span.extent_known&&span.end_seconds>span.start_seconds,quote:item.operator_quote||item.note,user:item.basis==="operator_assertion"});
  }
  for(const item of session.markers||[])if(activeReviewBadge(source,item.source_start_seconds,item.source_end_seconds,item.source_end_seconds>item.source_start_seconds))active.push({label:"DETECTOR HYPOTHESIS",kind:item.kind,start:item.source_start_seconds,end:item.source_end_seconds,known:item.source_end_seconds>item.source_start_seconds,quote:"Review candidate; musical verdict unknown.",user:false});
  const signature=JSON.stringify(active);if(signature===lastCalloutSignature)return;lastCalloutSignature=signature;target.replaceChildren();
  for(const item of active.slice(0,4)) {
    const badge=node("div",undefined,"live-review-badge"+(item.user?" user-reported":""));
    badge.append(node("strong",item.label+" · "+human(item.kind)),node("span",item.known?clock(item.start)+" → "+clock(item.end):"Point @ "+clock(item.start)+" · display cue only"),node("small",item.quote.length>120?item.quote.slice(0,117)+"…":item.quote));target.append(badge);
  }
  if(active.length>4)target.append(node("p",String(active.length-4)+" more active review entries; see saved reports and proposals.","muted"));
  if(!active.length)target.append(node("p","No review badge at this source position.","muted"));
}
function renderIssues() {
  const target=byId("saved-issues");target.replaceChildren();
  if(!issueStore?.annotations?.length)target.append(node("p","No user-reported issues saved for this source yet.","empty"));
  for(const item of issueStore?.annotations||[]) {
    const span=item.source_span, article=node("article",undefined,"saved-issue");
    const userReported=item.basis==="operator_assertion";
    const label=evidenceLabel(item.basis);
    article.append(node("h3",clock(span.start_seconds)+(span.extent_known?" → "+clock(span.end_seconds):" · point")),
      node("p",label+" · "+human(item.kind)+(userReported?" · "+(item.operator_certainty==="confirmed"?"user reports certainty":"uncertain"):""),userReported?"issue-provenance":"hypothesis-label"),
      node("p",item.operator_quote||""),node("p",item.note),
      node("p","Reported by "+item.reported_by.actor+" via "+item.reported_by.via+" · "+human(item.status)+" · musical verdict not established","meta"));
    const actions=node("div",undefined,"issue-actions");
    for(const [title,handler] of [["Seek timestamp",()=>seekSource(span.start_seconds)],
      ["Use as listening span",()=>{byId("note-start").value=span.start_seconds.toFixed(3);byId("note-end").value=span.end_seconds.toFixed(3);seekSource(span.start_seconds);updateLoopStatus();}],
      ["Edit report",()=>{if(issueBusy||issueUncertain||!userReported)return;issueEditId=item.id;issueEditItem=item;pendingIssue=null;byId("issue-start").value=span.start_seconds.toFixed(3);byId("issue-end").value=span.end_seconds.toFixed(3);byId("issue-span").checked=span.extent_known;byId("issue-kind").value=item.kind;byId("issue-certainty").value=item.operator_certainty;byId("issue-status").value=item.status;byId("issue-quote").value=item.operator_quote;byId("issue-note").value=item.note;syncIssueExtent();byId("issue-quote").focus();issueNotice("Editing your saved report. Authorship remains user reported.");}]]) {
      if(title==="Edit report"&&!userReported)continue;
      const button=node("button",title,"quiet");button.type="button";button.addEventListener("click",handler);actions.append(button);
    }
    article.append(actions);target.append(article);
  }
}
async function refreshIssues() {
  const response=await fetch("/api/annotations-v2",{cache:"no-store"});
  const value=await response.json();
  if(!response.ok)throw new Error(human(value.error||"Issues unavailable"));
  if(value.schema_version!==2||value.source_sha256!==session.source_sha256||value.manifest_sha256!==session.manifest_sha256||!Array.isArray(value.annotations))throw new Error("Issue store identity does not match this recording.");
  issueStore=value;renderIssues();renderCallouts();if(!issueBusy)byId("issue-save").disabled=false;
}
function buildIssueRequest() {
  const start=Number(byId("issue-start").value),known=byId("issue-span").checked;
  const end=known?Number(byId("issue-end").value):start;
  if(byId("issue-start").value.trim()===""||(known&&byId("issue-end").value.trim()==="")||!validSourceSpan(start,end,known,session.timeline))throw new Error("Choose an ordered timestamp or span within the original recording.");
  const quote=byId("issue-quote").value,note=byId("issue-note").value;
  if(!quote.trim()||!note.trim())throw new Error("Add your exact description and listening context.");
  const annotation={kind:byId("issue-kind").value,basis:"operator_assertion",status:byId("issue-status").value,source_span:{start_seconds:start,end_seconds:end,extent_known:known},reported_by:{actor:"operator",via:"browser"},operator_certainty:byId("issue-certainty").value,operator_quote:quote,note};
  if(issueEditId){annotation.id=issueEditId;for(const key of ["candidate_id","reference_sha256"])if(issueEditItem?.[key])annotation[key]=issueEditItem[key];}
  return {schema_version:2,expected_revision:issueStore.revision,idempotency_key:"browser-"+crypto.randomUUID(),source_sha256:session.source_sha256,manifest_sha256:session.manifest_sha256,annotation};
}
async function saveIssue(event) {
  event.preventDefault();if(issueBusy||!issueStore)return;
  try {if(!pendingIssue)pendingIssue=buildIssueRequest();}catch(error){issueNotice(error.message,true);return;}
  issueBusy=true;setIssueFieldsLocked(true);byId("issue-save").disabled=true;
  try {
    const response=await fetch("/api/annotations-v2",{method:"POST",headers:{"Content-Type":"application/json","X-Review-Token":session.token},body:JSON.stringify(pendingIssue)});
    const value=await response.json();
    if(!response.ok) {
      if(response.status>=500)throw new Error(human(value.error||"Server response leaves save outcome unclear."));
      issueUncertain=false;pendingIssue=null;
      if(value.error==="stale_annotation_revision") {
        await refreshIssues();throw new Error("Reports changed in another window. Review the refreshed issues, then save your draft again.");
      }
      throw new Error(human(value.error||"Could not save this issue."));
    }
    if(value.schema_version!==2||value.source_sha256!==session.source_sha256||value.manifest_sha256!==session.manifest_sha256||!value.mutation?.annotation_id)throw new Error("Save receipt identity is unclear. Retry the same report to reconcile it.");
    issueStore=value;issueEditId=value.mutation.annotation_id;pendingIssue=null;issueUncertain=false;
    renderIssues();renderCallouts();issueNotice(value.mutation.outcome==="replayed"?"Report reconciled from its original save. No duplicate was added.":"User-reported issue saved. Musical verdict remains unestablished.");
  } catch(error) {
    // A transport error or malformed success may happen after commit. Keep exact bytes/key.
    issueUncertain=pendingIssue!==null;
    issueNotice(issueUncertain?"Save outcome unclear. Retry this same report to reconcile it; the draft is held unchanged. "+error.message:error.message,true);
  } finally {
    issueBusy=false;setIssueFieldsLocked(issueUncertain);byId("issue-save").disabled=false;
    byId("issue-save").textContent=issueUncertain?"Retry same report":"Save user-reported issue";
  }
}
async function initPractice() {
  if(practiceInitialized)return;practiceInitialized=true;
  document.addEventListener("review-position",event=>renderCallouts(event.detail.source));
  renderCallouts();
  byId("source-transport").addEventListener("keydown",transportKey);
  byId("loop-span").addEventListener("change",updateLoopStatus);
  for(const id of ["note-start","note-end"]){byId(id).addEventListener("change",updateLoopStatus);byId(id).addEventListener("input",updateLoopStatus);}
  for(const [role,player] of players)player.addEventListener("loadedmetadata",()=>{if(role===activeRole)updateLoopStatus();});
  for(const id of ["span-start","span-end"])byId(id).addEventListener("click",updateLoopStatus);
  for(const id of ["issue-start","issue-end"]) {byId(id).min=session.timeline.source_min_seconds;byId(id).max=session.timeline.source_max_seconds;}
  byId("issue-span").addEventListener("change",syncIssueExtent);
  byId("issue-start").addEventListener("input",syncIssueExtent);
  for(const id of issueFields)byId(id).addEventListener("input",()=>{if(!issueBusy&&!issueUncertain)pendingIssue=null;});
  byId("issue-now").addEventListener("click",()=>{byId("issue-start").value=currentSource().toFixed(3);byId("issue-span").checked=false;syncIssueExtent();pendingIssue=null;});
  byId("issue-capture").addEventListener("click",()=>{byId("issue-start").value=byId("note-start").value;byId("issue-end").value=byId("note-end").value;byId("issue-span").checked=Number(byId("issue-end").value)>Number(byId("issue-start").value);syncIssueExtent();pendingIssue=null;});
  byId("issue-new").addEventListener("click",resetIssue);
  byId("issue-form").addEventListener("submit",saveIssue);
  byId("refresh-issues").addEventListener("click",()=>refreshIssues().then(()=>issueNotice("Saved issues refreshed. Any held retry remains unchanged.")).catch(error=>issueNotice(error.message,true)));
  resetIssue();
  try {await refreshIssues();}catch(error){byId("issue-save").disabled=true;issueNotice("Structured issue saving unavailable: "+error.message+" Listening notes above remain available.",true);}
}
document.addEventListener("review-ready",initPractice,{once:true});
if(typeof session!=="undefined"&&session&&typeof store!=="undefined"&&store)initPractice();
