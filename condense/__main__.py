"""python -m condense <stage> <talk.toml>"""

import argparse
import sys

from . import captions, check, edl, events, overlay, publish, render, transcribe
from .config import Config
from .recover import recover

STAGES = ["transcribe", "events", "edl", "render", "check", "captions", "overlay"]
ALL = [*STAGES, "publish"]  # `all` ends in a published run that verify-run accepted


def stage(name, cfg, names=()):
    if name in ("transcribe", "events"):
        for clip in (c for c in cfg.clips if not c["card"]):
            (transcribe.transcribe if name == "transcribe" else events.run)(cfg, clip)
    elif name == "check":
        if not check.check(cfg, names):
            sys.exit(1)
    elif name == "publish":
        try:
            publish.publish(cfg)
        except RuntimeError as refused:
            sys.exit(f"condense publish: {refused}")
    else:
        {"edl": edl.build, "render": render.render, "captions": captions.write, "overlay": overlay.burn}[name](cfg)


def main(argv=None):
    p = argparse.ArgumentParser(prog="condense", description=__doc__)
    p.add_argument("stage", choices=["recover", *ALL, "all"])
    p.add_argument("args", nargs="*", help="talk.toml [check names], or for recover: reference broken fixed")
    a = p.parse_args(argv)
    if a.stage == "recover":
        return recover(*a.args)
    cfg = Config(a.args[0])
    for name in ALL if a.stage == "all" else [a.stage]:
        stage(name, cfg, a.args[1:])


if __name__ == "__main__":
    main()
