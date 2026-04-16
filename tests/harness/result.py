"""
TestResult and VerificationResult dataclasses for capturing skill test outcomes.
Serializable to JSON for cross-run analysis.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class VerificationResult:
    passed: bool
    checks: list[dict[str, Any]]  # [{name, passed, message}, ...]
    summary: str


@dataclass
class TestResult:
    skill_name: str
    prompt: str
    wall_duration_ms: int
    num_turns: int
    total_cost_usd: float | None
    usage: dict[str, Any] | None  # input_tokens, output_tokens, cache_*
    is_error: bool
    stop_reason: str | None
    session_id: str | None
    text_output: str
    tool_calls: list[dict[str, Any]]
    raw_messages: list[Any] = field(repr=False, default_factory=list)

    # Populated after verification
    verification: VerificationResult | None = None
    test_case_id: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    model: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        if self.verification is None:
            return False
        return self.verification.passed and not self.is_error

    @property
    def input_tokens(self) -> int:
        return (self.usage or {}).get("input_tokens", 0)

    @property
    def output_tokens(self) -> int:
        return (self.usage or {}).get("output_tokens", 0)

    @property
    def cache_read_tokens(self) -> int:
        return (self.usage or {}).get("cache_read_input_tokens", 0)

    @property
    def cache_creation_tokens(self) -> int:
        return (self.usage or {}).get("cache_creation_input_tokens", 0)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, excluding raw_messages."""
        d = asdict(self)
        del d["raw_messages"]
        return d

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
