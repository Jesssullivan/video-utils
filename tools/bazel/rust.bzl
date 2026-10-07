"""Rust constants shared by the crate BUILD files.

The values mirror Cargo.toml and native/au-spike/Cargo.toml; the structural test
tests/test_bazel_graph_s3.py fails when they diverge.
"""

# edition = "2024" in both Cargo.toml files.
RUST_EDITION = "2024"

# version = "0.1.0" in both Cargo.toml files (CARGO_PKG_VERSION).
CRATE_VERSION = "0.1.0"

# [profile.release] overflow-checks = true (both crates).
RELEASE_RUSTC_FLAGS = select({
    "//tools/bazel:opt": ["-Coverflow-checks=on"],
    "//conditions:default": [],
})

# native/au-spike [profile.release] additionally sets panic = "abort": the AU
# static library must never unwind across the native ABI.
FFI_RELEASE_RUSTC_FLAGS = select({
    "//tools/bazel:opt": [
        "-Coverflow-checks=on",
        "-Cpanic=abort",
    ],
    "//conditions:default": [],
})
