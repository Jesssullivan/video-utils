"""Inert composition clock/branch guards; no media process or PCM fixture."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('accepted_compact_assembly',HERE/'2026-10-06-accepted-fuller-compact-assembly.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

class CompositionTests(unittest.TestCase):
    def branches(self):
        c={'status':'marked_review_preview_verified_unreviewed','source_sha256':h.SOURCE_SHA,'source_container_start_seconds':0,
           'marker_mode':'arrangement_reference_review','arrangement_marker_bindings':{'analyzed_input_sha256':h.ANALYSIS_INPUT_SHA,'assessment':{'sha256':h.ASSESSMENT_SHA}},
           'verification':{'decoded_video_frame_pts_preserved':True,'decoded_video_last_extent_preserved':True,'picture_geometry_preserved':True,
             'decoded_video_frame_count':3621,'decoded_video_first_pts_seconds':0,'decoded_video_last_extent_seconds':150.885}}
        m={'source':{'sha256':h.SOURCE_SHA},'timeline':{'audio_start_seconds':0,'format_start_seconds':0,'no_time_stretch':True},'pcm':{'sample_rate':44100,'channels':1,'sample_count':6657385}}
        e={'source_sha256':h.SOURCE_SHA,'verification':{'source_hash_verified':True,'video_frame_count_preserved':True,'relative_audio_video_start_verified':True,
             'dsp_latency_compensation_recorded':True,'final_true_peak_within_target':True,'video_packet_expected_translation_seconds':0,'physical_audio_video_sync_verified':False}}
        return c,m,e

    def test_common_original_and_analysis_branch_required(self):
        c,m,e=self.branches();h.branch_gate(c,m,e)
        c['arrangement_marker_bindings']['analyzed_input_sha256']='fuller-audio-hash'
        with self.assertRaisesRegex(ValueError,'analysis/assessment branch'):h.branch_gate(c,m,e)
        c,m,e=self.branches();m['source']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Common original'):h.branch_gate(c,m,e)

    def test_nonzero_source_origin_and_unverified_picture_are_refused(self):
        c,m,e=self.branches();m['timeline']['audio_start_seconds']=.025
        with self.assertRaisesRegex(ValueError,'Source-zero'):h.branch_gate(c,m,e)
        c,m,e=self.branches();c['status']='running'
        with self.assertRaisesRegex(ValueError,'verified terminal'):h.branch_gate(c,m,e)
        c,m,e=self.branches();c['verification']['decoded_video_last_extent_seconds']=150.9
        with self.assertRaisesRegex(ValueError,'extent'):h.branch_gate(c,m,e)

    def test_rational_equivalence_with_negative_decode_clock(self):
        a=[{'pts':0,'dts':-2,'duration':1,'data_hash':'SHA256:a'}]
        b=[{'pts':0,'dts':-4,'duration':2,'data_hash':'SHA256:a'}]
        h.exact_packets(a,b,'1/600','1/1200')
        b[0]['pts']=1
        with self.assertRaisesRegex(ValueError,'rational packet pts'):h.exact_packets(a,b,'1/600','1/1200')

    def test_aac_padding_and_payload_must_survive(self):
        a=[{'pts':-1024,'dts':-1024,'duration':1024,'data_hash':'SHA256:a','side_data_list':[{'skip_samples':1024,'discard_padding':0}]}]
        b=copy.deepcopy(a);h.exact_packets(a,b,'1/44100','1/44100',audio=True)
        b[0]['side_data_list'][0]['skip_samples']=0
        with self.assertRaisesRegex(ValueError,'priming/padding'):h.exact_packets(a,b,'1/44100','1/44100',audio=True)
        b=copy.deepcopy(a);b[0]['data_hash']='SHA256:b'
        with self.assertRaisesRegex(ValueError,'payload'):h.exact_packets(a,b,'1/44100','1/44100',audio=True)

    def test_composition_is_fresh_experiment_only(self):
        with tempfile.TemporaryDirectory() as d:
            old=h.ROOT;h.ROOT=Path(d).resolve()
            try:
                base=h.ROOT/'artifacts/experiments';base.mkdir(parents=True);p=base/'accepted-fuller-compact-one'
                self.assertEqual(h.fresh_output(p),p);p.mkdir()
                with self.assertRaisesRegex(ValueError,'Fresh'):h.fresh_output(p)
                with self.assertRaisesRegex(ValueError,'Fresh'):h.fresh_output(h.ROOT/'artifacts/runs/new')
            finally:h.ROOT=old

if __name__=='__main__':unittest.main()
