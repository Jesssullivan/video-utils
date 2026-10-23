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
    exit "$status"

# Rewrite the committed example JSON from the Dhall sources.
narrate-dhall-render:
    #!/usr/bin/env bash
    set -euo pipefail
    cd narrate/dhall
    for file in examples/*.dhall; do
        dhall-to-json --preserve-null --file "$file" > "${file%.dhall}.json"
    done
