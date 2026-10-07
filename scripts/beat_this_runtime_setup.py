#!/usr/bin/env python3
"""Explicit isolated Beat This runtime for Linux CPU (flake ml shell torch); never acquires a model.

The runtime is a venv created from an already-installed ml-shell interpreter
(torch/torchaudio/numpy from nixpkgs, recorded as system site packages) plus
four hash-pinned wheels extracted offline by this script: beat-this, einops,
rotary-embedding-torch and soxr. ``--check`` is read-only. Setup refuses on any
non-Linux host. Contract: docs/spec/sprints/MODEL_LANES_S3.md section 3.3.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_NAME = 'beat-this-1.1.0-linux'
# The lock lives here because program/ is root-owned; root may move it later.
# Every URL/size/sha256 below was read from the PyPI JSON API on 2026-10-07.
LOCK = {
    'schema_version': 1,
    'runtime': RUNTIME_NAME,
    'platform': 'linux',
    'interpreter': 'flake ml shell python3 (nixpkgs 2c423e03bbafcff28bfadc6781a4a8257f205cb5: python 3.14.7, torch 2.12.0, torchaudio 2.11.0, numpy 2.5.1)',
    'system_site_packages': ['torch', 'torchaudio', 'numpy'],
    'packages': [
        {'name': 'beat-this', 'version': '1.1.0', 'machine': 'any',
         'filename': 'beat_this-1.1.0-py3-none-any.whl', 'bytes': 40060,
         'sha256': '3f2b2d1e027c6dac380bf80c71555e3c28a4036a7f1af20129a945915a72a645',
         'url': 'https://files.pythonhosted.org/packages/ce/0e/e23cbbe6e3efcd54e84dec22b6d88954655036a993cc3843ab741bc24de4/beat_this-1.1.0-py3-none-any.whl',
         'license': 'MIT'},
        {'name': 'einops', 'version': '0.8.0', 'machine': 'any',
         'filename': 'einops-0.8.0-py3-none-any.whl', 'bytes': 43223,
         'sha256': '9572fb63046264a862693b0a87088af3bdc8c068fde03de63453cbbde245465f',
         'url': 'https://files.pythonhosted.org/packages/44/5a/f0b9ad6c0a9017e62d4735daaeb11ba3b6c009d69a26141b258cd37b5588/einops-0.8.0-py3-none-any.whl',
         'license': 'MIT'},
        {'name': 'rotary-embedding-torch', 'version': '0.6.4', 'machine': 'any',
         'filename': 'rotary_embedding_torch-0.6.4-py3-none-any.whl', 'bytes': 5366,
         'sha256': 'ad51d8a4a43a3c9ff78b70da49e7f5c267b92eca44553dd83f7ccfe456a80147',
         'url': 'https://files.pythonhosted.org/packages/20/65/4d3e6e5f30023924b7dce78d457b0e1a6550980be397c0dc136d2ebdc03a/rotary_embedding_torch-0.6.4-py3-none-any.whl',
         'license': 'MIT'},
        {'name': 'soxr', 'version': '1.1.0', 'machine': 'x86_64',
         'filename': 'soxr-1.1.0-cp312-abi3-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl', 'bytes': 240413,
         'sha256': '3b033078e86f3c4a658e5697fac8995764fad9e799563616b630136b613167f1',
         'url': 'https://files.pythonhosted.org/packages/5c/f1/0e55195893228609c9a08c3b13b7a83a46c3a992cd00d3304f0f320cfb07/soxr-1.1.0-cp312-abi3-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl',
         'license': 'LGPL-2.1-or-later'},
        {'name': 'soxr', 'version': '1.1.0', 'machine': 'aarch64',
         'filename': 'soxr-1.1.0-cp312-abi3-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl', 'bytes': 206529,
         'sha256': 'bf98c0d7b7d5ef5bf072fee8d3020e8b664f2d195933ea7bc5089267c2e22a06',
         'url': 'https://files.pythonhosted.org/packages/88/2b/2e5eba817a762a2ec589ff165b8bc5955b25a0ad140045f7cd8e45410543/soxr-1.1.0-cp312-abi3-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl',
         'license': 'LGPL-2.1-or-later'},
    ],
}
LOCK_SHA = '5cd29f827825973ad0dd30391919382449b807be4a4b87251d010313ec78d593'
IMPORT_NAMES = {'beat-this': 'beat_this', 'einops': 'einops', 'rotary-embedding-torch': 'rotary_embedding_torch', 'soxr': 'soxr'}
ALLOWED_HOSTS = ('files.pythonhosted.org',)
LIMITS = {'wheel_bytes': 4 * 1024**2, 'all_wheel_bytes': 8 * 1024**2, 'uncompressed_bytes': 32 * 1024**2,
          'members': 2000, 'disk_bytes': 64 * 1024**2, 'deadline_seconds': 600, 'probe_timeout_seconds': 60}


class Refused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def refusal(code: str, message: str) -> dict:
    return {'schema_version': 1, 'status': 'refused', 'refusal_code': code, 'message': message,
            'model_acquired': False, 'network_used': False}


def canonical_lock_bytes(lock: dict = LOCK) -> bytes:
    return json.dumps(lock, sort_keys=True, separators=(',', ':')).encode()


def lock_sha256(lock: dict = LOCK) -> str:
    return hashlib.sha256(canonical_lock_bytes(lock)).hexdigest()


def verified_lock(lock: dict = LOCK, expected: str | None = None) -> dict:
    """Self-hash check of the embedded lock, then structural validation."""
    expected = LOCK_SHA if expected is None else expected
    if lock_sha256(lock) != expected:
        raise Refused('lock_identity_mismatch', 'Embedded Beat This wheel lock failed its self-hash check')
    if lock.get('schema_version') != 1 or lock.get('platform') != 'linux':
        raise Refused('lock_identity_mismatch', 'Unsupported lock schema/platform')
    total = 0
    for package in lock['packages']:
        url = urllib.parse.urlparse(package['url'])
        if (url.scheme != 'https' or url.hostname not in ALLOWED_HOSTS or url.username or url.password
                or Path(package['filename']).name != package['filename'] or not package['filename'].endswith('.whl')
                or not isinstance(package['bytes'], int) or isinstance(package['bytes'], bool)
                or not 0 < package['bytes'] <= LIMITS['wheel_bytes'] or len(package['sha256']) != 64):
            raise Refused('lock_identity_mismatch', 'Invalid locked wheel entry: ' + package['filename'])
        total += package['bytes']
    if total > LIMITS['all_wheel_bytes']:
        raise Refused('lock_identity_mismatch', 'Locked wheel byte budget exceeded')
    return lock


def require_linux(system: str | None = None) -> None:
    system = sys.platform if system is None else system
    if not system.startswith('linux'):
        raise Refused('platform_unsupported', 'Beat This runtime is qualified only for Linux CPU (honey via the flake ml shell); no platform fallback')


def selected_packages(lock: dict, machine: str | None = None) -> list[dict]:
    machine = platform.machine() if machine is None else machine
    chosen = [p for p in lock['packages'] if p['machine'] in ('any', machine)]
    if sorted({p['name'] for p in chosen}) != sorted(IMPORT_NAMES) or len(chosen) != len(IMPORT_NAMES):
        raise Refused('platform_unsupported', f'No locked wheel set for machine {machine!r}')
    return chosen


def runtime_path(root: Path = ROOT) -> Path:
    return root / 'artifacts' / 'model-runtime-env' / RUNTIME_NAME


def digest(path: Path) -> str:
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def safe_ancestors(path: Path, root: Path = ROOT) -> None:
    raw = Path(path)
    if '..' in raw.parts:
        raise Refused('runtime_path_rejected', 'Runtime path must not contain traversal components')
    absolute = raw.absolute()
    if not absolute.is_relative_to(root):
        raise Refused('runtime_path_rejected', 'Runtime path must stay beneath the checkout')
    for item in (absolute, *absolute.parents):
        if item.is_symlink():
            raise Refused('runtime_path_rejected', 'Runtime path ancestors must not be symlinks')
        if item == root:
            break


def wheel_members(wheels: Path, packages: list[dict]) -> list[dict]:
    """Verify wheel bytes and inventories before any extraction."""
    result, total, count = [], 0, 0
    for package in packages:
        path = wheels / package['filename']
        if path.is_symlink() or not path.is_file() or path.stat().st_size != package['bytes'] or digest(path) != package['sha256']:
            raise Refused('runtime_not_qualified', 'Wheel checksum/extent mismatch: ' + package['filename'])
        with zipfile.ZipFile(path) as archive:
            names = set()
            for item in archive.infolist():
                member = PurePosixPath(item.filename)
                kind = stat.S_IFMT(item.external_attr >> 16)
                count += 1
                total += item.file_size
                if count > LIMITS['members'] or total > LIMITS['uncompressed_bytes']:
                    raise Refused('runtime_not_qualified', 'Wheel inventory budget exceeded')
                if (item.filename in names or member.is_absolute() or '..' in member.parts or '\\' in item.filename
                        or not member.parts or any(':' in part for part in member.parts) or item.flag_bits & 1
                        or kind not in (0, stat.S_IFREG, stat.S_IFDIR) or any(part.endswith('.data') for part in member.parts)):
                    raise Refused('runtime_not_qualified', 'Unsafe or unsupported wheel member: ' + item.filename)
                names.add(item.filename)
                if item.is_dir():
                    continue
                result.append({'package': package['name'], 'wheel': package['filename'], 'member': item.filename,
                               'bytes': item.file_size, 'sha256': hashlib.sha256(archive.read(item)).hexdigest()})
    return result


PROBE = """import json,sys,sysconfig,platform
print(json.dumps({'python':platform.python_version(),'implementation':sys.implementation.name,'prefix':sys.prefix,
 'site':sysconfig.get_paths()['purelib'],'free_threaded':bool(sysconfig.get_config_var('Py_GIL_DISABLED')),
 'platform':sys.platform,'machine':platform.machine()}))"""

IMPORTS = """import json,importlib.metadata as m,torch,torchaudio,numpy,einops,rotary_embedding_torch,soxr,beat_this.inference
print(json.dumps({'torch':torch.__version__,'torchaudio':torchaudio.__version__,'numpy':numpy.__version__,
 'beat-this':m.version('beat-this'),'einops':m.version('einops'),'rotary-embedding-torch':m.version('rotary-embedding-torch'),
 'soxr':m.version('soxr'),'beat_this_file':beat_this.inference.__file__}))"""


def bounded_run(command: list[str], timeout: float) -> str:
    env = {**os.environ, 'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2',
           'PYTHONDONTWRITEBYTECODE': '1', 'HTTP_PROXY': 'http://127.0.0.1:9', 'HTTPS_PROXY': 'http://127.0.0.1:9',
           'http_proxy': 'http://127.0.0.1:9', 'https_proxy': 'http://127.0.0.1:9', 'NO_PROXY': '', 'no_proxy': ''}
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout, env=env)
    if len(result.stdout) > 65536:
        raise Refused('runtime_not_qualified', 'Oversized interpreter output')
    return result.stdout


def probe(interpreter: Path) -> dict:
    info = json.loads(bounded_run([str(interpreter), '-B', '-c', PROBE], LIMITS['probe_timeout_seconds']))
    if info['implementation'] != 'cpython' or info['free_threaded'] or not info['platform'].startswith('linux'):
        raise Refused('runtime_not_qualified', 'Provide the existing non-free-threaded CPython of the flake ml shell on Linux')
    return info


def check(root: Path = ROOT, lock: dict = LOCK, system: str | None = None, machine: str | None = None) -> dict:
    """Read-only: no download, no install, no directory creation, no model access."""
    verified_lock(lock)
    require_linux(system)
    packages = selected_packages(lock, machine)
    base = runtime_path(root)
    safe_ancestors(base, root)
    if not base.is_dir():
        raise Refused('runtime_missing', 'Beat This runtime missing; root runs explicit beat-this-runtime-setup with the ml-shell python')
    copied = base / 'wheel-lock.json'
    if copied.is_symlink() or not copied.is_file() or hashlib.sha256(copied.read_bytes()).hexdigest() != lock_sha256(lock):
        raise Refused('runtime_not_qualified', 'Runtime copied wheel lock mismatch')
    interpreter = base / 'python' / 'bin' / 'python'
    info = probe(interpreter)
    if Path(info['prefix']).absolute() != (base / 'python').absolute():
        raise Refused('runtime_not_qualified', 'Venv launcher bypassed the isolated prefix')
    site = Path(info['site']).absolute()
    if not site.is_relative_to(base / 'python'):
        raise Refused('runtime_not_qualified', 'Runtime site-packages outside the isolated environment')
    config = (base / 'python' / 'pyvenv.cfg').read_text().lower()
    system_site = 'include-system-site-packages = true' in config
    if not system_site:
        raise Refused('runtime_not_qualified', 'Runtime must see the ml-shell torch through system site packages')
    expected = wheel_members(base / 'wheels', packages)
    for item in expected:
        installed = site / item['member']
        safe_ancestors(installed, root)
        if not installed.is_file() or installed.stat().st_size != item['bytes'] or digest(installed) != item['sha256']:
            raise Refused('runtime_not_qualified', 'Installed wheel member mismatch: ' + item['member'])
    versions = json.loads(bounded_run([str(interpreter), '-B', '-c', IMPORTS], LIMITS['probe_timeout_seconds']))
    for package in packages:
        if versions.get(package['name']) != package['version']:
            raise Refused('runtime_not_qualified', f"Imported {package['name']} version mismatch")
    if not Path(versions['beat_this_file']).absolute().is_relative_to(site):
        raise Refused('runtime_not_qualified', 'beat_this imported from outside the isolated site-packages')
    disk = sum(p.stat().st_size for p in base.rglob('*') if not p.is_symlink() and p.is_file())
    return {'schema_version': 1, 'status': 'already_qualified', 'runtime_dir': str(base), 'lock_sha256': lock_sha256(lock),
            'python': info['python'], 'machine': info['machine'], 'versions': {k: v for k, v in versions.items() if k != 'beat_this_file'},
            'include_system_site_packages': True,
            'system_site_packages_role': 'ml-shell torch/torchaudio/numpy only; recorded explicitly, not hash-pinned by this lock',
            'installed_member_count': len(expected), 'disk_bytes': disk,
            'model_acquired': False, 'inference_performed': False, 'network_used': False}


def official_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if (parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password
            or parsed.port not in (None, 443)):
        raise Refused('fetch_rejected', 'Wheel URL/redirect outside the official HTTPS host')


class OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        official_url(newurl)  # Reject BEFORE urllib dispatches the next request.
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch(package: dict, destination: Path, deadline: float) -> None:
    if destination.exists() or destination.is_symlink():
        raise Refused('fetch_rejected', 'Existing wheel destination must not be replaced')
    official_url(package['url'])
    temporary = destination.with_suffix(destination.suffix + '.partial')
    hasher, size = hashlib.sha256(), 0
    request = urllib.request.Request(package['url'], headers={'User-Agent': 'video-utils-beat-this-runtime-setup/1'})
    opener = urllib.request.build_opener(OfficialRedirectHandler())
    with opener.open(request, timeout=min(30, max(.001, deadline - time.monotonic()))) as response:
        official_url(response.geturl())
        with temporary.open('xb') as output:
            while chunk := response.read(1024**2):
                if time.monotonic() > deadline:
                    raise Refused('fetch_rejected', 'Setup download deadline exceeded')
                size += len(chunk)
                if size > package['bytes']:
                    raise Refused('fetch_rejected', 'Downloaded wheel exceeds locked extent')
                hasher.update(chunk)
                output.write(chunk)
    if size != package['bytes'] or hasher.hexdigest() != package['sha256']:
        temporary.unlink(missing_ok=True)
        raise Refused('fetch_rejected', 'Downloaded wheel checksum mismatch')
    temporary.chmod(0o600)
    os.link(temporary, destination)
    temporary.unlink()


def extract(wheels: Path, packages: list[dict], site: Path, members: list[dict]) -> None:
    """Offline --no-deps install by verified extraction (pure/abi3 wheels without .data)."""
    by_wheel = {}
    for item in members:
        by_wheel.setdefault(item['wheel'], []).append(item)
    for package in packages:
        with zipfile.ZipFile(wheels / package['filename']) as archive:
            for item in by_wheel.get(package['filename'], []):
                target = site / item['member']
                if target.exists():
                    raise Refused('runtime_not_qualified', 'Refusing to overwrite installed member: ' + item['member'])
                target.parent.mkdir(parents=True, exist_ok=True)
                data = archive.read(item['member'])
                if hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise Refused('runtime_not_qualified', 'Member changed during extraction: ' + item['member'])
                with target.open('xb') as output:
                    output.write(data)


def setup(python_path: Path | None, root: Path = ROOT, lock: dict = LOCK) -> dict:
    started = time.monotonic()
    deadline = started + LIMITS['deadline_seconds']
    verified_lock(lock)
    require_linux()
    packages = selected_packages(lock)
    base = runtime_path(root)
    safe_ancestors(base, root)
    if base.exists():
        return check(root, lock)
    if python_path is None:
        raise Refused('interpreter_required', 'Explicit --python path to the existing flake ml-shell python is required; no interpreter download')
    executable = Path(python_path).expanduser().absolute()
    if not executable.is_file():
        raise Refused('interpreter_required', 'Explicit Python executable missing')
    probe(executable)
    base.parent.mkdir(parents=True, exist_ok=True)
    safe_ancestors(base, root)
    base.mkdir(mode=0o700)
    receipt = {'recorded_utc': datetime.now(timezone.utc).isoformat(), 'authority': 'explicit root runtime setup; R-HOOK-CONVERGENCE-20261004 R-N13',
               'status': 'started', 'lock_sha256': lock_sha256(lock), 'limits': LIMITS, 'model_acquired': False}
    try:
        (base / 'wheel-lock.json').write_bytes(canonical_lock_bytes(lock))
        wheels = base / 'wheels'
        wheels.mkdir(mode=0o700)
        for package in packages:
            fetch(package, wheels / package['filename'], deadline)
        members = wheel_members(wheels, packages)
        bounded_run([str(executable), '-B', '-m', 'venv', '--without-pip', '--system-site-packages', str(base / 'python')],
                    max(1, deadline - time.monotonic()))
        info = probe(base / 'python' / 'bin' / 'python')
        site = Path(info['site']).absolute()
        safe_ancestors(site, root)
        extract(wheels, packages, site, members)
        (base / 'installed-wheel-members.json').write_text(json.dumps({'schema_version': 1, 'lock_sha256': lock_sha256(lock), 'members': members}, indent=2) + '\n')
        report = check(root, lock)
        if time.monotonic() >= deadline:
            raise Refused('runtime_not_qualified', 'Overall setup deadline exceeded')
        report['status'] = 'runtime_dependencies_qualified'
        receipt.update(report)
        return report
    except Exception as exc:
        receipt.update(status='failure', error=str(exc))
        raise
    finally:
        receipt['elapsed_seconds'] = time.monotonic() - started
        (base / 'setup-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, help='existing flake ml-shell python (setup only)')
    parser.add_argument('--check', action='store_true', help='read-only verification; no download or install')
    parser.add_argument('--print-lock-sha256', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.print_lock_sha256:
        print(lock_sha256())
        return 0
    try:
        result = check() if args.check else setup(args.python)
        print(json.dumps(result))
        return 0
    except Refused as exc:
        print(json.dumps(refusal(exc.code, str(exc))))
        return 2
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print(json.dumps(refusal('runtime_not_qualified', str(exc))))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
