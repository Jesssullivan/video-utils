"""python -m narrate {render,plan,evaluate,voices,engines,verify,export,spoken,video}"""

import argparse
import json
import sys
from pathlib import Path

from . import adapters, evaluate, export, registry, render, spoken, verify
from .adapters import InputError
from .config import Config, ConfigError
from .engine import EngineError
from .lexical import LexicalError
from .normalise import NormaliseError
from .policy import Refused
from .registry import RegistryError


def emit(value):
    print(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False))


def refusal(code, detail):
    print(json.dumps({"ok": False, "refused": code, "detail": detail}, sort_keys=True), file=sys.stderr)
    return 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["video"]:
        # The narrated-video graph (docs/spec/NARRATED_VIDEO.md) has its own parser: python -m narrate video -h.
        from .video import cli as video_cli

        return video_cli.main(argv[1:])
    p = argparse.ArgumentParser(prog="narrate", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("video", help="the narrated-video stage graph: init, plan, run, stage, status, explain, verify")

    def job_arguments(r):
        r.add_argument("config", help="narrate.toml")
        r.add_argument("--input", help="the script, instead of narrate.toml's input")
        r.add_argument("--rewrite", help="a rewrite of the script; accepted only when the RewriteCheck holds")
        r.add_argument("--engine", help="an engine id, instead of the job's")
        r.add_argument("--seed", type=int, help="the base seed, instead of the job's")
        o = r.add_argument_group("job overrides (recorded in the manifest's job.overrides; they never loosen policy)")
        o.add_argument("--voice", help="the job's voice id; it must pass the same consent checks")
        o.add_argument("--input-kind", choices=adapters.KINDS, help="the job's input kind")
        o.add_argument("--confidential", action="store_true", help="mark the job confidential (never clears it)")
        o.add_argument("--no-hosted", action="store_true", help="withdraw the job's allowHosted (never grants it)")
        o.add_argument("--max-chunk-wer", type=float, help="gates.maxChunkWer, 0 to 1")
        o.add_argument("--min-sim", type=float, help="gates.minSim, -1 to 1")
        o.add_argument("--max-takes", type=int, help="gates.maxTakes, 1 to 3")
        o.add_argument("--chunk-max-codepoints", type=int, help="chunkMaxCodepoints, 40 to 1000")
        o.add_argument("--loudness-lufs", type=float, help="post.loudnessLufs, -30 to -10")
        o.add_argument("--fit-max-stretch", type=float, help="post.fitMaxStretch, 0 to 0.08")

    r = sub.add_parser("render", help="render the job a narrate.toml names into artifacts/narrate/<run_id>/")
    job_arguments(r)
    r.add_argument("--out", help="the directory runs land in, instead of artifacts/narrate")
    out_format = r.add_mutually_exclusive_group()
    out_format.add_argument("--json", action="store_true", help="print a JSON summary with the manifest path")
    out_format.add_argument(
        "--result-line",
        action="store_true",
        help="print one compact JSON line {ok, run_id, content_sha256} (for a workflow task)",
    )
    r.add_argument(
        "--prerendered",
        metavar="DIR",
        help="an AudioCppBatch engine: the plan directory with the batch's receipts/ and wav/ (narrate plan)",
    )

    n = sub.add_parser("plan", help="an AudioCppBatch engine: write the request batch for a GPU window; no audio")
    job_arguments(n)
    n.add_argument("--out", required=True, help="a new directory for plan.json, requests/ and refs/")
    n.add_argument("--takes", type=int, help="seeds per chunk, 1 to the job's maxTakes (default maxTakes)")

    e = sub.add_parser("evaluate", help="score a rendered run; writes nothing")
    e.add_argument("run_dir")
    e.add_argument("--config", help="narrate.toml, for the whisper and SIM settings")
    e.add_argument(
        "--metrics", default=",".join(evaluate.METRICS), help="comma-separated: " + ", ".join(evaluate.METRICS)
    )
    e.add_argument("--reference-voice", help="sim: score every chunk against this voice's reference clip")

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
    g.add_argument("--reach", action="store_true", help="also try a TCP connect to each http engine (2 s, no request)")

    f = sub.add_parser("verify", help="re-hash and re-check a run")
    f.add_argument("run_dir")
    f.add_argument(
        "--result-line",
        action="store_true",
        help="print one compact JSON line {ok, run_id, content_sha256} instead of the receipt",
    )

    x = sub.add_parser(
        "export", help="copy a verified run's narration.wav to a consumer as <stem>.wav, never replacing"
    )
    x.add_argument("run_dir")
    x.add_argument("--to", required=True, help="the consumer's narration directory (it must exist)")
    x.add_argument("--stem", required=True, help="the file stem, for example NN-<slide-id> for a deck page")

    s = sub.add_parser("spoken", help="print only the text a render voices, through the input's adapter")
    s.add_argument("input", help="a script: manuscript page, SRT, WebVTT, words.json, dialog or plain text")
    s.add_argument(
        "--adapter",
        choices=adapters.KINDS,
        help="the input kind (default from the suffix: .md Markdown, .srt Srt, .vtt Vtt, .json CondenseWords, "
        "else PlainText; Dialog is never inferred)",
    )
    s.add_argument("--format", choices=spoken.FORMATS, default="lines", help="lines (default), json or srt")
    s.add_argument("--edl", help="CondenseWords: the condense edl.json whose output clock the words map to")
    s.add_argument("--clip", help="CondenseWords: the clip the words were transcribed from")
    s.add_argument("--sentence-gap-s", type=float, help="CondenseWords: a longer gap between words ends a segment")

    a = p.parse_args(argv)

    def job_overrides():
        return render.overrides_from(
            {k: getattr(a, k) for k in render.OVERRIDES if getattr(a, k) is not None and getattr(a, k) is not False}
        )

    try:
        if a.command == "spoken":
            path = Path(a.input)
            if not path.is_file():
                return refusal("input_invalid", f"{a.input}: no such file")
            options = {"edl": a.edl, "clip": a.clip}
            if a.sentence_gap_s is not None:
                options["sentence_gap_s"] = a.sentence_gap_s
            try:
                script = adapters.load(a.adapter or spoken.kind_for(path), path, options)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                return refusal("input_invalid", f"{a.input}: {exc}")
            sys.stdout.write(spoken.render(script, a.format))
            return 0
        if a.command == "plan":
            cfg = Config(a.config)
            path, document = render.plan(
                cfg,
                a.out,
                a.takes,
                input_path=a.input,
                rewrite=a.rewrite,
                engine_id=a.engine,
                seed=a.seed,
                overrides=job_overrides(),
            )
            emit({"ok": True, "plan": str(path), "batches": document["batches"], "totals": document["totals"]})
            return 0
        if a.command == "render":
            cfg = Config(a.config, {"out": str(Path(a.out).resolve())} if a.out else None)
            final, manifest = render.render(
                cfg,
                input_path=a.input,
                rewrite=a.rewrite,
                engine_id=a.engine,
                seed=a.seed,
                overrides=job_overrides(),
                prerendered=a.prerendered,
            )
            if a.json:
                emit(render.summary(final, manifest))
                return 0
            if a.result_line:
                # render verified the run before returning it (render.py raises verify_refused otherwise)
                print(verify.result_line(True, manifest["run_id"], manifest["content_sha256"]))
                return 0
            loud = manifest["loudness"]["measured"]["integrated_lufs"]
            print(
                f"{final}: {manifest['input']['chunks']} chunks, {manifest['timeline']['total_samples']} samples "
                f"at {manifest['timeline']['sample_rate']} Hz, {loud} LUFS, qa {manifest['qa']['chunks']}, "
                f"flags {', '.join(manifest['flags']) or 'none'}, verified"
            )
            return 0
        if a.command == "verify":
            return verify.main(a.run_dir, line=a.result_line)
        if a.command == "export":
            emit(export.export(a.run_dir, a.to, a.stem))
            return 0
        if a.command == "evaluate":
            cfg = Config(a.config) if a.config else None
            metrics = tuple(m for m in a.metrics.split(",") if m)
            unknown = sorted(set(metrics) - set(evaluate.METRICS))
            if unknown:
                return refusal("metric_unknown", f"{unknown}: one of {', '.join(evaluate.METRICS)}")
            result = evaluate.evaluate(a.run_dir, metrics, cfg, a.reference_voice)
            emit(result)
            return 0 if result["ok"] else 1
        cfg = Config(a.config)
        if a.command == "engines":
            emit(registry.engines(cfg, a.profile, a.reach))
            return 0
        if a.action == "add":
            missing = [n for n in ("clip", "transcript", "id", "consent") if not getattr(a, n)]
            if missing:
                p.error(f"voices add needs --{', --'.join(missing)}")
            emit(registry.add_voice(cfg, a.clip, a.transcript, a.id, a.consent, a.scope, a.allow_engine))
            return 0
        emit(registry.voices(cfg))
        return 0
    except (
        Refused,
        LexicalError,
        EngineError,
        render.RenderError,
        RegistryError,
        ConfigError,
        export.ExportError,
    ) as error:
        return refusal(error.code, error.detail)
    except (InputError, NormaliseError) as error:
        return refusal("input_invalid", str(error))


if __name__ == "__main__":
    sys.exit(main())
