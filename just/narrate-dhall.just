# Narration types (docs/spec/NARRATE.md). dhall and dhall-json come from the default dev shell.
# Root imports this file from the root justfile (`import 'just/narrate-dhall.just'`).

# Type-check every narrate Dhall file, check formatting, render the examples and compare them with the
# committed JSON, then check the fixture digests and the models.json v2 drafts. Offline; no weights.
narrate-dhall-check:
    #!/usr/bin/env bash
    set -euo pipefail
    cd narrate/dhall
    for file in *.dhall examples/*.dhall; do
        dhall type --quiet --file "$file"
    done
    dhall format --check *.dhall examples/*.dhall
    status=0
    for file in examples/*.dhall; do
        rendered="$(dhall-to-json --preserve-null --file "$file")"
        if ! diff -u "${file%.dhall}.json" <(printf '%s\n' "$rendered"); then
            echo "narrate-dhall-check: ${file%.dhall}.json differs from its render; run just narrate-dhall-render" >&2
            status=1
        fi
    done
    cd ../..
    python3 -I narrate/dhall/check.py || status=1
    python3 -I narrate/dhall/check.py --self-test || status=1
    exit "$status"

# Rewrite the committed example JSON from the Dhall sources. Each file is rendered to a temporary file
# first and moved into place only when the render succeeds, so a failed render leaves the old JSON.
narrate-dhall-render:
    #!/usr/bin/env bash
    set -euo pipefail
    cd narrate/dhall
    for file in examples/*.dhall; do
        target="${file%.dhall}.json"
        tmp="$(mktemp "${target}.XXXXXX")"
        if ! dhall-to-json --preserve-null --file "$file" > "$tmp"; then
            rm -f "$tmp"
            echo "narrate-dhall-render: $file failed to render; $target is unchanged" >&2
            exit 1
        fi
        mv "$tmp" "$target"
    done
