---
name: arize-code-evaluations
description: >
  Help users set up evaluators for Arize tracing spans. Arize supports three evaluator types:
  (1) Built-in managed evaluators (regex matching, JSON parseable, contains keywords),
  (2) LLM-as-a-judge evaluators for subjective quality assessment,
  (3) Custom code evaluators (CodeEvaluator subclasses) for deterministic logic.
  This skill guides users through choosing the right evaluator type for their goal and,
  when a custom code evaluator is needed, generates the Python implementation with separate
  imports and code blocks for the Arize UI. Use when the user wants to:
  create an evaluator, eval, or code eval for Arize; evaluate span attributes;
  compute metrics or scores from trace data; validate output format or content;
  build evaluations using span metadata or custom attributes; aggregate or compare
  values across span fields; or assess trace/session quality.
---

# Arize Code Evaluations

Write custom `CodeEvaluator` classes for Arize tracing that run as deterministic
background tasks against span data.

## Workflow

### 1. Understand the Goal

The user has a specific evaluation goal — start by understanding it. Ask what they're trying
to measure, detect, or enforce. Rephrase their goal back as a concrete evaluation statement:
"So you want to flag spans where [condition] and score them by [metric]."

Then recommend the right evaluator type:

- **Built-in managed evaluator** — if the goal is simple pattern matching, suggest these first:
  - *Matches Regex*: output matches a pattern
  - *JSON Parseable*: output is valid JSON
  - *Contains Any/All Keywords*: keyword presence checks
  - These require no code — just configure in the Arize UI.
- **LLM-as-a-judge** — if the goal requires subjective judgment (tone, quality, correctness
  against a rubric, nuanced reasoning), suggest an LLM evaluator instead of code.
- **Custom code evaluator** — if the goal requires deterministic logic, computation, aggregation,
  or access to specific span fields that built-in evaluators can't handle, proceed with this skill.

Examples of how goals map to evaluator types:
- "Check if output contains our disclaimer" → **built-in** (Contains All Keywords)
- "Rate answer helpfulness on a 1-5 scale" → **LLM-as-a-judge**
- "My RAG answers feel stale" → **custom code** (check document metadata timestamps)
- "Some tool calls are failing silently" → **custom code** (detect empty/error outputs on tool spans)
- "I want to track cost efficiency" → **custom code** (compute token ratios or budget thresholds)

If a built-in or LLM evaluator fits, explain how to set it up and stop here.
Otherwise, continue to step 2.

### 2. Discover Available Data

Ask the user what data their spans contain. Key questions:
- **What span kinds** are involved? (LLM, Tool, Retriever, Agent, etc.)
- **Any custom attributes?** Users often add domain-specific data at `attributes.metadata.<key>`
  or `attributes.<key>`. Ask what custom fields they've instrumented.
- **What does the output look like?** Is `attributes.output.value` plain text, JSON, structured data?

Use the Span Attributes Reference below to suggest relevant standard fields based on their span kinds.

### 3. Design the Evaluation

Based on the goal and available data, propose the evaluation logic before writing code:
- **What to extract** from `dataset_row` (which keys, what parsing)
- **How to compute** the result (comparison, calculation, validation)
- **What to return** — choose the right shape:
  - Binary pass/fail: `score=1.0/0.0` with descriptive `label` ("pass"/"fail")
  - Continuous metric: `score` as a normalized float, `label` as a category bucket
  - Categorical: `label` as the primary result, `score` optional
- **What to parameterize** in `__init__` (thresholds, keys, reference values)

Present this as a brief plan and confirm with the user before writing code.

### 4. Write the Evaluator

Produce **two separate blocks** for the Arize UI:
1. **Imports block** — all imports including Arize base classes
2. **Code block** — the evaluator class and any helper classes/functions

### 5. Review and Refine

Present the evaluator and walk through the logic. Ask if the scoring, labels, and edge
case handling match their expectations. Adjust based on feedback.

## Class Template

**Imports:**
```python
import json
from typing import Any, Mapping, Optional

from arize.experimental.datasets.experiments.evaluators.base import (
    CodeEvaluator,
    EvaluationResult,
    JSONSerializable,
)
```

**Code:**
```python
class MyEvaluator(CodeEvaluator):
    def evaluate(
        self,
        *,
        dataset_row: Optional[Mapping[str, JSONSerializable]] = None,
        **kwargs: Any,
    ) -> EvaluationResult:
        # Access span data via dataset_row.get("attributes.<key>")
        # Return EvaluationResult with score, label, and/or explanation
        ...
```

## Key Rules

- **Signature**: `evaluate(self, *, dataset_row, **kwargs) -> EvaluationResult` — do not change parameter names
- **dataset_row keys** use `attributes.` prefix: `attributes.output.value`, `attributes.llm.token_count.total`, etc.
- **EvaluationResult** requires at least `score` or `label` (both recommended):
  - `score: float | None` — numeric evaluation result
  - `label: str | None` — categorical result (e.g., "pass", "fail", "relevant")
  - `explanation: str | None` — human-readable reasoning
  - `metadata: dict` — additional key-value data
- **Available packages**: `numpy`, `pandas`, `scipy`, `pyarrow`, `pydantic`, `jellyfish`, `json`, standard library
- **Handle missing data** — always guard `dataset_row` being `None` and attributes being absent
- **Configurable values** go in `__init__` so users can adjust thresholds without editing `evaluate()`

## Span Attributes Reference

All keys in `dataset_row` use the `attributes.` prefix (e.g., `attributes.output.value`).
Custom user attributes appear at `attributes.metadata.<key>` or `attributes.<key>`.

### General (All Spans)

| Key | Type | Description |
|-----|------|-------------|
| `openinference.span.kind` | string | Span kind: LLM, EMBEDDING, TOOL, AGENT, RETRIEVER, CHAIN, GUARDRAIL, RERANKER, EVALUATOR |
| `input.value` | mixed | Input data |
| `output.value` | mixed | Output data |
| `metadata` | object | User-defined key-value pairs |
| `tag.tags` | array | Custom categorical labels |

### Context / Identity

| Key | Type |
|-----|------|
| `context.trace_id` | string |
| `context.span_id` | string |
| `parent_id` | string (null for root) |
| `start_time` | timestamp |

### LLM Spans

| Key | Type |
|-----|------|
| `llm.model_name` | string |
| `llm.input_messages` | array |
| `llm.output_messages` | array |
| `llm.token_count.prompt` | int |
| `llm.token_count.completion` | int |
| `llm.token_count.total` | int |
| `llm.invocation_parameters` | object |
| `llm.prompt_template.template` | string |
| `llm.prompt_template.variables` | array |
| `llm.tools` | array |
| `llm.function_call` | object |

### Tool Spans

| Key | Type |
|-----|------|
| `tool.name` | string |
| `tool.description` | string |
| `tool.parameters` | object (JSON string) |

### Retriever Spans

| Key | Type |
|-----|------|
| `retrieval.documents` | array |
| `retrieval.documents.N.document.id` | string |
| `retrieval.documents.N.document.score` | float |
| `retrieval.documents.N.document.content` | string |
| `retrieval.documents.N.document.metadata` | object |

### Reranker Spans

| Key | Type |
|-----|------|
| `reranker.input_documents` | array |
| `reranker.output_documents` | array |
| `reranker.query` | string |
| `reranker.model_name` | string |
| `reranker.top_k` | int |

### Embedding Spans

| Key | Type |
|-----|------|
| `embedding.model_name` | string |
| `embedding.text` | string |
| `embedding.vector` | array (numeric) |

### Agent Spans

| Key | Type |
|-----|------|
| `agent.name` | string |

## Examples

Each example shows separate **Imports** and **Code** blocks as entered in the Arize UI.
These illustrate different patterns: metric computation, structured data parsing, and external package usage.

### Pattern: Metric Computation (Token Efficiency)

Computes a ratio from numeric span attributes with threshold-based labeling.

**Imports:**
```python
import json
from typing import Any, Mapping, Optional

from arize.experimental.datasets.experiments.evaluators.base import (
    CodeEvaluator,
    EvaluationResult,
    JSONSerializable,
)
```

**Code:**
```python
class TokenEfficiencyEvaluator(CodeEvaluator):
    def __init__(self, min_ratio: float = 0.2):
        self.min_ratio = min_ratio

    def evaluate(
        self,
        *,
        dataset_row: Optional[Mapping[str, JSONSerializable]] = None,
        **kwargs: Any,
    ) -> EvaluationResult:
        if not dataset_row:
            return EvaluationResult(label="error", score=0.0, explanation="No data")

        prompt_tokens = dataset_row.get("attributes.llm.token_count.prompt") or 0
        completion_tokens = dataset_row.get("attributes.llm.token_count.completion") or 0
        total = prompt_tokens + completion_tokens

        if total == 0:
            return EvaluationResult(label="no_tokens", score=0.0, explanation="No token data")

        ratio = completion_tokens / total
        return EvaluationResult(
            score=round(ratio, 4),
            label="efficient" if ratio > self.min_ratio else "inefficient",
            explanation=f"Completion/total: {completion_tokens}/{total} = {ratio:.2%}",
        )
```

### Pattern: Structured Data Parsing (Retrieval Relevance)

Parses a nested JSON array attribute, aggregates values, and scores with configurable thresholds.

**Imports:**
```python
import json
from typing import Any, Mapping, Optional

from arize.experimental.datasets.experiments.evaluators.base import (
    CodeEvaluator,
    EvaluationResult,
    JSONSerializable,
)
```

**Code:**
```python
class RetrievalRelevanceScorer(CodeEvaluator):
    def __init__(self, min_score: float = 0.5, min_docs: int = 1):
        self.min_score = min_score
        self.min_docs = min_docs

    def evaluate(
        self,
        *,
        dataset_row: Optional[Mapping[str, JSONSerializable]] = None,
        **kwargs: Any,
    ) -> EvaluationResult:
        if not dataset_row:
            return EvaluationResult(label="error", score=0.0, explanation="No data")

        docs_raw = dataset_row.get("attributes.retrieval.documents")
        if not docs_raw:
            return EvaluationResult(label="no_retrieval", score=0.0,
                explanation="No retrieval documents found")

        docs = json.loads(docs_raw) if isinstance(docs_raw, str) else docs_raw
        scores = [d.get("document.score", 0) for d in docs if isinstance(d, dict)]

        if not scores:
            return EvaluationResult(label="no_scores", score=0.0,
                explanation="Documents have no scores")

        avg_score = sum(scores) / len(scores)
        above_threshold = sum(1 for s in scores if s >= self.min_score)
        passed = above_threshold >= self.min_docs and avg_score >= self.min_score

        return EvaluationResult(
            score=round(avg_score, 4),
            label="relevant" if passed else "irrelevant",
            explanation=f"{above_threshold}/{len(scores)} docs above {self.min_score}, avg={avg_score:.3f}",
        )
```

### Pattern: External Package (Schema Validation with Pydantic)

Uses pydantic to validate structured output against a user-defined schema.
Shows how helper classes go in the Code block alongside the evaluator.

**Imports:**
```python
import json
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ValidationError

from arize.experimental.datasets.experiments.evaluators.base import (
    CodeEvaluator,
    EvaluationResult,
    JSONSerializable,
)
```

**Code:**
```python
# Define the expected schema — adapt per use case
class ExpectedOutput(BaseModel):
    answer: str
    confidence: float
    sources: list[str]

class JSONSchemaEvaluator(CodeEvaluator):
    def evaluate(
        self,
        *,
        dataset_row: Optional[Mapping[str, JSONSerializable]] = None,
        **kwargs: Any,
    ) -> EvaluationResult:
        output_raw = dataset_row.get("attributes.output.value") if dataset_row else None

        if not output_raw:
            return EvaluationResult(score=0.0, label="no_output",
                explanation="No output to validate")

        try:
            data = json.loads(str(output_raw)) if isinstance(output_raw, str) else output_raw
        except json.JSONDecodeError as e:
            return EvaluationResult(score=0.0, label="invalid_json",
                explanation=f"JSON parse error: {e}")

        try:
            ExpectedOutput(**data)
            return EvaluationResult(score=1.0, label="valid_schema",
                explanation="Output matches expected schema")
        except ValidationError as e:
            return EvaluationResult(score=0.0, label="schema_mismatch",
                explanation=f"Schema validation failed: {str(e)[:200]}")
```
