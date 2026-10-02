#!/usr/bin/env python3
"""Export traces from LangSmith / Braintrust / Langfuse and ingest into Arize AX via OTLP/HTTP JSON.

This is the historical-trace path for arize-migrate-* skills.

Attribute mapping (destination = OpenInference on Arize):
  - source final output / outputs  -> attributes.output.value  (string; NOT a message array)
  - source input / inputs          -> attributes.input.value   (string)
  - optional structured messages   -> attributes.llm.input_messages / llm.output_messages
    only when the source already has chat-message shape; do not stuff tool timelines into output.value
  - openinference.span.kind        -> LLM | TOOL | CHAIN | AGENT | RETRIEVER | UNKNOWN
  - openinference.project.name     -> ARIZE project name
  - migration.source               -> langsmith | braintrust | langfuse

Usage:
  export ARIZE_API_KEY ARIZE_SPACE_ID
  export LANGSMITH_API_KEY   # or BRAINTRUST_API_KEY / LANGFUSE_* 
  python scripts/migrate_vendor_traces.py --vendor langsmith \\
    --source-project tracing-ui-compare-vercel \\
    --arize-project migrated-from-langsmith \\
    --limit 200
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


def _require(keys: list[str]) -> None:
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Missing env: {', '.join(missing)}")


def _extract_text_from_parts(parts: Any) -> str | None:
    if not isinstance(parts, list):
        return None
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            if part.get("type") == "text" and isinstance(part.get("content"), str):
                texts.append(part["content"])
            elif isinstance(part.get("text"), str):
                texts.append(part["text"])
    if texts:
        return texts[-1]
    return None


def _as_text(value: Any) -> str:
    """Map source I/O to a plain string for OpenInference output.value / input.value.

    Prefer final assistant text over raw message/tool timelines.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        # Sometimes sources stringify a JSON message array — unwrap if possible.
        s = value.strip()
        if s.startswith("[") or s.startswith("{"):
            try:
                return _as_text(json.loads(s))
            except json.JSONDecodeError:
                return value
        return value
    if isinstance(value, dict):
        # LangSmith / wrappers
        if isinstance(value.get("output"), (str, dict, list)):
            return _as_text(value["output"])
        if isinstance(value.get("content"), str):
            return value["content"]
        if isinstance(value.get("text"), str):
            return value["text"]
        # AI SDK shaped: {"content":[{"type":"text","text":"..."}]}
        if isinstance(value.get("content"), list):
            extracted = _extract_text_from_parts(value["content"])
            if extracted:
                return extracted
        # Chat transcript wrapper: {"messages":[...]}
        if isinstance(value.get("messages"), list):
            return _as_text(value["messages"])
        # Single assistant message object
        if value.get("role") == "assistant":
            extracted = _extract_text_from_parts(value.get("parts"))
            if extracted:
                return extracted
            if isinstance(value.get("content"), str):
                return value["content"]
        # Prefer last user text for inputs that are only user turns
        if value.get("role") == "user":
            extracted = _extract_text_from_parts(value.get("parts"))
            if extracted:
                return extracted
            if isinstance(value.get("content"), str):
                return value["content"]
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, list):
        # Message array: take last assistant text part
        for item in reversed(value):
            if isinstance(item, dict) and item.get("role") in (None, "assistant"):
                extracted = _extract_text_from_parts(item.get("parts"))
                if extracted:
                    return extracted
                if isinstance(item.get("content"), str):
                    return item["content"]
                if isinstance(item.get("content"), list):
                    extracted = _extract_text_from_parts(item["content"])
                    if extracted:
                        return extracted
        return json.dumps(value, ensure_ascii=False, default=str)
    return json.dumps(value, ensure_ascii=False, default=str)


def _hex_id(nbytes: int, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).digest()
    return digest[:nbytes].hex()


def _to_nanos(ts: Any) -> int:
    if ts is None:
        return int(time.time() * 1e9)
    if isinstance(ts, (int, float)):
        # Heuristic: seconds vs ms vs ns
        if ts > 1e17:
            return int(ts)
        if ts > 1e14:
            return int(ts * 1e3)
        if ts > 1e11:
            return int(ts * 1e6)
        return int(ts * 1e9)
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return int(ts.timestamp() * 1e9)
    if isinstance(ts, str):
        s = ts.replace("Z", "+00:00")
        return _to_nanos(datetime.fromisoformat(s))
    return int(time.time() * 1e9)


def _attr_str(key: str, value: str) -> dict[str, Any]:
    return {"key": key, "value": {"stringValue": value}}


def _first_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
        if value is not None and not isinstance(value, (dict, list)) and str(value).strip():
            return str(value)
    return None


def _bt_parent_id(row: dict[str, Any]) -> str | None:
    parents = row.get("span_parents")
    if isinstance(parents, list) and parents:
        return str(parents[0])
    raw = row.get("parent_span_id")
    if raw:
        return str(raw)
    return None


def _bt_metadata(row: dict[str, Any]) -> dict[str, Any]:
    md = row.get("metadata")
    return md if isinstance(md, dict) else {}


def _ls_metadata(run: Any) -> dict[str, Any]:
    extra = run.extra if isinstance(getattr(run, "extra", None), dict) else {}
    md = extra.get("metadata")
    if isinstance(md, dict):
        return md
    direct = getattr(run, "metadata", None)
    return direct if isinstance(direct, dict) else {}


def _kind_from_name(name: str, hint: str = "") -> str:
    blob = f"{name} {hint}".lower()
    if any(x in blob for x in ("tool", "listorders", "viewtracking", "execute_tool")):
        return "TOOL"
    if any(x in blob for x in ("llm", "chat", "generat", "completion", "gpt", "doGenerate")):
        return "LLM"
    if any(x in blob for x in ("agent", "invoke_agent", "conversation", "chat.session")):
        return "AGENT"
    if any(x in blob for x in ("retriev", "embed")):
        return "RETRIEVER"
    if any(x in blob for x in ("chain", "step", "request", "turn", "traceable")):
        return "CHAIN"
    return "CHAIN"


def build_otlp_span(
    *,
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    name: str,
    start_ns: int,
    end_ns: int,
    kind: str,
    input_text: str,
    output_text: str,
    extra_attrs: dict[str, str] | None = None,
) -> dict[str, Any]:
    attrs = [
        _attr_str("openinference.span.kind", kind),
        _attr_str("input.value", input_text),
        _attr_str("output.value", output_text),
    ]
    for k, v in (extra_attrs or {}).items():
        if v is not None:
            attrs.append(_attr_str(k, str(v)))
    span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name or "span",
        "kind": 1,  # INTERNAL
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(max(end_ns, start_ns + 1)),
        "attributes": attrs,
        "status": {"code": 1},  # OK
    }
    if parent_span_id:
        span["parentSpanId"] = parent_span_id
    return span


def post_otlp(spans: list[dict[str, Any]], project: str) -> None:
    _require(["ARIZE_API_KEY", "ARIZE_SPACE_ID"])
    endpoint = os.environ.get("ARIZE_OTLP_ENDPOINT", "https://otlp.arize.com/v1/traces")
    body = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attr_str("openinference.project.name", project),
                        _attr_str("model_id", project),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "arize-skills.migrate_vendor_traces", "version": "1.2"},
                        "spans": spans,
                    }
                ],
            }
        ]
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Content-Type": "application/json",
            "arize-space-id": os.environ["ARIZE_SPACE_ID"],
            "arize-api-key": os.environ["ARIZE_API_KEY"],
            "space_id": os.environ["ARIZE_SPACE_ID"],
            "api_key": os.environ["ARIZE_API_KEY"],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
            print(f"OTLP ingest OK ({len(spans)} spans) -> project={project}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"OTLP ingest failed: {exc.code} {exc.read()[:500]}") from exc


# ----- LangSmith -----


def export_langsmith(project: str, limit: int) -> list[dict[str, Any]]:
    _require(["LANGSMITH_API_KEY"])
    from langsmith import Client

    client = Client()
    runs: list[Any] = []
    for run in client.list_runs(project_name=project):
        runs.append(run)
        if len(runs) >= limit:
            break
    runs = runs[:limit]
    # Prefer most recent N root-ish by limiting after sort
    runs.sort(key=lambda r: r.start_time or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    by_id = {str(r.id): r for r in runs}
    spans: list[dict[str, Any]] = []
    seen_roots = 0
    # Map LS id -> otel ids
    id_map: dict[str, tuple[str, str]] = {}  # ls_id -> (trace_id, span_id)

    # First pass: assign ids. Use root run id for trace.
    def root_id(run) -> str:
        rid = str(run.id)
        parent = str(run.parent_run_id) if run.parent_run_id else None
        while parent and parent in by_id:
            rid = parent
            parent = str(by_id[parent].parent_run_id) if by_id[parent].parent_run_id else None
        return rid

    for run in runs:
        rid = str(run.id)
        root = root_id(run)
        trace_id = _hex_id(16, "ls", root)
        span_id = _hex_id(8, "ls-span", rid)
        id_map[rid] = (trace_id, span_id)

    for run in runs:
        rid = str(run.id)
        trace_id, span_id = id_map[rid]
        parent_span = None
        if run.parent_run_id and str(run.parent_run_id) in id_map:
            parent_span = id_map[str(run.parent_run_id)][1]
        else:
            seen_roots += 1

        rtype = (run.run_type or "").lower()
        kind_map = {
            "llm": "LLM",
            "tool": "TOOL",
            "retriever": "RETRIEVER",
            "embedding": "EMBEDDING",
            "prompt": "CHAIN",
            "parser": "CHAIN",
            "chain": "CHAIN",
        }
        kind = kind_map.get(rtype) or _kind_from_name(run.name or "", rtype)
        if "agent" in (run.name or "").lower():
            kind = "AGENT"

        start_ns = _to_nanos(run.start_time)
        end_ns = _to_nanos(run.end_time) if run.end_time else start_ns + 1_000_000

        md = _ls_metadata(run)
        session_id = _first_str(md.get("session_id"), md.get("thread_id"), getattr(run, "session_id", None))
        user_id = _first_str(md.get("user_id"), md.get("userId"))

        extra = {
            "migration.source": "langsmith",
            "migration.source_run_id": rid,
            "migration.source_run_type": rtype,
        }
        if session_id:
            extra["session.id"] = session_id
        if user_id:
            extra["user.id"] = user_id

        spans.append(
            build_otlp_span(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span,
                name=run.name or rtype or "run",
                start_ns=start_ns,
                end_ns=end_ns,
                kind=kind,
                input_text=_as_text(run.inputs),
                output_text=_as_text(run.outputs),
                extra_attrs=extra,
            )
        )
        if len(spans) >= limit:
            break

    print(f"LangSmith: exported {len(spans)} spans from project={project} (approx roots touched={seen_roots})")
    return spans


# ----- Braintrust -----


def export_braintrust(project: str, limit: int) -> list[dict[str, Any]]:
    _require(["BRAINTRUST_API_KEY"])
    api = os.environ.get("BRAINTRUST_API_URL", "https://api.braintrust.dev").rstrip("/")
    key = os.environ["BRAINTRUST_API_KEY"]

    req = urllib.request.Request(f"{api}/v1/project", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode())
    objs = payload if isinstance(payload, list) else payload.get("objects") or payload.get("projects") or []
    pid = next((p["id"] for p in objs if p.get("name") == project), None)
    if not pid:
        raise SystemExit(f"Braintrust project not found: {project}")

    query = (
        f"SELECT id, name, input, output, metrics, created, span_id, root_span_id, "
        f"span_parents, metadata, is_root, span_attributes "
        f"FROM project_logs('{pid}') "
        f"LIMIT {min(max(limit, 50), 500)}"
    )
    body = json.dumps({"query": query, "fmt": "json"}).encode()
    req = urllib.request.Request(
        f"{api}/btql",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    rows = data.get("data") or data.get("rows") or []
    by_sid: dict[str, dict[str, Any]] = {}
    for row in rows:
        sid = str(row.get("span_id") or row.get("id"))
        by_sid[sid] = row

    def row_name(row: dict[str, Any]) -> str:
        attrs = row.get("span_attributes") if isinstance(row.get("span_attributes"), dict) else {}
        return str(row.get("name") or attrs.get("name") or "span")

    def lookup_session(sid: str) -> tuple[str | None, str | None]:
        seen: set[str] = set()
        cur = sid
        while cur and cur not in seen:
            seen.add(cur)
            row = by_sid.get(cur)
            if not row:
                break
            md = _bt_metadata(row)
            session_id = _first_str(md.get("session_id"), md.get("sessionId"))
            user_id = _first_str(md.get("user_id"), md.get("userId"))
            if session_id:
                return session_id, user_id
            parent = _bt_parent_id(row)
            cur = parent or ""
        fallback = str(by_sid.get(sid, {}).get("root_span_id") or sid)
        return fallback, None

    def turn_root_id(sid: str) -> str:
        """AX traces are one Braintrust chat.request (turn), not the whole conversation."""
        seen: set[str] = set()
        cur = sid
        last = sid
        while cur and cur not in seen:
            seen.add(cur)
            row = by_sid.get(cur)
            if not row:
                break
            last = cur
            name = row_name(row).lower()
            if name in ("chat.request", "chat.turn") or ("request" in name and "chat" in name):
                return cur
            parent = _bt_parent_id(row)
            if not parent:
                return cur
            parent_row = by_sid.get(parent)
            if parent_row and row_name(parent_row).lower() in ("chat.session", "chat.conversation"):
                return cur
            cur = parent
        return last

    spans: list[dict[str, Any]] = []
    id_map: dict[str, str] = {}
    for sid in by_sid:
        id_map[sid] = _hex_id(8, "bt-span", sid)

    skipped_session = 0
    traces = set()
    for row in rows:
        sid = str(row.get("span_id") or row.get("id"))
        name = row_name(row)
        if name.lower() in ("chat.session", "chat.conversation"):
            skipped_session += 1
            continue

        turn = turn_root_id(sid)
        trace_id = _hex_id(16, "bt-turn", turn)
        traces.add(trace_id)
        span_id = id_map[sid]
        parent_raw = _bt_parent_id(row)
        parent_span = None
        if sid != turn and parent_raw and parent_raw in id_map:
            parent_name = row_name(by_sid[parent_raw]).lower() if parent_raw in by_sid else ""
            if parent_name not in ("chat.session", "chat.conversation"):
                parent_span = id_map[parent_raw]

        attrs = row.get("span_attributes") if isinstance(row.get("span_attributes"), dict) else {}
        type_hint = str(attrs.get("type") or "")
        kind = _kind_from_name(name, type_hint)
        created = row.get("created")
        start_ns = _to_nanos(created)
        metrics = row.get("metrics") or {}
        end_ns = start_ns + 1_000_000
        if isinstance(metrics, dict):
            if metrics.get("end") is not None and metrics.get("start") is not None:
                try:
                    start_ns = int(float(metrics["start"]) * 1e9)
                    end_ns = int(float(metrics["end"]) * 1e9)
                except (TypeError, ValueError):
                    pass

        session_id, user_id = lookup_session(sid)
        extra = {
            "migration.source": "braintrust",
            "migration.source_span_id": sid,
            "migration.source_root_span_id": str(row.get("root_span_id") or ""),
        }
        if session_id:
            extra["session.id"] = session_id
        if user_id:
            extra["user.id"] = user_id

        spans.append(
            build_otlp_span(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span,
                name=name,
                start_ns=start_ns,
                end_ns=end_ns,
                kind=kind,
                input_text=_as_text(row.get("input")),
                output_text=_as_text(row.get("output")),
                extra_attrs=extra,
            )
        )
        if len(spans) >= limit:
            break

    print(
        f"Braintrust: exported {len(spans)} spans from project={project} "
        f"(ax traces={len(traces)}, skipped session wrappers={skipped_session})"
    )
    return spans


# ----- Langfuse -----


def export_langfuse(limit: int, tag: str | None = None) -> list[dict[str, Any]]:
    _require(["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"])
    import base64

    base = os.environ["LANGFUSE_BASE_URL"].rstrip("/")
    # Strip accidental quotes from dotenv
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        os.environ[key] = os.environ[key].strip().strip('"').strip("'")
    base = os.environ["LANGFUSE_BASE_URL"].rstrip("/")
    auth = base64.b64encode(
        f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()
    ).decode()
    headers = {"Authorization": f"Basic {auth}"}

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=3)
    start_iso = start.isoformat().replace("+00:00", "Z")
    end_iso = end.isoformat().replace("+00:00", "Z")

    def get(url: str) -> Any:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())

    # Optional tag filter: resolve matching trace IDs first (keeps seed runs clean).
    allowed_trace_ids: set[str] | None = None
    trace_meta: dict[str, dict[str, Any]] = {}
    if tag:
        allowed_trace_ids = set()
        page = 1
        while True:
            url = (
                f"{base}/api/public/traces?limit=100&page={page}"
                f"&fromTimestamp={start_iso}&toTimestamp={end_iso}&tags={tag}"
            )
            payload = get(url)
            batch = payload.get("data") or []
            if not batch:
                break
            for tr in batch:
                tid = str(tr.get("id"))
                allowed_trace_ids.add(tid)
                trace_meta[tid] = {
                    "session_id": _first_str(tr.get("sessionId"), (tr.get("metadata") or {}).get("session_id") if isinstance(tr.get("metadata"), dict) else None),
                    "user_id": _first_str(tr.get("userId"), (tr.get("metadata") or {}).get("user_id") if isinstance(tr.get("metadata"), dict) else None),
                }
            meta = payload.get("meta") or {}
            if page >= (meta.get("totalPages") or 1):
                break
            page += 1
        print(f"Langfuse: tag={tag!r} matched {len(allowed_trace_ids)} traces")

    # Paginate observations
    observations: list[dict[str, Any]] = []
    page = 1
    while len(observations) < max(limit * 3, limit):  # over-fetch when filtering
        url = (
            f"{base}/api/public/observations?limit=100&page={page}"
            f"&fromStartTime={start_iso}&toStartTime={end_iso}"
        )
        payload = get(url)
        batch = payload.get("data") or []
        if not batch:
            break
        for obs in batch:
            tid = str(obs.get("traceId") or "")
            if allowed_trace_ids is not None and tid not in allowed_trace_ids:
                continue
            observations.append(obs)
        meta = payload.get("meta") or {}
        if page >= (meta.get("totalPages") or 1):
            break
        page += 1
        if allowed_trace_ids is None and len(observations) >= limit:
            break

    # Pull session/user for any traces we didn't already load via tag query
    needed = {str(o.get("traceId")) for o in observations if o.get("traceId")} - set(trace_meta)
    for tid in list(needed)[:200]:
        try:
            tr = get(f"{base}/api/public/traces/{tid}")
        except Exception:
            continue
        md = tr.get("metadata") if isinstance(tr.get("metadata"), dict) else {}
        trace_meta[tid] = {
            "session_id": _first_str(tr.get("sessionId"), md.get("session_id")),
            "user_id": _first_str(tr.get("userId"), md.get("user_id")),
        }

    observations = observations[:limit]
    spans: list[dict[str, Any]] = []
    id_map: dict[str, tuple[str, str]] = {}
    for obs in observations:
        oid = str(obs.get("id"))
        tid = str(obs.get("traceId") or oid)
        id_map[oid] = (_hex_id(16, "lf", tid), _hex_id(8, "lf-span", oid))

    for obs in observations:
        oid = str(obs.get("id"))
        tid = str(obs.get("traceId") or oid)
        trace_id, span_id = id_map[oid]
        parent_raw = obs.get("parentObservationId")
        parent_span = id_map.get(str(parent_raw), (None, None))[1] if parent_raw else None
        otype = (obs.get("type") or "").upper()
        kind = {
            "GENERATION": "LLM",
            "SPAN": "CHAIN",
            "EVENT": "CHAIN",
            "AGENT": "AGENT",
            "TOOL": "TOOL",
            "RETRIEVER": "RETRIEVER",
        }.get(otype) or _kind_from_name(obs.get("name") or "", otype)
        if otype == "AGENT" or "agent" in (obs.get("name") or "").lower():
            kind = "AGENT"

        start_ns = _to_nanos(obs.get("startTime"))
        end_ns = _to_nanos(obs.get("endTime")) if obs.get("endTime") else start_ns + 1_000_000

        meta = obs.get("metadata") if isinstance(obs.get("metadata"), dict) else {}
        tmeta = trace_meta.get(tid) or {}
        session_id = _first_str(tmeta.get("session_id"), meta.get("session_id"), meta.get("sessionId"))
        user_id = _first_str(tmeta.get("user_id"), meta.get("user_id"), meta.get("userId"))

        extra = {
            "migration.source": "langfuse",
            "migration.source_observation_id": oid,
            "migration.source_type": otype,
            "migration.source_trace_id": tid,
        }
        if session_id:
            extra["session.id"] = session_id
        if user_id:
            extra["user.id"] = user_id
        if tag:
            extra["migration.source_tag"] = tag

        spans.append(
            build_otlp_span(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span,
                name=obs.get("name") or otype or "observation",
                start_ns=start_ns,
                end_ns=end_ns,
                kind=kind,
                input_text=_as_text(obs.get("input")),
                output_text=_as_text(obs.get("output")),
                extra_attrs=extra,
            )
        )

    print(f"Langfuse: exported {len(spans)} observations" + (f" (tag={tag})" if tag else ""))
    return spans


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", required=True, choices=["langsmith", "braintrust", "langfuse"])
    parser.add_argument("--source-project", default="tracing-ui-compare-vercel")
    parser.add_argument("--arize-project", required=True)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--tag",
        default=None,
        help="Langfuse only: import observations belonging to traces with this tag "
        "(e.g. simple-langfuse-agent)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.vendor == "langsmith":
        spans = export_langsmith(args.source_project, args.limit)
    elif args.vendor == "braintrust":
        spans = export_braintrust(args.source_project, args.limit)
    else:
        spans = export_langfuse(args.limit, tag=args.tag)

    if not spans:
        print("No spans to ingest", file=sys.stderr)
        return 1

    # Show mapping sample
    sample = spans[0]
    attrs = {a["key"]: a["value"].get("stringValue") for a in sample["attributes"]}
    print("Sample mapped span:")
    print("  name:", sample["name"])
    print("  kind:", attrs.get("openinference.span.kind"))
    print("  session.id:", attrs.get("session.id"))
    print("  parentSpanId:", sample.get("parentSpanId"))
    print("  output.value preview:", (attrs.get("output.value") or "")[:180].replace("\n", " "))
    print("  input.value preview:", (attrs.get("input.value") or "")[:120].replace("\n", " "))

    if args.dry_run:
        print(f"Dry run: would ingest {len(spans)} spans into {args.arize_project}")
        return 0

    # Batch to avoid huge payloads
    batch_size = 50
    for i in range(0, len(spans), batch_size):
        post_otlp(spans[i : i + batch_size], args.arize_project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
