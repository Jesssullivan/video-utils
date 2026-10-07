"""S3 bazel_graph lane: structural contract test for the Bzlmod graph.

Contract: docs/spec/sprints/BAZEL_GRAPH_S3.md section 7. Stdlib only; no Bazel,
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
    "native/au-spike/BUILD.bazel", "just/bazel.just",
)
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
RECIPES = ("bazel-build", "bazel-test", "bazel-graph")
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
    locks = module.named("npm.npm_translate_lock")
    if len(locks) != 1 or locks[0].kwargs.get("pnpm_lock") != "//web:pnpm-lock.yaml":
        errors.append("exactly one npm.npm_translate_lock with pnpm_lock = //web:pnpm-lock.yaml is required")
    elif "//web:package.json" not in locks[0].kwargs.get("data", []):
        errors.append("npm_translate_lock data must include //web:package.json")
    elif locks[0].kwargs.get("npmrc") != "//web:.npmrc":
        errors.append("npm_translate_lock must declare npmrc = //web:.npmrc (rules_js refuses an undeclared one)")
    if module.named("npm.npm_import"):
        errors.append("npm.npm_import adds a second npm version site; use web/pnpm-lock.yaml only")
    for banned in ("local_path_override", "git_override", "archive_override"):
        if module.named(banned):
            errors.append(f"{banned} is not allowed in MODULE.bazel")
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
                                                               "tools/bazel")]
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


def classification_errors(root: Path) -> list[str]:
    errors = []
    build = read_build(root, "tests")
    document = json.loads((root / "tools/bazel/test_classification.json").read_text())
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
        if sorted(recorded.get("modules", [])) != sorted(listed):
            errors.append(f"tests/BUILD.bazel {key} list differs from tools/bazel/test_classification.json")
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


# --------------------------------------------------------------------------- tests on the repository tree


class GraphFilesTest(unittest.TestCase):
    def test_required_graph_files_exist(self):
        missing = [name for name in REQUIRED_FILES + HELPER_FILES if not (ROOT / name).is_file()]
        self.assertEqual(missing, [])
        self.assertEqual(len(REQUIRED_FILES), 11)

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
        owned = {"", "src", "scripts", "tests", "web", "native/au-spike", "tools/bazel"}
        names = {"BUILD", "BUILD.bazel", "MODULE.bazel", "WORKSPACE", "WORKSPACE.bazel", "REPO.bazel"}
        stray = []
        for path in listed.stdout.decode().split("\0"):
            directory, _, name = path.rpartition("/")
            if name not in names or (directory in owned and name in ("BUILD.bazel", "MODULE.bazel")):
                continue
            if not any(directory == tree or directory.startswith(tree + "/") for tree in ignored):
                stray.append(path)
        self.assertEqual(stray, [])
        for tree in ("site/vendor", "site/node_modules", "site/build", "site/.svelte-kit"):
            self.assertIn(tree, ignored)

    def test_every_bazel_file_is_inside_the_starlark_subset(self):
        read_module(ROOT)
        for package in ("", "src", "scripts", "tests", "web", "native/au-spike", "tools/bazel"):
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


# --------------------------------------------------------------------------- negative self-checks (no tree mutation)


class NegativeSelfChecks(unittest.TestCase):
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
