"""Python macros for the stdlib workers and their unittest modules."""

load("@rules_python//python:defs.bzl", "py_binary", "py_test")

_SHIM = "//tools/bazel:unittest_main.py"

# Tag applied to every unittest target. Reason (recorded in
# docs/spec/sprints/BAZEL_GRAPH_S3.md, Phase 2 amendments): each test module and
# worker locates the repository with Path(__file__).resolve(), which follows the
# runfiles symlink back to the real checkout, and many modules create scratch
# directories under <checkout>/artifacts. A sandbox would deny those writes.
_UNSANDBOXED = "no-sandbox"

def worker_binaries(srcs, deps = [], **kwargs):
    """Declares one py_binary per worker file, named after the file.

    Args:
        srcs: worker files of the calling package (for example glob(["*.py"])).
        deps: py_library targets every worker may import from.
        **kwargs: forwarded to py_binary.
    """
    for src in srcs:
        py_binary(
            name = src[:-len(".py")],
            srcs = [src],
            main = src,
            deps = deps,
            **kwargs
        )

def unittest_py_tests(
        srcs,
        ffmpeg = [],
        host_tools = [],
        exclusive = [],
        workspace_artifacts = [],
        web_tree = [],
        deps = [],
        data = []):
    """Declares one py_test per unittest module, run through the shared shim.

    The test name is the module name, so `bazel test //tests:test_media` is the
    counterpart of `PYTHONPATH=tests python3 -m unittest test_media -v`.

    Args:
        srcs: unittest module files (glob(["test_*.py"])).
        ffmpeg: module names that execute FFmpeg/FFprobe; tagged requires-ffmpeg.
        host_tools: module names that use node, pnpm, git or a pinned host
            binary; tagged requires-host-tools.
        exclusive: module names that mutate shared checkout state (web/build,
            web/node_modules) and must not run beside any other test.
        workspace_artifacts: module names that read or create paths under the
            checkout's artifacts/ tree; tagged workspace-artifacts and no-cache
            because that tree is not a declared input.
        web_tree: module names that read the checkout's web/ tree. //web is not
            a data dependency (loading it needs the npm lock translation, which
            must not be able to break the Python tests), so these are tagged
            reads-web-tree and no-cache.
        deps: py_library targets for every test.
        data: runfiles for every test.
    """
    names = [src[:-len(".py")] for src in srcs]
    for label, members in [
        ("ffmpeg", ffmpeg),
        ("host_tools", host_tools),
        ("exclusive", exclusive),
        ("workspace_artifacts", workspace_artifacts),
        ("web_tree", web_tree),
    ]:
        for member in members:
            if member not in names:
                fail("unittest_py_tests: %s lists %r, which is not a test module" % (label, member))

    for src, name in zip(srcs, names):
        tags = ["python-unittest", _UNSANDBOXED]
        if name in ffmpeg:
            tags.append("requires-ffmpeg")
        if name in host_tools:
            tags.append("requires-host-tools")
        if name in exclusive:
            tags.append("exclusive")
        if name in workspace_artifacts:
            tags.append("workspace-artifacts")
        if name in web_tree:
            tags.append("reads-web-tree")
        if name in workspace_artifacts or name in web_tree:
            tags.append("no-cache")
        heavy = name in ffmpeg or name in host_tools
        py_test(
            name = name,
            srcs = [src, _SHIM],
            main = _SHIM,
            args = [name],
            data = data,
            env = {"PYTHONDONTWRITEBYTECODE": "1"},
            imports = ["."],
            tags = tags,
            timeout = "long" if heavy else "moderate",
            deps = deps,
        )
