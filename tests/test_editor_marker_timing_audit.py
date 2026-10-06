"""Independent regressions for snapped coordinates leaving measured VFR coverage."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'scripts') not in sys.path:
    sys.path.insert(0,str(ROOT/'scripts'))
SPEC=importlib.util.spec_from_file_location('editor_marker_timing_audit',ROOT/'scripts/editor_marker_plan.py')
planner=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


class QuantizedPictureCoverageAudit(unittest.TestCase):
    def plan(self,start,end=None,target='davinci_resolve',shifted=False,frames=None):
        source_hash='c'*64
        item={'source_time_seconds':start,'end_seconds':start if end is None else end,
              'name':'uncertain_recurrence','confidence':'unknown','status':'needs_review','evidence':{}}
        generic={'source_sha256':source_hash,'markers':[item]}
        selection={'source_sha256':source_hash,'selected_markers':[
            {'marker_index':0,'marker_id':planner.marker_id(0,item)}]}
        profile={'source_sha256':source_hash,'target':target,
                 'source_origin':'-1/2' if shifted else 0,'asset_origin':2 if shifted else 0,
                 'clip_in':2 if shifted else 0,'clip_out':3 if shifted else 1,'parent_offset':3600,
                 'fixture_grid':{'frame_duration':'1/24','origin':2 if shifted else 0,'frame_id_origin':100 if shifted else 0}}
        ticks=frames or [(0,25),(25,24),(49,26),(75,25)]
        pts={'source_sha256':source_hash,'clock':'original_source_stream_timestamps_seconds','time_base':'1/600',
             'frames':[{'best_effort_timestamp':t-300 if shifted else t,'duration':d} for t,d in ticks]}
        return planner.make_plan(generic,selection,profile,pts)

    def test_last_frame_point_snapped_to_exclusive_video_end_abstains(self):
        for target in ('davinci_resolve','final_cut_pro'):
            with self.subTest(target=target):
                result=self.plan('33/200',target=target)
                row=result['markers'][0]
                self.assertEqual(row['preview_frame_index'],3)
                self.assertEqual(row['source_start'],'33/200')
                self.assertEqual(row['fixture_positions']['start_frame'],4)
                self.assertEqual(row['fixture_positions']['start_error_seconds'],'1/600')
                self.assertEqual(row['disposition'],'fixture_quantization_outside_video_coverage')
                self.assertEqual(result['actions'],[])

    def test_quantized_point_coverage_uses_inverse_nonzero_source_asset_map(self):
        result=self.plan('-67/200',shifted=True)
        row=result['markers'][0]
        self.assertEqual(row['preview_frame_index'],3)
        self.assertEqual(row['asset_local_start'],'433/200')
        self.assertEqual(row['fixture_positions']['start_frame'],104)
        self.assertEqual(row['disposition'],'fixture_quantization_outside_video_coverage')
        self.assertEqual(result['actions'],[])
        self.assertFalse(result['executable'])
        self.assertIsNone(row['host_frame_id'])

    def test_fcp_pair_is_atomic_when_outward_end_anchor_is_beyond_video(self):
        result=self.plan('7/50','4/25',target='final_cut_pro')
        row=result['markers'][0]
        self.assertEqual((row['fixture_positions']['start_frame'],row['fixture_positions']['end_frame']),(3,4))
        self.assertEqual((row['source_start'],row['source_end']),('7/50','4/25'))
        self.assertEqual(row['disposition'],'fixture_quantization_outside_video_coverage')
        self.assertEqual(result['actions'],[])

    def test_point_rounding_into_a_vfr_gap_abstains_without_timestamp_shift(self):
        result=self.plan('181/2000',frames=[(0,25),(54,1),(75,25)])
        row=result['markers'][0]
        self.assertEqual(row['preview_frame_index'],1)
        self.assertEqual(row['fixture_positions']['start_frame'],2)
        self.assertEqual(row['disposition'],'fixture_quantization_outside_video_coverage')
        self.assertEqual(row['source_start'],'181/2000')
        self.assertEqual(result['actions'],[])

    def test_fully_covered_fixture_points_are_still_descriptive_unverified_actions(self):
        for target in ('davinci_resolve','final_cut_pro'):
            with self.subTest(target=target):
                result=self.plan('1/8',target=target)
                self.assertEqual(len(result['actions']),1)
                self.assertEqual(result['actions'][0]['fixture_frame_id'],3)
                self.assertFalse(result['actions'][0]['executable'])
                self.assertEqual(result['native_contract_status'],'native_contract_unverified')
                self.assertIsNone(result['markers'][0]['host_frame_id'])


if __name__=='__main__':
    unittest.main()
