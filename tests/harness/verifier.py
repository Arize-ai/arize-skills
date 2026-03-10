"""
Composable verification strategies for checking skill test outcomes.

Each verifier implements verify(result, **context) -> VerificationResult.
Use CompositeVerifier to combine multiple checks (all must pass).
"""

import json
import os
import re
import subprocess
from abc import ABC, abstractmethod
from typing import Any

from .result import TestResult, VerificationResult


class Verifier(ABC):
    @abstractmethod
    def verify(self, result: TestResult, **context: Any) -> VerificationResult: ...


class CompositeVerifier(Verifier):
    """Run multiple verifiers; all must pass."""

    def __init__(self, *verifiers: Verifier):
        self.verifiers = verifiers

    def verify(self, result: TestResult, **context: Any) -> VerificationResult:
        all_checks: list[dict[str, Any]] = []
        for v in self.verifiers:
            vr = v.verify(result, **context)
            all_checks.extend(vr.checks)
        all_passed = all(c["passed"] for c in all_checks)
        return VerificationResult(
            passed=all_passed,
            checks=all_checks,
            summary="All checks passed" if all_passed else "Some checks failed",
        )


class NoErrorVerifier(Verifier):
    """Verify the run completed without errors."""

    def verify(self, result: TestResult, **context: Any) -> VerificationResult:
        passed = not result.is_error
        return VerificationResult(
            passed=passed,
            checks=[
                {
                    "name": "no_error",
                    "passed": passed,
                    "message": (
                        "Run completed without error"
                        if passed
                        else f"Run errored: stop_reason={result.stop_reason}"
                    ),
                }
            ],
            summary="No error" if passed else "Error detected",
        )


class OutputContainsVerifier(Verifier):
    """Verify the text output contains all required substrings."""

    def __init__(self, required_strings: list[str], case_sensitive: bool = False):
        self.required = required_strings
        self.case_sensitive = case_sensitive

    def verify(self, result: TestResult, **context: Any) -> VerificationResult:
        text = result.text_output if self.case_sensitive else result.text_output.lower()
        checks = []
        for s in self.required:
            target = s if self.case_sensitive else s.lower()
            found = target in text
            checks.append(
                {
                    "name": f"contains_{s[:30]}",
                    "passed": found,
                    "message": f"Found '{s}'" if found else f"Missing '{s}'",
                }
            )
        all_passed = all(c["passed"] for c in checks)
        return VerificationResult(
            passed=all_passed,
            checks=checks,
            summary="All strings found" if all_passed else "Missing expected strings",
        )


class OutputMatchesRegexVerifier(Verifier):
    """Verify the output matches a regex pattern."""

    def __init__(self, pattern: str):
        self.pattern = pattern

    def verify(self, result: TestResult, **context: Any) -> VerificationResult:
        match = bool(re.search(self.pattern, result.text_output, re.DOTALL))
        return VerificationResult(
            passed=match,
            checks=[
                {
                    "name": "regex_match",
                    "passed": match,
                    "message": f"Pattern {'matched' if match else 'not found'}",
                }
            ],
            summary="Regex matched" if match else "Regex not matched",
        )


class ToolWasCalledVerifier(Verifier):
    """Verify that specific tools were invoked."""

    def __init__(self, required_tools: list[str]):
        self.required_tools = required_tools

    def verify(self, result: TestResult, **context: Any) -> VerificationResult:
        called = {tc["tool"] for tc in result.tool_calls}
        checks = []
        for tool in self.required_tools:
            found = tool in called
            checks.append(
                {
                    "name": f"tool_called_{tool}",
                    "passed": found,
                    "message": (
                        f"Tool '{tool}' was called"
                        if found
                        else f"Tool '{tool}' was NOT called"
                    ),
                }
            )
        all_passed = all(c["passed"] for c in checks)
        return VerificationResult(
            passed=all_passed,
            checks=checks,
            summary="All tools called" if all_passed else "Some tools not called",
        )


class FileExistsVerifier(Verifier):
    """Verify that specific files were created in the workspace."""

    def __init__(self, file_paths: list[str]):
        self.file_paths = file_paths

    def verify(self, result: TestResult, **context: Any) -> VerificationResult:
        checks = []
        for fp in self.file_paths:
            exists = os.path.exists(fp)
            checks.append(
                {
                    "name": f"file_exists_{os.path.basename(fp)}",
                    "passed": exists,
                    "message": (
                        f"File '{fp}' exists" if exists else f"File '{fp}' NOT found"
                    ),
                }
            )
        all_passed = all(c["passed"] for c in checks)
        return VerificationResult(
            passed=all_passed,
            checks=checks,
            summary="All files exist" if all_passed else "Some files missing",
        )


class AxResourceExistsVerifier(Verifier):
    """Verify an ax resource (dataset, experiment) was created."""

    def __init__(self, resource_type: str, resource_name: str):
        self.resource_type = resource_type  # "datasets" or "experiments"
        self.resource_name = resource_name

    def verify(self, result: TestResult, **context: Any) -> VerificationResult:
        try:
            proc = subprocess.run(
                ["ax", self.resource_type, "list", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            items = json.loads(proc.stdout)
            found = any(item.get("name") == self.resource_name for item in items)
        except Exception:
            found = False
        return VerificationResult(
            passed=found,
            checks=[
                {
                    "name": f"ax_{self.resource_type}_exists",
                    "passed": found,
                    "message": (
                        f"{self.resource_type} '{self.resource_name}' "
                        f"{'found' if found else 'NOT found'}"
                    ),
                }
            ],
            summary=f"Resource {'exists' if found else 'missing'}",
        )


class URLFormatVerifier(Verifier):
    """Verify the output contains a properly formatted Arize URL."""

    def __init__(self, expected_params: list[str] | None = None):
        self.expected_params = expected_params or [
            "selectedTraceId",
            "startA",
            "endA",
        ]

    def verify(self, result: TestResult, **context: Any) -> VerificationResult:
        url_pattern = r"https://app\.arize\.com/[^\s]+"
        match = re.search(url_pattern, result.text_output)
        checks: list[dict[str, Any]] = []

        if match:
            url = match.group(0)
            checks.append(
                {
                    "name": "url_present",
                    "passed": True,
                    "message": f"Found Arize URL: {url[:80]}...",
                }
            )
            for param in self.expected_params:
                has_param = param in url
                checks.append(
                    {
                        "name": f"url_has_{param}",
                        "passed": has_param,
                        "message": f"URL {'has' if has_param else 'missing'} {param}",
                    }
                )
        else:
            checks.append(
                {
                    "name": "url_present",
                    "passed": False,
                    "message": "No Arize URL found in output",
                }
            )

        all_passed = all(c["passed"] for c in checks)
        return VerificationResult(
            passed=all_passed,
            checks=checks,
            summary="URL valid" if all_passed else "URL validation failed",
        )
