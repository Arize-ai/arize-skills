"""
Aggregate test results into a structured JSON report for analysis.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

from .result import TestResult


class TestReport:
    def __init__(self, report_dir: str = "test-results"):
        self.report_dir = report_dir
        self.results: list[TestResult] = []

    def add(self, result: TestResult) -> None:
        self.results.append(result)

    def summary(self) -> dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        total_cost = sum(r.total_cost_usd or 0 for r in self.results)
        total_input = sum(r.input_tokens for r in self.results)
        total_output = sum(r.output_tokens for r in self.results)
        total_cache_read = sum(r.cache_read_tokens for r in self.results)
        avg_duration = (
            sum(r.wall_duration_ms for r in self.results) / total if total else 0
        )

        by_skill: dict[str, dict[str, Any]] = {}
        for r in self.results:
            if r.skill_name not in by_skill:
                by_skill[r.skill_name] = {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "cost_usd": 0.0,
                    "total_duration_ms": 0,
                }
            s = by_skill[r.skill_name]
            s["total"] += 1
            if r.passed:
                s["passed"] += 1
            else:
                s["failed"] += 1
            s["cost_usd"] += r.total_cost_usd or 0
            s["total_duration_ms"] += r.wall_duration_ms

        for s in by_skill.values():
            s["avg_duration_ms"] = int(s["total_duration_ms"] / max(s["total"], 1))
            s["cost_usd"] = round(s["cost_usd"], 4)
            del s["total_duration_ms"]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total, 4) if total else 0,
            "total_cost_usd": round(total_cost, 4),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cache_read_tokens": total_cache_read,
            "avg_wall_duration_ms": int(avg_duration),
            "by_skill": by_skill,
        }

    def save(self, filename: str | None = None) -> str:
        os.makedirs(self.report_dir, exist_ok=True)
        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"report_{ts}.json"
        path = os.path.join(self.report_dir, filename)

        report = {
            "summary": self.summary(),
            "results": [json.loads(r.to_json()) for r in self.results],
        }
        with open(path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        return path
