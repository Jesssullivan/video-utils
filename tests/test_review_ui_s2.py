"""S2 practice UI: shipped JavaScript behaviour under Node plus the bundle composer and routes."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "review"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(REVIEW))
import annotation_v2  # noqa: E402
import make_practice_fixture_s2 as fixture_s2  # noqa: E402
import practice_s2_bundle as bundle_s2  # noqa: E402
import practice_s2_routes as routes_s2  # noqa: E402
import review_server  # noqa: E402

NODE = shutil.which("node")
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg")
TEST_TMP = ROOT / "artifacts" / "s2" / "ui_core" / "test-tmp"
VERDICT = re.compile(r"\b(?:rushed|dragged|late|early|mistakes?|errors?|wrong|missed|sloppy|tight)\b", re.IGNORECASE)
UNKNOWN_KEYS = ["operator_preference", "listening_acceptance", "perceived_fullness", "nasal_quality", "fundamental_32hz_presence",
                "monitoring_device", "true_peak_dbtp", "fan_only_gain", "music_only_gain", "click_identity", "physical_capture_latency",
                "detector_delay", "meter", "downbeat_confirmed", "anchor_adopted", "breakdown1_execution", "real_take_phrase_correctness",
                "missed_or_extra_notes", "phrase_timing.real_take_status", "browser_level_match", "walkthrough_listening"]

HARNESS = r'''
const fs=require("fs"),vm=require("vm");
const [s2Path,s1Path,bundlePath,sessionPath]=process.argv.slice(1);
class TextNode{constructor(t){this.textContent=String(t);this.children=[];this.className="";}}
class El{
  constructor(tag){this.tagName=String(tag).toUpperCase();this.children=[];this.attributes={};this.listeners={};this.style={};this.dataset={};this._text="";
    this.hidden=false;this.disabled=false;this.checked=false;this.value="";this.className="";this.paused=true;this.playCalls=0;this.pauseCalls=0;this.readyState=1;this.duration=10;this.currentTime=0;
    const self=this;const names=()=>new Set(self.className.split(" ").filter(Boolean));
    this.classList={add(c){const s=names();s.add(c);self.className=[...s].join(" ")},toggle(c,on){const s=names();if(on===undefined?!s.has(c):on)s.add(c);else s.delete(c);self.className=[...s].join(" ")},contains(c){return names().has(c)}};}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join("")}
  set textContent(v){this._text=String(v);this.children=[]}
  append(...items){for(const i of items)this.children.push(typeof i==="string"?new TextNode(i):i)}
  replaceChildren(...items){this.children=[];this.append(...items)}
  setAttribute(k,v){this.attributes[k]=String(v)} getAttribute(k){return k in this.attributes?this.attributes[k]:null}
  addEventListener(t,f){(this.listeners[t]||=[]).push(f)}
  dispatch(t,extra={}){const e={target:this,defaultPrevented:false,preventDefault(){this.defaultPrevented=true},stopImmediatePropagation(){},...extra};for(const f of this.listeners[t]||[])f(e);return e}
  click(){this.dispatch("click")} focus(){} load(){}
  pause(){this.pauseCalls++;this.paused=true}
  play(){this.playCalls++;this.paused=false;return Promise.resolve()}
  matches(sel){return sel.split(",").map(x=>x.trim().toUpperCase()).includes(this.tagName)}
}
const tags={"s2-template":"input","s2-kind":"select","s2-certainty":"select","s2-session":"input","position":"input","issue-start":"input","issue-end":"input","issue-span":"input","issue-kind":"select","issue-certainty":"select","issue-status":"select","issue-quote":"textarea","issue-note":"textarea","note-start":"input","note-end":"input","loop-span":"input"};
const elements=new Map();
function byId(id){if(!elements.has(id)){const e=new El(tags[id]||"div");e.id=id;elements.set(id,e);}return elements.get(id)}
let serial=0,seeks=[],requests=[],replies=[],cur=2,docListeners=[];
const s1Players=new Map([["clean",Object.assign(new El("audio"),{role:"clean"})]]);
const bundle=bundlePath&&bundlePath!=="-"?JSON.parse(fs.readFileSync(bundlePath,"utf8")):null;
const sessionValue=JSON.parse(fs.readFileSync(sessionPath,"utf8"));
const context={console,Number,Math,Array,JSON,Error,Set,Map,Object,String,Promise,setTimeout,
  document:{createElement:t=>new El(t),createTextNode:t=>new TextNode(t),addEventListener(t,f,o){docListeners.push([t,f,o])}},
  crypto:{randomUUID:()=>"key-"+String(++serial).padStart(4,"0")},
  byId,players:s1Players,activeRole:"clean",session:sessionValue,
  currentSource:()=>cur,seekSource:v=>{seeks.push(v);cur=v;byId("position").value=v},clock:v=>"t"+Number(v).toFixed(3),
  human:v=>String(v).replaceAll("_"," "),notice(){},
  node:(tag,text,cls)=>{const e=new El(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e},
  fetch:async(url,options)=>{requests.push({url,options});const reply=replies.shift();if(reply===undefined)throw new Error("no reply for "+url);if(reply instanceof Error)throw reply;return {ok:reply.ok,status:reply.status||200,json:async()=>reply.value}}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(s1Path,"utf8"),context);
vm.runInContext(fs.readFileSync(s2Path,"utf8"),context);
function run(code){return vm.runInContext(code,context)}
function emit(value){console.log(JSON.stringify(value))}
function walk(node,visit){visit(node);for(const child of node.children||[])walk(child,visit)}
function findAll(node,pred){const out=[];walk(node,n=>{if(pred(n))out.push(n)});return out}
function has(n,c){return typeof n.className==="string"&&n.className.split(" ").includes(c)}
function text(node,skipUpstream){if(skipUpstream&&has(node,"s2-upstream"))return "";if(!(node instanceof El))return node.textContent;return node._text+node.children.map(c=>text(c,skipUpstream)).join("")}
function panel(id){return byId(id+"-body")}
function store(revision,annotations=[]){return {schema_version:2,source_sha256:sessionValue.source_sha256,manifest_sha256:sessionValue.manifest_sha256,revision,annotations,listening_acceptance:"not_established"}}
async function boot(){replies.push({ok:true,status:200,value:bundle});await run("s2Init()");}
function key(k,extra={}){return byId("source-transport").dispatch("keydown",{key:k,shiftKey:false,altKey:false,ctrlKey:false,metaKey:false,target:byId("source-transport"),...extra})}
function allPlayers(){return [...s1Players.values(),...run("s2Players")]}
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FakeMedia:
    def __init__(self, path, expected):
        if sha(path) != expected:
            raise review_server.ReviewError("media_hash_mismatch", 409)
        self.closed = False

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, source_hash, manifest_hash):
        self.source_hash, self.manifest_hash = source_hash, manifest_hash


def load_phrase_anchor():
    spec = importlib.util.spec_from_file_location("phrase_anchor_s2_test", ROOT / "scripts" / "phrase_anchor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class S2Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)
        cls.tmp = Path(tempfile.mkdtemp(prefix="ui-s2-", dir=TEST_TMP))
        cls.fixture = fixture_s2.make_fixture(cls.tmp / "fixture")
        cls.args = fixture_s2.compose_arguments(cls.fixture)
        cls.bundle_dir = cls.tmp / "bundle"
        cls.bundle = bundle_s2.compose(cls.fixture["run"], cls.bundle_dir, timeout_seconds=60, **cls.args)
        status, cls.payload = routes_s2.api_response(routes_s2.load(cls.bundle_dir, FakeSession(cls.fixture["source_sha256"], cls.fixture["manifest_sha256"]), FakeMedia))
        assert status == 200, cls.payload
        cls.session_value = {"token": "test-token", "source_name": "synthetic-practice-s2.wav", "source_sha256": cls.fixture["source_sha256"],
                             "manifest_sha256": cls.fixture["manifest_sha256"], "markers": [],
                             "timeline": {"source_min_seconds": 1, "source_max_seconds": 12, "audio_start_seconds": 2, "format_start_seconds": 1}}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def write_json(self, name, value):
        path = self.tmp / name
        path.write_text(json.dumps(value))
        return path

    def check_js(self, code, payload=None, session=None):
        bundle_path = self.write_json(f"payload-{self._testMethodName}.json", self.payload if payload is None else payload) if payload != "-" else "-"
        session_path = self.write_json(f"session-{self._testMethodName}.json", session or self.session_value)
        result = subprocess.run([NODE, "-e", HARNESS + "(async()=>{" + code + "})().catch(e=>{console.error(e.stack);process.exit(1)});",
                                 str(REVIEW / "practice_s2.js"), str(REVIEW / "practice.js"), str(bundle_path), str(session_path)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def compose(self, name, **overrides):
        options = {**self.args, **overrides}
        return bundle_s2.compose(self.fixture["run"], self.tmp / name, timeout_seconds=60, **options)

    def layer_copy(self, name):
        target = self.tmp / name
        shutil.copytree(self.fixture["layers"], target)
        return target


@unittest.skipUnless(NODE, "Node required for shipped JavaScript behaviour")
class PracticeS2PageTests(S2Base):
    def test_stage_strip_short_hashes_and_analysis_input_divergence(self):
        value = self.check_js('''await boot();const body=panel("s2-stages");
          const codes=findAll(body,n=>has(n,"s2-hash")).map(n=>({text:n.textContent,aria:n.getAttribute("aria-label")}));
          emit({codes,text:text(body)});''')
        source = self.fixture["source_sha256"]
        self.assertEqual(value["codes"][0]["text"], source[:12])
        self.assertIn(source, value["codes"][0]["aria"])
        self.assertTrue(all(len(item["text"]) == 12 or item["text"] == "unknown" for item in value["codes"]))
        analysis = self.fixture["analysis_input_sha256"]
        self.assertIn(analysis[:12], [item["text"] for item in value["codes"]])
        self.assertIn("analysis input differs from tone stage — bound by original source only · no-stretch: unknown / true", value["text"])
        self.assertIn("Tone (FULLER)", value["text"])
        self.assertIn("anchor not adopted", value["text"])

    def test_ab_blind_key_hidden_until_reveal_and_reveal_not_saved(self):
        value = self.check_js('''await boot();const before=text(panel("s2-ab"));
          const reveal=findAll(panel("s2-ab"),n=>n.tagName==="BUTTON"&&n.textContent==="Reveal which is FULLER")[0];reveal.click();
          const after=text(panel("s2-ab"));
          findAll(panel("s2-ab"),n=>n.tagName==="BUTTON"&&n.textContent==="Pair 2")[0].click();const pair2=text(panel("s2-ab"));
          emit({before,after,pair2,requests:requests.map(r=>[r.url,r.options&&r.options.method||"GET"])});''')
        self.assertIn("Mapping hidden", value["before"])
        self.assertNotIn("X = ", value["before"])
        self.assertIn("X = FULLER delivery master · Y = source (display only; not saved, not a preference)", value["after"])
        self.assertNotIn("X = ", value["pair2"])
        self.assertEqual(value["requests"], [["/api/practice-s2", "GET"]])
        script = (REVIEW / "practice_s2.js").read_text()
        for forbidden in ("localStorage", "sessionStorage", "indexedDB"):
            self.assertNotIn(forbidden, script)

    def test_ab_shows_measured_lu_delta_gains_and_preference_not_recorded(self):
        value = self.check_js('emit(await (async()=>{await boot();return text(panel("s2-ab"));})());')
        self.assertIn("region match: ±0.02 LU over 0.5–9.5 s (measured, BS.1770 via FFmpeg loudnorm)", value)
        self.assertIn("operator_preference: not recorded", value)
        self.assertIn("listening acceptance: not established", value)
        self.assertIn("X: static gain −2.90 dB · excerpt LUFS -20.60 (informational) · sample peak -18.20 dBFS · true peak not measured", value)
        self.assertIn("Y: static gain −0.20 dB", value)

    def test_no_autoplay_no_play_calls_preload_none_exclusive_pause(self):
        for name in ("practice_s2.js", "index.html"):
            text = (REVIEW / name).read_text()
            self.assertNotIn("autoplay", text.lower().replace("autoplay-policy", ""))
            self.assertNotIn("innerHTML", text)
        self.assertIsNone(re.search(r"\.play\s*\(", (REVIEW / "practice_s2.js").read_text()))
        value = self.check_js('''await boot();const s2=run("s2Players");
          const shape=s2.map(p=>({preload:p.preload,controls:p.controls,autoplay:!!p.autoplay,src:p.src}));
          for(const p of allPlayers())p.paused=false;s2[0].paused=false;s2[0].dispatch("play");
          const afterS2=allPlayers().map(p=>p.paused);
          for(const p of allPlayers())p.paused=false;const s1=[...s1Players.values()][0];s1.dispatch("play");
          const afterS1=run("s2Players").map(p=>p.paused);
          emit({shape,afterS2,afterS1,plays:allPlayers().reduce((a,p)=>a+p.playCalls,0)});''')
        self.assertEqual(len(value["shape"]), 2)
        self.assertTrue(all(item["preload"] == "none" and item["controls"] and not item["autoplay"] for item in value["shape"]))
        self.assertTrue(value["shape"][0]["src"].startswith("/media/s2/excerpt-1-"))
        self.assertEqual(value["afterS2"], [True, False, True])  # S1 player and Y paused; X keeps playing
        self.assertEqual(value["afterS1"], [True, True])
        self.assertEqual(value["plays"], 0)

    def test_trial_player_labelled_unadopted_and_optional_when_unavailable(self):
        payload = copy.deepcopy(self.payload)
        trial = payload["layers"]["tone_ab"]["trial"]
        self.assertEqual(trial["status"], "unavailable")
        absent = self.check_js('await boot();emit({text:text(panel("s2-ab")),players:run("s2Players").length});', payload)
        self.assertIn("TRIAL excerpt unavailable: trial excerpts not requested · unreviewed experiment · not adopted", absent["text"])
        self.assertEqual(absent["players"], 2)
        payload["layers"]["tone_ab"]["trial"] = {**trial, "status": "available", "gain_db": -3.1, "reason": None,
                                                 "controls": {"type": "lowshelf", "frequency_hz": 100.0, "gain_db": 1.5},
                                                 "pairs": [{"pair": 1, "media": "trial-1.wav"}]}
        payload["served"]["media_urls"]["trial-1.wav"] = "/media/s2/trial-1.wav"
        present = self.check_js('await boot();const p=run("s2Players");emit({text:text(panel("s2-ab")),labels:p.map(x=>x.getAttribute("aria-label")),preload:p.map(x=>x.preload)});', payload)
        self.assertIn("TRIAL · lowshelf 100 Hz +1.5 dB · unreviewed experiment · not adopted", present["text"])
        self.assertIn("Unblinded.", present["text"])
        self.assertEqual(len(present["labels"]), 3)
        self.assertEqual(present["preload"], ["none"] * 3)

    def test_coverage_uncertain_and_weak_joins_have_text_and_shape_markers(self):
        value = self.check_js('''await boot();const ticks=findAll(panel("s2-coverage"),n=>has(n,"s2-tick"));
          emit({ticks:ticks.map(t=>({cls:t.className,aria:t.getAttribute("aria-label"),glyph:t.textContent})),
            outside:findAll(panel("s2-coverage"),n=>has(n,"s2-outside")).map(n=>n.textContent),text:text(panel("s2-coverage"))});''')
        ticks = value["ticks"]
        self.assertEqual(len(ticks), 6)
        uncertain = [item for item in ticks if "s2-join-uncertain" in item["cls"]]
        weak = [item for item in ticks if "s2-join-weak" in item["cls"]]
        self.assertEqual(len(uncertain), 3)
        self.assertTrue(all(item["aria"] == "uncertain join" and item["glyph"].startswith("?") for item in uncertain))
        self.assertEqual([item["glyph"] for item in weak], ["~"])
        self.assertEqual([item["glyph"] for item in ticks if "s2-join-supported" in item["cls"]], ["", ""])
        self.assertEqual(sum("≈" in item["glyph"] for item in ticks), 3)
        self.assertEqual(value["outside"], ["outro:1 outside source"])
        self.assertIn("anchor review candidate · not adopted · ±1 click alternatives", value["text"])

    def test_coverage_lanes_separate_and_summary_denominators(self):
        value = self.check_js('''await boot();const lanes=findAll(panel("s2-coverage"),n=>has(n,"s2-lane"));
          const tracks=lanes.map(l=>l.children[1].children.length);const unit=findAll(panel("s2-coverage"),n=>has(n,"s2-unit"))[0];unit.click();
          const anchor=findAll(panel("s2-coverage"),n=>n.id==="s2-anchor")[0];anchor.value="1";anchor.dispatch("change");
          emit({labels:lanes.map(l=>l.children[0].children[0].textContent),tracks,text:text(panel("s2-coverage")),seeks,
            plays:allPlayers().reduce((a,p)=>a+p.playCalls,0),k:findAll(panel("s2-coverage"),n=>has(n,"s2-unit"))[0].getAttribute("aria-label")});''')
        self.assertEqual(value["labels"], ["INTENT", "DETECTOR HYPOTHESIS", "USER REPORTED"])
        self.assertEqual(value["tracks"], [12, 3, 0])  # 6 units + 6 ticks, 3 detector spans, no user marks
        for line in ("intent units within source: 5/6", "boundaries by join confidence: supported 2, weak 1, uncertain 3 (of 6)", "detector review spans: 3"):
            self.assertIn(line, value["text"])
        self.assertIn("Overlap between lanes is not agreement, accuracy or correctness.", value["text"])
        self.assertEqual(value["seeks"], [2.0])
        self.assertEqual(value["plays"], 0)
        self.assertIn("t2.250", value["k"])  # k4 anchor shifts by 0.25 s

    def test_triage_default_at_most_one_per_window_navigation_and_suppressed_toggles(self):
        value = self.check_js('''await boot();const count=id=>{const l=findAll(panel("s2-flags"),n=>n.id===id)[0];return {n:findAll(l,n=>has(n,"s2-flag")).length,hidden:l.hidden}};
          const before={shown:count("s2-flags-shown"),nav:count("s2-flags-navigation"),sup:count("s2-flags-suppressed")};
          const boxes=findAll(panel("s2-flags"),n=>n.tagName==="INPUT");const checkedDefault=boxes.map(b=>b.checked);
          for(const b of boxes){b.checked=true;b.dispatch("change");}
          const after={shown:count("s2-flags-shown"),nav:count("s2-flags-navigation"),sup:count("s2-flags-suppressed")};
          const windows=findAll(findAll(panel("s2-flags"),n=>n.id==="s2-flags-shown")[0],n=>has(n,"s2-flag-head")).map(n=>n.textContent.split(" · ")[0]);
          emit({before,after,checkedDefault,windows,text:text(panel("s2-flags"))});''')
        self.assertEqual(value["before"], {"shown": {"n": 2, "hidden": False}, "nav": {"n": 0, "hidden": True}, "sup": {"n": 0, "hidden": True}})
        self.assertEqual(value["after"], {"shown": {"n": 2, "hidden": False}, "nav": {"n": 3, "hidden": False}, "sup": {"n": 1, "hidden": False}})
        self.assertEqual(value["checkedDefault"], [False, False])
        self.assertEqual(len(set(value["windows"])), len(value["windows"]))
        self.assertIn("shown 2 of 6 flags · navigation hidden 3 · suppressed 1", value["text"])
        self.assertIn("window basis: click-grid navigation window — not bar, phrase or meter", value["text"])
        self.assertIn("at most one per navigation window", value["text"])
        self.assertIn("Show navigation proxies (3)", value["text"])

    def test_basis_badges_user_reported_intent_review_detector_distinct(self):
        value = self.check_js('''emit(run(`[s2Badge({store:true,basis:"operator_assertion",claim_label:"USER REPORTED"}),s2Badge({store:true,basis:"operator_context"}),
          s2Badge({store:true,basis:"detector_hypothesis",claim_label:"REVIEW"}),s2Badge({store:true,basis:"reference_comparison"}),
          s2Badge({origin:"intent"}),s2Badge({origin:"detector"}),s2Badge({store:true,basis:"mystery"}),s2Badge({})]`));''', payload="-")
        texts = [item["text"] for item in value]
        self.assertEqual(texts, ["USER REPORTED", "INTENT", "REVIEW", "REFERENCE REVIEW", "INTENT · projected", "DETECTOR HYPOTHESIS", "UNKNOWN BASIS", "UNKNOWN BASIS"])
        self.assertEqual(value[2]["subtitle"], "detector hypothesis")
        shapes = [item["shape"] for item in value[:4]] + [value[5]["shape"]]
        self.assertEqual(len(set(shapes)), 5)
        self.assertEqual(value[1]["shape"], value[4]["shape"])
        self.assertEqual(annotation_v2.LABELS, {"operator_assertion": "USER REPORTED", "operator_context": "INTENT",
                                                "detector_hypothesis": "REVIEW", "reference_comparison": "REFERENCE REVIEW"})

    def test_phrase_timing_unvalidated_measurement_and_abstain_reason(self):
        value = self.check_js('''await boot();const rows=findAll(panel("s2-timing"),n=>n.tagName==="TR").slice(1).map(r=>r.children.map(c=>c.textContent));
          emit({rows,text:text(panel("s2-timing"))});''')
        self.assertIn("MEASUREMENT · unvalidated until operator spot check · click identity unverified · capture latency uncalibrated", value["text"])
        rows = value["rows"]
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0][4], "median offset −14.2 ms (delay-compensated: synthetic probe medians applied)")
        self.assertEqual(rows[0][5], "IQR −18.2 … −11.2 ms")
        self.assertEqual(rows[0][6], "click-proximal n 6")
        self.assertEqual([row[7] for row in rows[:3]], ["ahead of modelled click · synthetic known-offset fixture",
                                                        "behind modelled click · synthetic known-offset fixture",
                                                        "within ±5 ms of modelled click · synthetic known-offset fixture"])
        self.assertEqual(rows[3][4:], ["—", "—", "click-proximal n 2", "abstained: fewer than 4 click proximal onsets"])
        self.assertNotIn("0.0 ms", " ".join(rows[3]))
        self.assertIn("run kind: synthetic fixture", value["text"])
        self.assertIn("direction: synthetic known-offset fixture only", value["text"])

    def test_phrase_timing_real_take_direction_withheld(self):
        payload = copy.deepcopy(self.payload)
        doc = payload["layers"]["phrase_timing"]["files"][0]["document"]
        doc["run_kind"] = "real_take"
        for row in doc["phrases"]:
            if row["status"] == "measured":
                row.update(direction=None, direction_status="withheld_uncalibrated", direction_basis=None)
        forged = copy.deepcopy(payload)
        for row in forged["layers"]["phrase_timing"]["files"][0]["document"]["phrases"]:
            if row["status"] == "measured":
                row.update(direction="ahead_of_click", direction_status="synthetic_known_offset_fixture", tendency_label="ahead_of_click")
        code = '''await boot();const rows=findAll(panel("s2-timing"),n=>n.tagName==="TR").slice(1).map(r=>r.children.map(c=>c.textContent));
          emit({rows,text:text(panel("s2-timing"))});'''
        for name, value in (("withheld", self.check_js(code, payload)), ("forged_real_take", self.check_js(code, forged))):
            rows = value["rows"]
            self.assertEqual([row[7] for row in rows[:3]], ["direction withheld (uncalibrated)"] * 3, name)
            self.assertEqual(rows[0][4], "median offset −14.2 ms (delay-compensated: synthetic probe medians applied)", name)
            self.assertEqual(rows[3][7], "abstained: fewer than 4 click proximal onsets", name)
            for phrase in ("ahead of modelled click", "behind modelled click", "within ±5 ms"):
                self.assertNotIn(phrase, value["text"], name)
            self.assertIn("direction: withheld until operator calibration", value["text"], name)

    def test_generated_text_contains_no_verdict_words(self):
        value = self.check_js('''await boot();
          for(const b of findAll(panel("s2-flags"),n=>n.tagName==="INPUT")){b.checked=true;b.dispatch("change");}
          findAll(panel("s2-ab"),n=>n.tagName==="BUTTON"&&n.textContent==="Reveal which is FULLER")[0].click();
          run("s2SetSession(true)");byId("s2-template").value="my words";key("b");key("i");
          const ids=["s2-stages","s2-ab","s2-coverage","s2-flags","s2-timing","s2-prototypes"];
          const generated=ids.map(id=>text(panel(id),true)).join("\\n")+"\\n"+text(byId("s2-queue"),true)+"\\n"+text(byId("s2-queue-status"),true);
          emit({generated,upstream:findAll({children:ids.map(panel)},n=>has(n,"s2-upstream")).length});''')
        self.assertEqual(VERDICT.findall(value["generated"]), [])
        self.assertGreater(len(value["generated"]), 2000)
        self.assertGreater(value["upstream"], 0)
        self.assertIn("PROTOTYPE · not implemented", value["generated"])

    def test_quick_marks_saved_via_annotation_v2_are_accepted_by_phrase_anchor(self):
        local = Path(tempfile.mkdtemp(prefix="ui-s2-marks-", dir=TEST_TMP))
        try:
            fixture = fixture_s2.make_fixture(local / "fixture")
            session = review_server.Session(fixture["run"], open_media=False)
            session_value = {**self.session_value, "source_sha256": session.source_hash, "manifest_sha256": session.manifest_hash}
            value = self.check_js('''await boot();run("issueStore="+JSON.stringify(store(0)));run("s2SetSession(true)");
              byId("s2-template").value="phrase boundary";const keys=[];
              for(let i=0;i<12;i++){cur=1.5+i*0.75;keys.push(key("b").defaultPrevented);}
              for(let i=0;i<12;i++)replies.push({ok:true,value:{...store(i+1),mutation:{outcome:"saved",annotation_id:"id-"+i,committed_revision:i+1}}});
              await run("s2SaveQueue()");
              emit({keys,bodies:requests.filter(r=>r.options&&r.options.method==="POST").map(r=>r.options.body),queue:run("s2State.queue.length")});''',
                                 payload=self.payload, session=session_value)
            self.assertEqual(value["keys"], [True] * 12)
            self.assertEqual(value["queue"], 0)
            self.assertEqual(len(value["bodies"]), 12)
            store = annotation_v2.AnnotationStore(session)
            for body in value["bodies"]:
                request = json.loads(body)
                self.assertNotIn("candidate_id", request["annotation"])
                self.assertEqual(request["annotation"]["operator_quote"], "phrase boundary")
                self.assertTrue(request["annotation"]["note"].startswith("quick mark (key B) at t"))
                self.assertEqual(store.write(request)["mutation"]["outcome"], "saved")
            saved = json.loads((Path(fixture["run"]) / "review-annotations-v2.json").read_text())
            _, accepted, excluded = load_phrase_anchor().marks_from_annotation_store(saved)
            self.assertEqual((len(accepted), excluded), (12, {}))
            self.assertEqual(len({item["source_seconds"] for item in accepted}), 12)
            session.close()
        finally:
            shutil.rmtree(local, ignore_errors=True)

    def test_quick_mark_uncertain_save_retries_same_key_and_stale_keeps_queue(self):
        value = self.check_js('''await boot();requests.length=0;run("issueStore="+JSON.stringify(store(0)));run("s2SetSession(true)");byId("s2-template").value="boundary";
          for(const t of [3,4,5]){cur=t;key("b");}
          replies.push(new Error("lost connection"));await run("s2SaveQueue()");
          const held={uncertain:run("s2State.uncertain"),retryHidden:byId("s2-retry").hidden,queue:run("s2State.queue.length"),issueSave:byId("issue-save").disabled,blocked:(cur=6,key("b"),run("s2State.queue.length"))};
          replies.push({ok:true,value:{...store(1),mutation:{outcome:"replayed",annotation_id:"a",committed_revision:1}}},{ok:true,value:{...store(2),mutation:{outcome:"saved",annotation_id:"b"}}},{ok:true,value:{...store(3),mutation:{outcome:"saved",annotation_id:"c"}}});
          byId("s2-retry").click();await new Promise(r=>setTimeout(r,20));
          const bodies=requests.map(r=>r.options.body);const retried={same:bodies[0]===bodies[1],queue:run("s2State.queue.length"),status:byId("s2-queue-status").textContent,uncertain:run("s2State.uncertain"),issueSave:byId("issue-save").disabled};
          requests.length=0;for(const t of [7,8]){cur=t;key("b");}
          replies.push({ok:false,status:409,value:{error:"stale_annotation_revision"}},{ok:true,value:store(9)});await run("s2SaveQueue()");
          const firstKey=JSON.parse(requests[0].options.body).idempotency_key;
          const stale={queue:run("s2State.queue.length"),frozen:run("s2State.frozen"),requests:requests.map(r=>r.options&&r.options.method||"GET")};
          replies.push({ok:false,status:400,value:{error:"source_span_out_of_bounds"}});await run("s2SaveQueue()");
          const second=JSON.parse(requests[2].options.body);
          emit({held,retried,stale,firstKey,secondKey:second.idempotency_key,secondRevision:second.expected_revision,refused:run("s2State.queue[0].error"),queueAfter:run("s2State.queue.length")});''')
        self.assertEqual(value["held"], {"uncertain": True, "retryHidden": False, "queue": 3, "issueSave": True, "blocked": 3})
        self.assertTrue(value["retried"]["same"])
        self.assertEqual(value["retried"]["queue"], 0)
        self.assertFalse(value["retried"]["uncertain"])
        self.assertFalse(value["retried"]["issueSave"])
        self.assertIn("reconciled 1 replay without duplicates", value["retried"]["status"])
        self.assertEqual(value["stale"], {"queue": 2, "frozen": None, "requests": ["POST", "GET"]})
        self.assertNotEqual(value["firstKey"], value["secondKey"])
        self.assertEqual(value["secondRevision"], 9)
        self.assertEqual(value["refused"], "source_span_out_of_bounds")
        self.assertEqual(value["queueAfter"], 2)

    def test_quick_mark_keys_ignore_typing_and_modifiers_and_never_play(self):
        value = self.check_js('''await boot();run("issueStore="+JSON.stringify(store(0)));byId("s2-template").value="mark";
          key("b");const off=run("s2State.queue.length");run("s2SetSession(true)");
          key("b",{target:byId("s2-template")});key("b",{ctrlKey:true});key("b",{metaKey:true});key("b",{altKey:true});key("B",{shiftKey:true});
          const ignored=run("s2State.queue.length");
          cur=2.1;byId("position").value=2.1;key("n");const n1=seeks.at(-1);key("n");const n2=seeks.at(-1);key("p");const p1=seeks.at(-1);
          key("N",{shiftKey:true});const flag=seeks.at(-1);key("b");const note=run("s2State.queue.at(-1).annotation.note");
          key("i");byId("s2-kind").value="noise";key("i");const kinds=run("s2State.queue.map(q=>q.annotation.kind)");
          key("u");const afterUndo=run("s2State.queue.length");
          const bar=byId("s2-quickmark").dispatch("keydown",{key:"b",shiftKey:false,altKey:false,ctrlKey:false,metaKey:false,target:byId("s2-quickmark")});
          emit({off,ignored,n1,n2,p1,flag,note,kinds,afterUndo,bar:run("s2State.queue.length"),plays:allPlayers().reduce((a,p)=>a+p.playCalls,0)});''')
        self.assertEqual(value["off"], 0)
        self.assertEqual(value["ignored"], 0)
        self.assertEqual([value["n1"], value["n2"], value["p1"]], [3.5, 5.0, 3.5])
        self.assertEqual(value["flag"], 6.5)
        self.assertIn("near triaged flag flag-0004-synthetic (detector hypothesis)", value["note"])
        self.assertEqual(value["kinds"], ["phrase_duration", "phrase_duration", "noise"])
        self.assertEqual(value["afterUndo"], 2)
        self.assertEqual(value["bar"], 3)
        self.assertEqual(value["plays"], 0)

    def test_foreign_bundle_refused_and_s1_controls_remain(self):
        foreign = copy.deepcopy(self.payload)
        foreign["session_binding"]["original_source_sha256"] = "f" * 64
        value = self.check_js('''await boot();const ids=["s2-stages","s2-ab","s2-coverage","s2-flags","s2-timing"];
          const texts=ids.map(id=>text(panel(id)));const players=run("s2Players.length");
          run("transportKey")({target:{matches:()=>false},key:"ArrowRight",shiftKey:false,altKey:false,ctrlKey:false,metaKey:false,preventDefault(){}});
          run("s2SetSession(true)");key("n");
          emit({texts,players,ready:run("s2Ready"),seeks,issueSave:byId("issue-save").disabled});''', foreign)
        self.assertEqual(set(value["texts"]), {"S2 evidence belongs to another recording"})
        self.assertEqual(value["players"], 0)
        self.assertFalse(value["ready"])
        self.assertEqual(value["seeks"], [3])  # S1 arrow key still seeks; S2 boundary key has nothing to do
        self.assertFalse(value["issueSave"])
        missing = self.check_js('''replies.push({ok:false,status:404,value:{error:"practice_s2_bundle_not_configured"}});await run("s2Init()");
          emit(["s2-stages","s2-ab","s2-coverage","s2-flags","s2-timing"].map(id=>text(panel(id))));''')
        self.assertEqual(set(missing), {"Unavailable: practice s2 bundle not configured"})

    def test_prototype_labels_and_index_preserves_s1_ids_in_order(self):
        value = self.check_js('await boot();emit(findAll(panel("s2-prototypes"),n=>has(n,"s2-prototype")).map(n=>({text:n.textContent,buttons:findAll(n,c=>c.tagName==="BUTTON"||c.tagName==="INPUT").length})));')
        self.assertEqual(len(value), 5)
        self.assertTrue(all(item["text"].startswith("PROTOTYPE · not implemented") and item["buttons"] == 0 for item in value))
        html = (REVIEW / "index.html").read_text()
        original = subprocess.run(["git", "-C", str(ROOT), "show", "0cdca01:review/index.html"], capture_output=True, text=True, timeout=10)
        if original.returncode == 0:
            ids = re.findall(r'id="([^"]+)"', original.stdout)
            current = [item for item in re.findall(r'id="([^"]+)"', html) if item in set(ids)]
            self.assertEqual(current, ids)
        self.assertLess(html.index('src="/practice.js"'), html.index('src="/practice_s2.js"'))


class PracticeS2ComposerTests(S2Base):
    def test_composer_refuses_source_or_media_hash_mismatch_per_layer(self):
        layers = self.layer_copy("tampered-layers")
        excerpt = layers / "tone_ab" / "excerpt-2-Y.wav"
        excerpt.write_bytes(excerpt.read_bytes()[:-8] + b"\0" * 8)
        spans = json.loads((layers / "spans-k4.json").read_text())
        spans["provenance"]["original_source_sha256"] = "e" * 64
        (layers / "spans-k4.json").write_text(json.dumps(spans))
        triage = json.loads((layers / "flags-triage.json").read_text())
        triage["source_sha256"] = "d" * 64
        (layers / "flags-triage.json").write_text(json.dumps(triage))
        timing = json.loads((layers / "phrase-timing.json").read_text())
        timing["inputs"]["analyzed_input_sha256"] = "c" * 64
        (layers / "phrase-timing.json").write_text(json.dumps(timing))
        result = self.compose("tampered", tone_ab=layers / "tone_ab", flags_triage=layers / "flags-triage.json",
                              phrase_spans=[layers / "spans-k3.json", layers / "spans-k4.json"], phrase_timing=[layers / "phrase-timing.json"])
        self.assertEqual(result["layers"]["tone_ab"], {"status": "unavailable", "reason": "layer_hash_mismatch"})
        self.assertEqual(result["layers"]["flags_triage"], {"status": "unavailable", "reason": "layer_source_mismatch"})
        self.assertEqual(result["layers"]["phrase_timing"]["reason"], "layer_source_mismatch")
        intent = result["layers"]["coverage"]["intent"]
        self.assertEqual([item["file"] for item in intent["files"]], ["spans-k3.json"])
        self.assertEqual(intent["refused"], [{"file": "spans-k4.json", "reason": "layer_source_mismatch"}])
        self.assertEqual(result["layers"]["coverage"]["detector"]["status"], "available")
        self.assertEqual(result["media"], {})
        self.assertEqual(sorted(path.name for path in (self.tmp / "tampered" / "media").iterdir()), [])
        # Extent: a hash-consistent excerpt whose frame count differs from frames_per_file.
        layers2 = self.layer_copy("extent-layers")
        short = layers2 / "tone_ab" / "excerpt-1-X.wav"
        data = short.read_bytes()
        info = bundle_s2.riff_info(data)
        header = data[:data.index(b"data") + 8]
        body = data[len(header):len(header) + (info["frames"] - 10) * 4]
        short.write_bytes(header[:-4] + struct.pack("<I", len(body)) + body)
        record = json.loads((layers2 / "tone_ab" / "tone-ab.json").read_text())
        record["excerpts"]["pairs"][0]["files"]["X"]["sha256"] = sha(short)
        (layers2 / "tone_ab" / "tone-ab.json").write_text(json.dumps(record))
        extent = self.compose("extent", tone_ab=layers2 / "tone_ab")
        self.assertEqual(extent["layers"]["tone_ab"], {"status": "unavailable", "reason": "media_extent_mismatch"})
        record["run"]["source_sha256"] = "b" * 64
        (layers2 / "tone_ab" / "tone-ab.json").write_text(json.dumps(record))
        self.assertEqual(self.compose("foreign-tone", tone_ab=layers2 / "tone_ab")["layers"]["tone_ab"]["reason"], "layer_source_mismatch")

    def test_composer_timing_schema_2_direction_policy(self):
        layers = self.layer_copy("timing-policy-layers")
        original = json.loads((layers / "phrase-timing.json").read_text())

        def variant(name, mutate):
            value = copy.deepcopy(original)
            mutate(value)
            folder = layers / name
            folder.mkdir()
            (folder / "phrase-timing.json").write_text(json.dumps(value))
            return folder / "phrase-timing.json"

        def measured(value):
            return [row for row in value["phrases"] if row["status"] == "measured"]

        def schema_1(value):
            value["schema_version"] = 1
            for row in value["phrases"]:
                row["tendency_label"] = row.pop("direction")

        def real_withheld(value):
            value["run_kind"] = "real_take"
            for row in measured(value):
                row.update(direction=None, direction_status="withheld_uncalibrated", direction_basis=None)

        def real_with_direction(value):
            value["run_kind"] = "real_take"
            for row in measured(value):
                row["direction_status"] = "withheld_uncalibrated"

        def real_claims_synthetic(value):
            value["run_kind"] = "real_take"

        def synthetic_withheld(value):
            for row in measured(value):
                row.update(direction=None, direction_status="withheld_uncalibrated")

        def abstained_direction(value):
            value["phrases"][3]["direction"] = "within_5_ms"

        def tendency_key(value):
            value["phrases"][0]["tendency_label"] = "ahead_of_click"

        def unknown_run_kind(value):
            value["run_kind"] = "calibrated"
        cases = {"schema1": (schema_1, "layer_schema_superseded"), "realok": (real_withheld, None),
                 "realdir": (real_with_direction, "layer_direction_policy_violation"),
                 "realsyn": (real_claims_synthetic, "layer_direction_policy_violation"),
                 "synwithheld": (synthetic_withheld, "layer_direction_policy_violation"),
                 "abstaindir": (abstained_direction, "layer_direction_policy_violation"),
                 "tendency": (tendency_key, "layer_schema_unknown"), "runkind": (unknown_run_kind, "layer_schema_unknown")}
        paths = [layers / "phrase-timing.json"] + [variant(name, mutate) for name, (mutate, _) in cases.items()]
        result = self.compose("timing-policy", phrase_timing=paths)
        timing = result["layers"]["phrase_timing"]
        self.assertEqual(timing["status"], "available")
        self.assertEqual([entry["file"] for entry in timing["files"]], ["timing-policy-layers/phrase-timing.json", "realok/phrase-timing.json"])
        self.assertEqual({entry["file"]: entry["reason"] for entry in timing["refused"]},
                         {f"{name}/phrase-timing.json": reason for name, (_, reason) in cases.items() if reason})
        real = timing["files"][1]["document"]
        self.assertEqual(real["run_kind"], "real_take")
        self.assertTrue(all(row["direction"] is None for row in real["phrases"]))
        self.assertEqual(bundle_s2.TIMING_SCHEMA_VERSION, 2)

    def test_composer_refuses_existing_or_runs_output(self):
        def refusal(output, run=None):
            with self.assertRaises(bundle_s2.Refusal) as caught:
                bundle_s2.compose(run or self.fixture["run"], output, **self.args)
            return caught.exception.code
        self.assertEqual(refusal(self.bundle_dir), "output_exists")
        inside = ROOT / "artifacts" / "runs" / "ui-s2-never-created"
        self.assertEqual(refusal(inside), "output_inside_runs")
        self.assertFalse(inside.exists())
        outside = ROOT / "docs" / "ui-s2-never-created"
        self.assertEqual(refusal(outside), "output_outside_artifacts")
        self.assertFalse(outside.exists())
        bad_run = self.tmp / "bad-run"
        bad_run.mkdir()
        self.assertEqual(refusal(self.tmp / "out-missing", bad_run), "session_manifest_unreadable")
        (bad_run / "manifest.json").write_text(json.dumps({"source": {"path": "x.wav"}}))
        self.assertEqual(refusal(self.tmp / "out-nohash", bad_run), "session_source_hash_required")
        self.assertFalse((self.tmp / "out-missing").exists() or (self.tmp / "out-nohash").exists())
        self.assertEqual([path.name for path in self.tmp.iterdir() if ".staging-" in path.name], [])

    def test_bundle_carries_unknown_fields_and_claim_boundary(self):
        bundle = json.loads((self.bundle_dir / "bundle.json").read_text())
        self.assertEqual(bundle["schema_id"], "video-utils.practice-s2.bundle")
        self.assertEqual(list(bundle["unknown_fields"]), UNKNOWN_KEYS)
        self.assertTrue(all(isinstance(item.get("reason"), str) and item["reason"] for item in bundle["unknown_fields"].values()))
        fields = {key: item["value"] for key, item in bundle["unknown_fields"].items()}
        self.assertEqual(fields["operator_preference"], None)
        self.assertEqual(fields["listening_acceptance"], "not_established")
        for key in ("perceived_fullness", "nasal_quality", "fundamental_32hz_presence", "monitoring_device", "true_peak_dbtp", "fan_only_gain", "music_only_gain"):
            self.assertIsNone(fields[key], key)
        self.assertEqual(bundle["unknown_fields"]["nasal_quality"]["reason"], "Synthetic fixture: nasal_quality is a listening or unmeasured field.")
        self.assertEqual((fields["click_identity"], fields["physical_capture_latency"], fields["meter"]), ("unverified", "uncalibrated", "unknown"))
        self.assertEqual(fields["detector_delay"]["status"], "synthetic_probe_medians_applied")
        self.assertEqual((fields["downbeat_confirmed"], fields["anchor_adopted"]), (False, False))
        self.assertEqual(fields["breakdown1_execution"], "unknown_operator_reported_possible_rush_or_skip")
        self.assertEqual(fields["phrase_timing.real_take_status"], "unvalidated_until_operator_spot_check")
        self.assertEqual(fields["walkthrough_listening"], "not_performed")
        self.assertEqual(bundle["claim_boundary"], {"listening_acceptance": "not_established", "musical_verdict": "not_established",
                                                    "missed_or_extra_notes": "not_assessed_no_approved_reference", "default_adopted": False,
                                                    "master_changed": False, "operator_preference": "not_recorded"})
        self.assertEqual(bundle["stages"]["arrangement"]["adopted"], False)
        self.assertEqual({name: value["status"] for name, value in bundle["layers"].items()},
                         {"tone_ab": "available", "coverage": "available", "flags_triage": "available", "phrase_timing": "available"})
        self.assertEqual(bundle["layers"]["tone_ab"]["trial"], {"status": "unavailable", "reason": "trial_excerpts_not_requested"})
        for name, record in bundle["media"].items():
            self.assertEqual(sha(self.bundle_dir / record["file"]), record["sha256"], name)
        self.assertTrue(all(item["sha256_before"] == item["sha256_after"] for item in bundle["inputs"]))
        self.assertEqual(bundle["composer_sha256"], sha(REVIEW / "practice_s2_bundle.py"))

    def test_input_changed_during_compose_refuses_only_that_layer(self):
        layers = self.layer_copy("changing-layers")
        triage_path = layers / "flags-triage.json"

        class Changing(bundle_s2.Composer):
            def layer_timing(self, path, bound):
                with open(triage_path, "a") as stream:
                    stream.write("\n")
                return super().layer_timing(path, bound)
        result = Changing(self.fixture["run"], self.tmp / "changing", arrangement=self.args["arrangement"], timeout_seconds=60).compose(
            flags_triage=triage_path, phrase_timing=[layers / "phrase-timing.json"], detector_phrases=layers / "phrases.json")
        self.assertEqual(result["layers"]["flags_triage"], {"status": "unavailable", "reason": "input_changed_during_compose"})
        self.assertEqual(result["layers"]["phrase_timing"]["status"], "available")

    def test_routes_refuse_foreign_bundle_and_omit_tampered_media(self):
        foreign = routes_s2.load(self.bundle_dir, FakeSession("a" * 64, self.fixture["manifest_sha256"]), FakeMedia)
        self.assertEqual(routes_s2.api_response(foreign), (404, {"error": "practice_s2_bundle_foreign_recording"}))
        self.assertEqual(routes_s2.api_response(None), (404, {"error": "practice_s2_bundle_not_configured"}))
        copy_dir = self.tmp / "bundle-tampered"
        shutil.copytree(self.bundle_dir, copy_dir)
        (copy_dir / "media" / "excerpt-3-Y.wav").write_bytes(b"RIFF")
        loaded = routes_s2.load(copy_dir, FakeSession(self.fixture["source_sha256"], self.fixture["manifest_sha256"]), FakeMedia)
        status, value = routes_s2.api_response(loaded)
        self.assertEqual(status, 200)
        self.assertEqual(value["served"]["media_status"]["excerpt-3-Y.wav"], "modified_or_unavailable_omitted")
        self.assertNotIn("excerpt-3-Y.wav", value["served"]["media_urls"])
        self.assertIsNone(routes_s2.media_for(loaded, "excerpt-3-Y.wav"))
        self.assertIsNone(routes_s2.media_for(loaded, "../bundle.json"))
        self.assertIsNotNone(routes_s2.media_for(loaded, "excerpt-1-X.wav"))
        routes_s2.close(loaded)
        self.assertEqual(loaded.media, {})

    @unittest.skipUnless(FFMPEG and Path(FFMPEG).is_file(), "FFmpeg required for trial excerpts")
    def test_trial_excerpts_use_exact_sample_windows_and_trial_gain(self):
        result = self.compose("with-trial", trial_excerpts=True, ffmpeg=FFMPEG)
        trial = result["layers"]["tone_ab"]["trial"]
        self.assertEqual(trial["status"], "available", trial)
        self.assertEqual((trial["adopted"], trial["blinded"]), (False, False))
        self.assertEqual([item["pair"] for item in trial["pairs"]], [1, 2, 3])
        source = (Path(self.fixture["layers"]) / "tone_ab" / "trial-lowshelf.wav").read_bytes()
        offset = source.index(b"data") + 8
        gain = 10 ** (-3.1 / 20)
        for item, start in zip(trial["pairs"], fixture_s2.EXCERPT_STARTS):
            data = (self.tmp / "with-trial" / "media" / item["media"]).read_bytes()
            info = bundle_s2.riff_info(data)
            self.assertEqual((info["frames"], info["sample_rate"], info["channels"], info["format_tag"]), (22050, 44100, 1, 3))
            body = data.index(b"data") + 8
            got = struct.unpack("<100f", data[body:body + 400])
            want = struct.unpack("<100f", source[offset + start * 4:offset + start * 4 + 400])
            self.assertLess(max(abs(a - b * gain) for a, b in zip(got, want)), 1e-6)
        self.assertTrue(all(command["returncode"] == 0 and command["timeout_seconds"] <= 120 for command in result["commands"]))


if __name__ == "__main__":
    unittest.main()
