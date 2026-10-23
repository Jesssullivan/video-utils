"""A YAML subset reader for the repository's own Kubernetes manifests (deploy/), with no third-party module.

It reads block mappings and sequences, `---` document breaks, full-line and trailing ` #` comments, flow
sequences of scalars (`["ALL"]`, `[105]`), quoted strings, integers and booleans. Anchors, multi-line
strings and flow mappings are not supported; a manifest that needs them should be checked another way.
"""

import json
import re

_INT = re.compile(r"-?[0-9]+")


def _scalar(text):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_scalar(part) for part in inner.split(",")] if inner else []
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return json.loads(text)
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~", ""):
        return None
    if _INT.fullmatch(text):
        return int(text)
    return text


def _strip_comment(line):
    quoted = None
    for i, ch in enumerate(line):
        if ch in "\"'" and quoted in (None, ch):
            quoted = None if quoted else ch
        elif ch == "#" and quoted is None and (i == 0 or line[i - 1] == " "):
            return line[:i].rstrip()
    return line.rstrip()


def _block(lines, i, indent):
    if lines[i][1].startswith("- ") or lines[i][1] == "-":
        out = []
        while i < len(lines) and lines[i][0] == indent and (lines[i][1].startswith("- ") or lines[i][1] == "-"):
            content = lines[i][1][2:].strip()
            if re.match(r"^[^\"'\[][^:]*:( |$)", content):
                lines[i] = (indent + 2, content)  # a mapping item: its first key sits at the content column
                value, i = _block(lines, i, indent + 2)
            else:
                value, i = _scalar(content), i + 1
            out.append(value)
        return out, i
    out = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("- "):
        key, _, rest = lines[i][1].partition(":")
        i += 1
        if rest.strip():
            out[key.strip()] = _scalar(rest)
        elif i < len(lines) and (lines[i][0] > indent or (lines[i][0] == indent and lines[i][1].startswith("- "))):
            out[key.strip()], i = _block(lines, i, lines[i][0])
        else:
            out[key.strip()] = None
    return out, i


def load_all(text):
    docs, current = [], []
    for raw in text.splitlines() + ["---"]:
        if raw.strip() == "---":
            if current:
                value, end = _block(current, 0, current[0][0])
                if end != len(current):
                    raise ValueError(f"unparsed line: {current[end][1]!r}")
                docs.append(value)
            current = []
            continue
        line = _strip_comment(raw)
        if line.strip():
            current.append((len(line) - len(line.lstrip(" ")), line.strip()))
    return docs
