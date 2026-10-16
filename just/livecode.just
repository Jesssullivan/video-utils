# livecode (livecode/README.md): screen + camera corner + mic capture with plain ffmpeg, macOS only.
# Root imports this file from the root justfile (`import 'just/livecode.just'`).

# Shellcheck, the contract test on the source script, then the same test on the built Nix package.
livecode-check:
    shellcheck --shell=bash livecode/livecode.sh
    PYTHONDONTWRITEBYTECODE=1 LIVECODE_UNDER_TEST=livecode/livecode.sh python3 -m unittest discover -s livecode/tests -p 'test_*.py' -v
    nix build --no-link --print-build-logs ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).livecode"
