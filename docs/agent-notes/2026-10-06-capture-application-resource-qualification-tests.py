"""Hash-closed reuse of the 14 inert native qualification definitions."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
OLD_HARNESS=HERE/'2026-10-06-capture-application-native-qualification.py'
OLD_TESTS=HERE/'2026-10-06-capture-application-native-qualification-tests.py'
NEW_HARNESS=HERE/'2026-10-06-capture-application-resource-qualification.py'
def sha(file):return hashlib.sha256(file.read_bytes()).hexdigest()
assert sha(OLD_HARNESS)=='c0268e80fdfb3ee17791534d078c0707f077c3ab0efac490fe2ee7bcc27142ee'
assert sha(OLD_TESTS)=='6e2b8248b857806def5573e45a0bb46cd83eccf740d3be18e7d6e268f952d9bb'
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
new=load('resource_qualification_harness',NEW_HARNESS)
original=load('immutable_native_test_definitions',OLD_TESTS)
original.h=new
NativeQualificationHarnessTests=original.NativeQualificationHarnessTests

class ResourceRevisionIdentityTests(unittest.TestCase):
    def test_only_application_pin_differs_from_original_controller(self):
        before=OLD_HARNESS.read_text()
        expected=before.replace("'application':'00a03ef9fad8543be4335cb5cbcd3c9d9580a6b40b8faeb826811b105fd5daa6'",
                                "'application':'"+new.PINS['application']+"'")
        self.assertEqual(NEW_HARNESS.read_text(),expected)

    def test_historical_helpers_and_plan_remain_exact(self):
        self.assertEqual(sha(OLD_HARNESS),'c0268e80fdfb3ee17791534d078c0707f077c3ab0efac490fe2ee7bcc27142ee')
        self.assertEqual(sha(OLD_TESTS),'6e2b8248b857806def5573e45a0bb46cd83eccf740d3be18e7d6e268f952d9bb')
        self.assertEqual(sha(new.PLAN),'f2aa237b4d7c0a34e93e5065e7436639a20311c7a81945de196c39c985ecd683')

if __name__=='__main__':unittest.main()
