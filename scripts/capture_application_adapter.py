#!/usr/bin/env python3
"""Application-only bounded supervision; ownership observation is not containment."""
from __future__ import annotations
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
MAX_RECEIPT = 64 * 1024
MAX_RESULT = 16 * 1024
MAX_TABLE = 1024 * 1024
MAX_IDENTITIES = 512
MAX_GROUPS = 128
RULE = 'R-N11/R-N12/R-N13; R-HOOK-CONVERGENCE-20261004'
QUALIFIED_WORKER_SHA256 = '790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584'


class AdapterError(RuntimeError):
    def __init__(self, message, receipt=None, diagnostic=None, *, finalized=False):
        super().__init__(message)
        self.receipt = receipt
        self.diagnostic = diagnostic
        self.finalized = finalized


class InspectionError(ValueError):
    pass


class BSDInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in ('flags','status','xstatus','pid','ppid','uid','gid','ruid','rgid','svuid','svgid','reserved')]
    _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
    _fields_ += [(name, ctypes.c_uint32) for name in ('nfiles','pgid','jobc','tdev','tpgid')]
    _fields_ += [('nice', ctypes.c_int32), ('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]


class ProcessInspector:
    """Native birth metadata plus a bounded portable process table."""
    def darwin_library(self):
        if not hasattr(self, '_library'):
            lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
            lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
            lib.proc_pidinfo.restype = ctypes.c_int
            lib.proc_listallpids.argtypes = [ctypes.c_void_p, ctypes.c_int]
            lib.proc_listallpids.restype = ctypes.c_int
            self._library = lib
        return self._library

    def identity(self, pid):
        try:
            if sys.platform.startswith('linux'):
                with open(f'/proc/{pid}/stat', 'rb') as handle: raw = handle.read(4097)
                if len(raw) > 4096: raise InspectionError('process stat exceeds bound')
                fields = raw.decode().rsplit(')', 1)[1].split()
                ppid, pgid, sid = map(int, fields[1:4])
                birth = ('linux_start_ticks', int(fields[19]))
                if birth[1] <= 0: raise InspectionError('invalid native birth token')
                state = fields[0]
            elif sys.platform == 'darwin':
                lib = self.darwin_library()
                info = BSDInfo()
                ctypes.set_errno(0)
                got = lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
                if got <= 0 and ctypes.get_errno() == errno.ESRCH: return None
                if got != ctypes.sizeof(info) or info.pid != pid: raise InspectionError('native process identity unavailable')
                ppid, pgid, sid = info.ppid, info.pgid, os.getsid(pid)
                birth = ('darwin_start_microseconds', info.start_sec, info.start_usec)
                if info.start_sec <= 0 or info.start_usec >= 1000000: raise InspectionError('invalid native birth token')
                state = 'Z' if info.status == 5 else '?'
            else:
                raise InspectionError('supported native process birth identity unavailable')
            if pgid != os.getpgid(pid) or sid != os.getsid(pid): raise InspectionError('process group/session changed during inspection')
            return {'pid': pid, 'ppid': ppid, 'pgid': pgid, 'sid': sid, 'birth': list(birth), 'state': state}
        except (FileNotFoundError, ProcessLookupError):
            return None
        except (OSError, ValueError, IndexError, UnicodeError) as exc:
            raise InspectionError(str(exc)) from exc

    def snapshot(self, end):
        end = min(end, time.monotonic() + 1.)
        remaining = end - time.monotonic()
        if remaining <= 0: raise InspectionError('inspection budget exhausted')
        if sys.platform == 'darwin':
            # Public libproc enumeration avoids spawning ps repeatedly under load.
            lib = self.darwin_library()
            pids = (ctypes.c_int * 8192)()
            count = lib.proc_listallpids(pids, ctypes.sizeof(pids))
            if count <= 0 or count >= 8192: raise InspectionError('native process row inventory unavailable or exceeds bound')
            rows = {}
            for pid in pids[:count]:
                if time.monotonic() >= end: raise InspectionError('native inspection deadline exceeded')
                if pid <= 0: continue
                info = BSDInfo(); ctypes.set_errno(0)
                got = lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
                if got <= 0 and ctypes.get_errno() == errno.ESRCH: continue
                if got != ctypes.sizeof(info) or info.pid != pid:
                    if ctypes.get_errno() not in (errno.EPERM, errno.EACCES):
                        raise InspectionError('native process table short or inconsistent identity')
                    # Protected unrelated processes remain visible to group checks;
                    # unavailable birth/ancestry can never establish ownership.
                    try: pgid = os.getpgid(pid)
                    except ProcessLookupError: continue
                    rows[pid] = {'pid':pid, 'ppid':-1, 'pgid':pgid, 'state':'?', 'identity_unavailable':True}
                    continue
                else:
                    rows[pid] = {'pid':pid, 'ppid':info.ppid, 'pgid':info.pgid, 'state':'Z' if info.status==5 else '?'}
            if time.monotonic() >= end or len(json.dumps(rows).encode()) > MAX_TABLE:
                raise InspectionError('native inspection deadline/byte bound exceeded')
            return rows
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                completed = subprocess.run(['/bin/ps', '-ax', '-o', 'pid=,ppid=,pgid=,stat='],
                    stdin=subprocess.DEVNULL, stdout=out, stderr=err, timeout=remaining, start_new_session=True)
            except (OSError, subprocess.TimeoutExpired) as exc: raise InspectionError('bounded process inspection failed') from exc
            if completed.returncode or out.tell() > MAX_TABLE or err.tell() > 16384:
                raise InspectionError('process table failed or exceeds bound')
            out.seek(0); lines = out.read(MAX_TABLE + 1).decode('utf-8', errors='strict').splitlines()
        if len(lines) > 8192: raise InspectionError('process row bound exceeded')
        rows = {}
        for line in lines:
            if time.monotonic() >= end: raise InspectionError('inspection parsing deadline exceeded')
            fields = line.split()
            if len(fields) != 4 or not all(x.isdigit() for x in fields[:3]): raise InspectionError('malformed process table')
            pid, ppid, pgid = map(int, fields[:3])
            rows[pid] = {'pid': pid, 'ppid': ppid, 'pgid': pgid, 'state': fields[3]}
        return rows


class Inventory:
    def __init__(self, inspector, root_identity):
        self.inspector, self.root_identity = inspector, root_identity
        observed = time.monotonic()
        root_identity = dict(root_identity, first_observed=observed, last_observed=observed, ancestry=[])
        self.root_identity = root_identity
        self.records = {root_identity['pid']: root_identity}
        self.groups = {(root_identity['pgid'], root_identity['sid'])}
        self.incomplete = False
        self.errors = []

    def issue(self, message):
        self.incomplete = True
        if len(self.errors) < 8: self.errors.append(str(message)[:300])

    def observe(self, rows, end):
        end = min(end, time.monotonic() + 1.)
        root = self.root_identity['pid']
        live = self.inspector.identity(root) if root in rows else None
        if live and live['birth'] != self.root_identity['birth']:
            self.issue('worker birth identity changed'); raise InspectionError('worker birth identity changed')
        reachable = {root} if live else set()
        attempted = set(reachable)
        for _ in range(64):
            found = [pid for pid, row in rows.items() if pid not in attempted and row['ppid'] in reachable]
            if not found: break
            for pid in found:
                attempted.add(pid)
                if time.monotonic() >= end: raise InspectionError('ownership observation budget exhausted')
                identity = self.inspector.identity(pid)
                if not identity: continue
                if identity['ppid'] != rows[pid]['ppid'] or identity['pgid'] != rows[pid]['pgid']:
                    self.issue('ancestry/group changed during observation'); continue
                parent = self.inspector.identity(identity['ppid'])
                recorded_parent = self.records.get(identity['ppid'])
                if not parent or not recorded_parent or parent['birth'] != recorded_parent['birth']:
                    self.issue('parent identity continuity unavailable'); continue
                if pid in self.records and self.records[pid]['birth'] != identity['birth']:
                    self.issue('PID reuse observed'); continue
                if len(self.records) >= MAX_IDENTITIES and pid not in self.records: raise InspectionError('identity bound exceeded')
                if (identity['pgid'], identity['sid']) not in self.groups and len(self.groups) >= MAX_GROUPS:
                    raise InspectionError('group bound exceeded')
                old = self.records.get(pid)
                identity['first_observed'] = old['first_observed'] if old and 'first_observed' in old else time.monotonic()
                identity['last_observed'] = time.monotonic()
                identity['ancestry_parent'] = identity['ppid']
                identity['ancestry'] = recorded_parent.get('ancestry', []) + [{'pid': parent['pid'], 'birth': parent['birth']}]
                self.records[pid] = identity; self.groups.add((identity['pgid'], identity['sid'])); reachable.add(pid)
        else:
            raise InspectionError('ancestry depth bound exceeded')
        if live:
            live.update(first_observed=self.root_identity['first_observed'], last_observed=time.monotonic(), ancestry=[])
            self.records[root] = live
        # Recheck the root after resolving parent chains; no names confer ownership.
        if live:
            final = self.inspector.identity(root)
            if final and final['birth'] != live['birth']: raise InspectionError('root identity changed during ancestry scan')

    def verified_groups(self, rows, end):
        end = min(end, time.monotonic() + 1.)
        verified, unknown = [], []
        for pgid, sid in sorted(self.groups):
            members = [row for row in rows.values() if row['pgid'] == pgid and not row['state'].startswith('Z')]
            if not members: continue
            identities = []
            for row in members:
                if time.monotonic() >= end: raise InspectionError('group verification budget exhausted')
                current = self.inspector.identity(row['pid']); old = self.records.get(row['pid'])
                if not current: continue
                if not old or current['birth'] != old['birth'] or current['pgid'] != pgid or current['sid'] != sid:
                    unknown.append(pgid); break
                identities.append(current)
            else:
                if identities: verified.append((pgid, sid, identities))
        return verified, unknown

    def unresolved_retained(self, end):
        for old in self.records.values():
            if time.monotonic() >= end: raise InspectionError('retained identity verification exhausted')
            current = self.inspector.identity(old['pid'])
            if not current or current['state'] == 'Z': continue
            if current['birth'] != old['birth']:
                self.issue('retained PID birth changed'); return True
            if current['pgid'] != old['pgid'] or current['sid'] != old['sid']:
                self.issue('retained identity moved session/group'); return True
            if old['pid'] != self.root_identity['pid']: return True
        return False


def finite_json(raw):
    from tool_api import strict_json
    result = strict_json(raw.decode('utf-8'))
    if not isinstance(result, dict): raise ValueError('application result must be one finite JSON object')
    return result


class ApplicationAdapter:
    """Private worker injection is for fixtures; MCP callers cannot choose code."""
    def __init__(self, root=ROOT, *, worker_path=None, inspector=None):
        self.root = Path(root)
        self.worker = Path(worker_path) if worker_path is not None else self.root / 'scripts/apply_capture_profile.py'
        self.fixture_worker = worker_path is not None
        self.inspector = inspector or ProcessInspector()
        self.deadline = None
        self.last_receipt = None

    def check_budget(self):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise AdapterError('supervision reporting budget exhausted', self.last_receipt)

    def receipt(self, directory, data):
        self.check_budget()
        data = dict(data)
        events = data.get('events', [])
        data['events'] = events[-8:]
        data['events_omitted'] = len(events) > 8
        raw = (json.dumps(data, sort_keys=True, allow_nan=False) + '\n').encode()
        if len(raw) > MAX_RECEIPT: raise AdapterError('supervision receipt exceeds bound')
        path = directory / 'receipt.json'; stage = directory / '.receipt.partial'
        self.check_budget(); stage.write_bytes(raw)
        self.check_budget(); stage.replace(path)
        self.last_receipt = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
        return self.last_receipt

    def inventory_receipt(self, directory, inventory, data):
        self.check_budget()
        payload = {'processes': list(inventory.records.values()), 'events': data['events'],
                   'incomplete': inventory.incomplete, 'errors': inventory.errors}
        raw = (json.dumps(payload, sort_keys=True, allow_nan=False) + '\n').encode()
        if len(raw) > 256 * 1024: raise AdapterError('inventory metadata exceeds bound')
        path = directory / 'inventory.json'; stage = directory / '.inventory.partial'
        self.check_budget(); stage.write_bytes(raw)
        self.check_budget(); stage.replace(path)
        data['inventory'] = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                             'process_count': len(inventory.records), 'incomplete': inventory.incomplete}

    def cleanup(self, process, inventory, end, events):
        """One absolute end covers freeze, all inspections, signals and root reap."""
        unknown = False
        try:
            if process.returncode is None:
                if time.monotonic() >= end: raise InspectionError('root freeze budget exhausted')
                os.kill(process.pid, signal.SIGSTOP)
                events.append({'target': 'owned_unreaped_root', 'pid': process.pid, 'signal': 'SIGSTOP'})
            phase_end = min(end, time.monotonic() + 1.)
            rows = self.inspector.snapshot(phase_end); inventory.observe(rows, phase_end)
            groups, rejected = inventory.verified_groups(rows, end)
            unknown = bool(rejected) or inventory.incomplete
            if rejected: events.append({'unverified_groups': rejected[:32], 'signals': []})
            # Deeper recorded ancestry first; always keep the owned root group last.
            groups.sort(key=lambda item: (item[0] == process.pid, -max(len(inventory.records[x['pid']].get('ancestry', [])) for x in item[2])))
            for pgid, sid, identities in groups:
                fresh = self.inspector.snapshot(end)
                checked, rejected = inventory.verified_groups(fresh, end)
                target = next((item for item in checked if item[0:2] == (pgid, sid)), None)
                if not target or pgid in rejected:
                    unknown = True; continue
                if time.monotonic() >= end:
                    unknown = True; break
                try: os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError: pass
                events.append({'pgid': pgid, 'sid': sid, 'pids': [x['pid'] for x in target[2]][:32], 'signal': 'SIGKILL', 'birth_checked': True})
        except (InspectionError, OSError, UnicodeError) as exc:
            inventory.issue(exc); unknown = True
        finally:
            if process.returncode is None:
                try:
                    if time.monotonic() < end: process.kill()
                except OSError as exc:
                    unknown = True; events.append({'target': 'owned_root', 'signal_error': str(exc)[:300]})
                finally:
                    try: process.wait(timeout=max(0., end - time.monotonic()))
                    except (subprocess.TimeoutExpired, OSError): unknown = True
        if time.monotonic() >= end: return 'unknown'
        try:
            rows = self.inspector.snapshot(end)
            groups, rejected = inventory.verified_groups(rows, end)
            if groups or rejected: return 'incomplete' if groups else 'unknown'
            if inventory.unresolved_retained(min(end, time.monotonic() + 1.)): return 'unknown'
        except (InspectionError, OSError, UnicodeError): return 'unknown'
        return 'unknown' if unknown else 'no_runnable_recorded_members'

    def run(self, arguments):
        allowed = {'input', 'authoring_dir', 'receipt_sha256', 'timeout_seconds'}
        if set(arguments) - allowed or not allowed - {'timeout_seconds'} <= set(arguments): raise ValueError('closed application arguments required')
        timeout = arguments.get('timeout_seconds', 600)
        if type(timeout) is not int or not 12 <= timeout <= 600: raise ValueError('outer timeout must be integer12..600')
        for field in ('input', 'authoring_dir'):
            if not isinstance(arguments[field], str) or not 1 <= len(arguments[field]) <= 4096: raise ValueError('bounded path required')
            if '\x00' in arguments[field]: raise ValueError('path cannot contain NUL')
        digest = arguments['receipt_sha256']
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest): raise ValueError('lowercase SHA256 required')
        if self.worker.is_symlink() or not self.worker.is_file() or self.worker.stat().st_size > 256 * 1024:
            raise AdapterError('bounded regular application worker unavailable')
        worker_sha = hashlib.sha256(self.worker.read_bytes()).hexdigest()
        if not self.fixture_worker and worker_sha != QUALIFIED_WORKER_SHA256:
            raise AdapterError('application worker differs from qualified source')
        parent = self.root / 'artifacts/application-supervision'
        if parent.is_symlink() or (parent.parent.is_symlink()): raise AdapterError('supervision parent cannot be symlinked')
        parent.mkdir(parents=True, exist_ok=True)
        directory = parent / uuid.uuid4().hex; directory.mkdir(mode=0o700)
        started = time.monotonic(); end = started + timeout; fallback = end - 5
        self.deadline = end; self.last_receipt = None
        data = {'schema_version': 1, 'actor': 'capture_application_adapter', 'ruling': RULE,
                'status': 'starting', 'candidate_publication': 'unknown', 'containment_scope': 'observed_owned_sessions_only',
                'input': arguments['input'], 'authoring_dir': arguments['authoring_dir'], 'authoring_receipt_sha256': digest,
                'outer_seconds': timeout, 'inner_seconds': timeout - 10, 'fallback_seconds': 5,
                'worker_sha256': worker_sha, 'events': []}
        self.receipt(directory, data)
        command = [os.environ.get('VIDEO_UTILS_PYTHON', sys.executable), str(self.worker), arguments['input'],
                   '--authoring-dir', arguments['authoring_dir'], '--receipt-sha256', digest, '--timeout-seconds', str(timeout - 10)]
        inventory = None; reason = None; cleanup_end = None
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                process = subprocess.Popen(command, cwd=self.root, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            except (OSError, ValueError, UnicodeError) as exc:
                data['status'] = 'launch_failed'; data['reason'] = str(exc)[:500]; data['descendant_cleanup'] = 'not_started'
                raise AdapterError('application worker could not start', self.receipt(directory, data)) from exc
            data['root_pid'] = process.pid
            try:
                root_identity = self.inspector.identity(process.pid)
                if root_identity is None: raise InspectionError('owned root identity unavailable')
                inventory = Inventory(self.inspector, root_identity); data['root_identity'] = root_identity
                self.receipt(directory, data)
                while time.monotonic() < fallback:
                    if out.tell() > MAX_RESULT or err.tell() > MAX_RESULT: reason = 'worker output exceeds16KiB'; break
                    if fallback - time.monotonic() < 1.1:
                        time.sleep(max(0., fallback - time.monotonic())); break
                    try:
                        phase_end = min(fallback, time.monotonic() + 1.)
                        rows = self.inspector.snapshot(phase_end); inventory.observe(rows, phase_end)
                    except (InspectionError, OSError, UnicodeError) as exc:
                        inventory.issue(exc); reason = 'inspection failure'; break
                    if process.poll() is not None:
                        groups, rejected = inventory.verified_groups(rows, fallback)
                        if groups or rejected or inventory.unresolved_retained(min(fallback, time.monotonic() + 1.)):
                            reason = 'worker exited with recorded descendants or identity uncertainty'; break
                        if inventory.incomplete: reason = 'incomplete ownership inventory'; break
                        break
                    time.sleep(min(.2, max(0., fallback - time.monotonic())))
                if process.returncode is None and reason is None:
                    process.poll()
                    if process.returncode is None: reason = 'outer fallback deadline'
                    else:
                        phase_end = min(end - .1, time.monotonic() + 1.)
                        rows = self.inspector.snapshot(phase_end); inventory.observe(rows, phase_end)
                        groups, rejected = inventory.verified_groups(rows, phase_end)
                        if groups or rejected or inventory.incomplete or inventory.unresolved_retained(phase_end):
                            reason = 'worker exited with recorded descendants or identity uncertainty'
                if reason:
                    cleanup_end = min(end - .1, time.monotonic() + 5)
                    data['descendant_cleanup'] = self.cleanup(process, inventory, cleanup_end, data['events'])
                    data['status'] = 'supervision_failed'; data['reason'] = reason
                    data['inventory_errors'] = inventory.errors
                    data['worker_returncode'] = process.returncode
                    self.inventory_receipt(directory, inventory, data)
                    reference = self.receipt(directory, data)
                    raise AdapterError(reason, reference, finalized=True)
                out.seek(0); raw = out.read(MAX_RESULT + 1); err.seek(0); tail = err.read(MAX_RESULT + 1)
                if len(raw) > MAX_RESULT or len(tail) > MAX_RESULT: raise AdapterError('bounded application output exceeded')
                result = finite_json(raw)
                if result.get('schema_version') != 1 or result.get('tool') != 'apply_capture_profile':
                    raise AdapterError('unexpected application worker result identity')
                if process.returncode == 0 and (result.get('status') != 'rendered_unreviewed' or result.get('dsp_performed') is not True or result.get('listening_accepted') is not False or result.get('master_adopted') is not False):
                    raise AdapterError('application success claim differs from contract')
                worker_result = directory / 'worker-result.json'
                self.check_budget(); worker_result.write_bytes(raw)
                data['worker_result'] = {'path': str(worker_result), 'sha256': hashlib.sha256(raw).hexdigest()}
                data['status'] = 'worker_completed' if process.returncode == 0 else 'worker_error'
                data['descendant_cleanup'] = 'no_runnable_recorded_members'; data['worker_returncode'] = process.returncode
                self.inventory_receipt(directory, inventory, data)
                reference = self.receipt(directory, data)
                if process.returncode: raise AdapterError('application worker returned a diagnostic', reference, result, finalized=True)
                result['supervision'] = {'receipt': reference, 'descendant_cleanup': data['descendant_cleanup'], 'containment_scope': data['containment_scope']}
                if len(json.dumps(result, allow_nan=False).encode()) > MAX_RESULT:
                    raise AdapterError('application result with supervision exceeds16KiB')
                return result
            except BaseException as exc:
                if isinstance(exc, AdapterError) and exc.finalized: raise
                if inventory is None:
                    if cleanup_end is None: cleanup_end = min(end - .1, time.monotonic() + 5)
                    try:
                        if time.monotonic() < cleanup_end: process.kill()
                    except OSError as signal_error:
                        data['events'].append({'target': 'owned_root', 'signal_error': str(signal_error)[:300]})
                    finally:
                        try: process.wait(timeout=max(0., cleanup_end - time.monotonic()))
                        except (subprocess.TimeoutExpired, OSError): pass
                    data['descendant_cleanup'] = 'unknown'
                else:
                    if cleanup_end is None: cleanup_end = min(end - .1, time.monotonic() + 5)
                    data['descendant_cleanup'] = self.cleanup(process, inventory, cleanup_end, data['events'])
                data['status'] = 'supervision_failed'; data['reason'] = str(exc)[:500]; data['worker_returncode'] = process.returncode
                try:
                    if inventory is not None: self.inventory_receipt(directory, inventory, data)
                    reference = self.receipt(directory, data)
                except (AdapterError, OSError, ValueError):
                    raise AdapterError('supervision interrupted; inspect last durable receipt; publication/cleanup unknown', self.last_receipt, finalized=True) from exc
                raise AdapterError(str(exc), reference, finalized=True) from exc
