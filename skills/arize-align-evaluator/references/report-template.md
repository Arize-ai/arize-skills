# Pre-alignment report: what to show the user

Start from the Markdown the script prints, then add the parts that require reading the records. Keep the sections below in this order. Lead with the verdict and the decision needed, not with method.

```markdown
# Aligning <evaluator name> against "<queue name>"

**Verdict: DIRECTIONAL.** <One sentence: what can and cannot be concluded.>
**Decision needed:** <approve / edit / reject the proposal below, or "fix the queue first">.
Nothing has been changed in Arize.

## What the human labels say
- N records; annotators and completion (e.g. "A completed 10/10, B 0/10 pending").
- Distribution after consensus: label → count. Excluded: not applicable n, unscorable n, off-rubric n.
- What the human labels mean: one or two sentences in plain language, such as "humans judge the agent found the right span 7 of 10 times."

## Does this queue fit the evaluator?
- Unit: <span records vs session evaluator: verified / not verified, and how>.
- Rubric: <label sets, label definitions that diverge, classes with no human examples>.
- Applicability: <how many human-not-applicable records the evaluator scored substantively, and why>.
- Version: <current version and date; how many records predate it>.

## Is the queue good enough to align against?
<Gate table from the script, then one line per failed gate on what it means for this decision.>

## Annotator disagreements
<Table of disputed records with both votes and the proposed adjudication, or: "Only one annotator labeled these records; human-human agreement is unknown.">

## Where the evaluator disagrees with the humans
| Record | Session | Human | Evaluator | Who is right, and the evidence |
|---|---|---|---|---|
<One row per discrepancy. Quote the turn or tool call that decides it. Say "ambiguous" if it is.>

## Proposal
EITHER
- **Change:** <quote the exact current template text> → <exact replacement text>.
- **Evidence:** records <IDs>, and the pattern they share.
- **Expected effect:** which discrepancies it should fix; which other classes it could hurt.
OR
- **Do not change the evaluator yet.** Instead: <fix the admission filter / get second labels on N records / add examples of class X / clarify label Y>.

## Uncertainty
<What is unverified: unit mapping not spot-checked, single annotator, stored outputs possibly from an older version, small n.>
```

Rules:
- Give counts and the 95% interval next to every percentage ("8/10 (80%, 95% CI 49–94%)", not "80%"). The script prints them.
- Lead with recall per human label (TPR and TNR for a binary evaluator), then exact agreement.
- One discrepancy is an anecdote, not a pattern. Propose a template change only for a pattern seen in at least 2 gold records, or for one unambiguous instruction bug you can quote.
- Use **arize-link** to add UI links for the queue, the evaluator and each discrepancy's session if the user will review in the UI.
- End with the question and stop. Do not create the candidate evaluator in the same turn.
