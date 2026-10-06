"""Behavior checks of the local practice controls using the shipped JavaScript."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
HARNESS = r'''
const fs=require("fs"),vm=require("vm");
const elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{value:"",checked:false,disabled:false,textContent:"",classList:{toggle(){}},children:[],append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},addEventListener(){},focus(){},click(){this.clicked=true}});return elements.get(id)}
let serial=0,seek=null,prevented=false,requests=[],replies=[];
const context={console,Number,Math,Array,JSON,Error,Set,players:new Map([["original",{duration:10,readyState:1}],["video",{duration:11,readyState:1}]]),activeRole:"original",crypto:{randomUUID:()=>"key-"+(++serial)},document:{addEventListener(){}},byId:element,session:{token:"test-token",source_sha256:"a".repeat(64),manifest_sha256:"b".repeat(64),timeline:{source_min_seconds:1,source_max_seconds:12,audio_start_seconds:2,format_start_seconds:1}},currentSource:()=>4.5,seekSource:value=>{seek=value},clock:value=>String(value),human:value=>String(value).replaceAll("_"," "),node:(tag,text,cls)=>({tag,text,cls,children:[],append(...items){this.children.push(...items)},addEventListener(){}}),fetch:async(url,options)=>{requests.push({url,options});const reply=replies.shift();if(reply instanceof Error)throw reply;return {ok:reply.ok,status:reply.status||200,json:async()=>reply.value}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],"utf8"),context);
function run(code){return vm.runInContext(code,context)}
function emit(value){console.log(JSON.stringify(value))}
'''


@unittest.skipUnless(NODE, "Node required for shipped JavaScript behavior")
class PracticeUITests(unittest.TestCase):
    def check_js(self, code):
        result = subprocess.run([NODE, "-e", HARNESS + code, str(ROOT / "review/practice.js")], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_point_and_span_require_finite_original_source_bounds(self):
        value=self.check_js('emit(run(`[validSourceSpan(1,1,false,session.timeline),validSourceSpan(1,2,false,session.timeline),validSourceSpan(1,2,true,session.timeline),validSourceSpan(0,2,true,session.timeline),validSourceSpan(2,13,true,session.timeline),validSourceSpan(4,3,true,session.timeline),validSourceSpan(NaN,3,true,session.timeline),validSourceSpan(2,Infinity,true,session.timeline)]`));')
        self.assertEqual(value,[True,False,True,False,False,False,False,False])

    def test_keyboard_seek_preserves_typing_and_modifier_keys(self):
        value=self.check_js('context.event={target:{matches:()=>false},key:"ArrowRight",shiftKey:true,preventDefault:()=>{prevented=true}};run("transportKey(event)");const first={seek,prevented};seek=null;prevented=false;context.event.target.matches=()=>true;run("transportKey(event)");emit({first,typing:{seek,prevented}});')
        self.assertEqual(value,{"first":{"seek":9.5,"prevented":True},"typing":{"seek":None,"prevented":False}})

    def test_zero_span_does_not_arm_loop(self):
        value=self.check_js('element("note-start").value="4";element("note-end").value="4";element("loop-span").checked=true;const enabled=run("updateLoopStatus()");emit({enabled,checked:element("loop-span").checked,text:element("loop-status").textContent});')
        self.assertFalse(value["enabled"]);self.assertFalse(value["checked"])
        self.assertIn("nonzero",value["text"])

    def test_loop_refuses_global_span_before_active_audio_origin(self):
        value=self.check_js('element("note-start").value="1";element("note-end").value="1.5";element("loop-span").checked=true;const enabled=run("updateLoopStatus()");emit({enabled,armed:element("loop-span").checked,message:element("loop-status").textContent});')
        self.assertFalse(value["enabled"]);self.assertFalse(value["armed"])
        self.assertIn("source coverage: 2 → 12",value["message"])

    def test_loop_revalidates_video_to_audio_and_unknown_duration(self):
        value=self.check_js('element("note-start").value="1";element("note-end").value="1.5";element("loop-span").checked=true;context.activeRole="video";const video=run("updateLoopStatus()");context.activeRole="original";const audio=run("updateLoopStatus()");element("note-start").value="4";element("note-end").value="5";element("loop-span").checked=true;context.players.get("original").duration=NaN;const unknown=run("updateLoopStatus()");emit({video,audio,unknown,message:element("loop-status").textContent});')
        self.assertEqual([value["video"],value["audio"],value["unknown"]],[True,False,False])
        self.assertIn("duration is known",value["message"])
        self.assertIn('if(typeof updateLoopStatus==="function")updateLoopStatus();updatePosition();}',(ROOT / "review/app.js").read_text())

    def test_request_preserves_quote_and_point_extent(self):
        value=self.check_js('run("issueStore={revision:3}");element("issue-start").value="7.25";element("issue-end").value="11";element("issue-kind").value="phrase_duration";element("issue-certainty").value="uncertain";element("issue-status").value="needs_review";element("issue-quote").value="  I rushed? <script>literal</script>  ";element("issue-note").value="Compare second repeat";emit(run("buildIssueRequest()"));')
        self.assertEqual(value["annotation"]["operator_quote"],"  I rushed? <script>literal</script>  ")
        self.assertEqual(value["annotation"]["source_span"],{"start_seconds":7.25,"end_seconds":7.25,"extent_known":False})
        self.assertEqual(value["annotation"]["basis"],"operator_assertion")
        self.assertEqual(value["expected_revision"],3)

    def test_unclear_save_retries_identical_request_then_reconciles(self):
        value=self.check_js('''
run("issueStore={revision:0,annotations:[]}");
element("issue-start").value="4.5";element("issue-kind").value="rhythm_timing";element("issue-certainty").value="uncertain";element("issue-status").value="needs_review";element("issue-quote").value="Might have rushed";element("issue-note").value="Review attack";
replies.push(new Error("lost connection"),{ok:true,value:{schema_version:2,source_sha256:"a".repeat(64),manifest_sha256:"b".repeat(64),revision:1,annotations:[],mutation:{outcome:"replayed",annotation_id:"id1"}}});
(async()=>{await run("saveIssue({preventDefault(){}})");const locked=element("issue-quote").disabled;await run("saveIssue({preventDefault(){}})");emit({locked,equal:requests[0].options.body===requests[1].options.body,unlocked:!element("issue-quote").disabled,notice:element("issue-notice").textContent,revision:run("issueStore.revision")});})().catch(error=>{throw error});
''')
        self.assertTrue(value["locked"]);self.assertTrue(value["equal"]);self.assertTrue(value["unlocked"])
        self.assertEqual(value["revision"],1);self.assertIn("No duplicate",value["notice"])

    def test_stale_save_refreshes_without_retrying_or_erasing_draft(self):
        value=self.check_js('''
run("issueStore={revision:0,annotations:[]}");element("issue-start").value="4.5";element("issue-kind").value="noise";element("issue-certainty").value="uncertain";element("issue-status").value="needs_review";element("issue-quote").value="Fan here";element("issue-note").value="Compare residue";
replies.push({ok:false,value:{error:"stale_annotation_revision"}},{ok:true,value:{schema_version:2,source_sha256:"a".repeat(64),manifest_sha256:"b".repeat(64),revision:2,annotations:[]}});
(async()=>{await run("saveIssue({preventDefault(){}})");emit({requests:requests.map(x=>({url:x.url,method:x.options?.method||"GET"})),quote:element("issue-quote").value,pending:run("pendingIssue"),revision:run("issueStore.revision"),notice:element("issue-notice").textContent});})();
''')
        self.assertEqual(value["requests"],[{"url":"/api/annotations-v2","method":"POST"},{"url":"/api/annotations-v2","method":"GET"}])
        self.assertEqual(value["quote"],"Fan here");self.assertIsNone(value["pending"]);self.assertEqual(value["revision"],2)
        self.assertIn("save your draft again",value["notice"])

    def test_server5xx_retains_replay_key_instead_of_creating_duplicate(self):
        value=self.check_js('''run("issueStore={revision:0,annotations:[]}");element("issue-start").value="4";element("issue-kind").value="other";element("issue-certainty").value="uncertain";element("issue-status").value="needs_review";element("issue-quote").value="Unknown outcome";element("issue-note").value="Keep this draft";replies.push({ok:false,status:500,value:{error:"server_error"}});(async()=>{await run("saveIssue({preventDefault(){}})");emit({pending:run("pendingIssue.idempotency_key"),locked:element("issue-quote").disabled,button:element("issue-save").textContent});})();''')
        self.assertEqual(value["pending"],"browser-key-1");self.assertTrue(value["locked"])
        self.assertEqual(value["button"],"Retry same report")

    def test_edit_keeps_review_state_and_optional_reference_receipts(self):
        value=self.check_js('''run("issueStore={revision:4};issueEditId='existing-id';issueEditItem={candidate_id:'c'.repeat(64),reference_sha256:'d'.repeat(64)}");element("issue-start").value="4";element("issue-kind").value="phrase_duration";element("issue-certainty").value="confirmed";element("issue-status").value="accepted_observation";element("issue-quote").value="My exact statement";element("issue-note").value="Existing context";emit(run("buildIssueRequest().annotation"));''')
        self.assertEqual(value["status"],"accepted_observation")
        self.assertEqual(value["candidate_id"],"c"*64);self.assertEqual(value["reference_sha256"],"d"*64)
        self.assertEqual(value["basis"],"operator_assertion")

    def test_point_badge_dwell_is_display_only_and_span_end_is_exclusive(self):
        value=self.check_js('emit(run(`[activeReviewBadge(4,4,4,false),activeReviewBadge(4.749,4,4,false),activeReviewBadge(4.75,4,4,false),activeReviewBadge(3.99,4,4,false),activeReviewBadge(4.5,4,4.5,true),activeReviewBadge(4.499,4,4.5,true)]`));')
        self.assertEqual(value,[True,True,False,False,False,True])

    def test_saved_evidence_keeps_all_four_authorship_labels_distinct(self):
        value=self.check_js('''run("issueStore={annotations:['operator_assertion','operator_context','detector_hypothesis','reference_comparison'].map(basis=>({basis,kind:'other',source_span:{start_seconds:4,end_seconds:4,extent_known:false},operator_certainty:basis==='operator_assertion'?'confirmed':null,operator_quote:basis==='operator_assertion'?'Literal quote':null,note:'Context',reported_by:{actor:basis==='detector_hypothesis'?'detector':'operator',via:'cli'},status:'needs_review'}))}");run("renderIssues()");emit(element("saved-issues").children.map(article=>article.children[1].text));''')
        self.assertEqual(value,["USER REPORTED · other · user reports certainty","INTENT · other","DETECTOR HYPOTHESIS · other","REFERENCE COMPARISON · other"])

    def test_assets_do_not_inject_reports_as_html_or_start_playback(self):
        text=(ROOT / "review/practice.js").read_text()
        self.assertNotIn("innerHTML",text);self.assertNotIn(".play()",text)
        self.assertIn('"USER REPORTED',text)
        self.assertIn("DETECTOR HYPOTHESIS",(ROOT / "review/app.js").read_text())


if __name__=="__main__":unittest.main()
