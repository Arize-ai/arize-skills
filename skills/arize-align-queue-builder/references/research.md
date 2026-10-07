# Where the defaults come from

Each part of the queue design either rests on a published source or is an Arize heuristic. This page says which. Heuristics are starting points: change them when a user has a reason, and say so in the plan.

The tag after each source says how far it was checked: **[read]** means the source itself was read, **[abstract]** only its abstract or summary page, **[secondary]** a citation or summary of it elsewhere, and **[computed]** a number worked out here. Practitioner pages were read through a summarizing tool, so paraphrase them; check the live page before quoting one word for word.

| Design choice | Basis |
|---|---|
| Sample each of the evaluator's stored labels separately | Stratifying by a classifier's predicted label is the standard design for evaluating classifiers on skewed data; Bennett & Carvalho (2010) report about 20% less labeling than simple random sampling **[secondary]**. |
| Agreement within a stored label is precision, not recall | Stratifying by the prediction makes precision per predicted label directly estimable. Recall and production-wide agreement need each stratum weighted by its production count (Bennett & Carvalho 2010 **[secondary]**; Cochran's *Sampling Techniques* **[secondary]**). Practitioners measure judges by TPR and TNR (Husain) **[read]**, so the plan records production counts per stratum for `report --plan`. |
| Provider disagreements first, as their own weighted stratum, capped at 40% | Choosing records where two models disagree is query-by-committee (Seung, Opper & Sompolinsky 1992; Settles 2009) **[secondary]**, which finds errors efficiently. For measurement it biases agreement down, because those records are harder; active evaluation methods require a known selection probability and weighting by it (Kossen et al. 2021 **[secondary]**; Zrnic & Candès 2024 **[read]**; Poms et al. 2021 **[secondary]**). The plan therefore records disagreement as a sub-stratum with its own count. The 40% cap is an Arize heuristic. Both copies can share an error, so disagreement is not a complete error detector (Verga et al. 2024 on judge panels **[secondary]**). |
| Default sizing: about 10 gold records over all labels, ≥ 3 per label | **Arize heuristic** matching the evaluator's DIRECTIONAL tier. It catches gross misalignment but can't confirm alignment: 5/5 agreement has a 95% interval of about 57–100% **[computed]**. |
| `--mode validation`: ≥ 30 gold per label, ≥ 50 in all | Husain recommends 30–50 examples of each outcome in each of the dev and test sets **[read]**; Arize's alignment guide asks for 50–100 labeled examples **[read]**. Matches the evaluator's VALIDATED tier. |
| Expected exclusion 30% | **Arize heuristic**, from the 30–60% not-applicable rates seen on real queues. Use the previous queue's observed rate when there is one. |
| Two not-applicable records; scope probes | **Arize heuristics.** They are one-way tripwires for an applicability rule that is too strict, not estimates: 2/2 still has a 95% interval of about 34–100% **[computed]**. Reported separately and left out of the weighting strata. No published work covers checking a judge's applicability rule. |
| One record per session; skip units in earlier queues | Standard cluster sampling: turns of one session are not independent **[secondary]**. Note that skipping earlier queues shrinks the pool for rare labels. |
| Spread picks over time and entry points | Supported as coverage; note that a fixed quota per slice weights toward a balanced mix rather than production's, which the strata weighting corrects only by label. |
| Annotators label blind to the evaluator | Annotators who edit model output show an anchoring effect and overestimate the model (Berzak et al. 2016) **[secondary]**. A counterexample found no noteworthy bias for expert annotators (Schulz et al. 2019) **[abstract]**, so blindness is the safe default. |
| `cannot_judge` and `not_applicable` options | An "I don't know" option improved accuracy in Torre et al. (2019) **[abstract]**. Report exclusions per label, because the excluded records are likely the hard ones. |
| Version the instructions; top up only on counts | Grading criteria change as people label ("criteria drift", Shankar et al. 2024) **[abstract]**, so record which instructions each batch saw. A top-up triggered by low agreement so far would bias the result; trigger it only on label counts or exclusion rates, and draw with the same rules. |

## Sources

- Arize AX. "Align evals to human feedback." https://arize.com/docs/ax/evaluate/align-evals-to-human-feedback.md
- Bennett PN, Carvalho VR. "Online stratified sampling: evaluating classifiers at web-scale." CIKM 2010. https://www.microsoft.com/en-us/research/?p=161806
- Berzak Y et al. "Anchoring and Agreement in Syntactic Annotations." EMNLP 2016. https://arxiv.org/abs/1605.04481
- Cochran WG. *Sampling Techniques*, 3rd ed., Wiley, 1977.
- Husain H. "AI Evals FAQ." https://hamel.dev/blog/posts/evals-faq/
- Kossen J et al. "Active Testing: Sample-Efficient Model Evaluation." ICML 2021. https://proceedings.mlr.press/v139/kossen21a.html
- Poms F et al. "Low-Shot Validation: Active Importance Sampling for Estimating Classifier Performance on Rare Categories." ICCV 2021. https://arxiv.org/abs/2109.05720
- Schulz C et al. "Analysis of Automatic Annotation Suggestions for Hard Discourse-Level Tasks in Expert Domains." ACL 2019. https://arxiv.org/abs/1906.02564
- Settles B. "Active Learning Literature Survey." UW-Madison TR 1648, 2009. https://burrsettles.com/pub/settles.activelearning.pdf
- Shankar S et al. "Who Validates the Validators?" UIST 2024. https://arxiv.org/abs/2404.12272
- Torre M, Nakayama S, Tolbert TJ, Porfiri M. "Producing knowledge by admitting ignorance." *PLOS ONE*, 2019. https://ideas.repec.org/a/plo/pone00/0211907.html
- Verga P et al. "Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models." 2024. https://arxiv.org/abs/2404.18796
- Zrnic T, Candès EJ. "Active Statistical Inference." ICML 2024. https://arxiv.org/abs/2403.03208
