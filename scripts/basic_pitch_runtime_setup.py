#!/usr/bin/env python3
"""Explicit optional native-wheel Basic Pitch runtime setup; never acquire models."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
LOCK_SHA='c0e0a0f01023d5e701c13bcd092d23ef216dd3e96b2bc0320293c355252df23f'
VERSIONS={'onnxruntime':'1.30.0','numpy':'2.5.3','flatbuffers':'25.12.19','packaging':'26.3','protobuf':'7.36.2'}
LIMITS={'wheel_bytes':32*1024**2,'all_wheel_bytes':64*1024**2,'uncompressed_bytes':150*1024**2,
        'members':4000,'disk_bytes':256*1024**2,'rss_bytes':1024**3,'deadline_seconds':600,'log_bytes':2*1024**2}


def digest(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def runtime_path():return ROOT/'artifacts/model-runtime-env/onnx-1.30.0-cp314'


def locked_manifest():
    path=ROOT/'program/basic-pitch-runtime.json'
    if path.is_symlink() or not path.is_file():raise ValueError('Committed runtime wheel lock failed identity check')
    with path.open('rb') as source:payload=source.read(32769)
    if len(payload)>32768 or hashlib.sha256(payload).hexdigest()!=LOCK_SHA:
        raise ValueError('Committed runtime wheel lock failed identity check')
    lock=json.loads(payload) # Hash the exact bounded bytes parsed and copied.
    packages=lock.get('packages',[])
    if lock.get('schema_version')!=1 or lock.get('python')!='3.14.6' or lock.get('platform')!='macos-arm64':
        raise ValueError('Unsupported runtime lock schema/platform')
    if len(packages)!=5 or {p['name']:p['version'] for p in packages}!=VERSIONS:
        raise ValueError('Runtime lock must contain exactly the five qualified packages')
    for p in packages:
        url=urllib.parse.urlparse(p['url'])
        if (url.scheme!='https' or url.hostname!='files.pythonhosted.org' or url.username or url.password
            or Path(p['filename']).name!=p['filename'] or not p['filename'].endswith('.whl')
            or not isinstance(p['bytes'],int) or isinstance(p['bytes'],bool) or not 0<p['bytes']<=LIMITS['wheel_bytes']):
            raise ValueError('Invalid qualified wheel entry')
    if sum(p['bytes'] for p in packages)>LIMITS['all_wheel_bytes']:raise ValueError('Wheel byte budget exceeded')
    return payload,lock


def require_platform():
    if sys.platform!='darwin' or platform.machine()!='arm64':
        raise ValueError('Optional runtime requires native macOS arm64; no platform fallback')
    try:major=int(platform.mac_ver()[0].split('.')[0])
    except ValueError:raise ValueError('Cannot identify macOS release')
    if major<14:raise ValueError('Optional ONNX Runtime wheel requires macOS>=14')


def safe_ancestors(path):
    raw=Path(path)
    if '..' in raw.parts:raise ValueError('Runtime output must not contain traversal components')
    path=raw.absolute()
    if not path.is_relative_to(ROOT):raise ValueError('Runtime output must stay beneath checkout')
    for p in (path,*path.parents):
        if p.is_symlink():raise ValueError('Runtime output ancestors must not be symlinks')
        if p==ROOT:break


def probe(interpreter):
    code="""import sys,sysconfig,platform,json
print(json.dumps({'python':platform.python_version(),'implementation':sys.implementation.name,'prefix':sys.prefix,'site':sysconfig.get_paths()['purelib'],'free_threaded':bool(sysconfig.get_config_var('Py_GIL_DISABLED')),'platform':sys.platform,'machine':platform.machine(),'macos':platform.mac_ver()[0]}))"""
    result=subprocess.run([str(interpreter),'-I','-B','-c',code],capture_output=True,text=True,check=True,timeout=30)
    if len(result.stdout)>32768:raise ValueError('Oversized interpreter probe')
    info=json.loads(result.stdout)
    if (info['python']!='3.14.6' or info['implementation']!='cpython' or info['free_threaded']
        or info['platform']!='darwin' or info['machine']!='arm64' or int(info['macos'].split('.')[0])<14):
        raise ValueError('Provide already-installed non-free-threaded CPython3.14.6 on native macOS>=14 arm64')
    return info


def wheel_members(wheels,lock):
    result=[];total=0;count=0
    for p in lock['packages']:
        path=wheels/p['filename']
        if path.is_symlink() or path.stat().st_size!=p['bytes'] or digest(path)!=p['sha256']:
            raise ValueError('Wheel checksum/extent mismatch: '+p['name'])
        with zipfile.ZipFile(path) as archive:
            names=set()
            for item in archive.infolist():
                member=PurePosixPath(item.filename);kind=stat.S_IFMT(item.external_attr>>16)
                count+=1;total+=item.file_size
                if count>LIMITS['members'] or total>LIMITS['uncompressed_bytes']:raise ValueError('Wheel extraction inventory budget exceeded')
                if (item.filename in names or member.is_absolute() or '..' in member.parts or '\\' in item.filename
                    or not member.parts or any(':' in part for part in member.parts) or item.flag_bits&1
                    or kind not in (0,stat.S_IFREG,stat.S_IFDIR) or any(part.endswith('.data') for part in member.parts)):
                    raise ValueError('Unsafe or unsupported wheel member: '+item.filename)
                names.add(item.filename)
                if item.is_dir() or item.filename.endswith('.dist-info/RECORD'):continue
                result.append({'package':p['name'],'member':item.filename,'bytes':item.file_size,
                    'sha256':hashlib.sha256(archive.read(item)).hexdigest()})
    return result


def checked_runtime(base,lock):
    safe_ancestors(base)
    copied=base/'wheel-manifest-before-install.json'
    if copied.is_symlink() or digest(copied)!=LOCK_SHA:raise ValueError('Runtime copied wheel lock mismatch')
    for p in (base/'wheels',base/'python',base/'python/lib'):
        safe_ancestors(p)
    info=probe(base/'python/bin/python') # Keep the lexical venv launcher.
    if Path(info['prefix']).absolute()!=(base/'python').absolute():raise ValueError('Venv launcher bypassed isolated prefix')
    site=Path(info['site']).absolute()
    if not site.is_relative_to(base/'python'):raise ValueError('Runtime site-packages outside isolated environment')
    safe_ancestors(site)
    config=(base/'python/pyvenv.cfg').read_text().lower()
    if 'include-system-site-packages = false' not in config:raise ValueError('Runtime must exclude system packages')
    expected=wheel_members(base/'wheels',lock)
    for item in expected:
        installed=site/item['member'];safe_ancestors(installed)
        if not installed.is_file() or installed.stat().st_size!=item['bytes'] or digest(installed)!=item['sha256']:
            raise ValueError('Installed wheel member mismatch: '+item['member'])
    code="""import json,importlib.metadata,numpy,onnxruntime
names=('onnxruntime','numpy','flatbuffers','packaging','protobuf')
print(json.dumps({name:importlib.metadata.version(name) for name in names}))"""
    env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','MKL_NUM_THREADS':'2','PYTHONDONTWRITEBYTECODE':'1'}
    imports=subprocess.run([str(base/'python/bin/python'),'-I','-B','-c',code],capture_output=True,text=True,check=True,timeout=30,env=env)
    if len(imports.stdout)>32768 or json.loads(imports.stdout)!=VERSIONS:raise ValueError('Runtime imported version mismatch')
    disk=sum(p.stat().st_size for p in base.rglob('*') if not p.is_symlink() and p.is_file())
    if disk>LIMITS['disk_bytes']:raise ValueError('Runtime disk budget exceeded')
    return {'status':'already_qualified','runtime_dir':str(base),'wheel_lock_sha256':LOCK_SHA,
            'python':info['python'],'versions':VERSIONS,'installed_member_count':len(expected),'disk_bytes':disk,
            'model_acquired':False,'inference_performed':False},expected


def official_url(url):
    parsed=urllib.parse.urlparse(url)
    if (parsed.scheme!='https' or parsed.hostname!='files.pythonhosted.org'
        or parsed.username or parsed.password or parsed.port not in (None,443)):
        raise ValueError('Wheel URL/redirect outside official HTTPS host')


class OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        official_url(newurl) # Reject BEFORE urllib dispatches the next request.
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def fetch(package,destination,deadline):
    if destination.exists() or destination.is_symlink():raise FileExistsError('Existing wheel destination must not be replaced')
    if time.monotonic()>=deadline:raise ValueError('Setup deadline exceeded before download')
    temporary=destination.with_suffix(destination.suffix+'.partial')
    hasher=hashlib.sha256();size=0
    official_url(package['url'])
    request=urllib.request.Request(package['url'],headers={'User-Agent':'video-utils-explicit-runtime-setup/1'})
    opener=urllib.request.build_opener(OfficialRedirectHandler())
    with opener.open(request,timeout=min(30,max(.001,deadline-time.monotonic()))) as response:
        official_url(response.geturl())
        with temporary.open('xb') as output:
            while chunk:=response.read(1024**2):
                if time.monotonic()>deadline:raise ValueError('Setup download deadline exceeded')
                size+=len(chunk)
                if size>package['bytes']:raise ValueError('Downloaded wheel exceeds locked extent')
                hasher.update(chunk);output.write(chunk)
    if size!=package['bytes'] or hasher.hexdigest()!=package['sha256']:raise ValueError('Downloaded wheel checksum mismatch')
    temporary.chmod(0o600)
    os.link(temporary,destination) # Atomic no-overwrite finalization, same directory.
    temporary.unlink()


def run_owned(command,base,job,deadline):
    peak=0;stopped=None
    env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','MKL_NUM_THREADS':'2','UV_CONCURRENT_INSTALLS':'1','PYTHONDONTWRITEBYTECODE':'1'}
    with (base/(job+'.stdout.log')).open('xb') as stdout,(base/(job+'.stderr.log')).open('xb') as stderr:
        process=subprocess.Popen(command,stdout=stdout,stderr=stderr,env=env)
        try:
            while process.poll() is None:
                state=subprocess.run(['ps','-p',str(process.pid),'-o','ppid=,rss='],capture_output=True,text=True,timeout=5).stdout.split()
                if len(state)==2:
                    if int(state[0])!=os.getpid():raise ValueError('Setup subprocess ownership mismatch')
                    peak=max(peak,int(state[1])*1024)
                if peak>LIMITS['rss_bytes'] or time.monotonic()>=deadline:
                    stopped='rss_bound' if peak>LIMITS['rss_bytes'] else 'deadline';break
                if stdout.tell()+stderr.tell()>LIMITS['log_bytes']:stopped='log_byte_bound';break
                time.sleep(.1)
        except Exception as exc:stopped=str(exc)
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
            else:process.wait(timeout=3)
    receipt={'actor_pid':os.getpid(),'target_pid':process.pid,'ownership':'Popen direct child checked by PPID','ruling':'R-N11','argv':command,'returncode':process.returncode,'stop_reason':stopped,'observed_peak_rss_bytes':peak}
    (base/(job+'.resource.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    if stopped or process.returncode:raise ValueError('Explicit runtime setup subprocess failed: '+str(stopped or process.returncode))
    return receipt


def setup(python_path=None,check_only=False):
    started=time.monotonic();deadline=started+LIMITS['deadline_seconds']
    payload,lock=locked_manifest();require_platform();base=runtime_path();safe_ancestors(base)
    if base.exists():return checked_runtime(base,lock)[0]
    if check_only:raise ValueError('Optional runtime missing; run explicit basic-pitch-runtime-setup with already-installed CPython3.14.6')
    if python_path is None:raise ValueError('Explicit --python path to existing CPython3.14.6 required; no interpreter download')
    executable=Path(python_path).expanduser().absolute()
    if not executable.is_file():raise ValueError('Explicit Python executable missing')
    probe(executable)
    uv=shutil.which('uv')
    if not uv:raise ValueError('Existing uv executable required; setup does not install uv')
    uv_version=subprocess.run([uv,'--version'],capture_output=True,text=True,check=True,timeout=30).stdout.strip()
    base.parent.mkdir(parents=True,exist_ok=True);safe_ancestors(base);base.mkdir(mode=0o700)
    receipt={'recorded_utc':datetime.now(timezone.utc).isoformat(),'authority':'explicit operator runtime setup; R-HOOK-CONVERGENCE-20261004/R-N13','status':'started','wheel_lock_sha256':LOCK_SHA,'uv_version':uv_version,'jobs':[],'limits':LIMITS}
    try:
        (base/'wheel-manifest-before-install.json').write_bytes(payload)
        wheels=base/'wheels';wheels.mkdir(mode=0o700)
        for package in lock['packages']:fetch(package,wheels/package['filename'],deadline)
        members=wheel_members(wheels,lock) # Verify bytes and safe inventories BEFORE installing.
        receipt['jobs'].append(run_owned([str(executable),'-I','-B','-m','venv','--without-pip',str(base/'python')],base,'create-venv',deadline))
        command=[uv,'--no-config','--no-cache','pip','install','--python',str(base/'python/bin/python'),'--offline','--no-index','--no-deps','--no-build','--no-python-downloads',*[str(wheels/p['filename']) for p in lock['packages']]]
        receipt['jobs'].append(run_owned(command,base,'install-wheels',deadline))
        report,installed=checked_runtime(base,lock)
        if installed!=members:raise ValueError('Installed manifest differs from verified archives')
        (base/'installed-wheel-members.json').write_text(json.dumps({'schema_version':1,'wheel_lock_sha256':LOCK_SHA,'members':members},indent=2)+'\n')
        if time.monotonic()>=deadline:raise ValueError('Overall setup deadline exceeded')
        report['status']='runtime_dependencies_qualified';receipt.update(report);return report
    except Exception as exc:
        receipt.update(status='failure',error=str(exc));raise
    finally:
        receipt['elapsed_seconds']=time.monotonic()-started
        (base/'setup-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--python',type=Path);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    try:print(json.dumps(setup(args.python,args.check)));return 0
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError,zipfile.BadZipFile) as exc:
        print('basic pitch runtime setup: '+str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
