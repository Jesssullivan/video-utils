"""Independent sharing refusal/publication fixtures; no encoding or media probes."""
from contextlib import ExitStack
import importlib.util
import io
import json
import os
import signal
import sys
import time
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('share_export_independent_audit', ROOT / 'scripts/share_export.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class SharePublicationAudit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source.mp4'
        self.source.write_bytes(b'fixture-source-not-media')
        self.output = self.root / 'shared.mp4'
        worker.LAST_STATE = None
        self.addCleanup(setattr, worker, 'LAST_STATE', None)

    def mocked_media(self, *, peaks=None, mutate_source=False):
        stack = ExitStack()
        metadata = {'format': {'duration': '1'}, 'audio': {'index': 1, 'sample_rate': '44100', 'channels': 1, 'codec_name': 'aac', 'time_base': '1/44100'},
                    'video': {'index': 0, 'width': 320, 'height': 240, 'codec_name': 'h264', 'time_base': '1/1000', 'pix_fmt': 'yuv420p', 'sample_aspect_ratio': '1:1'}}
        calls = []
        def run(args, state):
            calls.append(args)
            destination = args[-1]
            if destination != '-':
                Path(destination).write_bytes(('fixture:' + Path(destination).name).encode())
                if mutate_source and Path(destination).name == 'export.mp4':
                    self.source.write_bytes(b'changed-fixture-source')
            return subprocess.CompletedProcess(args, 0, '', '')
        packet_rows = [dict(pts=0, dts=0, duration=500, data_hash='SHA256:one'), dict(pts=500, dts=500, duration=500, data_hash='SHA256:two')]
        audio = dict(start_seconds=0., end_seconds=1., decoded_samples=44100, frame_count=44, time_base='1/44100')
        measures = iter(peaks or [-2., -2.])
        stack.enter_context(patch.object(worker, 'command', side_effect=lambda args: ['fixture-ffmpeg', *args]))
        stack.enter_context(patch.object(worker, 'run', side_effect=run))
        stack.enter_context(patch.object(worker, 'probe', return_value=metadata))
        stack.enter_context(patch.object(worker, 'packets', return_value=packet_rows))
        stack.enter_context(patch.object(worker, 'audio_frames', return_value=audio))
        stack.enter_context(patch.object(worker, 'loudness', side_effect=lambda path,state: dict(integrated_lufs=-18., true_peak_dbtp=next(measures), silence=False)))
        return stack, calls

    def export(self):
        return worker.share_export(self.source, self.output, codec='copy', timeout_seconds=30)

    def test_existing_output_is_rejected_without_media_work_or_overwrite(self):
        self.output.write_bytes(b'operator-owned-output')
        with patch.object(worker, 'run', side_effect=AssertionError('must not run media')):
            with self.assertRaises(worker.ShareError):
                self.export()
        self.assertEqual(self.output.read_bytes(), b'operator-owned-output')
        self.assertEqual(self.source.read_bytes(), b'fixture-source-not-media')

    def test_leaf_symlink_source_is_rejected_without_media_work(self):
        link = self.root / 'source-link.mp4'
        link.symlink_to(self.source)
        with patch.object(worker, 'run', side_effect=AssertionError('must not run media')):
            with self.assertRaises(worker.ShareError):
                worker.share_export(link, self.output, codec='copy', timeout_seconds=30)
        self.assertFalse(self.output.exists())

    def test_source_mutation_blocks_publication_and_preserves_failure_staging(self):
        context, calls = self.mocked_media(mutate_source=True)
        with context, self.assertRaises(worker.ShareError) as caught:
            self.export()
        self.assertIn('source changed', str(caught.exception))
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_name(self.output.name+'.receipt.json').exists())
        self.assertEqual(caught.exception.share_failure['status'], 'failed_no_export_published')
        self.assertTrue(Path(caught.exception.share_failure['failure_receipt_path']).is_file())

    def test_destination_reappearing_at_publication_is_never_replaced(self):
        publish = worker.publish_no_clobber
        def collide(staged, destination):
            if destination == self.output:
                destination.write_bytes(b'concurrent-operator-file')
            return publish(staged, destination)
        context, calls = self.mocked_media()
        with context, patch.object(worker, 'publish_no_clobber', side_effect=collide), self.assertRaises(FileExistsError) as caught:
            self.export()
        self.assertEqual(self.output.read_bytes(), b'concurrent-operator-file')
        self.assertEqual(caught.exception.share_failure['status'], 'failed_no_export_published')
        self.assertEqual(self.source.read_bytes(), b'fixture-source-not-media')

    def test_real_link_then_exception_retains_committed_movie_recovery(self):
        publish = worker.publish_no_clobber
        def interrupted(staged, destination):
            publish(staged, destination)
            if destination == self.output:
                raise worker.ShareError('fixture interrupted after link')
        context, calls = self.mocked_media()
        with context, patch.object(worker, 'publish_no_clobber', side_effect=interrupted), self.assertRaises(worker.ShareError) as caught:
            self.export()
        diagnostic = caught.exception.share_failure
        self.assertTrue(self.output.is_file())
        self.assertEqual(diagnostic['status'], 'exported_unreviewed_reporting_interrupted')
        self.assertEqual(diagnostic['output']['path'], str(self.output))
        self.assertFalse(diagnostic['master_adopted'])
        self.assertFalse(diagnostic['listening_accepted'])

    def test_link_commit_with_staging_observation_missing_cannot_claim_absence(self):
        publish = worker.publish_no_clobber
        def interrupted(staged, destination):
            publish(staged, destination)
            if destination == self.output:
                staged.unlink()
                raise worker.ShareError('fixture interruption with unavailable staging alias')
        context, calls = self.mocked_media()
        with context, patch.object(worker, 'publish_no_clobber', side_effect=interrupted), self.assertRaises(worker.ShareError) as caught:
            self.export()
        self.assertTrue(self.output.is_file())
        self.assertNotEqual(caught.exception.share_failure['status'], 'failed_no_export_published')
        self.assertTrue(caught.exception.share_failure.get('output') or caught.exception.share_failure.get('possible_output'))

    def test_unobservable_attempted_publication_retains_possible_output(self):
        publish = worker.publish_no_clobber
        def interrupted(staged, destination):
            publish(staged, destination)
            if destination == self.output:
                raise worker.ShareError('fixture observation denied after link')
        stat = Path.stat
        def deny_output(path, *args, **kwargs):
            if path == self.output and worker.LAST_STATE and worker.LAST_STATE.get('publish_attempted'):
                raise PermissionError('fixture publication observation denied')
            return stat(path, *args, **kwargs)
        context, calls = self.mocked_media()
        with context, patch.object(worker, 'publish_no_clobber', side_effect=interrupted), patch.object(Path, 'stat', deny_output), self.assertRaises(worker.ShareError) as caught:
            self.export()
        diagnostic = caught.exception.share_failure
        self.assertTrue(self.output.is_file())
        self.assertEqual(diagnostic['status'], 'publication_outcome_unknown')
        self.assertIsNone(diagnostic['output'])
        self.assertEqual(diagnostic['possible_output']['path'], str(self.output))

    def test_sidecar_collision_retains_movie_and_never_replaces_competing_receipt(self):
        sidecar = self.output.with_name(self.output.name+'.receipt.json')
        publish = worker.publish_no_clobber
        def collide(staged, destination):
            if destination == sidecar:
                destination.write_bytes(b'operator-owned-receipt')
            return publish(staged, destination)
        context, calls = self.mocked_media()
        with context, patch.object(worker, 'publish_no_clobber', side_effect=collide), self.assertRaises(FileExistsError) as caught:
            self.export()
        diagnostic = caught.exception.share_failure
        self.assertTrue(self.output.is_file())
        self.assertEqual(sidecar.read_bytes(), b'operator-owned-receipt')
        self.assertEqual(diagnostic['status'], 'exported_unreviewed_reporting_interrupted')
        self.assertEqual(diagnostic['output']['path'], str(self.output))
        self.assertTrue(Path(diagnostic['failure_receipt_path']).is_file())

    def test_later_rejected_cli_call_cannot_reuse_previous_committed_recovery(self):
        context, calls = self.mocked_media()
        with context:
            self.export()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('sys.stdout', stdout), patch('sys.stderr', stderr):
            status = worker.main([str(self.source), str(self.root/'other.mp4'), '--height', '721'])
        result = json.loads(stdout.getvalue())
        self.assertEqual(status, 2)
        self.assertEqual(result['status'], 'rejected')
        self.assertFalse(result.get('output'))
        self.assertNotIn('failure_receipt_path', result)

    def test_peak_retry_is_audio_only_and_failed_second_attempt_never_publishes(self):
        context, calls = self.mocked_media(peaks=[-1., -1.4])
        with context, self.assertRaises(worker.ShareError):
            self.export()
        self.assertEqual(sum(Path(command[-1]).name=='video.mp4' for command in calls), 1)
        self.assertEqual(sum(Path(command[-1]).name.startswith('audio-') for command in calls), 2)
        self.assertFalse(self.output.exists())

    def test_inner_owned_deadline_reaps_inert_same_session_child_and_retains_logs(self):
        metadata = self.root / 'owned-inert-processes.json'
        code = ("import json,os,subprocess,sys,time; "
                "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
                "open(sys.argv[1],'w').write(json.dumps({'leader':os.getpid(),'child':child.pid,'pgid':os.getpgrp(),'sid':os.getsid(0)})); "
                "print('owned inert fixture',flush=True);time.sleep(30)")
        stage = self.root / 'inert-staging'; stage.mkdir()
        state = dict(staging=stage, events=[], deadline=worker.Deadline(1.))
        began = time.monotonic()
        try:
            with self.assertRaises(worker.app.ApplyError):
                worker.run([sys.executable, '-c', code, str(metadata)], state)
            self.assertLess(time.monotonic()-began, 6.5)
            identities = json.loads(metadata.read_text())
            self.assertEqual(identities['leader'], identities['pgid'])
            self.assertEqual(identities['leader'], identities['sid'])
            for pid in (identities['leader'], identities['child']):
                result = subprocess.run(['/bin/ps','-p',str(pid),'-o','stat='], capture_output=True, text=True, timeout=3)
                self.assertTrue(not result.stdout.strip() or result.stdout.strip().startswith('Z'), result.stdout)
            self.assertTrue(state['events'])
            self.assertTrue(all(row['session_id']==identities['sid'] for row in state['events']))
            self.assertIn('owned inert fixture', ''.join(path.read_text() for path in stage.glob('*.log')))
        finally:
            # Only a failed fixture can require this escape hatch. Recheck its
            # exact owned live session before signaling; never target outsiders.
            if metadata.exists():
                identities = json.loads(metadata.read_text())
                for pid in (identities['child'], identities['leader']):
                    try:
                        if os.getpgid(pid)==identities['pgid'] and os.getsid(pid)==identities['sid']:
                            status=subprocess.run(['/bin/ps','-p',str(pid),'-o','stat='],capture_output=True,text=True,timeout=3).stdout.strip()
                            if status and not status.startswith('Z'):
                                os.killpg(identities['pgid'],signal.SIGKILL)
                                break
                    except ProcessLookupError:
                        pass

    def test_cli_owned_alarm_cleans_inert_tree_before_failure_reporting(self):
        metadata=self.root/'cli-owned-inert.json'
        stage=self.root/'cli-inert-staging';stage.mkdir()
        code=("import json,os,subprocess,sys,time; "
              "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
              "open(sys.argv[1],'w').write(json.dumps({'leader':os.getpid(),'child':child.pid,'pgid':os.getpgrp(),'sid':os.getsid(0)}));time.sleep(30)")
        state=dict(source=self.source,output=self.output,receipt=self.output.with_name('receipt.json'),staging=stage,events=[],deadline=worker.Deadline(20),published=False)
        original_settings=worker.settings
        def fast_alarm(*args,**kwargs):
            cfg=original_settings(*args,**kwargs)
            cfg['operation_seconds']=1  # Fixture-only alarm, not public controls.
            return cfg
        def owned_fixture(*args,**kwargs):
            worker.LAST_STATE=state
            return worker.run([sys.executable,'-c',code,str(metadata)],state)
        stdout,stderr=io.StringIO(),io.StringIO()
        began=time.monotonic()
        try:
            with patch.object(worker,'settings',side_effect=fast_alarm),patch.object(worker,'share_export',side_effect=owned_fixture),patch('sys.stdout',stdout),patch('sys.stderr',stderr):
                status=worker.main([str(self.source),str(self.output),'--timeout-seconds','30'])
            self.assertLess(time.monotonic()-began,6.5)
            diagnostic=json.loads(stdout.getvalue())
            self.assertEqual(status,2)
            self.assertEqual(diagnostic['code'],'deadline_exceeded')
            self.assertEqual(diagnostic['status'],'failed_no_export_published')
            identities=json.loads(metadata.read_text())
            self.assertEqual(identities['leader'],identities['pgid'])
            self.assertEqual(identities['leader'],identities['sid'])
            self.assertTrue(any(event['reason']=='stage_interrupted' for event in state['events']))
            for pid in (identities['leader'],identities['child']):
                observed=subprocess.run(['/bin/ps','-p',str(pid),'-o','stat='],capture_output=True,text=True,timeout=3).stdout.strip()
                self.assertTrue(not observed or observed.startswith('Z'),observed)
            self.assertEqual(worker.signal.getitimer(worker.signal.ITIMER_REAL)[0],0)
            self.assertTrue(Path(diagnostic['failure_receipt_path']).is_file())
        finally:
            if metadata.exists():
                identities=json.loads(metadata.read_text())
                for pid in (identities['child'],identities['leader']):
                    try:
                        if os.getpgid(pid)==identities['pgid'] and os.getsid(pid)==identities['sid']:
                            observed=subprocess.run(['/bin/ps','-p',str(pid),'-o','stat='],capture_output=True,text=True,timeout=3).stdout.strip()
                            if observed and not observed.startswith('Z'):
                                os.killpg(identities['pgid'],signal.SIGKILL)
                                break
                    except ProcessLookupError:
                        pass

    def test_long_recovery_transport_cap_retains_publication_truth_and_pinned_selectors(self):
        output='/'+('a/'*1900)+'shared.mp4'
        staging='/'+('b/'*1900)+'.share-export-fixture'
        receipt=staging+'/failure-receipt.json'
        diagnostic=dict(status='exported_unreviewed_reporting_interrupted',error='fixture failure',code='export_failed',
                        output=dict(path=output,sha256='a'*64,bytes=10,receipt_path=output+'.receipt.json',receipt_sha256='b'*64),
                        possible_output=None,staging_dir=staging,failure_receipt_path=receipt,failure_receipt_sha256='c'*64,
                        stage_progress=[dict(path='stage-01-progress.txt',last_report=dict(speed='x'*100,frame=str(i))) for i in range(100)],
                        master_adopted=False,listening_accepted=False)
        compact=worker.bounded_diagnostic(diagnostic)
        self.assertLessEqual(len(worker.encoded(compact,worker.MAX_RESULT_BYTES)),16*1024)
        self.assertEqual(compact['status'],'exported_unreviewed_reporting_interrupted')
        self.assertEqual(compact['output']['path'],output)
        self.assertEqual(compact['output']['sha256'],'a'*64)
        self.assertEqual(compact['failure_receipt_path'],receipt)
        self.assertEqual(compact['failure_receipt_sha256'],'c'*64)
        self.assertIsNone(compact['possible_output'])
        self.assertIn('stage_progress',compact['diagnostic_fields_omitted'])
        self.assertFalse(compact['master_adopted'])
        self.assertFalse(compact['listening_accepted'])

    def test_negative_interior_packet_duration_cannot_receive_clock_proof(self):
        source = [dict(pts=0,dts=0,duration=40,data_hash='one'),dict(pts=40,dts=40,duration=40,data_hash='two')]
        output = [dict(row) for row in source]
        output[0]['duration'] = -40
        with self.assertRaises(worker.ShareError):
            worker.verify_packets(source, output, '1/1000', '1/1000', copy=True)


if __name__ == '__main__':
    unittest.main()
