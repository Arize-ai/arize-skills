#!/usr/bin/env python3
"""Alignment report for an Arize evaluator against human ground truth.

Four subcommands, standard library only (Python 3.9+):

  fetch   Read-only. Calls `ax` to save a queue, all of its records (every
          page), and an evaluator to a directory. With --count-turns, also
          counts each session's turns so `report` can flag stale stored outputs.
  report  Joins the saved files and prints a Markdown alignment report: the
          judge version, its status (provisional or measured) with blockers,
          heuristic warnings with their basis, test-split numbers first, fit
          (including the queue-vs-template label definitions), and production
          estimates. No verdict tiers. Writes nothing to Arize.

  compare Read-only. Compares two `report --json-out` files from the same gold
          set (before and after a change): agreement and Scott's π with
          intervals, recall per label, records that flipped each way, and the
          shift in the evaluator's label mix. Flags a dev-to-test drop, scores a
          second judge model, applies the ship gate, and counts looks at dev.
  lint    Read-only. Flags lines a revision added to a template that name a
          record, session or trace, or copy wording from dev records: rules
          that patch cases instead of stating general rules.

Examples:
  align_report.py fetch --space SPACE --queue QUEUE --evaluator EVALUATOR --out-dir align/
  align_report.py report --dir align/ --json-out align/report.json > align/report.md
  align_report.py compare align/baseline.json align/candidate_v2.json --split dev --ledger align/looks.json
  align_report.py lint align/template_v1.txt align/template_v2.txt --records align/baseline.json
"""

import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations

GRANULARITY_PREFIX = {"SPAN": "eval", "TRACE": "trace_eval", "SESSION": "session_eval"}
DEFAULT_NOT_APPLICABLE = ["not_applicable"]
DEFAULT_UNSCORABLE = ["cannot_judge", "unclear"]

# Status: a judge is `measured` only when its measurement set is big enough, carries no stale or older-version
# results, maps one record to one unit, and has no open criterion question (eval alignment SOP step 2 and
# addendum D). Anything else is `provisional`. There are no verdict tiers.
MIN_PER_CLASS_SPLIT = 30  # Husain & Shankar: 30 to 50 per label in both dev and test
# Warnings: Arize heuristics, shown with their basis; they never change the status.
MIN_GOLD = 10
MIN_PER_CLASS = 3
MAX_EXCLUDED_RATE = 0.30
MIN_JOIN_RATE = 0.90
MIN_KAPPA = 0.60
# When one label holds this share of an annotator pair's votes, κ is low even at high raw agreement
# (the kappa paradox), so the gate also accepts Gwet's AC1.
SKEW_SHARE = 0.80
MIN_SHARED_FOR_KAPPA = 20
SPLIT = {"train": 0.15, "dev": 0.425}  # the rest is test, scored once at the end
# Heuristics for revising without overfitting: a larger π drop from dev to test means the revision fit dev,
# and dev scorings beyond the budget make dev agreement optimistic. Neither has a published small-n value.
MAX_DEV_TEST_GAP = 0.10
LOOK_BUDGET = 5

# Where each status condition comes from, printed next to a blocker.
SRC = {
    "size": "Husain & Shankar, How many examples, \"LLM judges need labeled examples\" ¶2: 30 to 50 per label "
            "in both dev and test",
    "stale": "Eval alignment SOP rule 3: grade the whole session and reject stale results",
    "version": "Eval alignment SOP rule 2: a judge version is (rubric, prompt, model, admission filter)",
    "unit": "Eval alignment SOP addendum F: one record per session",
    "criterion": "Eval alignment SOP step 1 and addendum G: decide the criterion (or pass --criterion-decided)",
}


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def run_ax(ax, args, json_flag=True, retries=5):
    for attempt in range(retries + 1):
        proc = subprocess.run([ax] + args + (["-o", "json"] if json_flag else []), capture_output=True, text=True)
        if proc.returncode == 0:
            break
        msg = proc.stderr + proc.stdout
        if ("429" in msg or "Too Many Requests" in msg) and attempt < retries:
            time.sleep(2 ** attempt)
            continue
        if "No spans found" in msg:
            return []
        sys.exit(f"ax {' '.join(args)} failed:\n{proc.stderr.strip() or proc.stdout.strip()}")
    if not json_flag and not proc.stdout.strip():
        return []  # spans export prints nothing when no spans match
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(
            f"ax {' '.join(args)} did not return JSON. This is usually an outdated CLI "
            f"that cannot parse the API response; run `ax --version` and upgrade.\n"
            f"{proc.stderr.strip()[:500]}"
        )


def cmd_fetch(a):
    os.makedirs(a.out_dir, exist_ok=True)
    queue = run_ax(a.ax, ["annotation-queues", "get", a.queue, "--space", a.space])
    records, cursor = [], None
    while True:
        args = ["annotation-queues", "list-records", queue["id"], "--limit", "100"]
        if cursor:
            args += ["--cursor", cursor]
        page = run_ax(a.ax, args)
        records.extend(page.get("records", []))
        pag = page.get("pagination") or {}
        cursor = pag.get("next_cursor")
        if not pag.get("has_more") or not cursor:
            break
    evaluator = run_ax(a.ax, ["evaluators", "get", a.evaluator, "--space", a.space])
    for name, obj in (("queue", queue), ("records", records), ("evaluator", evaluator)):
        with open(os.path.join(a.out_dir, f"{name}.json"), "w") as f:
            json.dump(obj, f, indent=1)
    print(f"Saved queue '{queue['name']}', {len(records)} records, and evaluator "
          f"'{evaluator['name']}' to {a.out_dir}")
    turns_path = os.path.join(a.out_dir, "turns.json")
    if os.path.exists(turns_path):
        os.remove(turns_path)  # counts belong to the records just fetched
    if a.count_turns:
        if LAST_TURN_MARKER not in ((evaluator.get("version") or {}).get("template_config") or {}).get("template", ""):
            print(f"Skipping --count-turns: the template has no {LAST_TURN_MARKER} marker, so stored results "
                  "don't say how many turns the judge saw.")
            return
        turns = count_turns(a, records)
        with open(turns_path, "w") as f:
            json.dump(turns, f, indent=1)
        print(f"Counted turns for {len(turns)} sessions (turns.json)")


# Templates that ask the judge to name the highest turn it saw, e.g. "LAST_TURN_CHECK: Turn 7". Without the
# marker, a "Turn N" in an explanation is only the decisive turn, so staleness can't be read from it.
LAST_TURN_MARKER = "LAST_TURN_CHECK"
SESSIONS_PER_EXPORT = 50


def last_turn_seen(explanation):
    """The highest turn the judge says it saw, or None when the explanation doesn't say."""
    m = re.search(LAST_TURN_MARKER + r"\D{0,40}?(\d+)", explanation or "", re.I)
    return int(m.group(1)) if m else None


def count_turns(a, records):
    """Root spans (turns) per session, for records whose stored result can be checked for staleness."""
    if not a.project:
        sys.exit("--count-turns needs --project")
    first = {}
    for r in records:
        d = r.get("data") or {}
        sid, t = d.get("attributes.session.id"), parse_ms(d.get("start_time"))
        if sid and t and (sid not in first or t < first[sid]):
            first[sid] = t
    turns, todo = {}, sorted(first, key=first.get)

    def export(batch):
        ids = ", ".join("'" + str(x).replace("'", "''") + "'" for x in batch)
        spans = run_ax(a.ax, ["spans", "export", a.project, "--space", a.space,
                              "--filter", f"({a.count_turns}) AND attributes.session.id IN ({ids})",
                              "--start-time", (first[batch[0]] - timedelta(hours=1)).isoformat(),
                              "--end-time", (first[batch[-1]] + timedelta(days=3)).isoformat(),
                              "-l", "500", "--stdout"], json_flag=False)
        if len(spans) >= 500 and len(batch) > 1:
            # Page cap hit; split so no session's count is truncated.
            export(batch[:len(batch) // 2])
            export(batch[len(batch) // 2:])
            return
        if len(spans) >= 500:
            print(f"Warning: session {batch[0]} has 500+ turns matching the root filter; its count is a lower bound.")
        counts = Counter((sp.get("attributes") or {}).get("session.id") for sp in spans)
        turns.update({sid: counts.get(sid, 0) for sid in batch})

    for i in range(0, len(todo), SESSIONS_PER_EXPORT):
        export(todo[i:i + SESSIONS_PER_EXPORT])
    return turns


# ---------------------------------------------------------------------------
# report helpers
# ---------------------------------------------------------------------------

def load(path):
    with open(path) as f:
        return json.load(f)


def config_of(c):
    # The API wraps each config as a oneOf; the CLI exposes it as actual_instance.
    return c.get("actual_instance", c)


def short_email(email):
    return email.split("@")[0] if email else "(unattributed)"


def n_agree(pairs):
    return sum(1 for x, y in pairs if x == y)


def chance_corrected(pairs, pe_of):
    """(p_o − p_e) / (1 − p_e) for rater pairs, with p_e from pe_of(pairs, n); 1 when chance agreement is certain."""
    n = len(pairs)
    if n == 0:
        return None
    po, pe = n_agree(pairs) / n, pe_of(pairs, n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def cohen_kappa(pairs):
    def pe(pairs, n):
        ca, cb = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
        return sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    return chance_corrected(pairs, pe)


def gwet_ac1(pairs):
    """Gwet's AC1 for two raters; stable when one label dominates, where κ collapses."""
    def pe(pairs, n):
        share = Counter(x for p in pairs for x in p)
        return sum((c / (2 * n)) * (1 - c / (2 * n)) for c in share.values()) / (max(2, len(share)) - 1)
    return chance_corrected(pairs, pe)


def scott_pi(pairs):
    """Scott's π: chance-corrected agreement with one pooled label distribution for both raters."""
    return chance_corrected(pairs, lambda pairs, n: sum((c / (2 * n)) ** 2
                                                        for c in Counter(v for p in pairs for v in p).values()))


def pabak(pairs):
    """Prevalence- and bias-adjusted κ: (q·p_o − 1) / (q − 1)."""
    if not pairs:
        return None
    q = max(2, len({x for p in pairs for x in p}))
    return (q * n_agree(pairs) / len(pairs) - 1) / (q - 1)


def boot_ci(pairs, stat, b=1000, seed=0):
    """Percentile bootstrap 95% interval for a statistic of rater pairs (seeded, so stable across runs)."""
    if len(pairs) < 2:
        return None
    rng = random.Random(seed)
    vals = sorted(v for v in (stat(rng.choices(pairs, k=len(pairs))) for _ in range(b)) if v is not None)
    return (vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]) if vals else None


def pi_with_ci(pairs):
    return {"pi": scott_pi(pairs), "ci": boot_ci(pairs, scott_pi)}


def fmt_pi(m):
    """Scott's π with its interval, e.g. 'π 0.62 (95% CI 0.41–0.80)', from pi_with_ci."""
    if m["pi"] is None:
        return "π —"
    return f"π {m['pi']:.2f}" + (f" (95% CI {m['ci'][0]:.2f}–{m['ci'][1]:.2f})" if m["ci"] else "")


def pi_ci(pairs):
    return fmt_pi(pi_with_ci(pairs))


def fmt_rate(x):
    return "—" if x is None else f"{100 * x:.0f}%"


def wilson(x, n, z=1.96):
    """95% Wilson score interval for a proportion, as (low, high)."""
    if not n:
        return None
    p = x / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def pct(x, n):
    return f"{x}/{n} ({100 * x / n:.0f}%)" if n else f"{x}/0"


def pct_ci(x, n):
    """Count, percentage and 95% interval, e.g. '9/10 (90%, 95% CI 60–98%)'."""
    if not n:
        return f"{x}/0"
    lo, hi = wilson(x, n)
    return f"{x}/{n} ({100 * x / n:.0f}%, 95% CI {100 * lo:.0f}–{100 * hi:.0f}%)"


def unit_key(row):
    """Records from one session share a split, so turns of a session never leak between train, dev and test."""
    return row.get("session_id") or row.get("trace_id") or row["record_id"]


def assign_splits(gold, test_from=None, read=frozenset()):
    """Stable train/dev/test split by session, balanced within each human label by hash rank.

    With test_from, every session that started at or after it is test (a later batch, labeled after the
    prompt was frozen), and the earlier sessions split into train and dev in the same 15 : 42.5 ratio.
    A session holding gold records under several labels takes the split its rarest label gives it.

    Sessions in `read` were read while writing a rule (SOP rule 1: tune and report on different sessions), so
    they never count as test: a test pick among them moves to dev."""
    group_split = {}
    if test_from:
        for row in gold:
            if row["start_time"] and row["start_time"] >= test_from:
                group_split[unit_key(row)] = "test"
    by_label = defaultdict(set)
    for row in gold:
        if unit_key(row) not in group_split:
            by_label[row["consensus"]].add(unit_key(row))
    for lbl in sorted(by_label, key=lambda l: (len(by_label[l]), l)):
        ranked = stable_order(by_label[lbl])
        n = len(ranked)
        n_train = int(n * (SPLIT["train"] / (SPLIT["train"] + SPLIT["dev"]) if test_from else SPLIT["train"]))
        n_dev = n - n_train if test_from else int(round(n * SPLIT["dev"]))
        for i, g in enumerate(ranked):
            group_split.setdefault(g, "train" if i < n_train else "dev" if i < n_train + n_dev else "test")
    for row in gold:
        if group_split[unit_key(row)] == "test" and str(row["session_id"]) in read:
            group_split[unit_key(row)] = "dev"
    return {row["record_id"]: group_split[unit_key(row)] for row in gold}


def held_out_ceiling(rows, decisive):
    """Human ceiling with one rater held out at a time.

    For each record with 2+ attributed votes, each rater in turn is held out and the reference is the
    majority of the others (ties skipped). The held-out rater and the judge are scored against the same
    reference, so the judge isn't flattered by a pooled consensus it never had to match."""
    human, judge = [], []
    for row in rows:
        votes = {w: v for w, v in row["votes"].items() if w != "(unattributed)"}
        if len(votes) < 2 or not row["stored"] or row["stale"]:
            continue
        for who, vote in votes.items():
            others = Counter(v for o, v in votes.items() if o != who).most_common()
            if len(others) > 1 and others[0][1] == others[1][1]:
                continue
            ref = others[0][0]
            if ref in decisive:
                human.append((vote, ref))
                judge.append((row["stored"].get("label"), ref))
    return human, judge


def stable_order(ids):
    return sorted(ids, key=lambda r: hashlib.sha256(str(r).encode()).hexdigest())


def parse_ms(v):
    try:
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_iso(v):
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def clip(s, n=160):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def build(a):
    queue = load(os.path.join(a.dir, "queue.json"))
    records = load(os.path.join(a.dir, "records.json"))
    evaluator = load(os.path.join(a.dir, "evaluator.json"))
    adjudications = load(a.adjudications) if a.adjudications else {}
    turns_path = os.path.join(a.dir, "turns.json")
    turns = load(turns_path) if os.path.exists(turns_path) else {}

    version = evaluator.get("version") or {}
    tc = version.get("template_config") or {}
    choices = list((tc.get("classification_choices") or {}).keys())
    granularity = (tc.get("data_granularity") or "SPAN").upper()
    eval_column = a.eval_column or f"{GRANULARITY_PREFIX.get(granularity, 'eval')}.{tc.get('name')}"
    read = frozenset(s.strip() for s in open(a.read_sessions).read().split() if s.strip()) if a.read_sessions else frozenset()
    rescored_at = None
    if a.rescored_at:
        rescored_at = parse_iso(a.rescored_at)
        if not rescored_at or not rescored_at.tzinfo:
            sys.exit(f"--rescored-at must be an ISO 8601 time with a zone; got {a.rescored_at!r}")
    test_from = None
    if a.test_from:
        test_from = parse_iso(a.test_from)
        if not test_from or not test_from.tzinfo:
            sys.exit(f"--test-from must be an ISO 8601 time with a zone, e.g. 2026-10-14T00:00:00Z; got {a.test_from!r}")
    # A judge is (rubric, prompt, model, admission filter): change any one and agreement must be re-measured.
    judge = {"evaluator_version": version.get("id"),
             "prompt_sha": hashlib.sha256((tc.get("template") or "").encode()).hexdigest()[:12],
             "model": (tc.get("llm_config") or {}).get("model_name"),
             "rubric_version": a.rubric_version, "admission_filter": a.admission_filter, "test_from": a.test_from}

    configs = [config_of(c) for c in queue.get("annotation_configs", [])]
    if a.config:
        config = next((c for c in configs if c.get("name") == a.config), None)
        if not config:
            sys.exit(f"Queue has no annotation config named {a.config!r}; it has {[c.get('name') for c in configs]}")
    elif len(configs) == 1:
        config = configs[0]
    else:
        sys.exit(f"Queue has {len(configs)} annotation configs; pass --config with one of {[c.get('name') for c in configs]}")
    config_name = config.get("name")
    rubric = [v.get("label") for v in config.get("values") or [] if v.get("label")]

    na = set(a.not_applicable)
    unscorable = set(a.unscorable)
    assigned = [u.get("email") for u in queue.get("annotators", [])]

    rows, other_configs, unattributed_only = [], Counter(), 0
    completion = defaultdict(Counter)
    levels_used, self_conflicts, skipped_levels = Counter(), 0, Counter()
    for r in records:
        data = r.get("data") or {}
        votes, unattributed, conflicted = {}, [], False
        # A queue can store labels at span, trace, or session level depending on its config. A SESSION record
        # shows the whole session, so only its session-level labels count; a span-level label on it was made on
        # one turn (often from an older span record of the same session) and is reported, not counted.
        session_record = (r.get("granularity") or "").upper() == "SESSION"
        for level in ("annotations", "trace_annotations", "session_annotations"):
            for ann in r.get(level) or []:
                if ann.get("name") != config_name:
                    other_configs[ann.get("name")] += 1
                    continue
                if session_record and level != "session_annotations":
                    skipped_levels[level] += 1
                    continue
                levels_used[level] += 1
                who = (ann.get("annotator") or {}).get("email")
                if not who:
                    unattributed.append(ann.get("label"))
                elif who in votes and votes[who] != ann.get("label"):
                    conflicted = True
                else:
                    votes[who] = ann.get("label")
        if conflicted:
            # The same annotator left different labels at different levels; no single vote stands.
            self_conflicts += 1
            votes = {}
        if not votes and unattributed and not conflicted:
            # Annotations applied outside the queue carry no annotator; keep one as a single vote.
            votes["(unattributed)"] = unattributed[0]
            unattributed_only += 1
        for u in r.get("assigned_users") or []:
            completion[(u.get("user") or {}).get("email")][u.get("completion_status")] += 1
        stored = next((e for e in r.get("evaluations") or [] if e.get("name") == eval_column), None)
        # A stored result whose last turn seen is lower than the session's turn count was likely scored mid-session.
        n_turns = turns.get(data.get("attributes.session.id"))
        seen = last_turn_seen((stored or {}).get("explanation"))
        stale = bool(n_turns and seen and seen < n_turns)
        rows.append({
            "record_id": r.get("id"),
            "granularity": r.get("granularity"),
            "session_id": data.get("attributes.session.id"),
            "trace_id": data.get("context.trace_id"),
            "span_id": data.get("context.span_id"),
            "start_time": parse_ms(data.get("start_time")),
            "votes": votes,
            "stored": stored,
            "stale": stale,
        })

    # Resolve each record to a gold label (or a reason it has none).
    for row in rows:
        labels = set(row["votes"].values())
        adj = adjudications.get(row["record_id"])
        if adj:
            row["consensus"], row["status"] = adj, "adjudicated"
        elif not labels:
            row["consensus"], row["status"] = None, "unlabeled"
        elif len(labels) > 1:
            row["consensus"], row["status"] = None, "disputed"
        else:
            row["consensus"] = labels.pop()
            row["status"] = "single" if len(row["votes"]) == 1 else "agreed"
        c = row["consensus"]
        if c is None:
            row["bucket"] = row["status"]
        elif c in na:
            row["bucket"] = "not_applicable"
        elif c in unscorable:
            row["bucket"] = "unscorable"
        elif choices and c not in choices:
            row["bucket"] = "off_rubric"
        else:
            row["bucket"] = "gold"

    # Annotator agreement over records with at least two attributed votes.
    annotators = sorted({w for row in rows for w in row["votes"] if w != "(unattributed)"})
    iaa = []
    for x, y in combinations(annotators, 2):
        pairs = [(row["votes"][x], row["votes"][y]) for row in rows if x in row["votes"] and y in row["votes"]]
        if pairs:
            top = Counter(v for p in pairs for v in p).most_common(1)[0][1] / (2 * len(pairs))
            kappa, ac1 = cohen_kappa(pairs), gwet_ac1(pairs)
            skewed = top >= SKEW_SHARE
            iaa.append({"a": x, "b": y, "n": len(pairs), "agree": n_agree(pairs),
                        "kappa": kappa, "pi": scott_pi(pairs), "ac1": ac1, "pabak": pabak(pairs), "majority_share": top,
                        "skewed": skewed,
                        "ok": kappa >= MIN_KAPPA or (skewed and ac1 is not None and ac1 >= MIN_KAPPA)})
    multi = [row for row in rows if len(row["votes"]) >= 2]
    disputed = [row for row in rows if row["status"] == "disputed"]

    # Join and coverage.
    n = len(rows)
    joined = [row for row in rows if row["session_id"] or granularity != "SESSION"]
    session_counts = Counter(row["session_id"] for row in rows if row["session_id"])
    dup_sessions = {s: c for s, c in session_counts.items() if c > 1}
    with_stored = [row for row in rows if row["stored"]]
    created = parse_iso(version.get("created_at"))
    # After an in-place edit every earlier session started before the version was created. A one-off scoring run
    # on these sessions after the switch (--rescored-at) makes their stored results the current version's.
    if rescored_at and created and rescored_at < created:
        sys.exit(f"--rescored-at {a.rescored_at} is before the current version was created ({version.get('created_at')}); "
                 "re-score the sessions after the switch")
    older = [] if rescored_at else [row for row in rows if created and row["start_time"] and row["start_time"] < created]

    # Human vs evaluator.
    gold = [row for row in rows if row["bucket"] == "gold"]
    # A result scored before its session ended graded fewer turns than exist; it is not this judge version's result.
    gold_scored = [row for row in gold if row["stored"] and not row["stale"]]
    confusion = Counter((row["consensus"], row["stored"].get("label")) for row in gold_scored)
    per_label = {}
    for lbl in sorted({row["consensus"] for row in gold_scored}):
        tp = confusion[(lbl, lbl)]
        fp = sum(c for (h, e), c in confusion.items() if e == lbl and h != lbl)
        fn = sum(c for (h, e), c in confusion.items() if h == lbl and e != lbl)
        per_label[lbl] = {"precision": tp / (tp + fp) if tp + fp else None,
                          "recall": tp / (tp + fn) if tp + fn else None, "support": tp + fn,
                          "tp": tp, "predicted": tp + fp}
    agree = sum(c for (h, e), c in confusion.items() if h == e)
    # Mean recall over the human labels: the TPR/TNR average for a binary judge, robust to class imbalance.
    recalls = [m["recall"] for m in per_label.values() if m["recall"] is not None]
    balanced = sum(recalls) / len(recalls) if recalls else None
    judge_pairs = [(row["consensus"], row["stored"].get("label")) for row in gold_scored]

    # Applicability is scored on its own line: was the record in scope at all, per human and per judge.
    app_pairs = [("applicable" if row["bucket"] == "gold" else "not_applicable",
                  "not_applicable" if row["stored"].get("label") in na else "applicable")
                 for row in rows if row["bucket"] in ("gold", "not_applicable") and row["stored"] and not row["stale"]]
    decisive = [c for c in choices if c not in na]
    ceiling_human, ceiling_judge = held_out_ceiling(rows, decisive)

    # Held-out split of the gold records, by session and human label, stable across runs.
    splits = assign_splits(gold, test_from, read)
    unread = assign_splits(gold, test_from) if read else splits
    moved_from_test = sorted({str(row["session_id"]) for row in gold
                              if unread[row["record_id"]] == "test" and splits[row["record_id"]] != "test"})
    for row in rows:
        row["split"] = splits.get(row["record_id"])
    split_counts = {s: Counter(row["consensus"] for row in gold if row["split"] == s) for s in ("train", "dev", "test")}
    test_scored = [row for row in gold_scored if row["split"] == "test"]
    test_pairs = [(row["consensus"], row["stored"].get("label")) for row in test_scored]
    test_recall = {lbl: (sum(1 for h, e in test_pairs if h == lbl and e == lbl), sum(1 for h, _ in test_pairs if h == lbl))
                   for lbl in sorted({h for h, _ in test_pairs})}
    # With one dominant human label, π (like κ) is low even at high raw agreement, so report prevalence-robust
    # measures beside it and read the failing label's recall first.
    top_human = Counter(h for h, _ in judge_pairs).most_common(1)
    skew = None
    if top_human and top_human[0][1] / len(judge_pairs) >= SKEW_SHARE:
        skew = {"label": top_human[0][0], "share": top_human[0][1] / len(judge_pairs),
                "ac1": gwet_ac1(judge_pairs), "pabak": pabak(judge_pairs)}

    plan = load(a.plan) if a.plan else None
    weighted = weight_by_plan(plan, gold_scored) if plan else None
    production = ppi_rates(plan, rows, choices) if plan else None
    na_rows = [row for row in rows if row["bucket"] == "not_applicable" and row["stored"]]
    applicability = Counter(row["stored"].get("label") for row in na_rows)

    # Fit checks.
    vote_labels = Counter(v for row in rows for v in row["votes"].values())
    fit = []
    if (rows and rows[0]["granularity"] or "").upper() != granularity:
        fit.append(f"Queue records are `{rows[0]['granularity'] if rows else '?'}` but the evaluator scores "
                   f"`{granularity}`. Each record must map to exactly one {granularity.lower()}; "
                   f"verify the evaluator's input (e.g. `{{conversation}}`) is the full {granularity.lower()} the labeler saw.")
    missing_in_rubric = [c for c in choices if c not in rubric]
    if missing_in_rubric:
        fit.append(f"Evaluator choices missing from the human rubric: {missing_in_rubric}. Humans cannot produce these labels.")
    extra = [l for l in rubric if l not in choices and l not in na | unscorable]
    if extra:
        fit.append(f"Human rubric labels the evaluator cannot output: {extra}. Records with these labels are excluded as off-rubric.")
    unseen = [c for c in choices if c not in vote_labels and c not in na]
    if unseen:
        fit.append(f"Evaluator classes with zero human examples: {unseen}. The queue cannot test whether the evaluator produces them correctly.")
    template = tc.get("template") or ""
    if granularity == "SESSION" and LAST_TURN_MARKER not in template:
        fit.append(f"The template doesn't ask the judge to report `{LAST_TURN_MARKER}`, so results scored before a "
                   "session ended can't be detected or refused. Add the marker to session evaluators.")
    if "{turn_data}" in template:
        fit.append("The evaluator template reads `{turn_data}` (per-turn data from the task's query mappings), not the "
                   "whole session. If humans judged the whole session, the two sides graded different inputs.")
    instructions = queue.get("instructions") or ""
    undefined = [c for c in decisive
                 if not re.search(r"(?<![\w-])" + r"[_ ]".join(map(re.escape, re.split(r"[_ ]", c))) + r"(?![\w-])",
                                  instructions, re.I)]
    if undefined:
        fit.append(f"Queue instructions never mention {len(undefined)} of {len(decisive)} evaluator labels ({undefined}), "
                   "and annotation configs carry no label definitions. If labelers saw label names only, expect "
                   "disagreements about what a label means (phase 1 compares the definitions).")
    if other_configs:
        fit.append("Records also carry labels from other annotation configs "
                   + ", ".join(f"`{k}` ({v})" for k, v in other_configs.most_common())
                   + f". They were ignored; only `{config_name}` is used.")
    if levels_used:
        fit.append(f"`{config_name}` labels were read from: "
                   + ", ".join(f"`{k}` ({v})" for k, v in levels_used.most_common()) + ".")
    if skipped_levels:
        fit.append(f"Session records also carry span- or trace-level `{config_name}` labels "
                   + ", ".join(f"`{k}` ({v})" for k, v in skipped_levels.most_common())
                   + ". They judged one turn, not the session, so only `session_annotations` were counted.")
    if self_conflicts:
        fit.append(f"{self_conflicts} record(s) have one annotator giving different labels at different levels; "
                   "they are treated as unlabeled until resolved.")
    if unattributed_only:
        fit.append(f"{unattributed_only} record(s) have only unattributed `{config_name}` labels (applied outside the queue).")

    # Status. A judge is `measured` only when every condition below holds; otherwise it is `provisional`
    # (eval alignment SOP step 2 and addendum D). Each failing condition is a blocker.
    gold_classes = Counter(row["consensus"] for row in gold)
    scored_split = {s: Counter(row["consensus"] for row in gold_scored if row["split"] == s) for s in ("dev", "test")}
    sized = [c for c in gold_classes
             if scored_split["dev"][c] >= MIN_PER_CLASS_SPLIT and scored_split["test"][c] >= MIN_PER_CLASS_SPLIT]
    stale = [row for row in rows if row["stale"]]
    stale_gold = [row for row in gold if row["stale"]]
    older_gold = [] if rescored_at else [row for row in gold if created and row["start_time"] and row["start_time"] < created]
    unscored_gold = [row for row in gold if not row["stored"]]
    span_records = sum(1 for row in rows if (row["granularity"] or "").upper() != "SESSION")
    marker = LAST_TURN_MARKER in template
    defs = definition_diff(instructions, template, decisive)
    blockers = []
    if len(sized) < 2:
        blockers.append({
            "condition": f"Size: {MIN_PER_CLASS_SPLIT}+ scored gold records per label in each of dev and test, for 2+ labels",
            "value": "; ".join(f"`{c}` dev {scored_split['dev'][c]} / test {scored_split['test'][c]}"
                               for c in sorted(gold_classes)) or "no gold records",
            "source": SRC["size"]})
    if stale_gold:
        blockers.append({"condition": "No stale results on gold records",
                         "value": f"{len(stale_gold)} scored before their session ended",
                         "source": SRC["stale"]})
    elif granularity == "SESSION" and marker and not turns:
        blockers.append({"condition": "No stale results on gold records",
                         "value": "not checked: run `fetch --count-turns`", "source": SRC["stale"]})
    if unscored_gold or older_gold:
        blockers.append({"condition": "Every gold record carries a result from the current judge version",
                         "value": f"{len(unscored_gold)} with no stored result; {len(older_gold)} started before the "
                                  "current version was created (may be an older version's result)",
                         "source": SRC["version"]})
    if granularity == "SESSION" and (len(joined) < n or dup_sessions):
        blockers.append({"condition": "Each record is one session",
                         "value": f"{n - len(joined)} record(s) with no session ID; {len(dup_sessions)} duplicated session(s)",
                         "source": SRC["unit"]})
    if defs["flagged"] and not a.criterion_decided:
        blockers.append({"condition": "Queue and template define the labels the same way",
                         "value": "candidate criterion question: " + ", ".join(f"`{x}`" for x in defs["flagged"]),
                         "source": SRC["criterion"]})
    status = "measured" if not blockers else "provisional"

    # Warnings: Arize heuristics. They are shown with their basis and never change the status.
    excluded = sum(1 for row in rows if row["bucket"] in ("not_applicable", "unscorable", "off_rubric"))
    labeled = sum(1 for row in rows if row["bucket"] != "unlabeled")
    warnings = []
    def warn(ok, check, value, basis):
        if not ok:
            warnings.append({"check": check, "value": value, "basis": basis})
    warn(len(gold) >= MIN_GOLD, f"At least {MIN_GOLD} gold records", str(len(gold)),
         "Arize heuristic. At 10 records, 90% agreement has a 95% interval of about 60–98%.")
    thin = [c for c in decisive if gold_classes.get(c, 0) < MIN_PER_CLASS]
    warn(not thin, f"At least {MIN_PER_CLASS} gold records per label",
         ", ".join(f"`{c}` {gold_classes.get(c, 0)}" for c in thin), "Arize heuristic")
    warn(labeled == 0 or excluded / labeled <= MAX_EXCLUDED_RATE, f"Excluded share ≤ {MAX_EXCLUDED_RATE:.0%}",
         pct(excluded, labeled), "Arize heuristic. Excluding hard cases inflates agreement (Zheng et al., ties vs no ties).")
    warn(not gold or len(gold_scored) / len(gold) >= MIN_JOIN_RATE, f"Score coverage ≥ {MIN_JOIN_RATE:.0%} of gold",
         pct(len(gold_scored), len(gold)), "Arize heuristic")
    warn(n == 0 or len(joined) / n >= MIN_JOIN_RATE, f"Join coverage ≥ {MIN_JOIN_RATE:.0%}", pct(len(joined), n),
         "Arize heuristic")
    for p in iaa:
        warn(p["ok"], f"Annotator agreement κ ≥ {MIN_KAPPA} (AC1 when one label holds ≥ {SKEW_SHARE:.0%})",
             f"{short_email(p['a'])}/{short_email(p['b'])} κ {p['kappa']:.2f}, AC1 {p['ac1']:.2f} on {p['n']}",
             "Landis & Koch; McHugh 2012; Gwet 2008")
    warn(bool(multi), "Two or more annotators on some records", "single annotator; no human ceiling measured",
         "Eval alignment SOP addendum E; Mukherjee et al.")
    warn(not disputed, "No open disputes", f"{len(disputed)} disputed", "A disputed record has no gold label")
    warn(granularity != "SESSION" or not span_records, "Session judge labeled on session records",
         f"{span_records} span record(s): each opens on one turn",
         "Eval alignment SOP addendum F")

    # Failing labels, named with --fail-label: their recall leads, and leniency is the share of human-failed
    # records the judge did not fail.
    fail = [f for f in (a.fail_label or []) if f in choices]
    failed = [row for row in gold_scored if row["consensus"] in fail]
    leniency = (sum(1 for row in failed if row["stored"].get("label") not in fail), len(failed)) if fail else None

    mismatches = [row for row in rows if row["stored"] and row["consensus"] and row["stored"].get("label") != row["consensus"]]
    return {
        "queue": queue, "evaluator": evaluator, "version": version, "tc": tc, "choices": choices,
        "granularity": granularity, "eval_column": eval_column, "config_name": config_name, "rubric": rubric,
        "assigned": assigned, "completion": completion, "rows": rows,
        "iaa": iaa, "multi": multi, "disputed": disputed, "dup_sessions": dup_sessions,
        "with_stored": with_stored, "older": older, "gold": gold, "gold_scored": gold_scored,
        "confusion": confusion, "per_label": per_label, "agree": agree, "na_rows": na_rows,
        "applicability": applicability, "fit": fit, "status": status, "blockers": blockers, "warnings": warnings,
        "definitions": defs, "fail_labels": fail, "leniency": leniency,
        "gold_classes": gold_classes, "annotators": annotators, "mismatches": mismatches, "stale": stale,
        "turns_fetched": bool(turns), "marker": marker,
        "balanced": balanced, "split_counts": split_counts, "weighted": weighted,
        "judge": judge, "judge_pi": pi_with_ci(judge_pairs), "app_pairs": app_pairs, "skew": skew,
        "test_pairs": test_pairs, "test_pi": pi_with_ci(test_pairs), "test_recall": test_recall,
        "ceiling_human": ceiling_human, "ceiling_judge": ceiling_judge, "production": production,
        "planned": bool(plan), "read": sorted(read), "moved_from_test": moved_from_test,
        "rescored_at": a.rescored_at,
    }

class PlanIndex:
    """Planned records by span ID, falling back to session ID: a SESSION queue record's span is its session's
    first trace, which is usually but not always the span the plan recorded. Every reader of plan.json uses it."""

    def __init__(self, plan):
        recs = plan.get("records") or []
        self.by_span = {r.get("span_id"): r for r in recs}
        self.by_session = {str(r.get("session_id")): r for r in recs if r.get("session_id") is not None}

    def get(self, row):
        return self.by_span.get(row.get("span_id")) or self.by_session.get(str(row.get("session_id")))


def plan_index(plan):
    return PlanIndex(plan)


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
    side's doesn't. The script only points at candidates; the agent decides by reading both (phase 1)."""
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


def weight_by_plan(plan, gold_scored):
    """Production-weighted agreement and per-label recall, from the queue builder's strata.

    The queue oversamples rare stored labels and provider disagreements, so raw agreement on it is
    not a production rate. Each stratum's gold records stand in for its production units (strata
    without gold are reported as uncovered). Assumes exclusions are random within a stratum.

    Records from the plan's random stream are a uniform sample, so a queue of only those is already a
    measurement and needs no weights; they are never pooled into the targeted strata."""
    planned = plan_index(plan)
    streams = Counter((planned.get(row) or {}).get("stream", "unplanned") for row in gold_scored)
    if gold_scored and streams["random"] == len(gold_scored):
        frames = [s.get("frame") for s in plan.get("strata") or [] if s.get("stream") == "random"]
        return {"random_only": True, "streams": dict(streams),
                "frame": sum(frames) if frames and None not in frames else None}
    strata = {s["stratum"]: s for s in plan.get("strata") or [] if s.get("population") and s.get("stream") == "targeted"}
    if not strata:
        return {"error": "plan.json has no strata with production counts (re-plan with a current plan_queue.py)"}
    groups = defaultdict(list)
    for row in gold_scored:
        h = (planned.get(row) or {}).get("stratum")
        if h in strata:
            groups[h].append(row)
    covered = {h: s["population"] for h, s in strata.items() if groups.get(h)}
    total = sum(s["population"] for s in strata.values())
    if not covered:
        return {"error": "no gold record maps to a plan stratum (check the plan and queue match)"}
    pop = sum(covered.values())
    agree = sum(n * sum(1 for r in groups[h] if r["stored"].get("label") == r["consensus"]) / len(groups[h])
                for h, n in covered.items()) / pop
    recall = {}
    for lbl in sorted({r["consensus"] for g in groups.values() for r in g}):
        has = sum(n * sum(1 for r in groups[h] if r["consensus"] == lbl) / len(groups[h]) for h, n in covered.items())
        hit = sum(n * sum(1 for r in groups[h] if r["consensus"] == lbl and r["stored"].get("label") == lbl)
                  / len(groups[h]) for h, n in covered.items())
        recall[lbl] = hit / has if has else None
    return {"agreement": agree, "recall": recall, "covered_share": pop / total if total else None,
            "streams": dict(streams),
            "uncovered": sorted(h for h in strata if h not in covered),
            "lower_bound": any(s.get("population_lower_bound") for s in strata.values())}


def ppi_rates(plan, rows, labels):
    """Production rate of each human label, corrected with PPI++ from the plan's random-stream labels.

    The judge's labels on all production units are the random stratum's label_counts (every scored unit
    in that period); the human labels come only from random-stream records, because PPI assumes the
    labeled set is a random sample of that traffic. Each period (the first plan and every intake run) is
    estimated on its own and combined by its production size. λ is tuned per label and clipped to
    [0, 1]: 0 is the human-only estimate, 1 is plain PPI. The human-only estimate is reported too; use
    whichever interval is narrower."""
    planned = plan_index(plan)
    pops = {s.get("period", ""): Counter(s.get("label_counts") or {})
            for s in plan.get("strata") or [] if s.get("stream") == "random"}
    labeled = defaultdict(list)
    for row in rows:
        p = planned.get(row)
        if (p and p.get("stream") == "random" and row["bucket"] in ("gold", "not_applicable")
                and row["stored"] and not row["stale"]):
            labeled[p.get("period", "")].append((row["consensus"], row["stored"].get("label")))
    if not labeled:
        return {"error": "no labeled records from the plan's random stream; corrected rates need a random sample"}
    missing = sorted(p or "first plan" for p in labeled if not sum(pops.get(p, Counter()).values()))
    if missing:
        return {"error": f"no production label counts for {missing} (re-plan with a current plan_queue.py)"}
    total = sum(sum(pops[p].values()) for p in labeled)

    def wald(est, var):
        half = 1.96 * math.sqrt(max(var, 0.0))
        return max(0.0, est - half), min(1.0, est + half)

    def var_of(xs):
        m = sum(xs) / len(xs)
        return sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)

    rates = {}
    for k in labels:
        judge_only = est = var = human = human_var = 0.0
        for p, pairs in labeled.items():
            big_n, n = sum(pops[p].values()), len(pairs)
            w = big_n / total
            y = [1.0 if h == k else 0.0 for h, _ in pairs]
            f = [1.0 if j == k else 0.0 for _, j in pairs]
            f_all = pops[p][k] / big_n
            v_all = f_all * (1 - f_all)
            y_bar, f_bar = sum(y) / n, sum(f) / n
            cov = sum((yi - y_bar) * (fi - f_bar) for yi, fi in zip(y, f)) / max(1, n - 1)
            lam = min(1.0, max(0.0, cov / ((1 + n / big_n) * v_all))) if v_all > 0 else 0.0
            judge_only += w * f_all
            est += w * (lam * f_all + y_bar - lam * f_bar)
            var += w * w * (lam * lam * v_all / big_n + var_of([yi - lam * fi for yi, fi in zip(y, f)]) / n)
            human += w * y_bar
            human_var += w * w * var_of(y) / n
        ppi_ci, human_ci = wald(est, var), wald(human, human_var)
        rates[k] = {"judge_only": judge_only, "ppi": min(1.0, max(0.0, est)), "ppi_ci": ppi_ci,
                    "human": human, "human_ci": human_ci,
                    "use": "ppi" if ppi_ci[1] - ppi_ci[0] < human_ci[1] - human_ci[0] else "human"}
    return {"rates": rates, "n": sum(len(v) for v in labeled.values()), "units": total, "periods": len(labeled)}


NEXT_ACTIONS = {
    "provisional": "Report every number with its interval and don't claim a target. Fix clear criterion, scope or "
                   "queue problems first, then make at most one batch of template fixes; don't tune prompt by prompt.",
    "measured": "The revise loop and the ship gate apply: save the baseline, edit the evaluator in place and record the "
                "switch time, re-score, batched general edits, freeze, a later test batch scored once, a second judge "
                "model, then `compare --gate`.",
}


def render(r):
    q, ev, v, tc = r["queue"], r["evaluator"], r["version"], r["tc"]
    rows, out = r["rows"], []
    w = out.append
    w(f"# Alignment report: `{ev.get('name')}` vs queue \"{q.get('name')}\"\n")
    w("No evaluator, task, or queue was changed to produce this report.\n")

    j = r["judge"]
    w("## Judge version\n")
    w(f"- Evaluator `{ev.get('id')}`, version `{j['evaluator_version']}` created {v.get('created_at')} "
      f"(\"{clip(v.get('commit_message'), 120)}\")")
    w(f"- Prompt `{j['prompt_sha']}`, model `{j['model']}`, rubric `{j['rubric_version'] or 'not given'}`, admission "
      "filter " + (f"`{clip(j['admission_filter'], 120)}`" if j["admission_filter"] else "`not given`")
      + (f"; test batch from `{j['test_from']}`" if j["test_from"] else ""))
    w(f"- Granularity `{r['granularity']}`, output column `{r['eval_column']}`, choices {r['choices']}")
    w(f"- Queue `{q.get('id')}`: {len(rows)} records, annotation config `{r['config_name']}`, rubric {r['rubric']}")
    if not (j["rubric_version"] and j["admission_filter"]):
        w("  - Pass `--rubric-version` and `--admission-filter`: a change to either is a different judge, and these "
          "numbers don't carry over.")
    w("")

    w(f"## Status: {r['status']}\n")
    if r["blockers"]:
        w("| Blocking condition | Value | Source |")
        w("|---|---|---|")
        for b in r["blockers"]:
            w(f"| {b['condition']} | {b['value']} | {b['source']} |")
    else:
        w("Every status condition holds.")
    w("")
    w(f"**Allowed next actions:** {NEXT_ACTIONS[r['status']]}"
      + (" A criterion question is open: no template edits until it's decided." if any(
          "criterion" in b["source"] for b in r["blockers"]) else "") + "\n")

    if r["warnings"]:
        w("## Warnings\n")
        w("These don't change the status. Each states its basis.\n")
        w("| Check | Value | Basis |")
        w("|---|---|---|")
        for x in r["warnings"]:
            w(f"| {x['check']} | {x['value']} | {x['basis']} |")
        w("")

    gs, tp = r["gold_scored"], r["test_pairs"]
    fail = r["fail_labels"]
    order = lambda labels: sorted(labels, key=lambda lbl: (lbl not in fail, lbl))
    w("## Test split (the numbers to report)\n")
    if r["judge"]["test_from"]:
        w(f"Test is every gold session that started at or after `{r['judge']['test_from']}`: a batch labeled after "
          "the prompt was frozen. Score it once per judge version.\n")
    else:
        w("Test is drawn from the same batch as dev, so these numbers are **directional**. The real test is a batch "
          "labeled after freezing the prompt (`--test-from`).\n")
    if r["read"]:
        w(f"{len(r['read'])} session(s) were read while writing the rules (`--read-sessions`); they never count as test"
          + (f", so {len(r['moved_from_test'])} moved from test to dev" if r["moved_from_test"] else "")
          + " (SOP rule 1: tune and report on different sessions).\n")
    if not tp:
        w("No test record has a current stored result yet.\n")
    else:
        w(f"- Exact agreement: {pct_ci(n_agree(tp), len(tp))}; Scott's {fmt_pi(r['test_pi'])}")
        for lbl in order(r["test_recall"]):
            hit, n = r["test_recall"][lbl]
            w(f"- Recall for `{lbl}`{' (failing)' if lbl in fail else ''}: {pct_ci(hit, n)}")
        w("")

    w("## All scored gold records\n")
    if not gs:
        w("No gold record has a usable stored result, so agreement can't be computed yet.\n")
    else:
        w("Recall per human label (TPR and TNR for a binary judge), failing labels first:\n")
        for lbl in order(r["per_label"]):
            m = r["per_label"][lbl]
            w(f"- `{lbl}`{' (failing)' if lbl in fail else ''}: {pct_ci(m['tp'], m['support'])}")
        if r["balanced"] is not None:
            w(f"- Balanced accuracy (mean of the above): {100 * r['balanced']:.0f}%")
        if r["leniency"]:
            k, n = r["leniency"]
            w(f"- Leniency (human said {fail}, judge didn't): {pct_ci(k, n)}" if n else
              f"- Leniency: no gold record has a failing human label ({fail}).")
        elif not fail:
            w("- Leniency: pass `--fail-label` to name the failing labels.")
        w("")
        w(f"Exact agreement: {pct_ci(r['agree'], len(gs))}; Scott's {fmt_pi(r['judge_pi'])}. Never quote percent "
          "agreement alone: judges with over 90% agreement have still mis-scored by 10 points or more (Thakur et al.).\n")
        sk = r["skew"]
        if sk:
            w(f"One human label (`{sk['label']}`) holds {sk['share']:.0%} of these records, so π understates agreement "
              f"(the same prevalence effect as κ). Next to it: Gwet's AC1 {sk['ac1']:.2f}, PABAK {sk['pabak']:.2f}"
              + (f", balanced accuracy {100 * r['balanced']:.0f}%" if r["balanced"] is not None else "")
              + ". Read the failing labels' recall first.\n")
        w("Precision per judge label (the share humans confirmed):\n")
        for lbl in order(r["per_label"]):
            m = r["per_label"][lbl]
            w(f"- `{lbl}`: {pct_ci(m['tp'], m['predicted'])}")
        w("")
        w("| Human \\ Judge | " + " | ".join(f"`{c}`" for c in r["choices"]) + " |")
        w("|---|" + "---:|" * len(r["choices"]))
        for h in sorted({row["consensus"] for row in gs}):
            w(f"| `{h}` | " + " | ".join(str(r["confusion"].get((h, c), 0)) for c in r["choices"]) + " |")
        w("")
    ap = r["app_pairs"]
    if ap:
        w("### Applicability and grade\n")
        w(f"- Applicability (in scope or not): {pct_ci(n_agree(ap), len(ap))}; Scott's {pi_ci(ap)}")
        w(f"- Grade (gold records only): {pct_ci(r['agree'], len(gs))}")
        w("A scope disagreement needs a scope rule, not a grading rule (SOP step 1).\n")
    ch, cj = r["ceiling_human"], r["ceiling_judge"]
    w("### Human ceiling\n")
    if ch:
        w(f"One rater held out at a time, against the same reference as the judge, on {len(ch)} comparisons "
          "(Mukherjee et al.):\n")
        w(f"- Held-out humans: {pct_ci(n_agree(ch), len(ch))}; Scott's {pi_ci(ch)}")
        w(f"- Judge: {pct_ci(n_agree(cj), len(cj))}; Scott's {pi_ci(cj)}")
        w("Don't tune past the human ceiling.\n")
    else:
        w("Single annotator; no human ceiling measured. Every gold label rests on one person.\n")

    w("## Fit between queue and judge\n")
    d = r["definitions"]
    if d["rows"]:
        w("Each label's definition in the queue instructions and in the judge's template (phase 1). A difference "
          "means the human and the judge apply different rules: a criterion question, not a judge error.\n")
        w("| Label | Queue instructions | Judge template | Flag |")
        w("|---|---|---|---|")
        for x in d["rows"]:
            flag = ("⚠ " + ("differs" if x["similarity"] is not None and x["similarity"] < 0.6 else "")
                    + (f" names only on one side: {x['only_one_side']}" if x["only_one_side"] else "")) \
                if x["label"] in d["flagged"] else ("not defined on one side" if x["similarity"] is None else "")
            w(f"| `{x['label']}` | {clip(x['queue'], 220) or '—'} | {clip(x['template'], 220) or '—'} | {flag.strip()} |")
        w("")
        if d["shared_terms"]:
            w(f"Terms both documents use: {', '.join(f'`{s}`' for s in d['shared_terms'][:12])}. Check that each "
              "side states the same rule about them.\n")
    for f in r["fit"]:
        w(f"- {f}")
    w("")

    w("## Records and labels\n")
    w("| Annotator | Completed | Pending | Votes cast |")
    w("|---|---:|---:|---:|")
    vote_by = Counter(who for row in rows for who in row["votes"])
    for who in sorted(set(r["assigned"]) | set(r["completion"]) | set(vote_by)):
        c = r["completion"].get(who, Counter())
        w(f"| {short_email(who)} | {c.get('COMPLETED', 0)} | {sum(c.values()) - c.get('COMPLETED', 0)} | {vote_by.get(who, 0)} |")
    w("")
    buckets = Counter(row["bucket"] for row in rows)
    labels = Counter(row["consensus"] for row in rows if row["consensus"])
    w("| Human label | Records | Bucket |")
    w("|---|---:|---|")
    for lbl, c in labels.most_common():
        b = next(row["bucket"] for row in rows if row["consensus"] == lbl)
        w(f"| `{lbl}` | {c} | {b} |")
    for b in ("unlabeled", "disputed"):
        if buckets.get(b):
            w(f"| — | {buckets[b]} | {b} |")
    w("")
    if r["multi"]:
        for p in r["iaa"]:
            w(f"- {short_email(p['a'])} vs {short_email(p['b'])}: {pct_ci(p['agree'], p['n'])} agree, κ = {p['kappa']:.2f}, "
              f"π = {p['pi']:.2f}, AC1 = {p['ac1']:.2f}, PABAK = {p['pabak']:.2f}; top label {p['majority_share']:.0%}"
              + (" (the kappa paradox: with one dominant label κ understates agreement, so AC1 is the check)"
                 if p["skewed"] else "")
              + (f"; only {p['n']} shared records, a rough check" if p["n"] < MIN_SHARED_FOR_KAPPA else ""))
        w("")
    if r["disputed"]:
        w("Disputed records (no gold label until adjudicated):\n")
        for row in r["disputed"]:
            w(f"- `{row['record_id']}` session {row['session_id']}: "
              + ", ".join(f"{short_email(k)}=`{x}`" for k, x in row["votes"].items()))
        w("")
    w(f"- `{r['eval_column']}` present on {pct(len(r['with_stored']), len(rows))} records.")
    if r["stale"]:
        w(f"- {len(r['stale'])} stored result(s) saw fewer turns than the session has (`{LAST_TURN_MARKER}`): scored "
          "mid-session, so left out. Re-run the current version on those sessions.")
    elif r["marker"] and not r["turns_fetched"]:
        w(f"- The template reports `{LAST_TURN_MARKER}`; run `fetch --count-turns` to check for mid-session results.")
    if r["older"]:
        w(f"- {len(r['older'])} record(s) started before the current version was created; their results may be an "
          "older version's. After re-scoring them with the current version, pass `--rescored-at RUN_START`.")
    if r["rescored_at"]:
        w(f"- Stored results are taken as the current version's: re-scored by a run at `{r['rescored_at']}`.")
    if r["na_rows"]:
        w("- On records humans marked not applicable, the judge said: "
          + ", ".join(f"`{lbl}` {c}" for lbl, c in r["applicability"].most_common()))
    w("")

    wt, pr = r["weighted"], r["production"]
    w("## Production estimates\n")
    if not r["planned"]:
        w("No `--plan`: these records' selection probabilities are unknown, so nothing here is a production rate. "
          "Corrected rates need random-stream labels from **arize-align-queue-builder** (SOP rule 5).\n")
    if wt:
        if wt.get("error"):
            w(f"Weighted estimates not computed: {wt['error']}.\n")
        elif wt.get("random_only"):
            w("Every scored gold record is from the plan's random stream" + (f" (a uniform sample of {wt['frame']} scored "
              "units)" if wt.get("frame") else "") + ", so the numbers above are measurement estimates.\n")
        else:
            w("These records were targeted, so these weighted figures are a **secondary** estimate; take "
              "measurement from the calibration queue. Each stratum is weighted by its production count. This "
              "assumes uniform sampling within a stratum; the queue builder rotates across entry points inside a "
              "label without recording it, so treat these as approximate.\n"
              + (f"{wt['streams']['random']} gold records here are from the random stream.\n"
                 if wt["streams"].get("random") else ""))
            w(f"- Agreement: {100 * wt['agreement']:.0f}%")
            for lbl, rec in wt["recall"].items():
                w(f"- Recall for `{lbl}`: {fmt_rate(rec)}")
            w(f"- Strata with gold cover {100 * (wt['covered_share'] or 0):.0f}% of the planned production units"
              + (f"; no gold in: {wt['uncovered']}" if wt["uncovered"] else "") + ".\n")
    if pr:
        if pr.get("error"):
            w(f"Corrected production rates not computed: {pr['error']}.\n")
        else:
            w(f"Corrected production rates from the judge's labels on {pr['units']} units and {pr['n']} human-labeled "
              f"random-stream records (SOP step 8). Use whichever of the corrected and human-only intervals is "
              "narrower (Lee et al. §6).\n")
            w("| Label | Judge only | Corrected (PPI++) | Human only | Use |")
            w("|---|---:|---:|---:|---|")
            for k, m in pr["rates"].items():
                w(f"| `{k}` | {100 * m['judge_only']:.1f}% | {100 * m['ppi']:.1f}% "
                  f"({100 * m['ppi_ci'][0]:.1f}–{100 * m['ppi_ci'][1]:.1f}%) | {100 * m['human']:.1f}% "
                  f"({100 * m['human_ci'][0]:.1f}–{100 * m['human_ci'][1]:.1f}%) | "
                  + ("corrected" if m["use"] == "ppi" else "human only") + " |")
            if pr["n"] < 30:
                w(f"\nOnly {pr['n']} random-stream labels: these intervals are rough.")
            w("\nPPI assumes the labeled records have the same label mix as production. That holds for the random "
              "stream; a stratified sample without its weights biases it (Lee et al. §8). Re-collect labels after any "
              "judge version change.\n")

    sc = r["split_counts"]
    if r["gold"]:
        w("## Split\n")
        w("By session, within each human label, stable across runs. Train may supply few-shot examples, dev is for "
          "reading disagreements and iterating, test is scored once per frozen version.\n")
        w("| Human label | Train | Dev | Test |")
        w("|---|---:|---:|---:|")
        for lbl in sorted(r["gold_classes"]):
            w(f"| `{lbl}` | {sc['train'][lbl]} | {sc['dev'][lbl]} | {sc['test'][lbl]} |")
        w("")

    mism = r["mismatches"]
    if mism:
        w("## Disagreements\n")
        w("| Record | Session | Split | Human | Judge | Judge explanation |")
        w("|---|---|---|---|---|---|")
        for row in mism:
            w(f"| `{row['record_id']}` | {row['session_id']} | {row['split'] or '—'} | `{row['consensus']}` "
              f"({row['bucket']}) | `{row['stored'].get('label')}`{' (stale)' if row['stale'] else ''} | "
              f"{clip(row['stored'].get('explanation'))} |")
        w("")
    return "\n".join(out)


def cmd_report(a):
    r = build(a)
    print(render(r))
    if a.json_out:
        slim = {
            "status": r["status"], "blockers": r["blockers"], "warnings": r["warnings"],
            "eval_column": r["eval_column"], "config": r["config_name"], "fit": r["fit"],
            "definitions": r["definitions"], "fail_labels": r["fail_labels"],
            "summary": {
                "gold": len(r["gold"]), "gold_scored": len(r["gold_scored"]), "agree": r["agree"],
                "gold_classes": dict(r["gold_classes"]), "annotators": r["annotators"],
                "disagreements": len(r["mismatches"]), "stale": len(r["stale"]),
                "balanced_accuracy": r["balanced"], "leniency": r["leniency"], "weighted": r["weighted"],
                "pi": r["judge_pi"]["pi"], "pi_ci": r["judge_pi"]["ci"], "skew": r["skew"],
                "test": {"n": len(r["test_pairs"]), "agree": n_agree(r["test_pairs"]), "pi": r["test_pi"]["pi"],
                         "pi_ci": r["test_pi"]["ci"], "recall": r["test_recall"]},
                "applicability_pi": scott_pi(r["app_pairs"]),
                "ceiling": {"comparisons": len(r["ceiling_human"]), "human_pi": scott_pi(r["ceiling_human"]),
                            "judge_pi": scott_pi(r["ceiling_judge"])},
                "production": r["production"], "read_sessions": r["read"], "moved_from_test": r["moved_from_test"],
                "rescored_at": r["rescored_at"],
                "split_counts": {k: dict(v) for k, v in r["split_counts"].items()},
            },
            "judge": r["judge"],
            "records": [{
                "record_id": row["record_id"], "session_id": row["session_id"], "trace_id": row["trace_id"],
                "votes": row["votes"], "consensus": row["consensus"], "status": row["status"],
                "bucket": row["bucket"], "eval_label": (row["stored"] or {}).get("label"),
                "eval_explanation": (row["stored"] or {}).get("explanation"),
                "stale": row["stale"], "split": row["split"],
            } for row in r["rows"]],
        }
        with open(a.json_out, "w") as f:
            json.dump(slim, f, indent=1)

def gold_by_split(report):
    return {x["record_id"]: x for x in report["records"] if x["bucket"] == "gold"}


def stats(recs):
    """Agreement, Scott's π and recall per human label for scored records."""
    pairs = [(x["consensus"], x["eval_label"]) for x in recs if x.get("eval_label")]
    recall = {}
    for lbl in sorted({h for h, _ in pairs}):
        has = [j for h, j in pairs if h == lbl]
        recall[lbl] = sum(1 for j in has if j == lbl) / len(has)
    return {"n": len(pairs), "agree": n_agree(pairs), "pi": scott_pi(pairs), "pairs": pairs,
            "recall": recall}


def cmd_compare(a):
    """Before/after on the same gold set: agreement and π with intervals, recall per label, flipped records,
    label-mix shift; then the dev-to-test gap, a second judge, the ship gate and the look ledger."""
    before, after = load(a.before), load(a.after)
    split = a.split
    b_all, c_all = gold_by_split(before), {x["record_id"]: x for x in after["records"]}
    on_split = lambda src, name: stats([src[rid] for rid, x in b_all.items() if x.get("split") == name and rid in src])
    b = {rid: x for rid, x in b_all.items() if split is None or x.get("split") == split}
    c = {rid: c_all[rid] for rid in b if rid in c_all}
    both = [rid for rid in b if b[rid].get("eval_label") and c.get(rid, {}).get("eval_label")]
    hit = lambda x: x["eval_label"] == x["consensus"]
    fixed = [rid for rid in both if not hit(b[rid]) and hit(c[rid])]
    broke = [rid for rid in both if hit(b[rid]) and not hit(c[rid])]
    sb, sa = stats([b[r] for r in both]), stats([c[r] for r in both])
    print(f"# Before/after on {len(both)} gold records" + (f" ({split} split)" if split else "") + "\n")
    print(f"- Before: {pct_ci(sb['agree'], sb['n'])}; Scott's {pi_ci(sb['pairs'])}")
    print(f"- After: {pct_ci(sa['agree'], sa['n'])}; Scott's {pi_ci(sa['pairs'])}")
    for lbl in sorted(set(sb["recall"]) | set(sa["recall"])):
        rb, ra = sb["recall"].get(lbl), sa["recall"].get(lbl)
        print(f"- Recall for `{lbl}`: {fmt_rate(rb)} → {fmt_rate(ra)}")
    print(f"- Fixed (wrong before, right after): {len(fixed)}" + (f" — {fixed}" if fixed else ""))
    print(f"- Broken (right before, wrong after): {len(broke)}" + (f" — {broke}" if broke else ""))
    mix_b, mix_a = Counter(b[r]["eval_label"] for r in both), Counter(c[r]["eval_label"] for r in both)
    print("- Evaluator label mix: " + ", ".join(f"`{k}` {mix_b.get(k, 0)}→{mix_a.get(k, 0)}"
                                               for k in sorted(set(mix_b) | set(mix_a))))
    print("\nA change smaller than the run-to-run noise floor is not an improvement. Re-run the unchanged "
          "candidate once and compare it with itself to measure that floor.")

    # Dev-to-test gap on the AFTER judge: dev was used to choose the revision, test wasn't.
    dev, test = on_split(c_all, "dev"), on_split(c_all, "test")
    gap = dev["pi"] - test["pi"] if dev["n"] and test["n"] and dev["pi"] is not None and test["pi"] is not None else None
    if gap is not None:
        print(f"\n## Dev → test\n\n- After: dev π {dev['pi']:.2f} on {dev['n']}, test π {test['pi']:.2f} on {test['n']}, "
              f"gap {gap:+.2f}." + (f" **Over {MAX_DEV_TEST_GAP:.2f}: the revision fit dev; don't ship it.**"
                                   if gap > MAX_DEV_TEST_GAP else ""))

    second = load(a.second_judge) if a.second_judge else None
    s_test = None
    if second:
        s_test = on_split({x["record_id"]: x for x in second["records"]}, "test")
        print(f"\n## Second judge model\n\n- {(second.get('judge') or {}).get('model') or 'second judge'} on test: "
              f"{pct_ci(s_test['agree'], s_test['n'])}; Scott's {pi_ci(s_test['pairs'])}")
        if s_test["pi"] is not None and test["pi"] is not None and abs(s_test["pi"] - test["pi"]) > MAX_DEV_TEST_GAP:
            print(f"- The two judges differ by {abs(s_test['pi'] - test['pi']):.2f} π on the same records: part of "
                  "the measured agreement is a property of the judge model, not of the criterion.")

    if a.gate:
        bt = on_split(b_all, "test")
        fails = a.fail_label or sorted(bt["recall"])
        checks = [
            ("Test agreement holds (π after ≥ before)",
             bt["pi"] is not None and test["pi"] is not None and test["pi"] >= bt["pi"],
             f"{bt['pi'] if bt['pi'] is None else round(bt['pi'], 2)} → {test['pi'] if test['pi'] is None else round(test['pi'], 2)}"),
            (f"Dev → test gap ≤ {MAX_DEV_TEST_GAP:.2f}", gap is not None and gap <= MAX_DEV_TEST_GAP,
             "not measured" if gap is None else f"{gap:+.2f}"),
        ]
        for lbl in fails:
            rb, ra = bt["recall"].get(lbl), test["recall"].get(lbl)
            checks.append((f"Recall for `{lbl}` on test didn't drop", rb is not None and ra is not None and ra >= rb,
                           f"{fmt_rate(rb)} → {fmt_rate(ra)}"))
        # A judge can agree well overall and still carry a model-specific bias; a second judge model on the same
        # test records separates the judge from the criterion (Kochelka et al.). Required, per SOP step 5.
        checks.append(("Second judge model scored on test", bool(s_test and s_test["n"]),
                       f"{s_test['n']} records" if s_test else "missing: pass `--second-judge`"))
        # The best of several candidates scored on the same data looks better than it is (SIREN): the winner
        # must be re-scored on sessions no candidate was chosen on.
        if a.candidates > 1:
            fresh = load(a.fresh) if a.fresh else None
            fs = stats([x for x in fresh["records"] if x["bucket"] == "gold"]) if fresh else None
            checks.append((f"Winner of {a.candidates} candidates re-scored on fresh sessions", bool(fs and fs["n"]),
                           f"{fs['n']} records, π {fs['pi']:.2f}" if fs and fs["n"] and fs["pi"] is not None
                           else (f"{fs['n']} records" if fs else "missing: pass `--fresh`")))
        ok = all(passed for _, passed, _ in checks)
        print(f"\n## Ship gate: {'PASS' if ok else 'FAIL'}\n")
        for name, passed, val in checks:
            print(f"- {'✅' if passed else '❌'} {name}: {val}")

    ledger_path = a.ledger
    if ledger_path:
        ledger = load(ledger_path) if os.path.exists(ledger_path) else []
        entry = {"at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "after": os.path.basename(a.after),
                 "judge": after.get("judge"), "split": split or "all"}
        ledger.append(entry)
        with open(ledger_path, "w") as f:
            json.dump(ledger, f, indent=1)
        dev_looks = sum(1 for e in ledger if e["split"] in ("dev", "all"))
        prompt = lambda e: (e.get("judge") or {}).get("prompt_sha")
        test_looks = sum(1 for e in ledger if e["split"] in ("test", "all") and prompt(e) == prompt(entry))
        print(f"\n## Looks\n\n- Dev scored {dev_looks} time(s) in this ledger (budget {a.look_budget}).")
        if dev_looks > a.look_budget:
            print("- Over budget: dev agreement is now optimistic. Batch edits, and label a fresh dev batch "
                  "before more tuning.")
        if split in ("test", None) and test_looks > 1:
            print(f"- Test has been scored {test_looks} times for this prompt. Test is run once per judge version; "
                  "a second look makes it another dev set.")


def cmd_lint(a):
    """Flag lines a revision added that patch specific cases instead of stating general rules."""
    old = open(a.before_template).read().splitlines()
    new = open(a.after_template).read().splitlines()
    seen = set(old)
    added = [(i + 1, line) for i, line in enumerate(new) if line.strip() and line not in seen]
    report = load(a.records) if a.records else {"records": []}
    ids = {str(v) for x in report["records"] for v in (x.get("record_id"), x.get("session_id"), x.get("trace_id"))
           if v and len(str(v)) >= 6}
    words = lambda text: re.findall(r"[a-z0-9']+", (text or "").lower())
    shingles = set()
    for x in report["records"]:
        if x.get("split") == "dev":
            ws = words(x.get("eval_explanation"))
            shingles |= {" ".join(ws[k:k + 8]) for k in range(len(ws) - 7)}
    findings = []
    for n, line in added:
        why = []
        if any(i in line for i in ids):
            why.append("names a record, session or trace ID")
        if re.search(r"\b(?=[0-9a-f-]*\d)[0-9a-f-]{12,}\b", line, re.I):
            why.append("contains an ID-like token")
        if re.search(r"[\"“']([^\"”']+\s){3,}[^\"”']+[\"”']", line):
            why.append("quotes a phrase of 4+ words (copied wording?)")
        ws = words(line)
        if any(" ".join(ws[k:k + 8]) in shingles for k in range(len(ws) - 7)):
            why.append("repeats 8+ words from a dev record's explanation")
        if why:
            findings.append((n, line, why))
    print(f"# Revision lint: {len(added)} added line(s), {len(findings)} flagged\n")
    for n, line, why in findings:
        print(f"- Line {n}: {clip(line, 140)}\n  - " + "; ".join(why))
    if not findings:
        print("No added line names a record or copies dev wording. Still apply the reproduce check before trusting "
              "a dev gain.")
    else:
        print("\nRewrite flagged lines as general rules that would apply to sessions you haven't seen.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="Save queue, records, and evaluator JSON (read-only)")
    f.add_argument("--space", required=True)
    f.add_argument("--queue", required=True, help="Annotation queue name or ID")
    f.add_argument("--evaluator", required=True, help="Evaluator name or ID")
    f.add_argument("--out-dir", required=True)
    f.add_argument("--ax", default="ax", help="Path to the ax binary")
    f.add_argument("--count-turns", metavar="ROOT_FILTER",
                   help="Also count each session's turns (root spans matching this filter) so the report can flag stored "
                        f"results scored mid-session. Only for templates that report {LAST_TURN_MARKER}.")
    f.add_argument("--project", help="Project name or ID; required with --count-turns")
    f.set_defaults(func=cmd_fetch)

    r = sub.add_parser("report", help="Print the pre-alignment report (Markdown)")
    r.add_argument("--dir", required=True, help="Directory written by fetch")
    r.add_argument("--config", help="Annotation config name, if the queue has several")
    r.add_argument("--eval-column", help="Override the stored output column, e.g. session_eval.my_eval")
    r.add_argument("--not-applicable", nargs="*", default=DEFAULT_NOT_APPLICABLE)
    r.add_argument("--unscorable", nargs="*", default=DEFAULT_UNSCORABLE)
    r.add_argument("--adjudications", help='JSON file mapping record_id to the adjudicated label')
    r.add_argument("--json-out", help="Also write per-record results as JSON")
    r.add_argument("--plan", help="plan.json from arize-align-queue-builder; adds production-weighted estimates "
                                  "and PPI++ production rates from its random stream")
    r.add_argument("--test-from", metavar="ISO_TIME",
                   help="Make every gold session that started at or after this time the test split: a later batch "
                        "labeled after the prompt was frozen")
    r.add_argument("--rubric-version", help="Rubric or instructions version the labels were made under")
    r.add_argument("--admission-filter", help="The task's admission filter, recorded as part of the judge version")
    r.add_argument("--fail-label", action="append", help="A failing label (repeat): its recall leads and leniency uses it")
    r.add_argument("--read-sessions", metavar="FILE",
                   help="Session IDs (whitespace-separated) read while writing a rule; they never count as test")
    r.add_argument("--rescored-at", metavar="ISO_TIME",
                   help="Start of a scoring run, after the current version was created, that re-scored these sessions")
    r.add_argument("--criterion-decided", action="store_true",
                   help="The user has decided the criterion question the definition diff flagged")
    r.set_defaults(func=cmd_report)

    c = sub.add_parser("compare", help="Compare two report --json-out files from the same gold set")
    c.add_argument("before")
    c.add_argument("after")
    c.add_argument("--split", choices=["train", "dev", "test"], help="Only records in this split of the BEFORE file")
    c.add_argument("--second-judge", metavar="JSON", help="report --json-out from the same candidate run on another "
                                                          "judge model; scored on test next to AFTER")
    c.add_argument("--gate", action="store_true", help="Apply the ship gate on the test split")
    c.add_argument("--fail-label", action="append", help="Label whose test recall must not drop (default: every label)")
    c.add_argument("--ledger", metavar="JSON", help="Append this comparison to a looks ledger and count looks at dev")
    c.add_argument("--look-budget", type=int, default=LOOK_BUDGET)
    c.add_argument("--candidates", type=int, default=1, help="How many candidate templates were tried before this one")
    c.add_argument("--fresh", metavar="JSON", help="report --json-out of the winner on fresh sessions (needed when "
                   "--candidates > 1)")
    c.set_defaults(func=cmd_compare)

    lt = sub.add_parser("lint", help="Flag template lines that patch specific cases instead of stating rules")
    lt.add_argument("before_template")
    lt.add_argument("after_template")
    lt.add_argument("--records", help="report --json-out whose IDs and dev explanations to check against")
    lt.set_defaults(func=cmd_lint)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
