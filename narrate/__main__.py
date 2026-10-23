"""python -m narrate {render,evaluate,voices,engines,verify}"""

import argparse
import json
import sys
from pathlib import Path

from . import evaluate, registry, render, verify
from .adapters import InputError
from .config import Config
from .engine import EngineError
from .lexical import LexicalError
from .normalise import NormaliseError
from .policy import Refused


def emit(value):
    print(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False))


def refusal(code, detail):
    print(json.dumps({"ok": False, "refused": code, "detail": detail}, sort_keys=True), file=sys.stderr)
    return 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="narrate", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("render", help="render the job a narrate.toml names into artifacts/narrate/<run_id>/")
    r.add_argument("config", help="narrate.toml")
    r.add_argument("--input", help="the script, instead of narrate.toml's input")
    r.add_argument("--rewrite", help="a rewrite of the script; accepted only when the RewriteCheck holds")
    r.add_argument("--engine", help="an engine id, instead of the job's")
    r.add_argument("--seed", type=int, help="the base seed, instead of the job's")
    r.add_argument("--out", help="the directory runs land in, instead of artifacts/narrate")

    e = sub.add_parser("evaluate", help="score a rendered run; writes nothing")
    e.add_argument("run_dir")
    e.add_argument("--config", help="narrate.toml, for the whisper and SIM settings")
    e.add_argument(
        "--metrics", default=",".join(evaluate.METRICS), help="comma-separated: " + ", ".join(evaluate.METRICS)
    )

    v = sub.add_parser("voices", help="list voices with consent state, or add a reference clip to the store")
    v.add_argument("config", help="narrate.toml")
    v.add_argument("action", nargs="?", choices=["list", "add"], default="list")
    v.add_argument("--clip", help="add: a 10 to 30 s WAV of the consenting speaker")
    v.add_argument("--transcript", help="add: its human-verified transcript")
    v.add_argument("--id", help="add: the voice id")
    v.add_argument("--consent", help="add: the consent record id")
    v.add_argument("--scope", default="OwnContent", choices=["OwnContent", "ClientDisclosed"])
    v.add_argument("--allow-engine", action="append", default=[], help="add: an engine id the voice may use")

    g = sub.add_parser("engines", help="list engine profiles with confidentiality eligibility and availability")
    g.add_argument("config", help="narrate.toml")
    g.add_argument("--profile", help="only this profile (GpuSwitch, GpuDirect, MacMlx, RentedOpen, Hosted, Fake)")

    f = sub.add_parser("verify", help="re-hash and re-check a run")
    f.add_argument("run_dir")

    a = p.parse_args(argv)
    try:
        if a.command == "render":
            cfg = Config(a.config, {"out": str(Path(a.out).resolve())} if a.out else None)
            final, manifest = render.render(cfg, input_path=a.input, rewrite=a.rewrite, engine_id=a.engine, seed=a.seed)
            loud = manifest["loudness"]["measured"]["integrated_lufs"]
            print(
                f"{final}: {manifest['input']['chunks']} chunks, {manifest['timeline']['total_samples']} samples "
                f"at {manifest['timeline']['sample_rate']} Hz, {loud} LUFS, qa {manifest['qa']['chunks']}, "
                f"flags {manifest['flags'] or 'none'}, verified"
            )
            return 0
        if a.command == "verify":
            return verify.main(a.run_dir)
        if a.command == "evaluate":
            cfg = Config(a.config) if a.config else None
            result = evaluate.evaluate(a.run_dir, tuple(m for m in a.metrics.split(",") if m), cfg)
            emit(result)
            return 0 if result["ok"] else 1
        cfg = Config(a.config)
        if a.command == "engines":
            emit(registry.engines(cfg, a.profile))
            return 0
        if a.action == "add":
            missing = [n for n in ("clip", "transcript", "id", "consent") if not getattr(a, n)]
            if missing:
                p.error(f"voices add needs --{', --'.join(missing)}")
            emit(registry.add_voice(cfg, a.clip, a.transcript, a.id, a.consent, a.scope, a.allow_engine))
            return 0
        emit(registry.voices(cfg))
        return 0
    except (Refused, LexicalError, EngineError, render.RenderError) as error:
        return refusal(error.code, error.detail)
    except (InputError, NormaliseError) as error:
        return refusal("input_invalid", str(error))


if __name__ == "__main__":
    sys.exit(main())
