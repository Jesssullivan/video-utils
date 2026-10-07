# Bazel recipes (S3 bazel_graph lane, docs/spec/sprints/BAZEL_GRAPH_S3.md).
#
# Imported from the root justfile with:  import 'just/bazel.just'
# `just check`, `just test`, `just test-rust` and `pnpm build` stay the accepted
# gates; these recipes run the same sources through the Bazel graph.
#
# Every recipe goes through tools/bazel/run.py, which picks bazelisk or bazel,
# bounds the run (VIDEO_UTILS_BAZEL_TIMEOUT_S, default 1800 s), refuses remote
# cache/executor flags and shuts the Bazel server down afterwards.

# Build targets through Bazel (default: everything).
bazel-build *TARGETS="//...":
    python3 tools/bazel/run.py build {{TARGETS}}

# FFMPEG/FFPROBE are passed through when exported; tests tagged requires-ffmpeg
# skip, not pass, without them. Narrow with `just bazel-test //tests:python_stdlib`
# or `just bazel-test //... --test_tag_filters=-requires-ffmpeg,-requires-host-tools`;
# add `--config=host-tools` so node, pnpm and git are visible to the tests.

# Test targets through Bazel (default: everything).
bazel-test *TARGETS="//...":
    python3 tools/bazel/run.py test {{TARGETS}} --test_env=FFMPEG --test_env=FFPROBE

# Resolve and print the Bzlmod module graph, then run the structural contract test.
bazel-graph:
    python3 tools/bazel/run.py mod graph
    PYTHONPATH=tests python3 -m unittest test_bazel_graph_s3 -v

# S3 bazel_full lane (docs/spec/sprints/BAZEL_FULL_S3.md). //site is gated in
# .bazelrc until root applies the requested site/pnpm-workspace.yaml and
# .bazelignore lines; until then bazel-site reports the deleted package.

# Type-check and build the static site through Bazel (pnpm in site/ stays the gate).
bazel-site:
    python3 tools/bazel/run.py --timeout 1800 test //site:svelte_check_test
    python3 tools/bazel/run.py --timeout 1800 build //site:build

# Host tools and the exported FFMPEG/FFPROBE are passed through; failures do not
# stop the run, and known host-specific failures stay visible
# (bazel/known_host_failures.json). Gate the host first: bazel/host_gate.py.

# One full `bazel test //...` run with a Build Event Protocol file.
bazel-full BEP=".local/bazel/full-bep.json":
    python3 tools/bazel/run.py --timeout 7200 test //... --config=host-tools --jobs=4 --local_resources=cpu=4 --test_env=FFMPEG --test_env=FFPROBE --test_output=errors --test_summary=detailed --keep_going --build_event_json_file={{BEP}}
