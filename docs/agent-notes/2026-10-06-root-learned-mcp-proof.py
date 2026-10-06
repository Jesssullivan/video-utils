"""Collect an initialized tool-27 proof on already-frozen generated predictions.

This root evidence harness invokes metadata evaluation, never model inference.
Retain protocol bytes before assertions so a collector failure cannot erase them.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    nonce = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    proof = ROOT / 'artifacts/root-checkpoints' / ('learned-mcp-' + nonce)
    proof.mkdir(parents=True, exist_ok=False)
    output = ROOT / 'artifacts/benchmarks' / ('learned-actual-mcp-' + nonce)
    arguments = {
        'fixture_index': str(ROOT / 'artifacts/benchmarks/root-calibration-bank-20261005T2255/fixtures.json'),
        'pyin_pilot_index': str(ROOT / 'artifacts/benchmarks/root-calibration-pilot-20261005T2300/pitch-pilot-index.json'),
        'learned_pilot_index': str(ROOT / 'artifacts/benchmarks/learned-numerical-pilot-20261006T0131/learned-pilot-index.json'),
        'output': str(output),
    }
    messages = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-06-18', 'capabilities': {},
            'clientInfo': {'name': 'root-generated-pilot-proof', 'version': '1'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {
            'name': 'learned_pitch_evaluate', 'arguments': arguments}},
    ]
    wire = ''.join(json.dumps(row) + '\n' for row in messages)
    inputs = [Path(arguments[key]) for key in ('fixture_index', 'pyin_pilot_index', 'learned_pilot_index')]
    inputs += [ROOT / path for path in ('scripts/learned_pitch_evaluate.py', 'program/tools.json',
                                     'scripts/tool_api.py', 'artifacts/latest.json')]
    before = {str(path): digest(path) for path in inputs}
    (proof / 'mcp-request.jsonl').write_text(wire)
    started = time.monotonic()
    process = subprocess.run(['just', 'mcp'], input=wire, capture_output=True, text=True,
                             timeout=150, cwd=ROOT)
    (proof / 'mcp-response.jsonl').write_text(process.stdout)
    (proof / 'mcp-stderr.txt').write_text(process.stderr)
    assert process.returncode == 0 and not process.stderr.strip()
    responses = {row['id']: row for row in map(json.loads, process.stdout.splitlines())}
    assert len(responses[2]['result']['tools']) == 27
    call = responses[3]['result']
    assert not call.get('isError', False)
    wrapper = call['structuredContent']
    assert wrapper == json.loads(call['content'][0]['text'])
    assert wrapper['tool'] == 'learned_pitch_evaluate' and wrapper['status'] == 'completed'
    summary = wrapper['result']
    assert summary['hard_gates_passed'] and summary['case_count'] == 4 and summary['coverage_seconds'] == 30
    assert not summary['inference_invoked'] and not summary['real_performance_grading']
    assert summary['status'] == 'completed_with_regression_alerts'
    after = {str(path): digest(path) for path in inputs}
    assert before == after
    receipt = {
        'schema_version': 1, 'authority': 'Operator goal; AGENTS.md; R-HOOK-CONVERGENCE-20261004/R-N13',
        'observed_at': datetime.now(timezone.utc).isoformat(), 'tool_count': 27,
        'worker_sha256': before[str(ROOT / 'scripts/learned_pitch_evaluate.py')],
        'arguments': arguments, 'summary': summary, 'elapsed_seconds': time.monotonic() - started,
        'stdio_stderr_empty': True, 'input_hashes_preserved': True, 'before': before, 'after': after,
        'evaluation_sha256': digest(Path(summary['evaluation_json'])),
        'real_performance_grading': False, 'listening_accepted': False,
        'collector_correction': 'Earlier collector read wrapper fields as worker fields; pure evaluator completed. This proof retains wire bytes first.',
    }
    (proof / 'actual-mcp-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'proof_dir': str(proof), 'receipt_sha256': digest(proof / 'actual-mcp-receipt.json'),
                      'summary': summary, 'elapsed_seconds': receipt['elapsed_seconds']}, indent=2))


if __name__ == '__main__':
    main()
