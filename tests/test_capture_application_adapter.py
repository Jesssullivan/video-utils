"""Inert supervisor qualification; no restoration, actual recording or model work."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from capture_application_adapter import ApplicationAdapter, AdapterError, ProcessInspector, Inventory, InspectionError

CHILD = '''import json,os,pathlib,sys,time
sys.path.insert(0,sys.argv[2])
from capture_application_adapter import ProcessInspector
pathlib.Path(sys.argv[1]).write_text(json.dumps(ProcessInspector().identity(os.getpid())))
time.sleep(120)
'''

BOOTSTRAP = '''import json,pathlib,sys
sys.path.insert(0,sys.argv[1])
import mcp_server,tool_api
from capture_application_adapter import ApplicationAdapter,AdapterError,ProcessInspector,InspectionError
class FailingInspector(ProcessInspector):
    count=0
    def snapshot(self,end):
        self.count+=1
        if pathlib.Path(sys.argv[2],'owned-child.json').is_file() and self.count>5: raise InspectionError('fixture inspection unavailable')
        return super().snapshot(end)
inspector=FailingInspector() if sys.argv[4]=='inspection' else ProcessInspector()
adapter=ApplicationAdapter(pathlib.Path(sys.argv[2]),worker_path=pathlib.Path(sys.argv[3]),inspector=inspector)
original=tool_api.execute
def execute(name,args):
    if name!='apply_capture_profile': return original(name,args)
    try:return {'result':adapter.run(args)}
    except AdapterError as error:raise tool_api.ToolError(str(error),receipt={'supervision':error.receipt,'diagnostic':error.diagnostic})
tool_api.execute=execute
raise SystemExit(mcp_server.main())
'''


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='application-supervisor-fixture-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.marker = self.root / 'owned-child.json'
        self.worker = self.root / 'fixed-inert-worker.py'
        self.arguments = {'input': str(self.root / 'source-placeholder'), 'authoring_dir': str(self.root / 'authoring'),
                          'receipt_sha256': 'a' * 64, 'timeout_seconds': 12}
        self.addCleanup(self.cleanup_owned_child)

    def cleanup_owned_child(self):
        marker = self.root / 'escaped-child.json' if (self.root / 'escaped-child.json').is_file() else self.marker
        if not marker.is_file(): return
        record = json.loads(marker.read_text())
        live = ProcessInspector().identity(record['pid'])
        if live and live['birth']==record['birth'] and live['pgid']==record['pgid'] and live['sid']==record['sid']:
            try: os.killpg(record['pgid'], signal.SIGKILL)
            except ProcessLookupError: pass

    def worker_source(self, mode):
        child = repr(CHILD)
        base = f'''import argparse,json,os,pathlib,signal,subprocess,sys,time
parser=argparse.ArgumentParser();parser.add_argument('input');parser.add_argument('--authoring-dir');parser.add_argument('--receipt-sha256');parser.add_argument('--timeout-seconds',type=int)
args=parser.parse_args()
child_code={child}
marker={str(self.marker)!r};scripts={str(ROOT/'scripts')!r}
'''
        if mode=='inner':
            base += '''child=subprocess.Popen([sys.executable,'-c',child_code,marker,scripts],start_new_session=True)
time.sleep(args.timeout_seconds)
child.kill();child.wait()
print(json.dumps({'schema_version':1,'tool':'apply_capture_profile','status':'error','error':{'code':'deadline_exceeded'},'listening_accepted':False,'master_adopted':False}))
raise SystemExit(2)
'''
        elif mode in ('orphan','escaped'):
            if mode=='escaped':
                escape = CHILD.replace('time.sleep(120)', f'''parent=os.getppid()
while os.getppid()==parent: time.sleep(.03)
os.setsid()
pathlib.Path({str(self.root/'escaped-child.json')!r}).write_text(json.dumps(ProcessInspector().identity(os.getpid())))
time.sleep(120)''')
                base += f'child_code={escape!r}\n'
            leader = "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]]);time.sleep(1)"
            base += f"leader=subprocess.Popen([sys.executable,'-c',{leader!r},child_code,marker,scripts],start_new_session=True)\nleader.wait()\nsignal.signal(signal.SIGALRM,signal.SIG_IGN)\nos.kill(os.getpid(),signal.SIGSTOP)\ntime.sleep(120)\n"
        elif mode=='wedged':
            base += "child=subprocess.Popen([sys.executable,'-c',child_code,marker,scripts],start_new_session=True)\nsignal.signal(signal.SIGALRM,signal.SIG_IGN)\nos.kill(os.getpid(),signal.SIGSTOP)\ntime.sleep(120)\n"
        elif mode=='valid':
            base += "print(json.dumps({'schema_version':1,'tool':'apply_capture_profile','status':'rendered_unreviewed','dsp_performed':True,'listening_accepted':False,'master_adopted':False}))\n"
        self.worker.write_text(base)
        return ApplicationAdapter(self.root,worker_path=self.worker)

    def exchange(self, mode='normal'):
        boot = self.root / 'mcp-inert-bootstrap.py'; boot.write_text(BOOTSTRAP)
        messages = [dict(jsonrpc='2.0',id=1,method='initialize',params={'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'inert-adapter-test','version':'1'}}),
                    dict(jsonrpc='2.0',method='notifications/initialized'),
                    dict(jsonrpc='2.0',id=2,method='tools/call',params={'name':'apply_capture_profile','arguments':self.arguments})]
        result = subprocess.run([sys.executable,str(boot),str(ROOT/'scripts'),str(self.root),str(self.worker),mode],
            input=''.join(json.dumps(x)+'\n' for x in messages),capture_output=True,text=True,timeout=18)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
        return json.loads(result.stdout.splitlines()[1])['result']

    def receipt(self,response):
        metadata=json.loads(response['content'][0]['text'])['receipt']['supervision']
        return json.loads(Path(metadata['path']).read_text())

    def assert_child_stopped(self):
        self.assertTrue(self.marker.is_file())
        record=json.loads(self.marker.read_text()); live=ProcessInspector().identity(record['pid'])
        if live: self.assertTrue(live['state']=='Z' or live['birth']!=record['birth'],live)

    def test_native_birth_and_snapshot(self):
        inspector=ProcessInspector(); first=inspector.identity(os.getpid());second=inspector.identity(os.getpid())
        self.assertEqual(first['birth'],second['birth']);self.assertTrue(first['birth'][1]>0)
        self.assertEqual(first['pgid'],os.getpgrp());self.assertEqual(first['sid'],os.getsid(0))
        self.assertIn(os.getpid(),inspector.snapshot(time.monotonic()+1))

    def test_closed_controls_and_fixed_inner_budget(self):
        adapter=self.worker_source('valid')
        for changes in ({'timeout_seconds':11},{'timeout_seconds':True},{'timeout_seconds':601},{'receipt_sha256':'Z'*64},{'runtime':'/bin/python'},{'input':'nul\x00path'}):
            with self.subTest(changes=changes),patch('capture_application_adapter.subprocess.Popen') as launch:
                with self.assertRaises(ValueError):adapter.run(dict(self.arguments,**changes))
                launch.assert_not_called()
        result=adapter.run(self.arguments);self.assertFalse(result['master_adopted'])
        receipt=json.loads(Path(result['supervision']['receipt']['path']).read_text())
        self.assertEqual((receipt['outer_seconds'],receipt['inner_seconds'],receipt['fallback_seconds']),(12,2,5))
        self.assertEqual(receipt['containment_scope'],'observed_owned_sessions_only')
        self.arguments.pop('timeout_seconds')
        result=adapter.run(self.arguments)
        receipt=json.loads(Path(result['supervision']['receipt']['path']).read_text())
        self.assertEqual((receipt['outer_seconds'],receipt['inner_seconds']),(600,590))

    def test_actual_mcp_inner_cleanup_is_not_outer_fallback(self):
        self.worker_source('inner'); response=self.exchange();self.assertTrue(response['isError'])
        receipt=self.receipt(response);self.assertEqual(receipt['status'],'worker_error',receipt)
        self.assertNotIn('outer fallback',receipt.get('reason',''));self.assertEqual(receipt['events'],[])
        self.assert_child_stopped()

    def test_actual_mcp_wedged_new_session_fallback_preserves_unrelated_sentinel(self):
        self.worker_source('wedged')
        sentinel=subprocess.Popen([sys.executable,'-c',CHILD,str(self.root/'sentinel.json'),str(ROOT/'scripts')],start_new_session=True)
        def reap_sentinel():
            if sentinel.poll() is None: sentinel.kill()
            sentinel.wait(timeout=5)
        self.addCleanup(reap_sentinel)
        started=time.monotonic();response=self.exchange();elapsed=time.monotonic()-started
        self.assertTrue(response['isError']);receipt=self.receipt(response)
        self.assertGreaterEqual(elapsed,6.5,receipt);self.assertLess(elapsed,13)
        self.assertEqual(receipt['reason'],'outer fallback deadline',receipt)
        self.assertEqual(receipt['descendant_cleanup'],'no_runnable_recorded_members')
        self.assertEqual(receipt['candidate_publication'],'unknown');self.assertIsNone(sentinel.poll())
        child=json.loads(self.marker.read_text());self.assertNotEqual(child['sid'],receipt['root_pid'])
        self.assertTrue(any(event.get('pgid')==child['pgid'] for event in receipt['events']))
        self.assert_child_stopped()

    def test_actual_mcp_retained_orphan_group_after_leader_exit(self):
        self.worker_source('orphan');response=self.exchange();self.assertTrue(response['isError'])
        receipt=self.receipt(response);self.assertEqual(receipt['reason'],'outer fallback deadline',receipt)
        self.assertEqual(receipt['descendant_cleanup'],'no_runnable_recorded_members');self.assert_child_stopped()
        inventory=json.loads(Path(receipt['inventory']['path']).read_text())
        child=json.loads(self.marker.read_text());record=next(row for row in inventory['processes'] if row['pid']==child['pid'])
        self.assertEqual(record['birth'],child['birth']);self.assertNotEqual(record['ppid'],receipt['root_pid'])

    def test_actual_mcp_inspection_failure_does_not_claim_children_stopped(self):
        self.worker_source('wedged');response=self.exchange('inspection');self.assertTrue(response['isError'])
        receipt=self.receipt(response);self.assertEqual(receipt['descendant_cleanup'],'unknown')
        self.assertEqual(receipt['candidate_publication'],'unknown');self.assertTrue(receipt['inventory_errors'])
        self.assertFalse(any(event.get('pgid') for event in receipt['events']))
        self.assertTrue(self.marker.is_file());self.assertIsNotNone(ProcessInspector().identity(json.loads(self.marker.read_text())['pid']))

    def test_changed_birth_group_is_not_verified_or_signalled(self):
        class Inspector:
            def identity(self,pid): return {'pid':pid,'ppid':1,'pgid':20,'sid':20,'birth':['fake',2],'state':'S'}
        inventory=Inventory(Inspector(),{'pid':10,'ppid':1,'pgid':10,'sid':10,'birth':['fake',1],'state':'S'})
        inventory.records[20]={'pid':20,'ppid':10,'pgid':20,'sid':20,'birth':['fake',1],'state':'S'};inventory.groups={(20,20)}
        verified,rejected=inventory.verified_groups({20:{'pid':20,'ppid':1,'pgid':20,'state':'S'}},time.monotonic()+1)
        self.assertEqual(verified,[]);self.assertEqual(rejected,[20])

    def test_actual_mcp_recorded_orphan_that_moves_session_remains_unknown(self):
        self.worker_source('escaped'); response=self.exchange(); self.assertTrue(response['isError'])
        receipt=self.receipt(response);self.assertEqual(receipt['descendant_cleanup'],'unknown')
        self.assertEqual(receipt['candidate_publication'],'unknown')
        old=json.loads(self.marker.read_text());escaped=json.loads((self.root/'escaped-child.json').read_text())
        self.assertEqual(old['birth'],escaped['birth']);self.assertNotEqual(old['sid'],escaped['sid'])
        self.assertIsNotNone(ProcessInspector().identity(escaped['pid']))
        self.assertFalse(any(event.get('pgid')==escaped['pgid'] for event in receipt['events']))

    def test_inventory_and_event_receipts_are_bounded(self):
        adapter=self.worker_source('valid'); directory=self.root/'receipt';directory.mkdir()
        identity=ProcessInspector().identity(os.getpid());inventory=Inventory(ProcessInspector(),identity)
        data={'events':[{'index':i} for i in range(128)]}
        adapter.inventory_receipt(directory,inventory,data);ref=adapter.receipt(directory,data)
        receipt=json.loads(Path(ref['path']).read_text());self.assertEqual(len(receipt['events']),8)
        self.assertTrue(receipt['events_omitted']);self.assertEqual(len(json.loads((directory/'inventory.json').read_text())['events']),128)
        with self.assertRaises(AdapterError):adapter.receipt(directory,{'oversize':'x'*65536})

    def test_result_extension_cannot_exceed_combined_limit(self):
        self.worker_source('valid')
        raw=self.worker.read_text().replace("'dsp_performed':True", "'padding':'x'*16050,'dsp_performed':True")
        self.worker.write_text(raw)
        with self.assertRaises(AdapterError) as caught: ApplicationAdapter(self.root,worker_path=self.worker).run(self.arguments)
        self.assertIn('exceeds16KiB',str(caught.exception));self.assertIsNotNone(caught.exception.receipt)

    def test_fixed_source_pin_and_symlink_reject_before_spawn(self):
        scripts=self.root/'scripts';scripts.mkdir();worker=scripts/'apply_capture_profile.py';worker.write_text('print(1)')
        with patch('capture_application_adapter.subprocess.Popen') as launch:
            with self.assertRaises(AdapterError):ApplicationAdapter(self.root).run(self.arguments)
            launch.assert_not_called()
        self.worker_source('valid'); worker.unlink();worker.symlink_to(self.worker)
        with self.assertRaises(AdapterError):ApplicationAdapter(self.root).run(self.arguments)

    def test_exhausted_cleanup_budget_sends_no_signal(self):
        from types import SimpleNamespace
        process=SimpleNamespace(pid=99888,returncode=None,kill=unittest.mock.Mock(),wait=unittest.mock.Mock())
        inventory=Inventory(ProcessInspector(),{'pid':99888,'ppid':1,'pgid':99888,'sid':99888,'birth':['fixture',1],'state':'S'})
        with patch('capture_application_adapter.os.kill') as direct,patch('capture_application_adapter.os.killpg') as group:
            outcome=ApplicationAdapter().cleanup(process,inventory,time.monotonic()-1,[])
        self.assertEqual(outcome,'unknown');direct.assert_not_called();group.assert_not_called();process.kill.assert_not_called()
        process.wait.assert_called_once()

    def test_process_identity_overflow_refuses_before_signals(self):
        class Inspector:
            def identity(self,pid):return {'pid':pid,'ppid':0 if pid==1 else 1,'pgid':1,'sid':1,'birth':['fixture',pid],'state':'S'}
        inventory=Inventory(Inspector(),Inspector().identity(1))
        rows={pid:{'pid':pid,'ppid':0 if pid==1 else 1,'pgid':1,'state':'S'} for pid in range(1,514)}
        with self.assertRaisesRegex(InspectionError,'identity bound'):inventory.observe(rows,time.monotonic()+1)

    def test_slow_inspection_uses_passed_absolute_bound(self):
        with patch('capture_application_adapter.sys.platform','linux'),patch('capture_application_adapter.subprocess.run',side_effect=subprocess.TimeoutExpired('ps',.05)) as inspect:
            with self.assertRaises(InspectionError):ProcessInspector().snapshot(time.monotonic()+.05)
        self.assertLessEqual(inspect.call_args.kwargs['timeout'],.05)

    def test_worker_diagnostic_recovery_is_durable_and_not_adopted(self):
        self.worker_source('inner')
        candidate={'schema_version':1,'status':'rendered_unreviewed','run_dir':str(self.root/'test-owned-candidate'),
                   'source_sha256':'a'*64,'profile_sha256':'b'*64,'authoring_receipt_sha256':'c'*64,
                   'manifest':{'relative_path':'manifest.json','sha256':'d'*64},
                   'receipt':{'relative_path':'application-receipt.json','sha256':'e'*64},
                   'export_outcome':{'relative_path':'export/outcome.json','sha256':'f'*64},
                   'listening_accepted':False,'master_adopted':False}
        self.worker.write_text(self.worker.read_text().replace("'error':{'code':'deadline_exceeded'}", "'error':{'code':'reporting_interrupted'},'committed_candidate':"+repr(candidate)))
        with self.assertRaises(AdapterError) as caught:ApplicationAdapter(self.root,worker_path=self.worker).run(self.arguments)
        receipt=json.loads(Path(caught.exception.receipt['path']).read_text())
        durable=json.loads(Path(receipt['worker_result']['path']).read_text())
        self.assertEqual(durable['committed_candidate'],caught.exception.diagnostic['committed_candidate'])
        self.assertFalse(durable['committed_candidate']['master_adopted']);self.assert_child_stopped()
        self.assertEqual(durable['committed_candidate'],candidate)

    def test_nonfinal_starting_receipt_exception_still_cleans_owned_root(self):
        class Adapter(ApplicationAdapter):
            attempts=0
            cleaned=False
            def receipt(self,directory,data):
                self.attempts+=1
                if self.attempts==2:raise AdapterError('inert budget exception after launch',self.last_receipt)
                return super().receipt(directory,data)
            def cleanup(self,process,inventory,end,events):
                self.cleaned=True
                return super().cleanup(process,inventory,end,events)
        self.worker.write_text('import time;time.sleep(120)')
        adapter=Adapter(self.root,worker_path=self.worker)
        with self.assertRaises(AdapterError) as caught:adapter.run(self.arguments)
        self.assertTrue(adapter.cleaned);self.assertTrue(caught.exception.finalized)
        receipt=json.loads(Path(caught.exception.receipt['path']).read_text())
        self.assertEqual(receipt['status'],'supervision_failed');self.assertIsNotNone(receipt['worker_returncode'])

    def test_changed_birth_group_never_gets_cleanup_signal(self):
        from types import SimpleNamespace
        class Inspector:
            def identity(self,pid):return {'pid':pid,'ppid':0,'pgid':pid,'sid':pid,'birth':['fixture',2],'state':'S'}
            def snapshot(self,end):return {20:{'pid':20,'ppid':1,'pgid':20,'state':'S'}}
        inventory=Inventory(Inspector(),{'pid':10,'ppid':1,'pgid':10,'sid':10,'birth':['fixture',1],'state':'S'})
        inventory.records[20]={'pid':20,'ppid':10,'pgid':20,'sid':20,'birth':['fixture',1],'state':'S'};inventory.groups={(20,20)}
        process=SimpleNamespace(pid=10,returncode=0)
        with patch('capture_application_adapter.os.killpg') as signal_group:
            self.assertEqual(ApplicationAdapter(inspector=inventory.inspector).cleanup(process,inventory,time.monotonic()+1,[]),'unknown')
        signal_group.assert_not_called()

    def test_group_bound_and_native_zero_birth_are_rejected(self):
        class Inspector:
            def identity(self,pid):return {'pid':pid,'ppid':0 if pid==1 else 1,'pgid':pid,'sid':pid,'birth':['fixture',pid],'state':'S'}
        inventory=Inventory(Inspector(),Inspector().identity(1))
        rows={pid:{'pid':pid,'ppid':0 if pid==1 else 1,'pgid':pid,'state':'S'} for pid in range(1,132)}
        with self.assertRaisesRegex(InspectionError,'group bound'):inventory.observe(rows,time.monotonic()+1)
        import io
        fields=['S','1','2','2']+['0']*16
        with patch('capture_application_adapter.sys.platform','linux'),patch('builtins.open',return_value=io.BytesIO(('2 (fixture) '+' '.join(fields)).encode())):
            with self.assertRaisesRegex(InspectionError,'birth token'):ProcessInspector().identity(2)

    def test_native_table_overflow_short_read_and_slow_return_are_unknown(self):
        class Library:
            count=8192
            delay=0
            def proc_listallpids(self,pids,size):
                time.sleep(self.delay);pids[0]=42;return self.count
            def proc_pidinfo(self,*args):return 1
        library=Library();inspector=ProcessInspector()
        with patch('capture_application_adapter.sys.platform','darwin'),patch.object(inspector,'darwin_library',return_value=library):
            with self.assertRaisesRegex(InspectionError,'row inventory'):inspector.snapshot(time.monotonic()+1)
            library.count=1
            with self.assertRaisesRegex(InspectionError,'short'):inspector.snapshot(time.monotonic()+1)
            library.delay=.03
            with self.assertRaisesRegex(InspectionError,'deadline'):inspector.snapshot(time.monotonic()+.01)

    def test_outer_timeout_does_not_erase_already_written_candidate_metadata(self):
        self.worker_source('wedged')
        candidate=self.root/'test-owned-candidate';candidate.mkdir();manifest=candidate/'manifest.json'
        manifest.write_text('{"test_only":true,"listening_accepted":false,"master_adopted":false}')
        prior=manifest.read_bytes()
        response=self.exchange();self.assertTrue(response['isError'])
        self.assertEqual(self.receipt(response)['candidate_publication'],'unknown')
        self.assertEqual(manifest.read_bytes(),prior);self.assert_child_stopped()


if __name__=='__main__':unittest.main()
