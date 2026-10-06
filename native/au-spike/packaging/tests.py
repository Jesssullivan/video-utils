#!/usr/bin/env python3
"""Adversarial packaging contract checks; no compilers or bundles invoked."""
import copy
import json
from pathlib import Path
import unittest

import build


class PackagingContract(unittest.TestCase):
    def setUp(self):
        self.targets = json.loads((Path(__file__).parent / "targets.json").read_text())

    def test_reviewed_identity_and_no_ui_metadata(self):
        app, extension = build.metadata(build.validate_targets(self.targets))
        self.assertEqual(app["CFBundlePackageType"], "APPL")
        self.assertEqual(extension["CFBundlePackageType"], "XPC!")
        self.assertNotIn("NSExtensionMainStoryboard", extension["NSExtension"])
        self.assertEqual(len(extension["NSExtension"]["NSExtensionAttributes"]["AudioComponents"]), 1)

    def test_path_escape_and_identity_drift_reject(self):
        for target, key, bad in [("extension", "bundle", "../../Other.appex"),
                ("container", "executable", "/usr/bin/open"), ("extension", "identifier", "org.other.extension"),
                ("extension", "point", "com.apple.AudioUnit-UI"), ("component", "subtype", "bad!"),
                ("component", "version", True), ("component", "sandboxSafe", False)]:
            with self.subTest(target=target, key=key):
                value = copy.deepcopy(self.targets)
                value[target][key] = bad
                with self.assertRaises(ValueError):
                    build.validate_targets(value)

    def test_hidden_metadata_rejects(self):
        value = copy.deepcopy(self.targets)
        value["extension"]["NSExtensionMainStoryboard"] = "Unreviewed"
        with self.assertRaises(ValueError):
            build.validate_targets(value)

    def test_external_and_rpath_dependencies_reject(self):
        for dependency in ["/Users/jess/libAudio.dylib", "@rpath/libPrivate.dylib", "/nix/store/private.dylib"]:
            with self.subTest(dependency=dependency), self.assertRaises(ValueError):
                build.validate_linkage("binary:\n\t" + dependency + " (compatibility version 1.0.0)\n")
        self.assertEqual(build.validate_linkage("binary:\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n"),
                         ["/usr/lib/libSystem.B.dylib"])

    def test_fat_wrong_os_sdk_and_missing_entry_reject(self):
        header = "binary:\nMach header\nMH_MAGIC_64 ARM64 ALL 0x00 EXECUTE 35 4992 FLAGS\n"
        commands = "Load command 0\n cmd LC_BUILD_VERSION\n platform 1\n minos 26.0\n sdk 27.0\nLoad command 1\n cmd LC_MAIN\n entryoff 16384\n"
        self.assertEqual(build.validate_macho(header, commands, "26.0", "27.0")["slices"], 1)
        for bad_header, bad_commands in [(header + header, commands), (header.replace("ARM64", "X86_64"), commands),
                (header, commands.replace("minos 26.0", "minos 27.0")),
                (header, commands.replace("sdk 27.0", "sdk 26.0")),
                (header, commands.replace("platform 1", "platform 2")),
                (header, commands.replace("LC_MAIN", "LC_UNIXTHREAD"))]:
            with self.subTest(header=bad_header, commands=bad_commands), self.assertRaises(ValueError):
                build.validate_macho(bad_header, bad_commands, "26.0", "27.0")


if __name__ == "__main__":
    unittest.main()
