"""Source-only holdout reproduction without saved artifacts or audio generation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCES=("scripts/benchmark_holdout.py","scripts/benchmark.py","scripts/benchmark_bank.py",
         "program/benchmarks.json","program/benchmarks-v2.json","program/instrument.json",
         "tests/test_benchmark_holdout.py")
ADMITTED_SHA="495ad2f3f553b0bd7030ac797b6e8589f37748df657219c075d0fc4ce7491e74"


class HoldoutReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix="holdout-source-release-")
        # macOS /var can alias /private/var: artifact paths deliberately use
        # the canonical source root, preserving the worker's symlink rejection.
        self.checkout=(Path(self.temporary.name)/"source checkout").resolve()
        for name in SOURCES:
            target=self.checkout/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)
        self.script=self.checkout/"scripts/benchmark_holdout.py"

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self,*arguments):
        return subprocess.run([sys.executable,str(self.script),*map(str,arguments)],
                              cwd=self.temporary.name,capture_output=True,text=True,timeout=15)

    def test_checkout_without_artifacts_reconstructs_admitted_plan_and_safe_output(self):
        result=self.invoke("plan")
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout)
        raw=(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),ADMITTED_SHA)
        self.assertFalse((self.checkout/"artifacts").exists())
        path=self.checkout/"artifacts/benchmarks/portable output/plan.json"
        saved=self.invoke("plan","--output",path)
        self.assertEqual(saved.returncode,0,saved.stderr)
        before=path.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(),ADMITTED_SHA)
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        validated=self.invoke("validate",path)
        self.assertEqual(validated.returncode,0,validated.stderr)
        self.assertEqual(path.read_bytes(),before)
        self.assertFalse(json.loads(validated.stdout)["audio_generated"])
        self.assertEqual(list((self.checkout/"artifacts").rglob("*.wav")),[])
        overwritten=self.invoke("plan","--output",path)
        self.assertNotEqual(overwritten.returncode,0)
        self.assertEqual(path.read_bytes(),before)

    def test_existing_metadata_unit_test_runs_on_fresh_source_checkout(self):
        self.assertFalse((self.checkout/"artifacts").exists())
        result=subprocess.run([sys.executable,"-m","unittest","discover","-s",str(self.checkout/"tests"),
                               "-p","test_benchmark_holdout.py","-k","known_digest_integer","-v"],
                              cwd=self.temporary.name,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("Ran 1 test",result.stderr)
        self.assertEqual(list((self.checkout/"artifacts").rglob("*.wav")),[])


if __name__=="__main__":
    unittest.main()
