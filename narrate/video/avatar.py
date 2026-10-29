"""The avatar stages' dispatch over the registered externals (docs/spec/NARRATED_VIDEO.md, "Avatar externals").

A job's avatar.external names the external that draws its overlay: kitpip (narrate/video/kitpip.py, kitpip.manifest/v0
or avatar.manifest/v1) or vrm (narrate/video/vrm.py, avatar.manifest/v1). Both write overlay/overlay.mov (ProRes 4444)
and overlay/manifest.json into the avatar stage directory, so compose and handoff read either the same way.
"""

from . import kitpip, vrm
from .graph import avatar_external as external


def run_avatar_stage(rc, row, partial):
    if external(rc.job) == "vrm":
        return vrm.run_avatar_stage(rc, row, partial)
    return kitpip.run_avatar_stage(rc, row, partial)


def run_avatar_check(rc, row, partial):
    if external(rc.job) == "vrm":
        return vrm.run_avatar_check(rc, row, partial)
    return kitpip.run_avatar_check(rc, row, partial)
