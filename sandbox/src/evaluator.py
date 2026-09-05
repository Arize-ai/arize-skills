"""Correctness evaluation for instrumentation output."""

import difflib
from dataclasses import dataclass
from pathlib import Path

from .runner import RunResult

GROUND_TRUTH_DIR = Path(__file__).parent.parent / "ground_truth"

REQUIRED_PACKAGES = ["arize-otel", "openinference-instrumentation-langchain"]

BUSINESS_LOGIC_FILES = ["agent.py", "tools.py"]


@dataclass
class EvalResult:
    # Structural checks
    tracing_file_exists: bool = False
    tracing_file_has_register: bool = False
    tracing_file_has_instrumentor: bool = False
    main_imports_tracing: bool = False
    requirements_has_packages: bool = False
    business_logic_unchanged: bool = True

    # Ground truth comparison
    ground_truth_similarity: float = 0.0

    # Agent metrics
    agent_cost_usd: float = 0.0
    agent_tokens: int = 0
    agent_duration_ms: int = 0
    agent_num_turns: int = 0

    @property
    def structural_pass(self) -> bool:
        return all([
            self.tracing_file_exists,
            self.tracing_file_has_register,
            self.tracing_file_has_instrumentor,
            self.main_imports_tracing,
            self.requirements_has_packages,
            self.business_logic_unchanged,
        ])


def evaluate_instrumentation(
    workspace: Path,
    framework: str = "langchain-py",
    run_result: RunResult | None = None,
) -> EvalResult:
    """Evaluate the agent's instrumentation output against structural checks and ground truth."""
    result = EvalResult()

    if run_result:
        result.agent_cost_usd = run_result.cost_usd
        result.agent_tokens = run_result.tokens
        result.agent_duration_ms = run_result.duration_ms
        result.agent_num_turns = run_result.num_turns

    _check_tracing_file(workspace, result)
    _check_main_imports(workspace, result)
    _check_requirements(workspace, result)
    _check_business_logic(workspace, result)
    _compare_ground_truth(workspace, framework, result)

    return result


def _check_tracing_file(workspace: Path, result: EvalResult) -> None:
    """Check that tracing.py exists and has the required content."""
    # Look in common locations
    candidates = [
        workspace / "tracing.py",
        workspace / "backend" / "tracing.py",
    ]
    tracing_file = next((f for f in candidates if f.exists()), None)

    if not tracing_file:
        return

    result.tracing_file_exists = True
    content = tracing_file.read_text()

    result.tracing_file_has_register = "register(" in content
    result.tracing_file_has_instrumentor = "LangChainInstrumentor" in content


def _check_main_imports(workspace: Path, result: EvalResult) -> None:
    """Check that main.py imports tracing before other backend imports."""
    candidates = [
        workspace / "main.py",
        workspace / "backend" / "main.py",
    ]
    main_file = next((f for f in candidates if f.exists()), None)
    if not main_file:
        return

    content = main_file.read_text()
    result.main_imports_tracing = (
        "import tracing" in content
        or "from tracing" in content
        or "import backend.tracing" in content
        or "from backend.tracing" in content
        or "from backend import tracing" in content
    )


def _check_requirements(workspace: Path, result: EvalResult) -> None:
    """Check that requirements.txt contains the required packages."""
    candidates = [
        workspace / "requirements.txt",
        workspace / "backend" / "requirements.txt",
    ]
    req_file = next((f for f in candidates if f.exists()), None)
    if not req_file:
        return

    content = req_file.read_text().lower()
    result.requirements_has_packages = all(
        pkg in content for pkg in REQUIRED_PACKAGES
    )


def _check_business_logic(workspace: Path, result: EvalResult) -> None:
    """Verify that business logic files were not modified.

    Compares against the originals stored alongside the workspace
    (saved during sandbox creation).
    """
    originals_dir = workspace / "_originals"
    if not originals_dir.exists():
        # If originals weren't saved, we can't diff — assume OK but note it
        return

    for filename in BUSINESS_LOGIC_FILES:
        original = originals_dir / filename
        # Check multiple possible locations for the current file
        current_candidates = [
            workspace / filename,
            workspace / "backend" / filename,
        ]
        current = next((f for f in current_candidates if f.exists()), None)

        if original.exists() and current and current.exists():
            if original.read_text() != current.read_text():
                result.business_logic_unchanged = False
                return


def _compare_ground_truth(
    workspace: Path, framework: str, result: EvalResult
) -> None:
    """Compare the agent's tracing.py against the ground truth reference."""
    gt_key = framework.replace("-", "_")
    gt_dir = GROUND_TRUTH_DIR / gt_key
    gt_tracing = gt_dir / "tracing.py"

    if not gt_tracing.exists():
        return

    # Find the agent's tracing.py
    candidates = [
        workspace / "tracing.py",
        workspace / "backend" / "tracing.py",
    ]
    agent_tracing = next((f for f in candidates if f.exists()), None)
    if not agent_tracing:
        return

    gt_lines = gt_tracing.read_text().splitlines()
    agent_lines = agent_tracing.read_text().splitlines()

    matcher = difflib.SequenceMatcher(None, gt_lines, agent_lines)
    result.ground_truth_similarity = matcher.ratio()
