"""Shared by align_report.py and plan_queue.py, so the definition check before labeling (plan_queue) flags
what the alignment report flags after it, and both read staleness the same way. Standard library only."""
import re

GRANULARITY_PREFIX = {"SPAN": "eval", "TRACE": "trace_eval", "SESSION": "session_eval"}

# Templates that ask the judge to name the highest turn it saw, e.g. "LAST_TURN_CHECK: Turn 7". Without the
# marker, a "Turn N" in an explanation is only the decisive turn, so staleness can't be read from it.
LAST_TURN_MARKER = "LAST_TURN_CHECK"


def last_turn_seen(explanation):
    """The highest turn the judge says it saw, or None when the explanation doesn't say."""
    m = re.search(LAST_TURN_MARKER + r"\D{0,40}?(\d+)", explanation or "", re.I)
    return int(m.group(1)) if m else None


DEF_LINE = re.compile(r"^\s*[-*]\s*`?([A-Za-z0-9_]+)`?\s*:\s*(.*)$")
SECTION = re.compile(r"^\s*[A-Z][A-Za-z ]{0,30}:")  # "Evidence:", "Labels:" start a new section
IDENT = re.compile(r"`?\b([a-z]+(?:_[a-z0-9]+)+)\b`?")


def label_definitions(text, labels):
    """Each label's definition from `- label: text` lines, with indented or unbulleted continuation lines."""
    out, current = {}, None
    for line in (text or "").splitlines():
        m = DEF_LINE.match(line)
        if m:
            current = m.group(1) if m.group(1) in labels else None
            if current:
                out[current] = m.group(2).strip()
        elif not line.strip() or SECTION.match(line):
            current = None
        elif current and not line.lstrip().startswith(("-", "*", "#")):
            out[current] += " " + line.strip()
    return out


def definition_diff(instructions, template, labels):
    """Put the queue's and the template's definition of each label side by side, and flag candidates where they
    differ: text that is mostly different, or a tool or field name that one side's definition uses and the other
    side's doesn't. The script only points at candidates; reading both decides."""
    from difflib import SequenceMatcher
    q, t = label_definitions(instructions, labels), label_definitions(template, labels)
    rows, flagged = [], []
    for lbl in labels:
        a, b = q.get(lbl), t.get(lbl)
        if not (a and b):
            rows.append({"label": lbl, "queue": a, "template": b, "similarity": None, "only_one_side": []})
            continue
        ids = lambda s: {x for x in IDENT.findall(s) if x not in labels}
        one_side = sorted(ids(a) ^ ids(b))
        sim = SequenceMatcher(None, a.lower(), b.lower()).ratio()
        rows.append({"label": lbl, "queue": a, "template": b, "similarity": sim, "only_one_side": one_side})
        if sim < 0.6 or one_side:
            flagged.append(lbl)
    # A tool or field name both documents mention outside the label lines is a rule both sides state;
    # list it so the agent can check the two rules agree.
    shared = sorted({x for x in IDENT.findall(instructions or "")} & {x for x in IDENT.findall(template or "")} - set(labels))
    return {"rows": rows, "flagged": flagged, "shared_terms": shared}
