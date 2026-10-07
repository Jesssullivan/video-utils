"""S3 bazel_graph and bazel_full lanes: structural contract test for the Bzlmod graph.

Contracts: docs/spec/sprints/BAZEL_GRAPH_S3.md section 7 and
docs/spec/sprints/BAZEL_FULL_S3.md section 12 (//site, the classification
supplement, the known-host-failure register, the site gate). Stdlib only; no Bazel,
network, FFmpeg, node or pnpm is needed. The fixture is the repository tree.

This is an inventory check, not a build: it proves that the graph files exist,
agree with the Cargo/pyproject/package.json version sites and cover every worker
and test module. It does not prove that Bazel resolves or builds the graph, and
it is not proof of a dependency edge (`bazel mod graph` is that oracle).

BUILD and MODULE files are read with a small Starlark-subset evaluator (calls,
string/list/dict literals, `+`, names, `glob`, `select`, `package_name`).
Anything outside that subset raises instead of being skipped. The only
subprocess (the unittest shim self-check) is bounded by a timeout.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIM_TIMEOUT_S = 120
SHIM_MARKER_ENV = "BAZEL_GRAPH_S3_SHIM_SELFTEST"

REQUIRED_FILES = (
    ".bazelversion", ".bazelrc", ".bazelignore", "MODULE.bazel", "BUILD.bazel",
    "src/BUILD.bazel", "scripts/BUILD.bazel", "tests/BUILD.bazel", "web/BUILD.bazel",
    "native/au-spike/BUILD.bazel", "just/bazel.just", "site/BUILD.bazel", "bazel/BUILD.bazel",
)
LANE_FILES = (
    "bazel/test_classification_s3_full.json", "bazel/known_host_failures.json", "bazel/ci-bazel-full.draft.yml",
    "bazel/site_build.mjs", "bazel/host_gate.py", "bazel/full_run_report.py",
)
OWNED_PACKAGES = ("", "src", "scripts", "tests", "web", "site", "native/au-spike", "tools/bazel", "bazel")
HELPER_FILES = (
    "tools/bazel/BUILD.bazel", "tools/bazel/python.bzl", "tools/bazel/rust.bzl",
    "tools/bazel/unittest_main.py", "tools/bazel/run.py", "tools/bazel/web/sveltekit.mjs",
    "tools/bazel/coverage_exclusions.json", "tools/bazel/registry_modules.json",
    "tools/bazel/test_classification.json",
)
REQUIRED_RULE_MODULES = (
    "rules_rust", "rules_python", "aspect_rules_js", "aspect_rules_ts", "rules_nodejs", "aspect_bazel_lib",
)
REGISTRY_FIRST = re.compile(r"^https://raw\.githubusercontent\.com/tinyland-inc/bazel-registry/([0-9a-f]{40})$")
REGISTRY_SECOND = "https://bcr.bazel.build"
REMOTE_FLAGS = ("--remote_cache", "--remote_executor", "--bes_backend")
HOUSE_STACK = {"@skeletonlabs/skeleton": "5.0.1", "@skeletonlabs/skeleton-svelte": "5.0.1", "effect": "4.0.1"}
FORBIDDEN_MAJOR = {"@skeletonlabs/skeleton": 4, "@skeletonlabs/skeleton-svelte": 4, "effect": 3}
EXACT = re.compile(r"^\d+\.\d+\.\d+$")
IGNORED_TREES = (".local", "artifacts", "target", "data", "models", "web/node_modules", "web/build", "web/.svelte-kit")
BAZEL_FILE_NAMES = ("MODULE.bazel", "BUILD.bazel")
RECIPES = ("bazel-build", "bazel-test", "bazel-graph", "bazel-site", "bazel-full")
DECISIONS = {"consumed", "blocked_estate_drift_TIN-5716", "blocked_unverifiable", "not_applicable",
             "deferred_needs_root_change"}
CLASS_TAGS = {"ffmpeg": "requires-ffmpeg", "host_tools": "requires-host-tools", "exclusive": "exclusive",
              "workspace_artifacts": "workspace-artifacts", "web_tree": "reads-web-tree"}


# --------------------------------------------------------------------------- Starlark subset


class StarlarkSubsetError(ValueError):
    """The file uses a construct this reader does not evaluate."""


class Call:
    """One evaluated call: dotted name, positional values and keyword values."""

    def __init__(self, name: str, args: list, kwargs: dict):
        self.name, self.args, self.kwargs = name, args, kwargs

    def __repr__(self) -> str:
        return f"Call({self.name}, {self.args}, {self.kwargs})"


def glob_regex(pattern: str) -> re.Pattern:
    out, index = "", 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out, index = out + "(?:[^/]+/)*", index + 3
        elif pattern.startswith("**", index):
            out, index = out + ".*", index + 2
        elif pattern[index] == "*":
            out, index = out + "[^/]*", index + 1
        else:
            out, index = out + re.escape(pattern[index]), index + 1
    return re.compile(out + "$")


def package_files(package_dir: Path) -> list[str]:
    """Files of one Bazel package: the directory tree minus nested packages."""
    found = []
    for current, directories, files in os.walk(package_dir):
        here = Path(current)
        if here != package_dir and any((here / name).is_file() for name in ("BUILD.bazel", "BUILD")):
            directories[:] = []
            continue
        directories.sort()
        found += [(here / name).relative_to(package_dir).as_posix() for name in sorted(files)]
    return found


def expand_glob(package_dir: Path, include: list[str], exclude: list[str]) -> list[str]:
    keep, drop = [glob_regex(p) for p in include], [glob_regex(p) for p in exclude]
    return sorted(name for name in package_files(package_dir)
                  if any(p.match(name) for p in keep) and not any(p.match(name) for p in drop))


class Starlark:
    """Evaluates the declarative subset used by this repository's Bazel files."""

    def __init__(self, text: str, package_dir: Path | None = None, repo_root: Path | None = None,
                 label: str = "<starlark>"):
        self.package_dir, self.repo_root, self.label = package_dir, repo_root, label
        self.names: dict = {}
        self.calls: list[Call] = []
        try:
            tree = ast.parse(text)
        except SyntaxError as error:
            raise StarlarkSubsetError(f"{label}: not parseable: {error}") from error
        for statement in tree.body:
            self.statement(statement)

    def fail(self, node: ast.AST, what: str):
        raise StarlarkSubsetError(f"{self.label}:{getattr(node, 'lineno', '?')}: unsupported {what}")

    def statement(self, node: ast.stmt):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = self.value(node.value)
            if isinstance(call, Call):
                self.calls.append(call)
                if call.name == "load":
                    self.load(call)
            return
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            self.names[node.targets[0].id] = self.value(node.value)
            return
        self.fail(node, f"statement {type(node).__name__}")

    def load(self, call: Call):
        """Imports constants from first-party .bzl files; rule names stay opaque."""
        source = call.args[0] if call.args else ""
        if not (self.repo_root and source.startswith("//tools/bazel:") and source.endswith(".bzl")):
            return
        path = self.repo_root / "tools/bazel" / source.split(":", 1)[1]
        if not path.is_file():
            raise StarlarkSubsetError(f"{self.label}: load of missing {source}")
        try:
            constants = Starlark(path.read_text(), repo_root=self.repo_root, label=str(path)).names
        except StarlarkSubsetError:
            constants = {}  # a macro file (def statements): its symbols are rules, not constants
        for name in list(call.args[1:]) + list(call.kwargs.values()):
            if name in constants:
                self.names[name] = constants[name]

    def dotted(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self.dotted(node.value)}.{node.attr}"
        self.fail(node, "call target")

    def value(self, node: ast.AST):
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, bool, type(None))):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self.value(item) for item in node.elts]
        if isinstance(node, ast.Dict):
            return {self.value(key): self.value(item) for key, item in zip(node.keys, node.values)}
        if isinstance(node, ast.Name):
            if node.id not in self.names:
                self.fail(node, f"name {node.id!r}")
            return self.names[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = self.value(node.left), self.value(node.right)
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, list) and isinstance(right, dict) and "select" in right:
                return left  # a select() extends a list by configuration; the base list is the inventory
            self.fail(node, "operands of +")
        if isinstance(node, ast.Call):
            name = self.dotted(node.func)
            args = [self.value(item) for item in node.args]
            kwargs = {}
            for keyword in node.keywords:
                if keyword.arg is None:
                    self.fail(node, "**kwargs")
                kwargs[keyword.arg] = self.value(keyword.value)
            if name == "glob":
                if self.package_dir is None:
                    self.fail(node, "glob outside a package")
                include = args[0] if args else kwargs.get("include", [])
                return expand_glob(self.package_dir, include, kwargs.get("exclude", []))
            if name == "package_name":
                if self.package_dir is None or self.repo_root is None:
                    self.fail(node, "package_name outside a package")
                return self.package_dir.relative_to(self.repo_root).as_posix()
            if name == "select":
                return {"select": args[0] if args else {}}
            return Call(name, args, kwargs)
        self.fail(node, f"expression {type(node).__name__}")

    def named(self, *names: str) -> list[Call]:
        return [call for call in self.calls if call.name in names]


def read_build(root: Path, package: str) -> Starlark:
    package_dir = root / package if package else root
    path = package_dir / "BUILD.bazel"
    return Starlark(path.read_text(), package_dir=package_dir, repo_root=root, label=str(path.relative_to(root)))


def read_module(root: Path) -> Starlark:
    return Starlark((root / "MODULE.bazel").read_text(), repo_root=root, label="MODULE.bazel")


# --------------------------------------------------------------------------- checkers (return error lists)


def rc_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


def bazelrc_errors(text: str) -> list[str]:
    errors = []
    lines = rc_lines(text)
    registries = [word.split("=", 1)[1] for line in lines for word in line.split() if word.startswith("--registry=")]
    if len(registries) != 2:
        errors.append(f"expected exactly 2 --registry lines, found {len(registries)}")
    else:
        if not REGISTRY_FIRST.match(registries[0]):
            errors.append(f"first registry is not the commit-pinned tinyland-inc registry: {registries[0]}")
        if registries[1] != REGISTRY_SECOND:
            errors.append(f"second registry is not {REGISTRY_SECOND}: {registries[1]}")
    for line in lines:
        if "--registry=" in line and not line.startswith("common "):
            errors.append(f"registry flag outside `common`: {line}")
        for flag in REMOTE_FLAGS:
            if flag in line:
                errors.append(f"remote backend flag in .bazelrc: {line}")
    if "common --enable_bzlmod" not in lines:
        errors.append("missing `common --enable_bzlmod`")
    for variable in ("FFMPEG", "FFPROBE"):
        if f"test --test_env={variable}" not in lines:
            errors.append(f"missing pass-through `test --test_env={variable}`")
        if any(f"--test_env={variable}=" in line for line in lines):
            errors.append(f"{variable} must be passed through, not given a value")
    imports = [line for line in lines if line.startswith(("import ", "try-import "))]
    if imports != ["try-import %workspace%/user.bazelrc"]:
        errors.append(f"only `try-import %workspace%/user.bazelrc` may be imported, found {imports}")
    return errors


def registry_commit(text: str) -> str | None:
    for line in rc_lines(text):
        for word in line.split():
            match = REGISTRY_FIRST.match(word.split("=", 1)[1]) if word.startswith("--registry=") else None
            if match:
                return match.group(1)
    return None


def bazel_deps(module: Starlark) -> dict[str, str]:
    return {call.kwargs.get("name"): call.kwargs.get("version") for call in module.named("bazel_dep")}


def module_errors(module: Starlark) -> list[str]:
    errors = []
    deps = bazel_deps(module)
    for name in REQUIRED_RULE_MODULES:
        version = deps.get(name)
        if not isinstance(version, str) or not re.match(r"^\d+\.\d+\.\d+$", version):
            errors.append(f"bazel_dep {name} needs a literal X.Y.Z version, found {version!r}")
    locks = {call.kwargs.get("name"): call for call in module.calls if call.name.endswith(".npm_translate_lock")}
    if len([call for call in module.calls if call.name.endswith(".npm_translate_lock")]) != len(TRANSLATIONS) \
            or sorted(locks) != sorted(TRANSLATIONS):
        errors.append(f"exactly the npm_translate_lock calls {sorted(TRANSLATIONS)} are required, found {sorted(locks)}")
    for name, package in TRANSLATIONS.items():
        call = locks.get(name)
        if call is None:
            continue
        if call.kwargs.get("pnpm_lock") != f"//{package}:pnpm-lock.yaml":
            errors.append(f"npm_translate_lock {name} must read //{package}:pnpm-lock.yaml")
        if f"//{package}:package.json" not in call.kwargs.get("data", []):
            errors.append(f"npm_translate_lock {name} data must include //{package}:package.json")
        if call.kwargs.get("npmrc") != f"//{package}:.npmrc":
            errors.append(f"npm_translate_lock {name} must declare npmrc = //{package}:.npmrc (rules_js refuses an undeclared one)")
    if [call for call in module.calls if call.name.endswith(".npm_import")]:
        errors.append("npm_import adds a second npm version site; use the package's pnpm-lock.yaml only")
    for banned in ("git_override", "archive_override", "single_version_override", "multiple_version_override"):
        if module.named(banned):
            errors.append(f"{banned} is not allowed in MODULE.bazel")
    errors += local_override_errors(module)
    return errors


TRANSLATIONS = {"npm": "web", "npm_site": "site"}


def vendored_module(root: Path, path: str) -> dict:
    """name/version of a vendored carrier's own module() call."""
    calls = Starlark((root / path / "MODULE.bazel").read_text(), label=f"{path}/MODULE.bazel").named("module")
    return calls[0].kwargs if calls else {}


def local_override_errors(module: Starlark, root: Path | None = None) -> list[str]:
    """A local_path_override may only point at a vendored carrier under site/vendor (contract 9.3.2)."""
    root = root or ROOT
    errors = []
    deps = bazel_deps(module)
    for call in module.named("local_path_override"):
        name, path = call.kwargs.get("module_name"), call.kwargs.get("path", "")
        if not isinstance(path, str) or not path.startswith("site/vendor/") or ".." in path.split("/"):
            errors.append(f"local_path_override {name!r} path {path!r} is not under site/vendor/")
            continue
        if not (root / path / "MODULE.bazel").is_file():
            errors.append(f"local_path_override {name!r}: {path}/MODULE.bazel does not exist")
            continue
        vendored = vendored_module(root, path)
        if vendored.get("name") != name or deps.get(name) != vendored.get("version"):
            errors.append(f"local_path_override {name!r} does not match {path}/MODULE.bazel {vendored}")
    return errors


def lock_importer(lock_text: str) -> dict[str, dict[str, str]]:
    """Stdlib parse of importers['.'] in a pnpm lockfile v9: name -> specifier/version."""
    lines = lock_text.splitlines()
    try:
        start = lines.index("importers:")
    except ValueError:
        return {}
    found, name = {}, None
    for line in lines[start + 1:]:
        if line and not line.startswith(" "):
            break
        package = re.match(r"^      '?([^':]+(?:/[^':]+)?)'?:\s*$", line)
        field = re.match(r"^        (specifier|version):\s*(.+)$", line)
        if package:
            name = package.group(1)
            found[name] = {}
        elif field and name:
            found[name][field.group(1)] = field.group(2).strip().strip("'").split("(")[0]
    return found


def lock_integrity(lock_text: str, name: str, version: str) -> str | None:
    match = re.search(rf"^  '?{re.escape(name)}@{re.escape(version)}'?:\n    resolution: \{{integrity: ([^}}\s,]+)",
                      lock_text, re.MULTILINE)
    return match.group(1) if match else None


def satisfies_engines(version: str, engines: str) -> bool:
    """Evaluates a space-separated list of >=, >, <=, < comparators (the form web/package.json uses)."""
    def parts(text: str) -> tuple[int, ...]:
        numbers = [int(x) for x in text.split(".")]
        return tuple(numbers + [0] * (3 - len(numbers)))
    actual = parts(version)
    for comparator in engines.split():
        match = re.match(r"^(>=|<=|>|<)(\d+(?:\.\d+){0,2})$", comparator)
        if not match:
            raise ValueError(f"unsupported engines comparator {comparator!r}")
        bound = parts(match.group(2))
        if not {">=": actual >= bound, "<=": actual <= bound, ">": actual > bound, "<": actual < bound}[match.group(1)]:
            return False
    return True


def bazel_texts(root: Path) -> dict[str, str]:
    """Every Bazel-owned text file: MODULE.bazel, each BUILD.bazel and tools/bazel/*.bzl."""
    paths = [root / "MODULE.bazel", root / "BUILD.bazel"]
    paths += [root / package / "BUILD.bazel" for package in ("src", "scripts", "tests", "web", "native/au-spike",
                                                               "tools/bazel", "bazel")]
    paths += sorted((root / "tools/bazel").glob("*.bzl")) if (root / "tools/bazel").is_dir() else []
    return {str(path.relative_to(root)): path.read_text() for path in paths if path.is_file()}


def npm_pin_errors(package_json: dict, lock_text: str, module: Starlark, texts: dict[str, str]) -> list[str]:
    errors = []
    declared = {**package_json.get("dependencies", {}), **package_json.get("devDependencies", {})}
    importer = lock_importer(lock_text)
    for name, expected in HOUSE_STACK.items():
        if declared.get(name) != expected:
            errors.append(f"web/package.json {name} is {declared.get(name)!r}, house stack is {expected}")
        locked = importer.get(name, {})
        if locked.get("specifier") != expected or locked.get("version") != expected:
            errors.append(f"web/pnpm-lock.yaml importer {name} is {locked}, house stack is {expected}")
    # Bazel literals that name an npm package version must equal package.json.
    for label, call in [("MODULE.bazel", call) for call in module.calls]:
        package, version = call.kwargs.get("package"), call.kwargs.get("version")
        if isinstance(package, str) and isinstance(version, str) and package in declared | HOUSE_STACK:
            if version != declared.get(package, HOUSE_STACK.get(package)):
                errors.append(f"{label}: {call.name} pins {package} {version}, package.json has {declared.get(package)}")
    names = sorted(set(declared) | set(HOUSE_STACK), key=len, reverse=True)
    token = re.compile(r"(?<![\w@/.-])(" + "|".join(re.escape(n) for n in names) + r")@(\d+\.\d+\.\d+)")
    for label, text in texts.items():
        for name, version in token.findall(text):
            if version != declared.get(name):
                errors.append(f"{label}: literal {name}@{version} differs from package.json {declared.get(name)}")
            if int(version.split(".")[0]) == FORBIDDEN_MAJOR.get(name):
                errors.append(f"{label}: {name}@{version} is a forbidden major (Skeleton 4 / Effect 3)")
    manager = package_json.get("packageManager", "")
    pnpm = [call.kwargs.get("pnpm_version") for call in module.named("pnpm.pnpm")]
    if pnpm and pnpm != [manager.removeprefix("pnpm@").split("+")[0]]:
        errors.append(f"MODULE.bazel pnpm_version {pnpm} differs from packageManager {manager!r}")
    typescript = module.named("typescript.deps")
    if len(typescript) != 1 or typescript[0].kwargs.get("version") != declared.get("typescript"):
        errors.append(f"MODULE.bazel typescript.deps version differs from package.json {declared.get('typescript')!r}")
    for call in typescript:
        integrity = call.kwargs.get("integrity")
        if integrity != lock_integrity(lock_text, "typescript", declared.get("typescript", "")):
            errors.append("MODULE.bazel typescript integrity differs from the typescript integrity in web/pnpm-lock.yaml")
    engines = package_json.get("engines", {}).get("node")
    for call in module.named("node.toolchain"):
        version = call.kwargs.get("node_version", "")
        if not EXACT.match(version) or (engines and not satisfies_engines(version, engines)):
            errors.append(f"MODULE.bazel node_version {version!r} is outside package.json engines {engines!r}")
    return errors


def target_srcs(build: Starlark, rule_names: tuple[str, ...]) -> set[str]:
    covered = set()
    for call in build.named(*rule_names):
        srcs = call.kwargs.get("srcs", [])
        if not isinstance(srcs, list) or not all(isinstance(item, str) for item in srcs):
            raise StarlarkSubsetError(f"{build.label}: {call.name} srcs is not a list of strings")
        covered |= set(srcs)
    return covered


def coverage_errors(root: Path) -> list[str]:
    """Every scripts/**/*.py worker and tests/test_*.py module is in a target or an exclusion with a reason."""
    errors = []
    workers = {path.relative_to(root).as_posix() for path in (root / "scripts").rglob("*.py")
               if "__pycache__" not in path.parts}
    modules = {path.relative_to(root).as_posix() for path in (root / "tests").glob("test_*.py")}
    scripts_build, tests_build = read_build(root, "scripts"), read_build(root, "tests")
    covered_workers = {f"scripts/{name}" for name in target_srcs(scripts_build, ("py_library", "py_binary"))}
    covered_tests = {f"tests/{name}" for name in target_srcs(tests_build, ("unittest_py_tests", "py_test"))}
    document = json.loads((root / "tools/bazel/coverage_exclusions.json").read_text())
    excluded: dict[str, set[str]] = {"worker": set(), "test": set()}
    for entry in document.get("exclusions", []):
        path, kind, reason = entry.get("path"), entry.get("kind"), entry.get("reason")
        if kind not in excluded:
            errors.append(f"exclusion {path!r} has unknown kind {kind!r}")
            continue
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"exclusion {path!r} has no reason")
        if not isinstance(path, str) or not (root / path).is_file():
            errors.append(f"exclusion {path!r} does not name an existing file")
            continue
        excluded[kind].add(path)
    for kind, existing, covered in (("worker", workers, covered_workers), ("test", modules, covered_tests)):
        for path in sorted(existing - covered - excluded[kind]):
            errors.append(f"{kind} {path} is in no Bazel target and has no exclusion")
        for path in sorted(covered & excluded[kind]):
            errors.append(f"{kind} {path} is both covered and excluded")
    return errors


def classification_union(root: Path) -> dict[str, list[str]]:
    """class key -> sorted union of tools/bazel/test_classification.json and the bazel_full supplement."""
    base = json.loads((root / "tools/bazel/test_classification.json").read_text())
    supplement_path = root / "bazel/test_classification_s3_full.json"
    supplement = json.loads(supplement_path.read_text()) if supplement_path.is_file() else {"classes": {}}
    union = {}
    for key in CLASS_TAGS:
        members = set(base.get("classes", {}).get(key, {}).get("modules", []))
        members |= set(supplement.get("classes", {}).get(key, {}).get("modules", []))
        union[key] = sorted(members)
    return union


def supplement_errors(root: Path) -> list[str]:
    errors = []
    document = json.loads((root / "bazel/test_classification_s3_full.json").read_text())
    modules = {path.stem for path in (root / "tests").glob("test_*.py")}
    base = json.loads((root / "tools/bazel/test_classification.json").read_text())
    if document.get("module_count_at_supplement") != len(modules):
        errors.append(f"supplement module_count_at_supplement {document.get('module_count_at_supplement')} != {len(modules)} modules")
    for name in document.get("added_modules", []):
        if name not in modules:
            errors.append(f"supplement added module {name} does not exist")
    for key, tag in CLASS_TAGS.items():
        entry = document.get("classes", {}).get(key)
        if entry is None or entry.get("tag") != tag:
            errors.append(f"supplement class {key} must record tag {tag}")
            continue
        listed = entry.get("modules", [])
        if listed != sorted(set(listed)):
            errors.append(f"supplement {key} list must be sorted and unique")
        for name in listed:
            if name not in modules:
                errors.append(f"supplement {key} lists {name}, which is not a test module")
            if not str(entry.get("reasons", {}).get(name, "")).strip():
                errors.append(f"supplement {key} member {name} has no reason")
            if name in base.get("classes", {}).get(key, {}).get("modules", []):
                errors.append(f"supplement {key} repeats {name} from tools/bazel/test_classification.json")
    if document.get("manual", {}).get("modules"):
        errors.append("the supplement may not add a manual module")
    return errors


def classification_errors(root: Path) -> list[str]:
    errors = []
    build = read_build(root, "tests")
    document = json.loads((root / "tools/bazel/test_classification.json").read_text())
    union = classification_union(root)
    modules = {path.stem for path in (root / "tests").glob("test_*.py")}
    macros = build.named("unittest_py_tests")
    if len(macros) != 1:
        return [f"tests/BUILD.bazel must call unittest_py_tests exactly once, found {len(macros)}"]
    macro_text = (root / "tools/bazel/python.bzl").read_text()
    for key, tag in CLASS_TAGS.items():
        recorded = document.get("classes", {}).get(key, {})
        listed = macros[0].kwargs.get(key, [])
        if recorded.get("tag") != tag:
            errors.append(f"classification {key} must record tag {tag}")
        if union[key] != sorted(listed):
            errors.append(f"tests/BUILD.bazel {key} list differs from the union of tools/bazel/test_classification.json "
                          f"and bazel/test_classification_s3_full.json")
        if listed != sorted(set(listed)):
            errors.append(f"{key} list must be sorted and unique")
        for name in sorted(set(listed) - modules):
            errors.append(f"{key} lists {name}, which is not a test module")
        if not re.search(rf'if name in {key}:\n\s+tags\.append\("{re.escape(tag)}"\)', macro_text):
            errors.append(f"tools/bazel/python.bzl does not map {key} to the tag {tag}")
    if '"no-sandbox"' not in macro_text or '"python-unittest"' not in macro_text:
        errors.append("every unittest target must carry python-unittest and the recorded no-sandbox tag")
    if not document.get("all_modules", {}).get("reason", "").strip():
        errors.append("the no-sandbox tag needs a recorded reason")
    return errors


def rust_errors(root: Path) -> list[str]:
    errors = []
    channel = tomllib.loads((root / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    module = read_module(root)
    toolchains = module.named("rust.toolchain")
    if len(toolchains) != 1:
        return [f"MODULE.bazel must declare exactly one rust.toolchain, found {len(toolchains)}"]
    if toolchains[0].kwargs.get("versions") != [channel]:
        errors.append(f"rust.toolchain versions {toolchains[0].kwargs.get('versions')} != rust-toolchain.toml {channel}")
    constants = Starlark((root / "tools/bazel/rust.bzl").read_text(), repo_root=root, label="tools/bazel/rust.bzl").names
    crates = {"src": root / "Cargo.toml", "native/au-spike": root / "native/au-spike/Cargo.toml"}
    for package, manifest_path in crates.items():
        manifest = tomllib.loads(manifest_path.read_text())["package"]
        if not channel.startswith(manifest["rust-version"]):
            errors.append(f"{manifest_path.name} rust-version {manifest['rust-version']} is not toolchain {channel}")
        for label, value in (("edition", toolchains[0].kwargs.get("edition")), ("RUST_EDITION", constants.get("RUST_EDITION"))):
            if value != manifest["edition"]:
                errors.append(f"{package}: {label} {value!r} != Cargo edition {manifest['edition']!r}")
        if constants.get("CRATE_VERSION") != manifest["version"]:
            errors.append(f"{package}: CRATE_VERSION {constants.get('CRATE_VERSION')!r} != Cargo version {manifest['version']!r}")
        for call in read_build(root, package).named("rust_library", "rust_binary", "rust_static_library", "rust_test"):
            if call.kwargs.get("edition") != manifest["edition"]:
                errors.append(f"//{package}:{call.kwargs.get('name')} edition is {call.kwargs.get('edition')!r}")
    for call in read_build(root, "tests").named("rust_test"):
        if call.kwargs.get("edition") != constants.get("RUST_EDITION"):
            errors.append(f"//tests:{call.kwargs.get('name')} edition is {call.kwargs.get('edition')!r}")
    return errors


def rust_target_inventory(root: Path) -> dict[str, bool]:
    """The six crate targets of contract metric 7."""
    src, tests, ffi = read_build(root, "src"), read_build(root, "tests"), read_build(root, "native/au-spike")

    def has(build: Starlark, rule: str, **wanted) -> bool:
        return any(all(call.kwargs.get(key) == value for key, value in wanted.items()) for call in build.named(rule))

    return {
        "video-utils lib": has(src, "rust_library", name="video_utils", crate_root="lib.rs"),
        "video-utils bin": has(src, "rust_binary", name="video-utils", srcs=["main.rs"]),
        "tests/cli.rs": has(tests, "rust_test", srcs=["cli.rs"]),
        "tests/dsp.rs": has(tests, "rust_test", srcs=["dsp.rs"]),
        "video-utils-gain-ffi lib": has(ffi, "rust_library", name="video_utils_gain_ffi", srcs=["src/lib.rs"])
        and has(ffi, "rust_static_library", crate_name="video_utils_gain_ffi", srcs=["src/lib.rs"]),
        "biquad_ffi.rs": has(ffi, "rust_test", srcs=["tests/biquad_ffi.rs"]),
    }


def registry_errors(module: Starlark, web_build: Starlark, document: dict, pinned_commit: str | None) -> list[str]:
    errors = []
    registry = document.get("registry", {})
    if registry.get("commit") != pinned_commit:
        errors.append(f"registry_modules.json commit {registry.get('commit')} != .bazelrc pin {pinned_commit}")
    known = document.get("modules", {})
    if registry.get("module_count") != len(known):
        errors.append("registry module_count differs from the recorded module list")
    decisions = {entry.get("module"): entry for entry in document.get("decisions", [])}
    for name, entry in decisions.items():
        if entry.get("decision") not in DECISIONS:
            errors.append(f"{name}: unknown decision {entry.get('decision')!r}")
        if not entry.get("evidence") or not entry.get("reasons"):
            errors.append(f"{name}: a decision needs evidence and reasons")
        if name not in known:
            errors.append(f"{name}: decided module is not in the recorded registry listing")
    not_evaluated = document.get("not_evaluated", {})
    if not_evaluated.get("count") != len(not_evaluated.get("modules", [])):
        errors.append("not_evaluated count differs from its module list")
    if set(decisions) & set(not_evaluated.get("modules", [])):
        errors.append("a module is both decided and not evaluated")
    if set(decisions) | set(not_evaluated.get("modules", [])) != set(known):
        errors.append("decisions + not_evaluated must partition the registry listing")
    deps = bazel_deps(module)
    consumed = sorted(name for name in deps if name in known)
    if consumed != sorted(document.get("consumed", [])):
        errors.append(f"registry modules in MODULE.bazel {consumed} != recorded consumed {document.get('consumed')}")
    for name in consumed:
        entry = decisions.get(name)
        if not entry or entry.get("decision") != "consumed":
            errors.append(f"bazel_dep {name} is a Tinyland registry module without a `consumed` decision")
            continue
        closure = [entry] + [decisions.get(item.split("@")[0], {}) for item in entry.get("closure", [])]
        for member in closure:
            if not member:
                errors.append(f"{name}: a closure member has no recorded decision")
            elif member.get("pins_skeleton_4") is not False or member.get("pins_effect_3") is not False:
                errors.append(f"{name}: closure member {member.get('module')} pins Skeleton 4 or Effect 3, or is unverified")
    for call in web_build.named("npm_link_package"):
        source = call.kwargs.get("src", "")
        match = re.match(r"^@([A-Za-z0-9_.-]+)//", source)
        if not match or match.group(1) not in deps:
            errors.append(f"npm_link_package src {source!r} has no matching bazel_dep")
        elif match.group(1) not in consumed:
            errors.append(f"npm_link_package src {source!r} is not a recorded consumed registry module")
    return errors


def just_errors(text: str) -> list[str]:
    errors = []
    for recipe in RECIPES:
        if not re.search(rf"^{re.escape(recipe)}\b[^\n]*:\s*$", text, re.MULTILINE):
            errors.append(f"just/bazel.just does not define {recipe}")
    for flag in REMOTE_FLAGS:
        if any(flag in line for line in text.splitlines() if not line.lstrip().startswith("#")):
            errors.append(f"just/bazel.just contains {flag}")
    if "tools/bazel/run.py" not in text:
        errors.append("recipes must go through the bounded launcher tools/bazel/run.py")
    return errors


def load_launcher(root: Path):
    spec = importlib.util.spec_from_file_location("bazel_graph_launcher", root / "tools/bazel/run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- bazel_full checkers (//site, gate, registers)

SITE_GATE_LINES = ("common --ignore_dev_dependency", "common --deleted_packages=site")
SITE_VENDOR_TEST_IGNORE = "site/vendor/xoxd-theme/test"
SITE_HOUSE_STACK = {"@skeletonlabs/skeleton": "5.0.1", "@skeletonlabs/skeleton-svelte": "5.0.1"}
SITE_TYPESCRIPT = "6.0.3"
SITE_TARGETS = {"svelte_check_test": "js_test", "build": "js_run_binary", "sveltekit_types": "js_run_binary"}
FAILURE_CLASSES = ("dot_path_component", "macos_process_inspection", "other")
FAILURE_KEYS = ("case", "target", "class", "bazel_outcome", "first_error_line", "plain_unittest_repro",
                "control_repro", "baseline_repro", "cause", "claim_class")
SKIP_TOKENS = ("manual", "expectedFailure", "SkipTest", "skipTest", "unittest.skip", "known_host_failures")
DEFAULT_RC_FILTERS = ("--test_tag_filters", "--test_filter", "--build_tag_filters", "--test_lang_filters")


def private_needles() -> list[str]:
    """Private-tree and recording needles, assembled so this file never contains them literally."""
    return ["".join(("art", "ifacts", "/")), "".join((".loc", "al/sprint")), "".join(("Mov", "ie on ")),
            "".join(("/Us", "ers/"))]


def site_gate(root: Path) -> dict:
    """State of the .bazelrc site gate and of the two root-owned prerequisites it stands in for."""
    lines = rc_lines((root / ".bazelrc").read_text())
    present = [line for line in SITE_GATE_LINES if line in lines]
    workspace = root / "site/pnpm-workspace.yaml"
    allow_builds = workspace.is_file() and re.search(r"^allowBuilds:", workspace.read_text(), re.MULTILINE) is not None
    ignored = [line.strip() for line in (root / ".bazelignore").read_text().splitlines() if line.strip()]
    vendor_exposed = "site/vendor" not in ignored and SITE_VENDOR_TEST_IGNORE in ignored
    state = {2: "gated", 0: "open"}.get(len(present), "partial")
    errors = []
    if state == "partial":
        errors.append(f"site gate is half applied: {present}")
    if state == "gated" and allow_builds and vendor_exposed:
        errors.append("site prerequisites are applied; remove the two .bazelrc site gate lines")
    if state == "open" and not (allow_builds and vendor_exposed):
        errors.append("site gate removed before site/pnpm-workspace.yaml allowBuilds and the .bazelignore change landed")
    if state == "gated":
        usage = Starlark((root / "MODULE.bazel").read_text(), repo_root=root, label="MODULE.bazel").names.get("npm_site")
        if not isinstance(usage, Call) or usage.kwargs.get("dev_dependency") is not True:
            errors.append("while gated, the npm_site translation must sit in a dev_dependency = True usage")
    return {"state": state, "allow_builds": allow_builds, "vendor_exposed": vendor_exposed, "errors": errors}


def vendored_carrier_dirs(root: Path) -> list[str]:
    document = json.loads((root / "site/vendor/PROVENANCE.json").read_text())
    return sorted("site/" + carrier["directory"] for carrier in document.get("carriers", []))


def stray_bazel_files(paths: list[str], ignored: list[str], gate_state: str, root: Path | None = None) -> list[str]:
    """Tracked Bazel boundary files outside this graph's packages and outside every ignored tree."""
    root = root or ROOT
    names = {"BUILD", "BUILD.bazel", "MODULE.bazel", "WORKSPACE", "WORKSPACE.bazel", "REPO.bazel"}
    carriers = vendored_carrier_dirs(root) if gate_state == "open" else []
    stray = []
    for path in paths:
        directory, _, name = path.rpartition("/")
        if name not in names or (directory in OWNED_PACKAGES and name in ("BUILD.bazel", "MODULE.bazel")):
            continue
        if directory in carriers and name in ("BUILD.bazel", "MODULE.bazel"):
            continue  # provenance-bound vendored carrier packages, exposed once the gate is open
        if not any(directory == tree or directory.startswith(tree + "/") for tree in ignored):
            stray.append(path)
    return stray


def site_build_errors(root: Path, text: str | None = None) -> list[str]:
    errors = []
    text = text if text is not None else (root / "site/BUILD.bazel").read_text()
    build = Starlark(text, package_dir=root / "site", repo_root=root, label="site/BUILD.bazel")
    loads = [call.args[0] for call in build.named("load") if call.args]
    if "@npm_site//:defs.bzl" not in loads:
        errors.append("site/BUILD.bazel must load @npm_site//:defs.bzl")
    if any(source.startswith("@npm//") for source in loads):
        errors.append("site/BUILD.bazel must not link web's @npm packages")
    rules = {call.kwargs.get("name"): call.name for call in build.calls}
    for name, rule in SITE_TARGETS.items():
        if rules.get(name) != rule:
            errors.append(f"site/BUILD.bazel needs {rule} {name}, found {rules.get(name)}")
    if len(build.named("npm_link_all_packages")) != 1:
        errors.append("site/BUILD.bazel must call npm_link_all_packages once")
    package = json.loads((root / "site/package.json").read_text())
    declared = {f":node_modules/{name}" for name in {**package.get("dependencies", {}), **package.get("devDependencies", {})}}
    if set(build.names.get("SITE_NPM_PACKAGES", [])) != declared:
        errors.append("SITE_NPM_PACKAGES differs from site/package.json dependencies + devDependencies")
    for needle in private_needles():
        if needle in text:
            errors.append(f"site/BUILD.bazel contains a private-tree needle ({len(needle)} chars)")
    return errors


def site_pin_errors(root: Path, module: Starlark, lock_text: str | None = None, package: dict | None = None) -> list[str]:
    errors = []
    package = package if package is not None else json.loads((root / "site/package.json").read_text())
    lock_text = lock_text if lock_text is not None else (root / "site/pnpm-lock.yaml").read_text()
    declared = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    importer = lock_importer(lock_text)
    for name, expected in SITE_HOUSE_STACK.items():
        if declared.get(name) != expected:
            errors.append(f"site/package.json {name} is {declared.get(name)!r}, house stack is {expected}")
        locked = importer.get(name, {})
        if locked.get("specifier") != expected or locked.get("version") != expected:
            errors.append(f"site/pnpm-lock.yaml importer {name} is {locked}, house stack is {expected}")
    if "effect" in declared and (declared["effect"] != "4.0.1" or importer.get("effect", {}).get("version") != "4.0.1"):
        errors.append(f"site effect must be absent or exactly 4.0.1, found {declared['effect']!r}")
    if declared.get("typescript") != SITE_TYPESCRIPT or importer.get("typescript", {}).get("version") != SITE_TYPESCRIPT:
        errors.append(f"site typescript must be {SITE_TYPESCRIPT} in package.json and the lock importer")
    for name, major in FORBIDDEN_MAJOR.items():
        if re.search(rf"^  '?{re.escape(name)}@{major}\.", lock_text, re.MULTILINE):
            errors.append(f"site/pnpm-lock.yaml resolves {name}@{major}.x (Skeleton 4 / Effect 3)")
    manager = package.get("packageManager", "")
    pnpm = [call.kwargs.get("pnpm_version") for call in module.named("pnpm.pnpm")]
    if pnpm != [manager.removeprefix("pnpm@").split("+")[0]]:
        errors.append(f"MODULE.bazel pnpm_version {pnpm} differs from site packageManager {manager!r}")
    engines = package.get("engines", {}).get("node")
    for call in module.named("node.toolchain"):
        version = call.kwargs.get("node_version", "")
        if not EXACT.match(version) or (engines and not satisfies_engines(version, engines)):
            errors.append(f"MODULE.bazel node_version {version!r} is outside site engines {engines!r}")
    return errors


def case_exists(root: Path, case: str) -> bool:
    """module.Class.method names a class defined in tests/<module>.py that has (or inherits in-module) the method."""
    parts = case.split(".")
    if len(parts) != 3:
        return False
    module, cls, method = parts
    path = root / "tests" / f"{module}.py"
    if not path.is_file():
        return False
    tree = ast.parse(path.read_text())
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}

    def has(name: str, seen: set) -> bool:
        node = classes.get(name)
        if node is None or name in seen:
            return False
        seen.add(name)
        if any(isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method for item in node.body):
            return True
        return any(isinstance(base, ast.Name) and has(base.id, seen) for base in node.bases)

    return cls in classes and has(cls, set())


def known_failure_errors(root: Path, document: dict) -> list[str]:
    errors = []
    entries = document.get("entries")
    if not isinstance(entries, list):
        return ["known_host_failures.json needs an entries list"]
    for index, entry in enumerate(entries):
        label = entry.get("case", f"entry {index}")
        missing = [key for key in FAILURE_KEYS if key not in entry]
        if missing:
            errors.append(f"{label}: missing {missing}")
            continue
        if not case_exists(root, entry["case"]):
            errors.append(f"{label}: does not name an existing tests/<module>.py Class.method")
        if entry["target"] != "//tests:" + entry["case"].split(".")[0]:
            errors.append(f"{label}: target {entry['target']} does not match the module")
        if entry["class"] not in FAILURE_CLASSES:
            errors.append(f"{label}: unknown class {entry['class']!r}")
        if entry["bazel_outcome"] not in ("FAIL", "ERROR"):
            errors.append(f"{label}: bazel_outcome must be FAIL or ERROR")
        if not isinstance(entry["first_error_line"], str) or not entry["first_error_line"].strip():
            errors.append(f"{label}: first_error_line must be the verbatim line")
        repro = entry["plain_unittest_repro"]
        if not isinstance(repro, dict) or not {"command", "cwd", "outcome"} <= set(repro) \
                or repro.get("outcome") not in ("FAIL", "ERROR", "PASS"):
            errors.append(f"{label}: plain_unittest_repro needs command, cwd and a FAIL/ERROR/PASS outcome")
        elif repro["outcome"] == "PASS":
            errors.append(f"{label}: passes under plain unittest, so it is a Bazel-graph defect, not a host failure")
        for key, fields in (("control_repro", {"path_kind", "outcome"}), ("baseline_repro", {"commit", "outcome"})):
            value = entry[key]
            if value is not None and (not isinstance(value, dict) or not fields <= set(value)):
                errors.append(f"{label}: {key} must be null or carry {sorted(fields)}")
        if not isinstance(entry["cause"], str) or not entry["cause"].strip():
            errors.append(f"{label}: cause is empty")
        if entry["claim_class"] not in ("M", "I"):
            errors.append(f"{label}: claim_class must be M or I")
    for item in document.get("not_reproduced", []):
        if not isinstance(item, dict) or not item.get("prediction") or not item.get("evidence"):
            errors.append("not_reproduced items need a prediction and evidence")
    return errors


def register_reference_errors(root: Path) -> list[str]:
    """The register is documentation only: no BUILD, MODULE or .bzl file may read it."""
    errors = []
    pruned = {".git", ".local", "artifacts", "node_modules", "target", "vendor", ".svelte-kit", "build", "data",
              "models", "__pycache__"}
    for current, directories, files in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in pruned)
        for name in files:
            if name in ("BUILD.bazel", "BUILD", "MODULE.bazel") or name.endswith(".bzl"):
                path = Path(current) / name
                if "known_host_failures" in path.read_text(errors="replace"):
                    errors.append(f"{path.relative_to(root).as_posix()} references the known-host-failure register")
    return errors


def skip_mechanism_errors(tests_build: str, macros: str, shim: str, bazelrc: str) -> list[str]:
    """No manual tag, case-level skip, expected-failure or default filter hides a failing target."""
    errors = []
    if re.search(r'"manual"', tests_build):
        errors.append("tests/BUILD.bazel tags a target manual")
    for label, text in (("tools/bazel/python.bzl", macros), ("tools/bazel/unittest_main.py", shim)):
        for token in SKIP_TOKENS:
            if token in text:
                errors.append(f"{label} contains {token!r}")
    for line in rc_lines(bazelrc):
        command = line.split()[0]
        if ":" in command:
            continue  # a named config is opt-in
        for flag in DEFAULT_RC_FILTERS:
            if flag in line:
                errors.append(f".bazelrc default line filters tests: {line}")
    return errors


def load_lane_helper(root: Path, name: str):
    spec = importlib.util.spec_from_file_location(f"bazel_full_{name}", root / "bazel" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- tests on the repository tree


class GraphFilesTest(unittest.TestCase):
    def test_required_graph_files_exist(self):
        missing = [name for name in REQUIRED_FILES + HELPER_FILES + LANE_FILES if not (ROOT / name).is_file()]
        self.assertEqual(missing, [])
        self.assertEqual(len(REQUIRED_FILES), 13)

    def test_bazelversion_is_one_exact_version(self):
        text = (ROOT / ".bazelversion").read_text()
        self.assertRegex(text, r"\A\d+\.\d+\.\d+\n\Z")

    def test_bazelignore_keeps_private_and_generated_trees_out(self):
        ignored = set((ROOT / ".bazelignore").read_text().split())
        self.assertEqual([tree for tree in IGNORED_TREES if tree not in ignored], [])

    def test_foreign_bazel_packages_are_ignored_so_wildcard_patterns_load(self):
        """Vendored trees carry their own MODULE.bazel/BUILD.bazel (another module's labels).

        `bazel build //...` loads every un-ignored BUILD file, so one outside this graph's packages
        breaks the default `just bazel-build` / `just bazel-test` pattern at analysis time.
        """
        import subprocess
        listed = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, timeout=60)
        if listed.returncode != 0:
            self.skipTest("not a git checkout; tracked-file inventory unavailable (skip is not a pass)")
        ignored = [line.strip() for line in (ROOT / ".bazelignore").read_text().splitlines() if line.strip()]
        self.assertEqual(stray_bazel_files(listed.stdout.decode().split("\0"), ignored, site_gate(ROOT)["state"]), [])
        for tree in ("site/node_modules", "site/build", "site/.svelte-kit"):
            self.assertIn(tree, ignored)

    def test_every_bazel_file_is_inside_the_starlark_subset(self):
        read_module(ROOT)
        for package in OWNED_PACKAGES:
            with self.subTest(package=package or "//"):
                read_build(ROOT, package)

    def test_module_lock_is_json_when_present(self):
        lock = ROOT / "MODULE.bazel.lock"
        if not lock.exists():
            self.skipTest("MODULE.bazel.lock absent: Bazel has not resolved the graph in this tree (allowed, recorded)")
        document = json.loads(lock.read_text())
        self.assertIn("lockFileVersion", document)
        pinned = registry_commit((ROOT / ".bazelrc").read_text())
        house = [key for key in document.get("registryFileHashes", {}) if "/bazel-registry/" in key]
        self.assertTrue(house, "the lock records no lookup against the Tinyland registry")
        self.assertEqual([key for key in house if f"/tinyland-inc/bazel-registry/{pinned}/" not in key], [],
                         "MODULE.bazel.lock was generated against a different registry pin than .bazelrc")


class RegistryOrderTest(unittest.TestCase):
    def test_bazelrc_registry_order_and_no_remote_backend(self):
        self.assertEqual(bazelrc_errors((ROOT / ".bazelrc").read_text()), [])

    def test_registry_pin_matches_recorded_registry_commit(self):
        document = json.loads((ROOT / "tools/bazel/registry_modules.json").read_text())
        self.assertEqual(registry_commit((ROOT / ".bazelrc").read_text()), document["registry"]["commit"])

    def test_bazel_dep_closure_declares_rule_modules_with_literal_versions(self):
        self.assertEqual(module_errors(read_module(ROOT)), [])


class VersionIdentityTest(unittest.TestCase):
    def test_house_stack_pins_are_identical_across_package_json_lock_and_bazel(self):
        errors = npm_pin_errors(json.loads((ROOT / "web/package.json").read_text()),
                                (ROOT / "web/pnpm-lock.yaml").read_text(), read_module(ROOT), bazel_texts(ROOT))
        self.assertEqual(errors, [])

    def test_web_build_links_exactly_the_package_json_dependencies(self):
        package = json.loads((ROOT / "web/package.json").read_text())
        declared = {f":node_modules/{name}" for name in {**package["dependencies"], **package["devDependencies"]}}
        build = read_build(ROOT, "web")
        self.assertEqual(set(build.names["APP_NPM_PACKAGES"]), declared)
        self.assertEqual(len(build.named("npm_link_all_packages")), 1)

    def test_rust_toolchain_and_edition_match_cargo(self):
        self.assertEqual(rust_errors(ROOT), [])

    def test_six_crate_targets_exist(self):
        inventory = rust_target_inventory(ROOT)
        self.assertEqual(len(inventory), 6)
        self.assertEqual([name for name, present in inventory.items() if not present], [])

    def test_every_root_crate_source_is_in_a_target(self):
        build = read_build(ROOT, "src")
        covered = target_srcs(build, ("rust_library", "rust_binary"))
        self.assertEqual(sorted(path.name for path in (ROOT / "src").glob("*.rs") if path.name not in covered), [])

    def test_hermetic_python_meets_pyproject_floor(self):
        floor = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["requires-python"]
        toolchains = read_module(ROOT).named("python.toolchain")
        self.assertEqual(len(toolchains), 1)
        self.assertTrue(satisfies_engines(toolchains[0].kwargs["python_version"], floor))
        self.assertNotIn("pip.parse", [call.name for call in read_module(ROOT).calls])


class CoverageTest(unittest.TestCase):
    def test_every_worker_and_test_module_is_covered_or_excluded_with_reason(self):
        self.assertEqual(coverage_errors(ROOT), [])

    def test_classification_lists_match_the_recorded_classification_and_tags(self):
        self.assertEqual(classification_errors(ROOT), [])

    def test_classification_supplement_covers_the_added_modules_with_reasons(self):
        self.assertEqual(supplement_errors(ROOT), [])

    def test_python_tests_do_not_depend_on_the_web_package(self):
        macro = read_build(ROOT, "tests").named("unittest_py_tests")[0]
        self.assertEqual([label for label in macro.kwargs["data"] if label.startswith("//web")], [])


class RegistryModulesTest(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((ROOT / "tools/bazel/registry_modules.json").read_text())

    def test_no_unrecorded_or_noncompliant_registry_module_is_consumed(self):
        errors = registry_errors(read_module(ROOT), read_build(ROOT, "web"), self.document,
                                 registry_commit((ROOT / ".bazelrc").read_text()))
        self.assertEqual(errors, [])

    def test_named_candidates_and_their_closure_are_decided(self):
        decided = {entry["module"] for entry in self.document["decisions"]}
        for name in ("xoxd_spectrogram", "xoxd_theme", "xoxd_public_chrome", "tummycrypt_tinyland_composables",
                     "tummycrypt_tinyland_color_utils"):
            self.assertIn(name, decided)
        self.assertEqual(self.document["claim_classes"]["dependency_edges"].split(":")[0], "unknown")


class RecipesTest(unittest.TestCase):
    def test_just_recipes_exist_without_remote_backend(self):
        self.assertEqual(just_errors((ROOT / "just/bazel.just").read_text()), [])

    def test_launcher_refuses_remote_backends_and_bounds_the_run(self):
        launcher = load_launcher(ROOT)
        self.assertEqual(launcher.refused_flags(["build", "//...", "--remote_cache=grpc://cache"]),
                         ["--remote_cache=grpc://cache"])
        self.assertEqual(launcher.refused_flags(["test", "--remote_executor=grpc://x", "--bes_backend=y"]),
                         ["--remote_executor=grpc://x", "--bes_backend=y"])
        self.assertEqual(launcher.refused_flags(["build", "//src:all", "--remote_cache="]), [])
        self.assertEqual(launcher.parse(["--timeout", "30", "mod", "graph"]), (30, False, ["mod", "graph"]))
        self.assertEqual(launcher.DEFAULT_TIMEOUT_S, 1800)
        for bad in ([], ["--timeout", "0", "build"], ["--timeout"]):
            with self.assertRaises(ValueError):
                launcher.parse(bad)
        self.assertEqual(launcher.main(["build", "--remote_cache=grpc://cache"]), launcher.EXIT_USAGE)


class ShimSelfTest(unittest.TestCase):
    def test_marker_case_runs_only_under_the_shim(self):
        if os.environ.get(SHIM_MARKER_ENV) != "1":
            self.skipTest("marker case: selected by the shim self-check below")
        self.assertEqual(Path.cwd().resolve(), ROOT)

    def test_unittest_shim_runs_one_module_from_the_repository_root(self):
        if os.environ.get(SHIM_MARKER_ENV) == "1":
            self.skipTest("already inside the shim self-check")
        environment = {**os.environ, SHIM_MARKER_ENV: "1", "TESTBRIDGE_TEST_ONLY": "test_marker_case"}
        with tempfile.TemporaryDirectory() as elsewhere:
            done = subprocess.run([sys.executable, str(ROOT / "tools/bazel/unittest_main.py"), "test_bazel_graph_s3"],
                                  cwd=elsewhere, env=environment, capture_output=True, text=True,
                                  timeout=SHIM_TIMEOUT_S)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stderr, r"Ran 1 test")
        self.assertIn("test_marker_case_runs_only_under_the_shim", done.stderr)
        self.assertNotIn("skipped", done.stderr.splitlines()[-1])
        refused = subprocess.run([sys.executable, str(ROOT / "tools/bazel/unittest_main.py"), "not_a_test"],
                                 cwd=ROOT, capture_output=True, text=True, timeout=SHIM_TIMEOUT_S)
        self.assertNotEqual(refused.returncode, 0)


class SiteGraphTest(unittest.TestCase):
    """bazel_full contract section 12: //site, the site gate and the second translation."""

    def test_site_package_declares_check_and_build_without_private_needles(self):
        self.assertEqual(site_build_errors(ROOT), [])

    def test_site_gate_matches_the_root_owned_prerequisites(self):
        gate = site_gate(ROOT)
        self.assertIn(gate["state"], ("gated", "open"))
        self.assertEqual(gate["errors"], [])

    def test_site_house_stack_pins(self):
        self.assertEqual(site_pin_errors(ROOT, read_module(ROOT)), [])

    def test_two_translations_each_on_its_own_lock(self):
        module = read_module(ROOT)
        locks = {call.kwargs["name"]: call.kwargs["pnpm_lock"] for call in module.calls
                 if call.name.endswith(".npm_translate_lock")}
        self.assertEqual(locks, {"npm": "//web:pnpm-lock.yaml", "npm_site": "//site:pnpm-lock.yaml"})
        self.assertEqual(local_override_errors(module), [])

    def test_site_build_runner_is_exported_and_shared_runner_reused(self):
        site = read_build(ROOT, "site")
        sources = {call.kwargs.get("name"): call.kwargs.get("src") for call in site.named("copy_file")}
        self.assertEqual(sources.get("sveltekit_runner"), "//tools/bazel:web/sveltekit.mjs")
        self.assertEqual(sources.get("site_build_runner"), "//bazel:site_build.mjs")
        exported = [name for call in read_build(ROOT, "bazel").named("exports_files") for name in call.args[0]]
        self.assertIn("site_build.mjs", exported)


class RegisterTest(unittest.TestCase):
    """bazel_full contract section 7: the known-host-failure register is complete and documentation only."""

    def test_known_host_failure_register_schema_and_cases(self):
        document = json.loads((ROOT / "bazel/known_host_failures.json").read_text())
        self.assertEqual(document.get("schema"), "vu.bazel_full.known_host_failures.v1")
        self.assertEqual(known_failure_errors(ROOT, document), [])

    def test_no_bazel_file_reads_the_register(self):
        self.assertEqual(register_reference_errors(ROOT), [])

    def test_no_manual_tag_skip_or_default_filter_hides_a_target(self):
        errors = skip_mechanism_errors((ROOT / "tests/BUILD.bazel").read_text(),
                                       (ROOT / "tools/bazel/python.bzl").read_text(),
                                       (ROOT / "tools/bazel/unittest_main.py").read_text(),
                                       (ROOT / ".bazelrc").read_text())
        self.assertEqual(errors, [])


class LaneHelperTest(unittest.TestCase):
    """The bazel_full helpers on synthetic inputs (no Bazel run, no load reading of this host)."""

    LOG = "\n".join((
        "test_alpha (test_x.AlphaTest.test_alpha) ... ok",
        "test_beta (test_x.AlphaTest.test_beta)",
        "Docstring first line ... FAIL",
        "test_gamma (test_x.AlphaTest.test_gamma) ... skipped 'FFMPEG is not set'",
        "test_delta (test_x.AlphaTest.test_delta) ... ERROR",
        "",
        "======================================================================",
        "ERROR: test_delta (test_x.AlphaTest.test_delta)",
        "----------------------------------------------------------------------",
        "Traceback (most recent call last):",
        '  File "x.py", line 1, in test_delta',
        "    raise ValueError('path component starts with a dot')",
        "ValueError: path component starts with a dot",
        "",
        "======================================================================",
        "FAIL: test_beta (test_x.AlphaTest.test_beta)",
        "Docstring first line",
        "----------------------------------------------------------------------",
        "Traceback (most recent call last):",
        '  File "x.py", line 2, in test_beta',
        "AssertionError: 1 != 2",
        "",
        "----------------------------------------------------------------------",
        "Ran 4 tests in 0.010s",
        "",
        "FAILED (failures=1, errors=1, skipped=1)",
    ))

    def test_unittest_log_parse_counts_reasons_and_first_error_lines(self):
        report = load_lane_helper(ROOT, "full_run_report")
        parsed = report.parse_unittest_log(self.LOG)
        self.assertTrue(parsed["parsed"])
        self.assertEqual((parsed["ran"], parsed["failures"], parsed["errors"], parsed["skipped"]), (4, 1, 1, 1))
        self.assertEqual(parsed["skip_reasons"], {"FFMPEG is not set": 1})
        self.assertEqual(parsed["failing_cases"], [
            {"case": "test_x.AlphaTest.test_delta", "kind": "ERROR",
             "first_error_line": "ValueError: path component starts with a dot"},
            {"case": "test_x.AlphaTest.test_beta", "kind": "FAIL", "first_error_line": "AssertionError: 1 != 2"},
        ])
        self.assertFalse(report.parse_unittest_log("no summary here")["parsed"])

    def test_bep_report_gives_every_denominator_target_one_status(self):
        report = load_lane_helper(ROOT, "full_run_report")
        events = [
            {"id": {"started": {}}, "started": {"command": "test"}},
            {"id": {"testSummary": {"label": "//tests:test_x"}},
             "testSummary": {"overallStatus": "FAILED", "attemptCount": 1, "totalRunDurationMillis": "1200"}},
            {"id": {"testSummary": {"label": "//tests:test_y"}}, "testSummary": {"overallStatus": "PASSED"}},
            {"id": {"targetCompleted": {"label": "//web:svelte_check_test"}},
             "aborted": {"reason": "ANALYSIS_FAILURE"}},
            {"id": {"buildFinished": {}}, "finished": {"exitCode": {"name": "TESTS_FAILED", "code": 3}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "bep.json").write_text("\n".join(json.dumps(event) for event in events) + "\n")
            (base / "targets.txt").write_text("//tests:test_x\n//tests:test_y\n//web:svelte_check_test\n//src:t\n")
            (base / "logs/tests/test_x").mkdir(parents=True)
            (base / "logs/tests/test_x/test.log").write_text(self.LOG)
            document = report.build_report(base / "bep.json", base / "targets.txt", base / "logs")
        self.assertEqual(document["denominator_targets"], 4)
        statuses = {row["target"]: row["status"] for row in document["targets"]}
        self.assertEqual(statuses, {"//tests:test_x": "FAILED", "//tests:test_y": "PASSED",
                                    "//web:svelte_check_test": "NO_STATUS", "//src:t": "NO_STATUS"})
        rows = {row["target"]: row for row in document["targets"]}
        self.assertEqual(rows["//web:svelte_check_test"]["reason"], "ANALYSIS_FAILURE")
        self.assertEqual(rows["//tests:test_x"]["unittest"]["errors"], 1)
        self.assertFalse(rows["//tests:test_y"]["unittest"]["parsed"])
        self.assertEqual(document["bep"]["exit_code"], 3)
        self.assertEqual(sum(document["status_counts"].values()), 4)

    def test_host_gate_waits_logs_and_blocks(self):
        gate = load_lane_helper(ROOT, "host_gate")
        clock = iter(range(0, 10_000, 30))
        now = [0.0]

        def tick():
            now[0] = float(next(clock))
            return now[0]

        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "gate.jsonl"
            loads = iter([(40.0, 0, 0), (30.0, 0, 0), (12.0, 0, 0)])
            self.assertEqual(gate.gate("s", log, 24.0, 600, 60, clock=tick, load=lambda: next(loads),
                                       pause=lambda _: None), gate.EXIT_OPEN)
            readings = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual([r["open"] for r in readings], [False, False, True])
            blocked = Path(directory) / "blocked.jsonl"
            self.assertEqual(gate.gate("s", blocked, 24.0, 100, 60, clock=tick, load=lambda: (99.0, 0, 0),
                                       pause=lambda _: None), gate.EXIT_BLOCKED)
            self.assertIn("blocked_on_host", blocked.read_text())


# --------------------------------------------------------------------------- negative self-checks (no tree mutation)


class NegativeSelfChecks(unittest.TestCase):
    def test_bazel_full_negative_self_checks(self):
        module_text = (ROOT / "MODULE.bazel").read_text()
        third = module_text + ('npm.npm_translate_lock(name = "npm_extra", pnpm_lock = "//extra:pnpm-lock.yaml", '
                               'npmrc = "//extra:.npmrc", data = ["//extra:package.json"])\n')
        self.assertTrue(any("npm_translate_lock calls" in e for e in module_errors(Starlark(third, repo_root=ROOT))))
        effect3 = (ROOT / "site/pnpm-lock.yaml").read_text() + "\n  effect@3.22.1:\n    resolution: {integrity: x}\n"
        self.assertTrue(any("Effect 3" in e for e in site_pin_errors(ROOT, read_module(ROOT), lock_text=effect3)))
        package = json.loads((ROOT / "site/package.json").read_text())
        package["devDependencies"]["@skeletonlabs/skeleton"] = "4.15.2"
        self.assertTrue(site_pin_errors(ROOT, read_module(ROOT), package=package))
        outside = module_text + 'local_path_override(module_name = "xoxd_theme", path = "../elsewhere")\n'
        self.assertTrue(local_override_errors(Starlark(outside, repo_root=ROOT)))
        entry = {"case": "test_media.NoSuchClass.test_nothing", "target": "//tests:test_media", "class": "other",
                 "bazel_outcome": "FAIL", "first_error_line": "AssertionError", "cause": "x", "claim_class": "M",
                 "plain_unittest_repro": {"command": "c", "cwd": "w", "outcome": "FAIL"},
                 "control_repro": None, "baseline_repro": None}
        self.assertTrue(any("existing" in e for e in known_failure_errors(ROOT, {"entries": [entry]})))
        passing = dict(entry, case="test_bazel_graph_s3.SiteGraphTest.test_site_house_stack_pins",
                       target="//tests:test_bazel_graph_s3",
                       plain_unittest_repro={"command": "c", "cwd": "w", "outcome": "PASS"})
        self.assertTrue(any("Bazel-graph defect" in e for e in known_failure_errors(ROOT, {"entries": [passing]})))
        tests_build = (ROOT / "tests/BUILD.bazel").read_text().replace(
            'tags = ["python-unittest"],', 'tags = ["python-unittest", "manual"],')
        self.assertNotEqual(tests_build, (ROOT / "tests/BUILD.bazel").read_text())
        macros, shim = (ROOT / "tools/bazel/python.bzl").read_text(), (ROOT / "tools/bazel/unittest_main.py").read_text()
        rc = (ROOT / ".bazelrc").read_text()
        self.assertTrue(skip_mechanism_errors(tests_build, macros, shim, rc))
        self.assertTrue(skip_mechanism_errors((ROOT / "tests/BUILD.bazel").read_text(), macros,
                                              shim + "\nunittest.expectedFailure\n", rc))
        self.assertTrue(skip_mechanism_errors((ROOT / "tests/BUILD.bazel").read_text(), macros, shim,
                                              rc + "\ntest --test_tag_filters=-macos\n"))
        self.assertEqual(skip_mechanism_errors((ROOT / "tests/BUILD.bazel").read_text(), macros, shim,
                                               rc + "\ntest:ci --test_tag_filters=-requires-host-tools\n"), [])
        site_text = (ROOT / "site/BUILD.bazel").read_text() + "# " + private_needles()[0] + "runs/x\n"
        self.assertTrue(any("needle" in e for e in site_build_errors(ROOT, site_text)))

    def test_site_gate_inconsistencies_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "site").mkdir()
            (base / "MODULE.bazel").write_text('npm_site = use_extension("@x//:e.bzl", "npm", dev_dependency = True)\n')
            gate = "\n".join(SITE_GATE_LINES) + "\n"
            cases = {
                "partial": (SITE_GATE_LINES[0] + "\n", "packages: [.]\n", "site/vendor\n", "half applied"),
                "gated_but_ready": (gate, "allowBuilds: {}\n", SITE_VENDOR_TEST_IGNORE + "\n", "remove the two"),
                "open_too_early": ("", "packages: [.]\n", "site/vendor\n", "gate removed"),
            }
            for label, (rc, workspace, ignore, needle) in cases.items():
                with self.subTest(case=label):
                    (base / ".bazelrc").write_text(rc)
                    (base / "site/pnpm-workspace.yaml").write_text(workspace)
                    (base / ".bazelignore").write_text(ignore)
                    self.assertTrue(any(needle in e for e in site_gate(base)["errors"]), site_gate(base))
            (base / ".bazelrc").write_text(gate)
            (base / "site/pnpm-workspace.yaml").write_text("packages: [.]\n")
            (base / ".bazelignore").write_text("site/vendor\n")
            self.assertEqual(site_gate(base)["errors"], [])
            (base / "MODULE.bazel").write_text('npm_site = use_extension("@x//:e.bzl", "npm")\n')
            self.assertTrue(any("dev_dependency" in e for e in site_gate(base)["errors"]))

    def test_vendored_carrier_files_are_stray_only_while_gated_and_unignored(self):
        carrier = vendored_carrier_dirs(ROOT)[0] + "/BUILD.bazel"
        self.assertEqual(stray_bazel_files([carrier], ["site/vendor"], "gated"), [])
        self.assertEqual(stray_bazel_files([carrier], [SITE_VENDOR_TEST_IGNORE], "open"), [])
        self.assertEqual(stray_bazel_files([carrier], [SITE_VENDOR_TEST_IGNORE], "gated"), [carrier])
        self.assertEqual(stray_bazel_files(["elsewhere/BUILD.bazel"], [], "open"), ["elsewhere/BUILD.bazel"])

    def test_swapped_registry_order_is_rejected(self):
        lines = (ROOT / ".bazelrc").read_text().splitlines()
        first, second = [index for index, line in enumerate(lines) if line.startswith("common --registry=")]
        lines[first], lines[second] = lines[second], lines[first]
        self.assertTrue(any("first registry" in error for error in bazelrc_errors("\n".join(lines))))

    def test_floating_or_extra_registry_is_rejected(self):
        text = (ROOT / ".bazelrc").read_text()
        floating = re.sub(r"bazel-registry/[0-9a-f]{40}", "bazel-registry/main", text)
        self.assertTrue(bazelrc_errors(floating))
        self.assertTrue(bazelrc_errors(text + "\ncommon --registry=https://example.invalid/registry\n"))

    def test_added_remote_cache_is_rejected(self):
        text = (ROOT / ".bazelrc").read_text()
        for flag in ("build --remote_cache=grpc://cache.invalid:9092", "build --remote_executor=grpc://x",
                     "build:ci --bes_backend=grpc://y"):
            with self.subTest(flag=flag):
                self.assertTrue(any("remote backend" in error for error in bazelrc_errors(text + "\n" + flag + "\n")))
        self.assertTrue(just_errors((ROOT / "just/bazel.just").read_text()
                                    + "\nbad:\n    bazel build --remote_cache=grpc://x //...\n"))

    def test_ffmpeg_value_in_bazelrc_is_rejected(self):
        text = (ROOT / ".bazelrc").read_text() + "\ntest --test_env=FFMPEG=/usr/bin/ffmpeg\n"
        self.assertTrue(any("passed through" in error for error in bazelrc_errors(text)))

    def make_tree(self, base: Path, tests_build: str, exclusions: list) -> Path:
        for name in ("tests/test_alpha.py", "tests/test_beta.py", "scripts/worker.py", "scripts/frozen/old.py"):
            (base / name).parent.mkdir(parents=True, exist_ok=True)
            (base / name).write_text("")
        (base / "tools/bazel").mkdir(parents=True)
        (base / "tests/BUILD.bazel").write_text(tests_build)
        (base / "scripts/BUILD.bazel").write_text('py_library(name = "workers", srcs = glob(["*.py", "frozen/*.py"]))\n')
        (base / "tools/bazel/coverage_exclusions.json").write_text(json.dumps({"exclusions": exclusions}))
        return base

    def test_dropped_test_target_and_bad_exclusions_are_rejected(self):
        full = 'unittest_py_tests(srcs = glob(["test_*.py"]))\n'
        dropped = 'unittest_py_tests(srcs = glob(["test_*.py"], exclude = ["test_beta.py"]))\n'
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(coverage_errors(self.make_tree(Path(directory) / "ok", full, [])), [])
            errors = coverage_errors(self.make_tree(Path(directory) / "dropped", dropped, []))
            self.assertEqual(errors, ["test tests/test_beta.py is in no Bazel target and has no exclusion"])
            reasoned = [{"path": "tests/test_beta.py", "kind": "test", "reason": "needs a licensed host"}]
            self.assertEqual(coverage_errors(self.make_tree(Path(directory) / "reasoned", dropped, reasoned)), [])
            for label, entry, needle in (
                    ("empty", {"path": "tests/test_beta.py", "kind": "test", "reason": " "}, "has no reason"),
                    ("absent", {"path": "tests/test_gone.py", "kind": "test", "reason": "x"}, "existing file"),
                    ("kind", {"path": "tests/test_beta.py", "kind": "module", "reason": "x"}, "unknown kind")):
                with self.subTest(case=label):
                    errors = coverage_errors(self.make_tree(Path(directory) / label, dropped, [entry]))
                    self.assertTrue(any(needle in error for error in errors), errors)
            both = [{"path": "tests/test_alpha.py", "kind": "test", "reason": "x"}]
            errors = coverage_errors(self.make_tree(Path(directory) / "both", full, both))
            self.assertEqual(errors, ["test tests/test_alpha.py is both covered and excluded"])
            tree = self.make_tree(Path(directory) / "worker", full, [])
            (tree / "scripts/BUILD.bazel").write_text('py_library(name = "workers", srcs = glob(["*.py"]))\n')
            self.assertEqual(coverage_errors(tree), ["worker scripts/frozen/old.py is in no Bazel target and has no exclusion"])

    def test_effect_3_and_skeleton_4_literals_are_rejected(self):
        package = json.loads((ROOT / "web/package.json").read_text())
        lock = (ROOT / "web/pnpm-lock.yaml").read_text()
        module_text = (ROOT / "MODULE.bazel").read_text()
        cases = {
            "npm_import": 'npm.npm_import(name = "npm__effect__3.22.1", package = "effect", version = "3.22.1")\n',
            "token": '# pin effect@3.22.1 for the registry module\n',
            "skeleton": 'npm.npm_import(name = "sk", package = "@skeletonlabs/skeleton", version = "4.15.2")\n',
        }
        for label, addition in cases.items():
            with self.subTest(case=label):
                text = module_text + addition
                module = Starlark(text, repo_root=ROOT, label="MODULE.bazel")
                errors = npm_pin_errors(package, lock, module, {"MODULE.bazel": text})
                self.assertTrue(errors, label)
        drifted = json.loads(json.dumps(package))
        drifted["dependencies"]["effect"] = "3.22.1"
        self.assertTrue(npm_pin_errors(drifted, lock, read_module(ROOT), bazel_texts(ROOT)))
        self.assertTrue(module_errors(Starlark(module_text + cases["npm_import"], repo_root=ROOT)))

    def test_toolchain_literal_drift_is_rejected(self):
        package = json.loads((ROOT / "web/package.json").read_text())
        lock = (ROOT / "web/pnpm-lock.yaml").read_text()
        text = (ROOT / "MODULE.bazel").read_text()
        for label, old, new in (("pnpm", 'pnpm_version = "11.25.0"', 'pnpm_version = "10.13.1"'),
                                ("typescript", 'version = "6.0.3"', 'version = "5.9.3"'),
                                ("node", 'node_version = "22.13.1"', 'node_version = "24.1.0"')):
            with self.subTest(case=label):
                self.assertIn(old, text)
                module = Starlark(text.replace(old, new), repo_root=ROOT)
                self.assertTrue(npm_pin_errors(package, lock, module, {}), label)

    def test_noncompliant_or_unrecorded_registry_module_is_rejected(self):
        document = json.loads((ROOT / "tools/bazel/registry_modules.json").read_text())
        commit = document["registry"]["commit"]
        web = read_build(ROOT, "web")
        text = (ROOT / "MODULE.bazel").read_text() + 'bazel_dep(name = "xoxd_spectrogram", version = "0.1.0")\n'
        module = Starlark(text, repo_root=ROOT)
        self.assertTrue(any("without a `consumed` decision" in e or "recorded consumed" in e
                            for e in registry_errors(module, web, document, commit)))
        forced = json.loads(json.dumps(document))
        forced["consumed"] = ["xoxd_spectrogram"]
        for entry in forced["decisions"]:
            if entry["module"] == "xoxd_spectrogram":
                entry["decision"] = "consumed"
            if entry["module"] == "tummycrypt_tinyland_composables":
                entry["pins_effect_3"] = True
        errors = registry_errors(module, web, forced, commit)
        self.assertTrue(any("pins Skeleton 4 or Effect 3" in error for error in errors), errors)
        linked = Starlark('npm_link_package(name = "node_modules/@xoxd/spectrogram", src = "@xoxd_spectrogram//:pkg")\n')
        self.assertTrue(any("no matching bazel_dep" in e for e in registry_errors(read_module(ROOT), linked, document, commit)))
        self.assertTrue(registry_errors(read_module(ROOT), web, document, "0" * 40))

    def test_constructs_outside_the_subset_raise_instead_of_being_skipped(self):
        for text in ("def macro():\n    pass\n", "[py_test(name = n) for n in NAMES]\n", "x = unknown_name\n",
                     "if True:\n    pass\n", "x = 1 - 1\n", "f(**{})\n", "x = (\n"):
            with self.subTest(text=text):
                with self.assertRaises(StarlarkSubsetError):
                    Starlark(text, package_dir=ROOT, repo_root=ROOT)

    def test_glob_expansion_matches_bazel_semantics_for_the_patterns_used(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for name in ("a.py", "test_a.py", "frozen/b.py", "frozen/deep/c.py", "sub/BUILD.bazel", "sub/d.py"):
                (base / name).parent.mkdir(parents=True, exist_ok=True)
                (base / name).write_text("")
            self.assertEqual(expand_glob(base, ["*.py"], []), ["a.py", "test_a.py"])
            self.assertEqual(expand_glob(base, ["*.py", "frozen/*.py"], ["test_*.py"]), ["a.py", "frozen/b.py"])
            self.assertEqual(expand_glob(base, ["**/*.py"], []), ["a.py", "frozen/b.py", "frozen/deep/c.py", "test_a.py"])
            self.assertEqual(expand_glob(base, ["**"], ["**/deep/**"]), ["a.py", "frozen/b.py", "test_a.py"])

    def test_engines_comparator(self):
        self.assertTrue(satisfies_engines("22.13.1", ">=22.12 <23"))
        self.assertFalse(satisfies_engines("22.11.0", ">=22.12 <23"))
        self.assertFalse(satisfies_engines("23.0.0", ">=22.12 <23"))
        self.assertTrue(satisfies_engines("3.12", ">=3.12"))
        with self.assertRaises(ValueError):
            satisfies_engines("22.13.1", "^22")


if __name__ == "__main__":
    unittest.main()
