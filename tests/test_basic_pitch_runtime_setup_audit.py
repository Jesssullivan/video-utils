"""Independent confinement/no-overwrite fixtures; never contact the network."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import basic_pitch_runtime_setup as runtime


class Response(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url


class IndependentRuntimeSetupAuditTests(unittest.TestCase):
    def test_returned_lock_payload_always_matches_pinned_digest(self):
        payload, _ = runtime.locked_manifest()
        original_digest = runtime.digest
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / 'checkout'
            program = checkout / 'program'
            program.mkdir(parents=True)
            path = program / 'basic-pitch-runtime.json'
            path.write_bytes(payload)

            def mutate_after_path_hash(target):
                result = original_digest(target)
                if Path(target) == path:
                    # Same valid metadata, different exact bytes after the check.
                    path.write_bytes(payload + b' ')
                return result

            with patch.object(runtime, 'ROOT', checkout), \
                    patch.object(runtime, 'digest', side_effect=mutate_after_path_hash):
                try:
                    returned, _ = runtime.locked_manifest()
                except ValueError:
                    return
                self.assertEqual(hashlib.sha256(returned).hexdigest(), runtime.LOCK_SHA)

    def test_existing_wheel_destination_is_preserved(self):
        data = b'qualified'
        package = {'url': 'https://files.pythonhosted.org/wheel.whl',
                   'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        response = lambda *args, **kwargs: Response(data, package['url'])
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'wheel.whl'
            destination.write_bytes(b'operator-existing-wheel')
            with patch.object(runtime.urllib.request, 'urlopen', side_effect=response), \
                    patch.object(runtime.urllib.request, 'build_opener',
                                 return_value=SimpleNamespace(open=response)):
                with self.assertRaises((OSError, ValueError)):
                    runtime.fetch(package, destination, time.monotonic() + 5)
            self.assertEqual(destination.read_bytes(), b'operator-existing-wheel')

    def test_lexical_parent_traversal_cannot_escape_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / 'checkout'
            checkout.mkdir()
            with patch.object(runtime, 'ROOT', checkout):
                with self.assertRaises(ValueError):
                    runtime.safe_ancestors(checkout / '..' / 'outside')
            self.assertFalse((Path(temporary) / 'outside').exists())

    def test_redirects_are_rejected_before_forbidden_target_contact(self):
        data = b'qualified'
        package = {'url': 'https://files.pythonhosted.org/wheel.whl',
                   'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        for target in ('https://elsewhere.invalid/wheel.whl',
                       'http://files.pythonhosted.org/wheel.whl'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                contacts = []

                def default_urlopen(*args, **kwargs):
                    # Model urllib's automatic dispatch before final-URL checking.
                    contacts.append(target)
                    return Response(data, target)

                def build_opener(*handlers):
                    def open_request(request, *args, **kwargs):
                        for candidate in handlers:
                            handler = candidate() if isinstance(candidate, type) else candidate
                            if isinstance(handler, urllib.request.HTTPRedirectHandler):
                                handler.redirect_request(request, None, 302, 'Found',
                                                         {'Location': target}, target)
                        contacts.append(target)
                        return Response(data, target)
                    return SimpleNamespace(open=open_request)

                destination = Path(temporary) / 'wheel.whl'
                with patch.object(runtime.urllib.request, 'urlopen',
                                  side_effect=default_urlopen), \
                        patch.object(runtime.urllib.request, 'build_opener',
                                     side_effect=build_opener):
                    with self.assertRaises((OSError, ValueError)):
                        runtime.fetch(package, destination, time.monotonic() + 5)
                self.assertEqual(contacts, [], 'Forbidden redirect was contacted before rejection')
                self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
