#!/usr/bin/env python3
"""Saved JSON/hash audit only, after the frozen order-null runner has completed."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def digest(path):
 with Path(path).open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
def read(path,expected=None):
 path=Path(path)
 if path.is_symlink() or not path.is_file() or path.stat().st_size>20_000_000:raise ValueError('Invalid saved JSON')
 if expected and digest(path)!=expected:raise ValueError('Saved JSON hash changed')
 return json.loads(path.read_text())
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-dir',type=Path,required=True);parser.add_argument('--bank-index',type=Path,required=True);args=parser.parse_args()
 base=args.run_dir.absolute();bank_path=args.bank_index.absolute();permitted=ROOT/'artifacts/experiments/phrase-window-ablation'
 if any('..' in path.parts or not path.is_relative_to(permitted) or any(p.is_symlink() for p in (path,*path.parents)) for path in (base,bank_path)):raise ValueError('Audit outside isolated roots')
 receipt=read(base/'run.json')
 if receipt['status']!='completed_isolated_order_null_measurements':raise ValueError('Do not inspect truth or quality until predictions/scoring completed')
 bank=read(bank_path,receipt['bank_index_sha256']);evaluation=read(base/'evaluation.json',receipt['evaluation_sha256'])
 hashes={'run.json':digest(base/'run.json'),'evaluation.json':digest(base/'evaluation.json')};rows=[];common=[];counts={}
 for case,row in zip(bank['cases'],receipt['cases']):
  prediction=read(base/row['result'],row['result_sha256']);hashes[row['result']]=row['result_sha256']
  for name,sha in row['artifact_hashes'].items():
   if digest(base/name)!=sha:raise ValueError('Analysis/cache artifact changed')
   hashes[name]=sha
  if digest(base/'inputs'/f"audio-{row['ordinal']:02d}.wav")!=row['source_sha256']:raise ValueError('Opaque source changed')
  if digest(bank_path.parent/case['source']['path'])!=row['source_sha256']:raise ValueError('Original generated source changed')
  score=next(s for s in evaluation['cases'] if s['id']==case['id'])
  dispositions={key:dict(Counter(audit[key+'_status'] for audit in prediction['audit'])) for key in ('control','order')}
  indexes={arm:{item['original_candidate_index'] for item in candidates} for arm,candidates in prediction['arms'].items()}
  control=indexes['Bcontrol'];order=indexes['Border'];shared=control&order
  rows.append({'id':case['id'],'seed':case['seed'],'cohort':case['cohort'],'proposal_count':len(prediction['proposal_universe']),
   'control_dispositions':dispositions['control'],'order_dispositions':dispositions['order'],
   'postcap_shared_proposal_indices':sorted(shared),'postcap_control_only_indices':sorted(control-order),
   'postcap_order_only_indices':sorted(order-control),'scores':score['scores']})
 for arm in ('Bcontrol','Border'):
  counts[arm]={}
  for i,threshold in enumerate((.5,.75)):
   metrics=[row['scores'][arm]['pair_metrics'][i] for row in evaluation['cases']]
   counts[arm][str(threshold)]={key:sum(v[key] for v in metrics) for key in ('tp','fp','fn')}
   for key,v in counts[arm][str(threshold)].items():
    if evaluation['aggregate']['all'][arm][i][key]!=v:raise ValueError('Aggregate does not reproduce saved case metrics')
 for item in evaluation['common_reference_endpoints']:
  common.append({**item,'common_reference_ids':['generated-repeat-1' for _ in item['common_reference_indices']],
   'lost_reference_ids':['generated-repeat-1' for _ in item['lost_reference_indices']],
   'gained_reference_ids':['generated-repeat-1' for _ in item['gained_reference_indices']]})
 snapshot={}
 for path,sha in receipt['copied_source_hashes'].items():
  if digest(base/path)!=sha:raise ValueError('Copied source changed')
  snapshot[path]=sha
 canonical={
 'docs/agent-notes/2026-10-06-phrase-order-null.py':receipt['runner_sha256'],
 'docs/agent-notes/2026-10-06-phrase-order-null-settings.json':receipt['settings_sha256'],
 'scripts/phrase_evaluate.py':receipt['evaluator_sha256'],
 'program/instrument.json':receipt['instrument_registry_sha256'],
 'scripts/guitar_features.py':'2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe',
 'scripts/rhythm.py':'264b723ca29e4731da0a12d5dce221e7826a38b67f848ce9f4ffcf8bfe4b35b9',
 'docs/agent-notes/2026-10-05-phrase-guarded-arms.py':'78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c'}
 for path,sha in canonical.items():
  if digest(ROOT/path)!=sha:raise ValueError('Canonical/source pin changed')
 output={'schema_version':1,'status':'owner_saved_json_hash_audit','quality_scope':'generator_only_not_musician',
  'bank_index_sha256':receipt['bank_index_sha256'],'artifact_hashes':hashes,'copied_source_hashes':snapshot,
  'current_canonical_source_hashes':canonical,'rows':rows,'recomputed_aggregate_counts':counts,'common_reference_endpoints':common,
  'all_result_files_older_than_evaluation':all((base/row['result']).stat().st_mtime_ns<(base/'evaluation.json').stat().st_mtime_ns for row in receipt['cases']),
  'ordering_claim_scope':'frozen runner branch ordering and timestamps; not adversarial attestation',
  'signal_receipts':receipt['signal_receipts'],'inference_reexecuted':False,'thresholds_changed':False,
  'performance_issue_confirmed':False,'canonical_defaults_activated':False,'independent_review':False}
 target=base/'result-disposition-audit.json'
 with target.open('x') as handle:handle.write(json.dumps(output,indent=2,allow_nan=False)+'\n')
 print(json.dumps({'receipt':str(target),'sha256':digest(target),'aggregate_counts':counts,'elapsed_seconds':receipt['elapsed_seconds']}))
if __name__=='__main__':main()
