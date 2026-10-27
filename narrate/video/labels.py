"""Stage labels: they only grow (docs/spec/NARRATED_VIDEO.md, "Labels").

A stage with any synthetic input writes synthetic: true and the union of its upstream consent ids and voice ids, and
passes the job's persona through unchanged. check() compares a stage's labels with its parents' and refuses
label_chain_broken when one was dropped or altered. Labels are manifest metadata only (KP-15): no stage draws them.
"""

from .common import StageRefused


def of(manifest):
    """The labels of one stage manifest, with every field present."""
    labels = (manifest or {}).get("labels") or {}
    return {
        "synthetic": labels.get("synthetic") is True,
        "consent_ids": sorted(labels.get("consent_ids") or []),
        "voice_ids": sorted(labels.get("voice_ids") or []),
        "persona": labels.get("persona"),
    }


def grow(parents, persona):
    """The labels a stage writes from its parents' manifests: the union, synthetic when any parent is."""
    rows = [of(p) for p in parents]
    return {
        "synthetic": any(r["synthetic"] for r in rows),
        "consent_ids": sorted({c for r in rows for c in r["consent_ids"]}),
        "voice_ids": sorted({v for r in rows for v in r["voice_ids"]}),
        "persona": persona,
    }


def check(labels, parents, persona):
    """Refuse label_chain_broken when labels lack anything a parent carries, or alter the persona."""
    child = of({"labels": labels})
    for parent in (of(p) for p in parents):
        if parent["synthetic"] and not child["synthetic"]:
            raise StageRefused("label_chain_broken", "a stage with a synthetic input dropped synthetic: true")
        dropped = sorted(set(parent["consent_ids"]) - set(child["consent_ids"])) + sorted(
            set(parent["voice_ids"]) - set(child["voice_ids"])
        )
        if dropped:
            raise StageRefused("label_chain_broken", f"a stage dropped {len(dropped)} upstream consent or voice ids")
        if parent["persona"] is not None and parent["persona"] != child["persona"]:
            raise StageRefused("label_chain_broken", "a stage altered the persona label")
    if child["persona"] != persona:
        raise StageRefused("label_chain_broken", "a stage's persona is not the job's labels.persona")
    return child
