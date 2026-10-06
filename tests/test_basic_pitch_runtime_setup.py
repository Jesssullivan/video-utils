from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import basic_pitch_runtime_setup as rt


def wheel(directory,member='sample.py',content=b'qualified',mode=None):
    path=directory/'sample.whl'
    with zipfile.ZipFile(path,'w') as archive:
        if mode is None:archive.writestr(member,content)
        else:
            info=zipfile.ZipInfo(member);info.external_attr=mode<<16;archive.writestr(info,content)
    package={'name':'fixture','filename':path.name,'bytes':path.stat().st_size,'sha256':rt.digest(path)}
    return path,{'packages':[package]}


class LockTests(unittest.TestCase):
    def test_committed_manifest_has_exact_qualified_hash(self):
        payload,lock=rt.locked_manifest()
        self.assertEqual(hashlib.sha256(payload).hexdigest(),rt.LOCK_SHA)
        self.assertEqual(len(lock['packages']),5)
        self.assertNotIn(b'/Users/',payload)
        self.assertEqual(sum(p['bytes'] for p in lock['packages']),34171831)

    def test_corrupt_lock_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'program').mkdir();(root/'program/basic-pitch-runtime.json').write_bytes(b'{}')
            with patch.object(rt,'ROOT',root),self.assertRaisesRegex(ValueError,'identity'):
                rt.locked_manifest()

    def test_unsupported_platform_before_acquisition(self):
        with patch.object(rt.sys,'platform','linux'),patch.object(rt,'fetch') as download:
            with self.assertRaisesRegex(ValueError,'native macOS arm64'):rt.setup(Path('/existing/python'))
            download.assert_not_called()

    def test_lexical_traversal_rejected_before_confinement(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(rt,'ROOT',Path(temp)):
            with self.assertRaisesRegex(ValueError,'traversal'):rt.safe_ancestors(Path(temp)/'../escape')

    def test_unsupported_macos_version(self):
        with patch.object(rt.sys,'platform','darwin'),patch.object(rt.platform,'machine',return_value='arm64'),patch.object(rt.platform,'mac_ver',return_value=('13.0',('','',''),'')):
            with self.assertRaisesRegex(ValueError,'macOS>=14'):rt.require_platform()

    def test_probe_rejects_wrong_python_and_free_threading(self):
        good={'python':'3.14.6','implementation':'cpython','free_threaded':False,'platform':'darwin','machine':'arm64','macos':'26.0','prefix':'/runtime/python','site':'/runtime/python/lib/python3.14/site-packages'}
        for key,value in [('python','3.12.1'),('free_threaded',True),('implementation','pypy'),('machine','x86_64')]:
            info={**good,key:value}
            result=subprocess.CompletedProcess([],0,json.dumps(info),'')
            with patch.object(rt.subprocess,'run',return_value=result),self.assertRaisesRegex(ValueError,'already-installed'):
                rt.probe(Path('/explicit/python'))

    def test_check_missing_is_readonly_and_does_not_download(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(rt,'ROOT',Path(temp)),patch.object(rt,'locked_manifest',return_value=(b'{}',{})),patch.object(rt,'require_platform'),patch.object(rt,'fetch') as fetch:
            with self.assertRaisesRegex(ValueError,'Optional runtime missing'):rt.setup(check_only=True)
            fetch.assert_not_called();self.assertEqual(list(Path(temp).iterdir()),[])

    def test_existing_incomplete_runtime_never_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);base=root/'artifacts/model-runtime-env/onnx-1.30.0-cp314';base.mkdir(parents=True);sentinel=base/'operator-file';sentinel.write_bytes(b'preserve')
            with patch.object(rt,'ROOT',root),patch.object(rt,'locked_manifest',return_value=(b'{}',{})),patch.object(rt,'require_platform'),patch.object(rt,'fetch') as fetch:
                with self.assertRaises(OSError):rt.setup(Path('/existing/python'))
                fetch.assert_not_called();self.assertEqual(sentinel.read_bytes(),b'preserve');self.assertEqual(list(base.iterdir()),[sentinel])

    def test_symlink_output_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'actual').mkdir();(root/'link').symlink_to(root/'actual',target_is_directory=True)
            with patch.object(rt,'ROOT',root),self.assertRaisesRegex(ValueError,'symlinks'):
                rt.safe_ancestors(root/'link/child')


class WheelTests(unittest.TestCase):
    def test_archive_hash_precedes_parse(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);wheelpath,lock=wheel(path);wheelpath.write_bytes(b'wrong')
            with patch.object(rt.zipfile,'ZipFile') as parser,self.assertRaisesRegex(ValueError,'checksum'):
                rt.wheel_members(path,lock)
            parser.assert_not_called()

    def test_destination_finalization_never_overwrites_existing_wheel(self):
        class Response(io.BytesIO):
            def geturl(self):return 'https://files.pythonhosted.org/wheel.whl'
        package={'url':'https://files.pythonhosted.org/wheel.whl','bytes':9,'sha256':hashlib.sha256(b'qualified').hexdigest()}
        with tempfile.TemporaryDirectory() as temp,patch.object(rt.urllib.request.OpenerDirector,'open',return_value=Response(b'qualified')):
            destination=Path(temp)/'wheel.whl';destination.write_bytes(b'operator-owned')
            with self.assertRaises(FileExistsError):rt.fetch(package,destination,time.monotonic()+5)
            self.assertEqual(destination.read_bytes(),b'operator-owned')

    def test_official_redirect_handler_rejects_before_dispatch(self):
        handler=rt.OfficialRedirectHandler();request=rt.urllib.request.Request('https://files.pythonhosted.org/wheel.whl')
        for target in ('https://elsewhere.invalid/wheel','http://files.pythonhosted.org/wheel'):
            with self.subTest(target=target),patch.object(rt.urllib.request.HTTPRedirectHandler,'redirect_request') as dispatch:
                with self.assertRaisesRegex(ValueError,'official HTTPS'):handler.redirect_request(request,None,302,'Found',{},target)
                dispatch.assert_not_called()

    def test_valid_member_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);wheelpath,lock=wheel(path)
            self.assertEqual(rt.wheel_members(path,lock),[{'package':'fixture','member':'sample.py','bytes':9,'sha256':hashlib.sha256(b'qualified').hexdigest()}])

    def test_rejects_traversal_absolute_and_data_relocation(self):
        for member in ('../escape','/absolute','pkg\\escape','pkg.data/purelib/module.py','pkg/drive:escape'):
            with self.subTest(member=member),tempfile.TemporaryDirectory() as temp:
                path=Path(temp);_,lock=wheel(path,member)
                with self.assertRaisesRegex(ValueError,'Unsafe'):rt.wheel_members(path,lock)

    def test_rejects_symlink_member(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);_,lock=wheel(path,mode=stat.S_IFLNK|0o777)
            with self.assertRaisesRegex(ValueError,'Unsafe'):rt.wheel_members(path,lock)

    def test_archive_inventory_bounds(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);_,lock=wheel(path)
            with patch.dict(rt.LIMITS,{'members':0}),self.assertRaisesRegex(ValueError,'inventory'):rt.wheel_members(path,lock)

    def test_download_exact_hash_and_extent(self):
        class Response(io.BytesIO):
            def geturl(self):return 'https://files.pythonhosted.org/wheel.whl'
        package={'url':'https://files.pythonhosted.org/wheel.whl','bytes':9,'sha256':hashlib.sha256(b'qualified').hexdigest()}
        with tempfile.TemporaryDirectory() as temp,patch.object(rt.urllib.request.OpenerDirector,'open',return_value=Response(b'qualified')):
            destination=Path(temp)/'wheel.whl';rt.fetch(package,destination,time.monotonic()+5);self.assertEqual(destination.read_bytes(),b'qualified')

    def test_wrong_download_hash_never_finalizes_wheel(self):
        class Response(io.BytesIO):
            def geturl(self):return 'https://files.pythonhosted.org/wheel.whl'
        package={'url':'https://files.pythonhosted.org/wheel.whl','bytes':5,'sha256':'a'*64}
        with tempfile.TemporaryDirectory() as temp,patch.object(rt.urllib.request.OpenerDirector,'open',return_value=Response(b'wrong')):
            destination=Path(temp)/'wheel.whl'
            with self.assertRaisesRegex(ValueError,'checksum'):rt.fetch(package,destination,time.monotonic()+5)
            self.assertFalse(destination.exists())

    def test_nonofficial_redirect_rejected(self):
        class Response(io.BytesIO):
            def geturl(self):return 'https://elsewhere.invalid/wheel.whl'
        with tempfile.TemporaryDirectory() as temp,patch.object(rt.urllib.request.OpenerDirector,'open',return_value=Response(b'wrong')):
            with self.assertRaisesRegex(ValueError,'official HTTPS'):rt.fetch({'url':'https://files.pythonhosted.org/wheel.whl'},Path(temp)/'wheel.whl',time.monotonic()+5)

    def test_deadline_cleanup_of_owned_setup_child(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            with self.assertRaisesRegex(ValueError,'deadline'):
                rt.run_owned([sys.executable,'-c','import time;time.sleep(10)'],base,'bounded',time.monotonic()+.1)
            receipt=json.loads((base/'bounded.resource.json').read_text());self.assertEqual(receipt['actor_pid'],os.getpid());self.assertEqual(receipt['stop_reason'],'deadline');self.assertIsNotNone(receipt['returncode'])


if __name__=='__main__':unittest.main()
