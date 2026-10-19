# Sources

Every rule in this skill cites one of these sources, or says it's an **Arize heuristic**. The locator is a page and line where the quote was checked against the PDF's text, counting text lines from the top of the page. Otherwise it's the section the source's notes give. Blogs and docs are cited by heading and paragraph.

## Measurement

| Short name | Source | Locator and what it supports |
|---|---|---|
| Husain & Shankar | *How many examples do I need for an eval?* [hamel.dev](https://hamel.dev/blog/posts/evals-faq/how-many-examples-do-i-need-for-an-eval.html) | "LLM judges need labeled examples" ¶2: "include 30 to 50 Pass examples and 30 to 50 Fail examples in both the dev and test sets." This sets the size condition. |
| Husain | *Using LLM-as-a-Judge for Evaluation* [hamel.dev](https://hamel.dev/blog/posts/llm-judge/) | "How do you validate an LLM judge against human labels?" ¶2: "10 to 20 percent… for training, with 40 to 45 percent each for dev and test". Also report TPR and TNR separately. Critiques detailed enough for few-shot use. |
| Thakur et al. | *Judging the Judges* (v6) [arXiv 2406.12624](https://arxiv.org/abs/2406.12624) | p.2 L111–117: high percent agreement can hide 10–20 point score gaps. p.8 L93–94: "We recommend computing both percent agreement and Scott's π". |
| Mukherjee et al. | *The Geometry of LLM-as-Judge* [arXiv 2606.03043](https://arxiv.org/abs/2606.03043) | Hold one rater out for the human ceiling: scoring against a pooled mean raised r from 0.418 to 0.519. Two or three human-rated demos beat rescaling. |
| Landis & Koch; McHugh 2012 | [McHugh, Biochemia Medica](https://www.biochemia-medica.com/en/journal/22/3/10.11613/BM.2012.031) | κ bands; "any kappa below 0.60 indicates inadequate agreement". The basis of the annotator-agreement warning. |
| Feinstein & Cicchetti 1990; Byrt et al. 1993; Gwet 2008 | High agreement with low κ; PABAK; AC1 | The prevalence effect. The skew measures, when one label holds ≥ 80%. |
| Zheng et al. | *MT-Bench and Chatbot Arena* [arXiv 2306.05685](https://arxiv.org/abs/2306.05685) | Agreement rises when ties are excluded (85% vs about 66%). This is the direction behind the exclusion warning. |
| Shankar et al. | *Who Validates the Validators?* [arXiv 2404.12272](https://arxiv.org/abs/2404.12272) | p.2 L13–15: "it is impossible to completely determine evaluation criteria prior to human judging of LLM outputs" (criteria drift). §7.3.3: a misread criterion can't be fixed with more grades. |

## Revising without overfitting

| Short name | Source | Locator and what it supports |
|---|---|---|
| Dwork et al. | *Generalization in Adaptive Data Analysis and Holdout Reuse* [arXiv 1506.02629](https://arxiv.org/abs/1506.02629) | §5: reusing a holdout reported over 63% where the truth was 50%. The basis for limiting looks at dev. |
| SIREN | Xu et al., *Correcting the Winner's Curse* [arXiv 2605.05973](https://arxiv.org/abs/2605.05973) | Reporting the winner on the same data was biased upward in 176 of 176 cells. The basis for re-scoring the winner on fresh sessions. |
| Bertran, Roth, Wu | *What Fits Doesn't Overfit* [arXiv 2606.11045](https://arxiv.org/abs/2606.11045) | 38 of 102 checkpoints overfit with sample-level access. The reproduce check flagged all 38. |
| Kochelka et al. | *Do LLMs Make More Mistakes If They Do Not Believe the Input Data?* [arXiv 2609.09363](https://arxiv.org/abs/2609.09363) | Table 1: the tuning judge fell from κ_w 0.555 to 0.350 on a held-out set labeled after freezing. A second judge model separates the judge from the measurement. |
| SPEAR | Lu et al. [arXiv 2605.26275](https://arxiv.org/abs/2605.26275) | App. H: dev → test drops of 0.44 and 0.25 κ on a 65/65 re-split. An accuracy-trained optimizer collapsed to the majority label, so optimize π or macro-F1. |
| Elganayni et al. | ICAIL 2026 [arXiv 2604.20726](https://arxiv.org/abs/2604.20726) | Strict signals produced case-specific rules. The basis for `lint`. |

## Production rates

| Short name | Source | Locator and what it supports |
|---|---|---|
| Angelopoulos et al. | *Prediction-Powered Inference* [arXiv 2301.09633](https://arxiv.org/abs/2301.09633) | p.3 L11–13: assumes the labeled and unlabeled data "are independently and identically distributed samples from a common distribution". |
| PPI++ | Angelopoulos, Duchi, Zrnic [arXiv 2311.01453](https://arxiv.org/abs/2311.01453) | A tuned λ, "essentially never worse" than classical or plain PPI |
| Lee et al. | *How to Correctly Report LLM-as-a-Judge Evaluations* (v4) [arXiv 2511.21140](https://arxiv.org/abs/2511.21140) | §6: human-only can beat judge-assisted estimates. §8: PPI is biased when the labeled set's label mix differs from production; Rogan–Gladen survives this. |
| Chen et al. | *Efficient Inference for Noisy LLM-as-a-Judge Evaluation* [arXiv 2601.05420](https://arxiv.org/abs/2601.05420) | For binary labels, PPI++ is the efficient estimator. Intervals were about 3× narrower than Rogan–Gladen on real data. |
| Egami et al. | *Design-based Supervised Learning* [arXiv 2306.04746](https://arxiv.org/abs/2306.04746) | p.1 L16–18: surrogate labels used directly give bias even at 80–90% accuracy. p.3 L26–27 and p.4 L41–43: label-dependent sampling is valid when the probability is known. |
| Zrnic & Candès | *Active Statistical Inference* [arXiv 2403.03208](https://arxiv.org/abs/2403.03208) | p.4 L29: inverse propensity weighting with model-chosen labels |
| Fisch et al. | *Stratified PPI* [arXiv 2406.04291](https://arxiv.org/abs/2406.04291) | §5.2: strata defined by the autorater's own predictions. Read through a summary only; the quote hasn't been checked at page level. |
| Divekar | [arXiv 2606.05308](https://arxiv.org/abs/2606.05308) | Drift degrades the correction, so re-collect labels after a judge version change |

## Internal

- **Eval alignment SOP** (`Alyx-Eval-Alignment-SOP-2026-10-14.md`, with its 2026-10-17 addendum): rules 1–5, steps 1–9, addenda A–G.
- **The 2026-10-05 Alyx L2 adjudication:** found stale judge results and human labels that matched turn 1 only. This is the basis for rule 3 and session records.
- **The 2026-10-16 session-record test:** the same session was labeled `not_applicable` from its turn-1 span record and `filter_correct` from the whole session.

## Arize heuristics

These have no published source. Each is labeled wherever it appears:

- the 10-record and 3-per-label warnings
- the 30% exclusion warning
- the 90% coverage warnings
- the 0.10 dev → test gap (observed gaps were 0.25–0.44 κ in SPEAR and 0.205 κ_w in Kochelka)
- the dev look budget of 5
- the 80% skew threshold
- revising one or two judges per week
