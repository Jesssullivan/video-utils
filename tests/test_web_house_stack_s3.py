"""House-stack contract and static lane checks for the web app (WEB_TESTS_S3.md section 5.4).

Run from the repository root:  PYTHONPATH=tests python3 -m unittest test_web_house_stack_s3 -v

Stdlib only: no node, no install, no network. The estate P0 rule is "latest Skeleton v5 and latest Effect
everywhere". This module pins the three contract packages exactly, compares their majors with the npm
`latest` values recorded in docs/agent-notes/sprints/20261007-s3/web_tests-npm-latest.json (a measurement
of the registry at the recorded time; this test never asks the registry), and refuses a Skeleton 4 shim or
an Effect 3 import path. The Skeleton and Effect lists it checks against are read from that record, where
they were derived from the Skeleton v5 migration guide and npm export maps; nothing is asserted from memory.

Claim classes: every assertion here is a contract (a static statement about committed files) except
FixtureDrift, which regenerates the synthetic e2e fixtures and reports a typed skip
`fixture_generation_unavailable` (not a pass) when FFmpeg or a generator dependency is missing.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
SITE = ROOT / 'site'
RECEIPTS = ROOT / 'docs' / 'agent-notes' / 'sprints' / '20261007-s3'
NPM_LATEST = RECEIPTS / 'web_tests-npm-latest.json'
E2E = WEB / 'e2e'
FIXTURES = E2E / 'fixtures' / 'control-api'
GENERATOR = E2E / 'fixtures' / 'generate.py'
OUT = ROOT / 'artifacts' / 's2' / 'web_tests'

CONTRACT_PINS = {'@skeletonlabs/skeleton': '5.0.1', '@skeletonlabs/skeleton-svelte': '5.0.1', 'effect': '4.0.1'}
SKELETON_PACKAGES = ('@skeletonlabs/skeleton', '@skeletonlabs/skeleton-svelte')
ADDED_DEV_DEPENDENCIES = ('vitest', '@playwright/test', '@axe-core/playwright', 'fast-check')
LANE_SCRIPTS = {'test:unit': 'vitest run', 'test:e2e': 'playwright test --project=e2e',
                'test:a11y': 'playwright test --project=a11y'}
EXACT_VERSION = re.compile(r'^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')
EXPECTED_TOOL_COUNT = 42
GENERATE_TIMEOUT_S = 300
UNAVAILABLE_EXIT = 75
SOURCE_SUFFIXES = {'.ts', '.js', '.svelte', '.css', '.html'}
HOST_PATH = re.compile(r'/Users/|/home/|/private/|/Volumes/|/nix/store/|/tmp/|[A-Za-z]:\\\\')
UNIT_TEST_FILES = (
    'src/lib/schema/control.test.ts', 'src/lib/server/processing/schema.test.ts', 'src/lib/server/runs/schema.test.ts',
    'src/lib/server/processing/forms.test.ts', 'src/lib/server/processing/options.test.ts',
    'src/lib/server/job-request.test.ts', 'src/lib/idempotency.test.ts', 'src/lib/refusal-text.test.ts',
    'src/lib/server/auth/cf-access.test.ts', 'src/lib/server/auth/gate.test.ts', 'src/lib/server/config.test.ts',
    'src/lib/polling.test.ts', 'src/lib/components/review/review-logic.test.ts')
E2E_SPECS = ('library', 'upload', 'source', 'capture', 'process', 'runs', 'jobs', 'tools', 'keyboard', 'no-autoplay',
             'headers')
FORBIDDEN_IN_LANE_FILES = ('0.0.0.0', '--no-sandbox', '--disable-web-security', 'autoplay-policy', 'gitleaks:allow',
                           'gitleaks-allow', '.gitleaksignore', 'pragma: allowlist')
METRICS: dict = {}


def strict_loads(text):
    """JSON with duplicate keys and NaN/Infinity refused."""
    def pairs(items):
        keys = [key for key, _ in items]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate key')
        return dict(items)

    def constant(value):
        raise ValueError(f'non-finite constant {value}')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def read_json(path):
    return strict_loads(Path(path).read_text())


def declared(package):
    """name -> (spec, block) over every dependency block of a package.json document."""
    out = {}
    for block in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies'):
        for name, spec in (package.get(block) or {}).items():
            out[name] = (spec, block)
    return out


def lock_versions(text):
    """package name -> set of resolved versions in the `packages:` section of a pnpm lockfile (v9 layout)."""
    versions = {}
    in_packages = False
    for line in text.splitlines():
        if re.match(r'^[A-Za-z]', line):
            in_packages = line.strip() == 'packages:'
            continue
        if not in_packages:
            continue
        match = re.match(r"^  '?((?:@[^/@'\s]+/)?[^@'\s]+)@([^'():\s]+)'?:\s*$", line)
        if match:
            versions.setdefault(match.group(1), set()).add(match.group(2))
    return versions


def source_files(directory):
    return sorted(path for path in Path(directory).rglob('*')
                  if path.is_file() and path.suffix in SOURCE_SUFFIXES and 'node_modules' not in path.parts)


def module_specifiers(text):
    """Import/export/@import/@plugin specifiers of a JS/TS/Svelte/CSS source text."""
    found = set(re.findall(r'''(?:from|import)\s*\(?\s*['"]([^'"\n]+)['"]''', text))
    found |= set(re.findall(r'''@(?:import|plugin|source|reference)\s+(?:url\()?['"]([^'"\n]+)['"]''', text))
    return found


def named_imports(text, module):
    names = set()
    for block in re.findall(r'import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*[\'"]%s[\'"]' % re.escape(module), text):
        for part in block.split(','):
            name = part.strip().removeprefix('type ').split(' as ')[0].strip()
            if name:
                names.add(name)
    return names


def major(version):
    return int(version.split('.')[0])


class Stack:
    """One package directory (web/, or site/ when it exists) checked against the house-stack rules."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.package = read_json(self.directory / 'package.json')
        self.declared = declared(self.package)
        lock = self.directory / 'pnpm-lock.yaml'
        self.lock_text = lock.read_text() if lock.is_file() else None
        self.lock = lock_versions(self.lock_text) if self.lock_text is not None else None
        workspace = self.directory / 'pnpm-workspace.yaml'
        self.workspace_text = workspace.read_text() if workspace.is_file() else ''
        self.sources = source_files(self.directory / 'src') if (self.directory / 'src').is_dir() else []


def load_record():
    return read_json(NPM_LATEST)


def check_pins(case, stack, required):
    """Exact contract pins. `required` False (site/) applies the rule only where a package is declared."""
    checked = 0
    for name, pin in CONTRACT_PINS.items():
        if name not in stack.declared:
            case.assertFalse(required, f'{name} is not declared')
            continue
        spec, block = stack.declared[name]
        case.assertEqual(spec, pin, f'{name} must be pinned exactly to {pin}')
        if name == 'effect':
            case.assertEqual(block, 'dependencies', 'effect is a runtime dependency')
        if stack.lock is not None:
            case.assertEqual(stack.lock.get(name), {pin}, f'lockfile must resolve exactly one {name} version')
        checked += 1
    if 'svelte' in stack.declared:
        case.assertRegex(stack.declared['svelte'][0], r'^5\.\d+\.\d+$', 'svelte must be an exact 5.x.y pin')
        checked += 1
    else:
        case.assertFalse(required, 'svelte is not declared')
    for name, (spec, _block) in stack.declared.items():
        case.assertRegex(spec, EXACT_VERSION, f'{name} must be an exact version, got {spec!r}')
    return checked


def check_major_latest(case, stack, record):
    latest = {row['package']: row for row in record['packages']}
    rows = []
    for name in CONTRACT_PINS:
        if name not in stack.declared:
            continue
        case.assertIn(name, latest, f'no recorded npm latest for {name}')
        row = latest[name]
        case.assertRegex(row['latest'], EXACT_VERSION)
        case.assertTrue(row.get('checked_at_utc'), f'{name}: the record lacks a timestamp')
        case.assertEqual(row.get('command'), f'npm view {name} version')
        pin = stack.declared[name][0]
        case.assertGreaterEqual(major(pin), major(row['latest']),
                                f'{name} pin {pin} is a major behind the recorded npm latest {row["latest"]}')
        rows.append({'package': name, 'pin': pin, 'recorded_latest': row['latest'],
                     'pin_equals_recorded_latest': pin == row['latest']})
    return rows


def check_no_skeleton4_shim(case, stack, record):
    skeleton = record['skeleton']
    asserted = 0
    for legacy in skeleton['legacy_packages']:
        case.assertNotIn(legacy, stack.declared, f'{legacy} is a Skeleton legacy plugin')
        if stack.lock_text is not None:
            case.assertNotIn(legacy, stack.lock_text)
    asserted += 1
    # No alias, override, resolution or patch that swaps in another Skeleton build.
    for name, (spec, _block) in stack.declared.items():
        case.assertFalse(spec.startswith(('npm:', 'link:', 'file:', 'workspace:', 'git', 'http')), f'{name}: {spec}')
        if 'skeleton' in spec.lower():
            case.fail(f'{name} aliases a Skeleton package: {spec}')
    for key in ('overrides', 'resolutions', 'patchedDependencies'):
        blocks = [stack.package.get(key), (stack.package.get('pnpm') or {}).get(key)]
        for block in blocks:
            for name in (block or {}):
                case.assertNotIn('skeleton', name.lower(), f'package.json {key} names a Skeleton package')
    for key in ('overrides', 'patchedDependencies', 'packageExtensions', 'catalog'):
        match = re.search(rf'(?m)^{key}:\s*\n((?:[ \t]+.*\n?)*)', stack.workspace_text)
        if match:
            case.assertNotIn('skeleton', match.group(1).lower(), f'pnpm-workspace.yaml {key} names a Skeleton package')
    asserted += 1
    if stack.lock is not None:
        for name in SKELETON_PACKAGES:
            if name in stack.declared:
                case.assertEqual(len(stack.lock.get(name, set())), 1, f'second {name} version in the lockfile')
        for name, versions in stack.lock.items():
            if name.startswith('@skeletonlabs/'):
                case.assertTrue(all(major(version) == 5 for version in versions), f'{name} resolves a non-v5 version')
    asserted += 1
    # Entry points: every Skeleton import must be a v5 export key; the derived v4-only list must not be imported.
    v5_keys = skeleton['export_keys_v5']
    v4_only = skeleton['v4_only_entry_points']
    case.assertIsInstance(v4_only, list)
    imports = 0
    for path in stack.sources:
        for specifier in module_specifiers(path.read_text()):
            if not specifier.startswith('@skeletonlabs/'):
                continue
            imports += 1
            package = '/'.join(specifier.split('/')[:2])
            subpath = '.' + specifier[len(package):]
            case.assertIn(package, v5_keys, f'{path.name}: unknown Skeleton package {specifier}')
            allowed = any(re.fullmatch(re.escape(key).replace(r'\*', r'[^/]+'), subpath) for key in v5_keys[package])
            case.assertTrue(allowed, f'{path.name}: {specifier} is not a Skeleton v5 entry point')
            case.assertNotIn(specifier, v4_only)
    asserted += 1
    # Renamed/removed v4 design tokens and replaced v4 classes named by the migration guide.
    tokens = skeleton['v4_tokens_renamed_in_v5'] + skeleton['v4_tokens_removed_in_v5']
    classes = skeleton['v4_classes_replaced_in_v5']
    case.assertGreaterEqual(len(tokens), 20)
    for path in stack.sources:
        if path.name.endswith('.test.ts'):
            continue
        text = path.read_text()
        for token in tokens:
            case.assertIsNone(re.search(rf'(?<![\w-]){re.escape(token)}(?![\w-])', text), f'{path.name}: v4 token {token}')
        for name in classes:
            case.assertIsNone(re.search(rf'(?<![\w-]){re.escape(name)}(?![\w-])', text), f'{path.name}: v4 class {name}')
        for variant in skeleton['v4_variants_removed_in_v5']:
            case.assertNotIn(variant, text, f'{path.name}: removed v4 variant')
    asserted += 1
    return {'rules_asserted': asserted, 'not_asserted': 0, 'skeleton_imports_checked': imports,
            'v4_only_entry_points': len(v4_only), 'v4_tokens_checked': len(tokens), 'v4_classes_checked': len(classes)}


def check_no_effect3_paths(case, stack, record):
    exports = record['effect_exports']
    only3 = set(record['effect3']['effect3_only_subpaths'])
    case.assertGreaterEqual(len(only3), 10)
    for legacy in record['legacy_effect_packages']:
        case.assertNotIn(legacy, stack.declared, f'{legacy} is an Effect 3 era package')
        if stack.lock is not None:
            case.assertNotIn(legacy, stack.lock)
    if stack.lock is not None and 'effect' in stack.declared:
        case.assertTrue(all(major(version) == 4 for version in stack.lock.get('effect', set())))
    explicit = {key[2:] for key in exports['export_keys'] if key.startswith('./') and '*' not in key}
    modules = set(exports['wildcard_modules'])
    case.assertIn('./*', exports['export_keys'])
    subpaths = roots = 0
    for path in stack.sources:
        text = path.read_text()
        for specifier in module_specifiers(text):
            if specifier.startswith('@effect/'):
                case.assertNotIn(specifier.split('/')[0] + '/' + specifier.split('/')[1],
                                 record['legacy_effect_packages'], f'{path.name}: {specifier}')
            if specifier == 'effect':
                roots += 1
                for name in named_imports(text, 'effect'):
                    case.assertNotIn(name, only3, f'{path.name}: {name} exists only in the Effect 3 line')
            elif specifier.startswith('effect/'):
                subpaths += 1
                subpath = specifier[len('effect/'):]
                case.assertFalse(subpath.startswith('internal'), f'{path.name}: {specifier} is internal')
                case.assertNotIn(subpath, only3, f'{path.name}: {specifier} exists only in the Effect 3 line')
                case.assertTrue(subpath in explicit or subpath in modules,
                                f'{path.name}: {specifier} is not an export of effect@{exports["version"]}')
    return {'rules_asserted': 3, 'not_asserted': 0, 'effect_root_imports': roots, 'effect_subpath_imports': subpaths,
            'effect3_only_subpaths_checked': len(only3)}


class HouseStackPins(unittest.TestCase):
    def test_w1_contract_pins_are_exact_and_single_in_the_lockfile(self):
        stack = Stack(WEB)
        self.assertIsNotNone(stack.lock)
        checked = check_pins(self, stack, required=True)
        self.assertEqual(checked, 4)
        METRICS['W1_pins'] = {'checked': checked, 'denominator': 4, 'lockfile_single_version': 3,
                              'pins': {name: stack.declared[name][0] for name in (*CONTRACT_PINS, 'svelte')}}

    def test_lock_parser_reads_the_importer_packages(self):
        stack = Stack(WEB)
        self.assertGreater(len(stack.lock), 50)
        for name, (spec, _block) in stack.declared.items():
            self.assertIn(spec, stack.lock.get(name, set()), f'{name}@{spec} is not resolved in the lockfile')


class MajorLatest(unittest.TestCase):
    def test_pins_are_not_a_major_behind_the_recorded_npm_latest(self):
        self.assertTrue(NPM_LATEST.is_file(), 'web_tests-npm-latest.json is missing')
        record = load_record()
        self.assertEqual(record['contract_packages'], list(CONTRACT_PINS))
        rows = check_major_latest(self, Stack(WEB), record)
        self.assertEqual(len(rows), 3)
        checked = datetime.datetime.strptime(record['checked_at_utc'], '%Y-%m-%dT%H:%M:%SZ').replace(
            tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - checked).total_seconds() / 86400
        self.assertGreaterEqual(age, -1, 'the record is dated in the future')
        # The registry is never contacted: today's latest is an explicit unknown, and the record's age is reported.
        self.assertIsNone(record['npm_latest_at_ci_time'])
        METRICS['major_latest'] = {'rows': rows, 'record_checked_at_utc': record['checked_at_utc'],
                                   'record_age_days': round(age, 2), 'npm_latest_at_ci_time': None}

    def test_a_pin_behind_the_recorded_major_is_detected(self):
        record = load_record()
        stack = Stack(WEB)
        stack.declared = dict(stack.declared, effect=('3.22.2', 'dependencies'))
        with self.assertRaises(AssertionError):
            check_major_latest(self, stack, record)
        missing = json.loads(json.dumps(record))
        missing['packages'] = [dict(row, checked_at_utc='') for row in missing['packages']]
        with self.assertRaises(AssertionError):
            check_major_latest(self, Stack(WEB), missing)


class NoSkeleton4Shim(unittest.TestCase):
    def test_w2_no_skeleton4_shim(self):
        record = load_record()
        self.assertTrue(record['skeleton']['guide_url'].startswith('https://www.skeleton.dev/'))
        self.assertRegex(record['skeleton']['guide_sha256'], r'^[0-9a-f]{64}$')
        self.assertTrue(record['skeleton']['guide_fetched_at_utc'])
        self.assertTrue(record['skeleton4_entry_point_list_source'])
        METRICS['W2_skeleton'] = check_no_skeleton4_shim(self, Stack(WEB), record)
        self.assertGreaterEqual(METRICS['W2_skeleton']['skeleton_imports_checked'], 3)

    def test_a_shim_is_detected(self):
        record = load_record()
        stack = Stack(WEB)
        stack.declared = dict(stack.declared, **{'@skeletonlabs/tw-plugin': ('0.4.1', 'devDependencies')})
        with self.assertRaises(AssertionError):
            check_no_skeleton4_shim(self, stack, record)
        aliased = Stack(WEB)
        aliased.declared = dict(aliased.declared, **{'skeleton-v4': ('npm:@skeletonlabs/skeleton@4.15.2', 'devDependencies')})
        with self.assertRaises(AssertionError):
            check_no_skeleton4_shim(self, aliased, record)
        doubled = Stack(WEB)
        doubled.lock = dict(doubled.lock, **{'@skeletonlabs/skeleton': {'5.0.1', '4.15.2'}})
        with self.assertRaises(AssertionError):
            check_no_skeleton4_shim(self, doubled, record)


class NoEffect3Paths(unittest.TestCase):
    def test_w2_no_effect3_import_paths(self):
        record = load_record()
        self.assertEqual(record['effect_exports']['version'], CONTRACT_PINS['effect'])
        self.assertEqual(record['effect_exports']['command'], 'npm view effect@4.0.1 exports --json')
        self.assertTrue(record['effect3_only_subpath_list_source'])
        METRICS['W2_effect'] = check_no_effect3_paths(self, Stack(WEB), record)
        self.assertGreaterEqual(METRICS['W2_effect']['effect_root_imports'], 5)

    def test_an_effect3_path_is_detected(self):
        record = load_record()
        with tempfile.TemporaryDirectory(prefix='web-house-stack-') as tmp:
            for body in ("import { Schema } from '@effect/schema';\n", "import * as Either from 'effect/Either';\n",
                         "import { Effect, Either } from 'effect';\n", "import { x } from 'effect/internal/core';\n",
                         "import { NotAModule } from 'effect/NotAModule';\n"):
                stack = Stack(WEB)
                probe = Path(tmp) / 'probe.ts'
                probe.write_text(body)
                stack.sources = [probe]
                with self.assertRaises(AssertionError, msg=body):
                    check_no_effect3_paths(self, stack, record)
            stack = Stack(WEB)
            probe = Path(tmp) / 'probe.ts'
            probe.write_text("import { Effect, Schema } from 'effect';\nimport * as Schema2 from 'effect/Schema';\n")
            stack.sources = [probe]
            check_no_effect3_paths(self, stack, record)


class SiteObeysSameRule(unittest.TestCase):
    def test_site_package_obeys_the_same_rules_when_present(self):
        present = (SITE / 'package.json').is_file()
        METRICS['site'] = {'site_package_present': present}
        if not present:
            # Nothing is claimed about a site that does not exist in this repository.
            return
        record = load_record()
        stack = Stack(SITE)
        METRICS['site'].update(pins_checked=check_pins(self, stack, required=False),
                               major_latest=check_major_latest(self, stack, record),
                               skeleton=check_no_skeleton4_shim(self, stack, record),
                               effect=check_no_effect3_paths(self, stack, record))


class LaneStatics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = read_json(WEB / 'package.json')
        cls.fixtures = sorted(FIXTURES.glob('*.json'))

    def test_w3_added_dev_dependencies_are_exact_and_scripts_exist(self):
        dev = self.package['devDependencies']
        lock = lock_versions((WEB / 'pnpm-lock.yaml').read_text())
        for name in ADDED_DEV_DEPENDENCIES:
            self.assertIn(name, dev)
            self.assertRegex(dev[name], EXACT_VERSION)
            self.assertIn(dev[name], lock.get(name, set()))
        for name, command in LANE_SCRIPTS.items():
            self.assertEqual(self.package['scripts'].get(name), command)
        for name in ('dev', 'build', 'preview', 'start', 'sync', 'check'):
            self.assertIn(name, self.package['scripts'], 'an existing script was removed')
        METRICS['W3_dev_dependencies'] = {name: dev[name] for name in ADDED_DEV_DEPENDENCIES}

    def test_w4_w8_test_files_are_present(self):
        for name in UNIT_TEST_FILES:
            self.assertTrue((WEB / name).is_file(), name)
        self.assertEqual(len(UNIT_TEST_FILES), 13)
        outside = [str(path.relative_to(WEB)) for path in WEB.rglob('*.test.ts')
                   if 'node_modules' not in path.parts and 'src' not in path.relative_to(WEB).parts[:1]]
        self.assertEqual(outside, [], 'unit tests live next to the module under test, inside web/src')
        for name in E2E_SPECS:
            self.assertTrue((E2E / f'{name}.spec.ts').is_file(), name)
        self.assertEqual(len(E2E_SPECS), 11)
        self.assertTrue((E2E / 'a11y-routes.spec.ts').is_file())
        METRICS['files'] = {'unit_test_files': len(UNIT_TEST_FILES), 'e2e_specs': len(E2E_SPECS), 'a11y_specs': 1}

    def test_w11_registry_holds_42_tools_and_the_fixture_matches_it(self):
        tools = read_json(ROOT / 'program' / 'tools.json')['tools']
        names = sorted(tool['name'] for tool in tools)
        self.assertEqual(len(names), EXPECTED_TOOL_COUNT)
        capabilities = read_json(FIXTURES / 'capabilities.json')
        self.assertEqual(capabilities['tool_count'], EXPECTED_TOOL_COUNT)
        self.assertEqual(sorted(tool['name'] for tool in capabilities['tools']), names)
        METRICS['W11_tools'] = {'registry': len(names), 'fixture': capabilities['tool_count']}

    def test_fixtures_are_strict_synthetic_low_entropy_and_path_free(self):
        readme = read_json(E2E / 'fixtures' / 'README.json')
        self.assertEqual(readme['claim_class'], 'synthetic_fixture')
        self.assertIs(readme['contains_real_media_facts'], False)
        self.assertIs(readme['real_take_facts_in_fixtures'], False)
        self.assertEqual(sorted(readme['cases']), [path.name for path in self.fixtures])
        self.assertGreaterEqual(len(self.fixtures), 40)
        ids = 0
        for path in self.fixtures:
            text = path.read_text()
            strict_loads(text)
            self.assertIsNone(HOST_PATH.search(text), f'{path.name} contains a host path')
            for value in re.findall(r'\b(?:job|art|src|rev|evd)_([0-9a-f]{32})\b', text):
                self.assertRegex(value, r'^(0{24}[0-9a-f]{8}|f{31}1)$', f'{path.name}: id is not a counter value')
                ids += 1
            for value in re.findall(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])', text):
                self.assertRegex(value, r'^0{56}[0-9a-f]{8}$', f'{path.name}: hash is not a counter value')
            for value in re.findall(r'"idempotency_key":\s*"([^"]+)"', text):
                self.assertRegex(value, r'^fixture-000000\d\d$', f'{path.name}: idempotency key {value}')
        self.assertGreater(ids, 100)
        routes = read_json(FIXTURES / 'routes.json')['routes']
        files = {row['file'] for row in routes}
        self.assertEqual(files | {'ids.json', 'routes.json'}, {path.name for path in self.fixtures})
        for row in routes:
            self.assertTrue(row['path'].startswith('/api/v1/'))
            self.assertNotIn('limit=', row['path'])
        METRICS['fixtures'] = {'files': len(self.fixtures), 'routes': len(routes), 'ids_checked': ids}

    def test_lane_files_carry_no_weakening_flag_scanner_allowlist_or_host_path(self):
        files = [*source_files(E2E), *source_files(WEB / 'tests'), E2E / 'mock-control-api.mjs', GENERATOR,
                 WEB / 'playwright.config.ts', WEB / 'vitest.config.ts', *(WEB / name for name in UNIT_TEST_FILES),
                 E2E / 'a11y-baseline.json', E2E / 'fixtures' / 'README.json']
        files = sorted(set(files))
        self.assertGreaterEqual(len(files), 30)
        for path in files:
            text = path.read_text()
            for needle in FORBIDDEN_IN_LANE_FILES:
                self.assertNotIn(needle, text, f'{path.relative_to(ROOT)} contains {needle!r}')
            self.assertIsNone(HOST_PATH.search(text), f'{path.relative_to(ROOT)}: host path')
            self.assertNotRegex(text, r'-----BEGIN', f'{path.relative_to(ROOT)}: key material')
        config = (WEB / 'playwright.config.ts').read_text()
        self.assertRegex(config, r'workers:\s*1\b')
        self.assertRegex(config, r'retries:\s*0\b')
        self.assertRegex(config, r"video:\s*'off'")
        self.assertNotRegex(config, r':3000\b')
        self.assertNotRegex(config, r'webServer')
        vitest = (WEB / 'vitest.config.ts').read_text()
        self.assertIn("environment: 'node'", vitest)
        self.assertIn("include: ['src/**/*.test.ts']", vitest)
        self.assertIn('passWithNoTests: false', vitest)
        setup = (WEB / 'tests' / 'setup.ts').read_text()
        self.assertIn('PROPERTY_SEED = 20261007', setup)
        self.assertIn('PROPERTY_RUNS = 200', setup)
        METRICS['W20_lane_files_scanned'] = len(files)

    def test_axe_protocol_is_sealed_and_the_baseline_is_well_formed(self):
        spec = (E2E / 'a11y-routes.spec.ts').read_text()
        for tag in ('wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'):
            self.assertIn(f"'{tag}'", spec)
        for call in ('disableRules', '.exclude(', 'withRules', '.options('):
            self.assertNotIn(call, spec, f'the axe spec may not narrow the protocol with {call}')
        baseline = read_json(E2E / 'a11y-baseline.json')
        self.assertEqual(baseline['schema_version'], 1)
        keys = set()
        for entry in baseline['violations']:
            for field in ('rule_id', 'route', 'scheme', 'impact', 'wcag_tags', 'node_count', 'selectors'):
                self.assertIn(field, entry)
            self.assertIn(entry['scheme'], ('light', 'dark'))
            self.assertGreaterEqual(entry['node_count'], 1)
            self.assertTrue(entry['route'].startswith('/'))
            key = (entry['route'], entry['scheme'], entry['rule_id'])
            self.assertNotIn(key, keys, 'duplicate baseline entry')
            keys.add(key)
        support = (WEB / 'tests' / 'e2e-support.ts').read_text()
        self.assertEqual(len(re.findall(r"\{ name: '[a-z-]+', route: '/", support)), 16, 'the 16 sealed routes')
        self.assertEqual(len(re.findall(r"name: 'state-[a-z-]+'", spec)), 3, 'the 3 sealed states')
        by_rule = {}
        for entry in baseline['violations']:
            by_rule[entry['rule_id']] = by_rule.get(entry['rule_id'], 0) + 1
        METRICS['a11y_baseline'] = {'entries': len(baseline['violations']), 'by_rule': by_rule,
                                    'wcag_conformance': None, 'screen_reader_acceptance': None}


class FixtureDrift(unittest.TestCase):
    def test_regenerated_fixtures_match_the_committed_set(self):
        spec = importlib.util.spec_from_file_location('web_e2e_fixture_generator', GENERATOR)
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        with tempfile.TemporaryDirectory(prefix='web-e2e-drift-') as tmp:
            try:
                result = subprocess.run([sys.executable, str(GENERATOR), '--out', tmp], cwd=ROOT, capture_output=True,
                                        text=True, timeout=GENERATE_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                self.fail(f'fixture generator exceeded {GENERATE_TIMEOUT_S} s')
            if result.returncode == UNAVAILABLE_EXIT:
                reason = (result.stdout.strip().splitlines() or ['no reason printed'])[-1]
                METRICS['fixture_drift'] = {'status': 'not_checked', 'skip_code': 'fixture_generation_unavailable',
                                            'reason': reason}
                self.skipTest(f'fixture_generation_unavailable: {reason} (not a pass)')
            self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-2000:])
            fresh = {path.name: path.read_text() for path in sorted(Path(tmp).glob('*.json'))}
        committed = {path.name: path.read_text() for path in sorted(FIXTURES.glob('*.json'))}
        self.assertEqual(sorted(fresh), sorted(committed), 'the fixture file set changed')
        exact = [name for name in committed if fresh[name] == committed[name]]
        differing_shape = [name for name in committed
                           if generator.shape(strict_loads(fresh[name])) != generator.shape(strict_loads(committed[name]))]
        METRICS['fixture_drift'] = {'status': 'equal' if not differing_shape else 'differs', 'files': len(committed),
                                    'basis': 'file set, ids.json, routes.json, and keys + JSON types of every file',
                                    'exact_equal_files': len(exact), 'shape_differs': differing_shape}
        self.assertEqual(differing_shape, [], 'regenerate with web/e2e/fixtures/generate.py and review the diff')
        for name in ('ids.json', 'routes.json'):
            self.assertEqual(fresh[name], committed[name], name)
        capabilities = strict_loads(fresh['capabilities.json'])
        self.assertEqual(sorted(tool['name'] for tool in capabilities['tools']),
                         sorted(tool['name'] for tool in strict_loads(committed['capabilities.json'])['tools']))


def tearDownModule():
    """Best-effort metrics file for the lane receipts (gitignored run output; never a committed artifact)."""
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'house-stack.json').write_text(json.dumps(METRICS, indent=2, sort_keys=True) + '\n')
    except OSError:
        pass
    if os.environ.get('WEB_HOUSE_STACK_PRINT') == '1':
        print(json.dumps(METRICS, indent=2, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
