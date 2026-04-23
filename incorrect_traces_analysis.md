# What Went Wrong: Traces Where Custom_eval_correctness Was Incorrect

The **Custom_eval_correctness** eval compares **what the user asked for** (“Desired Eval”) to **what the model produced** (“Generated Eval”) and marks a trace incorrect when they don’t align. Below is a summary of what went wrong in the 20 traces.

---

## 1. **Overfitting to travel / haiku (generic “suitable eval” → travel-specific)**

**User asked:** “create a suitable eval for my dataset” (generic, no domain specified).

**What went wrong:** The model inspected the dataset, saw travel/haiku columns (destination, travel_style, budget, etc.), and **always built a travel- or haiku-specific eval** (e.g. “Travel Content Alignment”, “Travel Haiku Relevance”, “Haiku Coherence”) instead of a **general-purpose** eval suitable for “any” dataset.

**Eval explanation:** The Generated Eval is specific to travel/haikus; the user asked for a suitable eval for the dataset without specifying that domain, so the response is misaligned.

**Traces:** 1, 5, 7, 9, 14.

---

## 2. **Literal interpretation of “create everything by yourself”**

**User asked:** “Create everything by yourselft” [sic].

**What went wrong:** The user likely meant “figure it out yourself” or “do it end-to-end.” The **correctness eval** treated “by yourself” as “**without any tool calls or external data**.” The model used `get_dataset_preview`, `build_eval`, `create_eval_form`, etc., so the eval said the response did not fulfill “created entirely by the AI itself.”

**Traces:** 2.

---

## 3. **“Implement it” treated as eval content, not as instruction**

**User asked:** “implement it” (follow-up in context of a dataset/eval).

**What went wrong:** The model responded with tool calls and an evaluation framework. The eval expected the response to **directly implement** the user’s request in line with the **current context** (e.g. evaluator hub state, time), not to output a generic eval template and tool-call sequence. So “implementation” was judged as not directly addressed.

**Traces:** 3.

---

## 4. **Generic troubleshooting instead of user-specific code help**

**User asked:** Help with GT_OCR-4-Testing, CustomArizeEvaluator, code evaluator class, column name, etc.

**What went wrong:** The model gave a **general** troubleshooting guide (e.g. “message about Arize API key is expected…”). It did **not** tie advice to the user’s **exact** code, parameters, dataset structure, or confirm whether their test was actually passing/failing. So the response was not tailored to the Desired Eval’s specific setup.

**Traces:** 4.

---

## 5. **Answering out of scope / deflecting**

**User asked:** About RBAC, space topology, projects, monitors, dashboards, naming, user access.

**What went wrong:** The model said it’s for building evaluations and pointed to docs/customer success. It **did not answer** the RBAC/space-architecture question. So the Generated Eval was judged as not addressing the user’s question.

**Traces:** 6.

---

## 6. **Right answer but too much extra (verbosity / tool calls)**

**User asked:** “what attribute do I want to put in the {} to target the actual user input from a trace?”

**What went wrong:** The model **did** give the right attribute (`attributes.input.value`) but also added tool-call signatures and long explanation. The eval expected a **direct, concise** answer to “what attribute,” so the extra content made the response “not accurately reflect the user’s request in a concise manner.”

**Traces:** 8.

---

## 7. **Clarification instead of doing the task**

**User asked:** “posh” (in context of a toxicity evaluator).

**What went wrong:** The model asked for clarification (edit? test? review? create new?). The **correctness** eval expected the model to **perform** the toxicity eval task (classify as toxic/non-toxic per criteria), not to ask what to do. So “asks for clarification” was labeled incorrect.

**Traces:** 10.

---

## 8. **Hard failure: API key error**

**User asked:** “Customize this template for stock market prediction.”

**What went wrong:** The response was a **user-facing error** (e.g. “401 Incorrect API key provided: blah”). So the Generated Eval was completely unrelated to the desired stock-market hallucination eval; it was an auth failure.

**Traces:** 11.

---

## 9. **Incomplete or wrong eval structure (RAG, compliance, user frustration)**

**User asked:** e.g. “build a RAG relevance for travel,” “compliance eval for telecoms,” “user frustration eval.”

**What went wrong:**

- **RAG relevance (travel):** Model started (find dataset, build eval) but did not **finalize** the evaluation template/criteria as specified; used different labels (e.g. relevant/irrelevant vs correct/incorrect); or indicated missing columns.
- **Compliance (telecoms):** Response was mostly **procedural steps and tool calls**, not a clear evaluation framework; used different classification choices (e.g. compliant/partial/non_compliant vs the requested correct/incorrect).
- **User frustration:** Either the response was mostly **process** (steps, tool calls) rather than a **final, clear eval structure**, or the **output was empty** (spans 18–20 had empty `output.value` and status UNSET), so no evaluation content was produced at all.

**Traces:** 12, 13, 17, 18, 19, 20.

---

## 10. **Wrong format or style (review/fixes, step 4)**

**User asked:** “Review the Template prompt and suggest fixes” or “How to write step 4?”

**What went wrong:**

- **Review/suggest fixes:** The eval expected a **structured, concise review** of the template and fixes. The model gave **tool calls and a long explanation** instead, so it didn’t “address the user’s request in a structured manner.”
- **Step 4:** The user wanted a **strict JSON output**. The model suggested **removing** the JSON output requirement. So the Generated Eval contradicted the Desired Eval’s format.

**Traces:** 15, 16.

---

## Summary Table

| Failure mode | # Traces | Main issue |
|-------------|----------|------------|
| Travel/haiku overfitting (generic “suitable eval”) | 5 | Model always built travel/haiku evals instead of general evals. |
| Literal “by yourself” (no tools) | 1 | Eval expected no tool use; model used tools. |
| “Implement it” not tied to context | 1 | Response was generic eval content, not direct implementation. |
| Generic vs specific troubleshooting | 1 | General guide, not tailored to user’s code/setup. |
| Out of scope / deflection | 1 | Didn’t answer RBAC/space question. |
| Correct but too verbose | 1 | Right attribute, but extra tool calls/explanation. |
| Clarification instead of execution | 1 | Asked what to do instead of doing toxicity eval. |
| API key / hard error | 1 | Response was an error, not an eval. |
| Incomplete/wrong eval structure | 6 | Process only, wrong labels, or empty output. |
| Wrong format (review, step 4) | 2 | Not structured/concise or contradicted required format. |

---

## Recommendations (high level)

1. **“Create a suitable eval”:** Avoid defaulting to travel/haiku when the dataset has those columns; support a “general suitability” or ask the user for domain.
2. **Intent vs literal:** Treat “by yourself” as “end-to-end by you,” not “no tools”; align correctness rubric with that.
3. **Follow-up (“implement it”):** Stronger use of conversation/dataset/eval-hub context so the response implements the current intent, not a generic eval.
4. **Specific vs generic:** For code/troubleshooting, tie answers to the user’s exact code, columns, and test outcome.
5. **Scope:** Either answer RBAC/architecture within scope or clearly say “out of scope” and still satisfy the eval if that’s the intended behavior.
6. **Conciseness:** When the user asks for one thing (e.g. attribute name), prefer a short, direct answer; optional “want more detail?” instead of long default output.
7. **Ambiguous input (“posh”):** Define correctness for very short/ambiguous queries (clarify vs infer-and-act) and align the eval with that.
8. **Infrastructure:** Handle auth/API key errors so the response is not a raw error when the user asked for an eval.
9. **Complete evals:** For “build X eval,” ensure the response includes a **final** template/criteria/labels, not only steps; handle empty outputs (e.g. timeouts, truncation).
10. **Format compliance:** For “review and suggest fixes” or “how to write step N,” enforce structured, concise output and required format (e.g. strict JSON) in the eval.
