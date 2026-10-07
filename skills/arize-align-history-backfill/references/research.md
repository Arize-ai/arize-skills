# Where the defaults come from

Each part of the backfill method either rests on a published source or is an Arize heuristic. This page says which. Heuristics are starting points: change them when a user has a reason, and say so in the plan.

The tag after each source says how far it was checked: **[read]** means the source itself was read, **[abstract]** only its abstract or summary page, **[secondary]** a citation or summary of it elsewhere. Practitioner pages were read through a summarizing tool, so paraphrase them; check the live page before quoting one word for word.

| Design choice | Basis |
|---|---|
| Backfill history with an evaluation task | Arize recommends a one-time backfill over historical data to set a baseline before continuous evaluation **[read]**. |
| Backfilled labels only choose records; humans label blind | Treating model labels as ground truth biases downstream estimates substantially, even at 80–90% surrogate accuracy (Egami et al. 2023) **[abstract]**. Using model predictions to decide what humans label is established practice in prediction-powered and active inference (Angelopoulos et al. 2023 **[abstract]**; Zrnic & Candès 2024 **[read]**). This protects the labels, not the metrics computed on the chosen records: those need each record's selection probability, which **arize-align-queue-builder** records per stratum. |
| Measure run-to-run noise with a second copy before blaming noise | Hosted LLMs are not repeatable at temperature 0. Atil et al. report accuracy swings of up to 15% across runs and answer agreement from 0% to 99.6% depending on model and task **[abstract]**. Thinking Machines got 80 distinct completions from 1,000 identical temperature-0 calls, because server batch size changes with load (He 2025) **[read]**. Judge test-retest reliability varies by task (Schroeder & Wood-Doughty 2024 **[abstract]**; Lau 2026 **[abstract]**). So the noise floor must be measured, not assumed. |
| Report κ next to raw label agreement | Raw agreement overstates consistency; κ runs well below it on skewed labels (Norman et al. 2026) **[abstract]**. |
| Settings that don't copy are a finding, not a footnote | Output format changes results systematically, not just their variance: JSON-constrained output cut one model's GSM8K accuracy from 86.5% to 23.4% (Tam et al. 2024) **[secondary]**. Temperature changes run-to-run variance **[secondary]**. Compare the label mix, not only agreement. |
| Pin the model and record it with every backfill | Model behavior behind one name changes over time: GPT-4's accuracy on one task fell from 84% to 51% between March and June 2023 (Chen, Zaharia & Zou 2023) **[read]**. An alias may point at a different snapshot than production used; `copy-evaluator` writes a manifest and warns on alias-looking names. If production's snapshot is no longer available, treat the copy as a new evaluator. |
| Set aside disagreements where the two runs saw different turn counts | **Arize heuristic** with adjacent support: LangSmith waits for a thread to go idle (10 minutes by default) before scoring it, and does not backfill multi-turn evaluators **[read]**. No study measures how often verdicts flip between partial and complete conversations. |
| Only compare an evaluator with an exact copy of itself | **Arize heuristic.** A predecessor was built to behave differently, so its labels and admission are not a reference. |
| Admission must match within 5% each way; one-day check; 5% noise margin | **Arize heuristics.** Arize advises starting with a low sampling rate and scaling up **[read]**, which the one-day check follows. |
| Check that the platform accepts results on old spans | Arize's online-evals docs say evals apply to spans up to 14 days back **[read]**. It is not confirmed whether this limits task backfills; check the test slice before running a window older than 14 days. |

## Sources

- Angelopoulos AN, Bates S, Fannjiang C, Jordan MI, Zrnic T. "Prediction-Powered Inference." *Science*, 2023. https://arxiv.org/abs/2301.09633
- Arize AX. Online evals. https://arize.com/docs/ax/observe/online-evals
- Arize AX. Run evals on traces. https://arize.com/docs/ax/evaluate/run-evals-on-traces
- Atil B et al. "Non-Determinism of 'Deterministic' LLM Settings." 2024. https://arxiv.org/abs/2408.04667
- Chen L, Zaharia M, Zou J. "How is ChatGPT's behavior changing over time?" 2023. https://arxiv.org/abs/2307.09009
- Egami N, Hinck M, Stewart BM, Wei H. "Using Imperfect Surrogates for Downstream Inference." NeurIPS 2023. https://arxiv.org/abs/2306.04746
- He H / Thinking Machines Lab. "Defeating Nondeterminism in LLM Inference," 2025. https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/
- LangSmith. Multi-turn online evaluations. https://docs.langchain.com/langsmith/online-evaluations-multi-turn
- Lau. "Same Input, Different Scores." 2026. https://arxiv.org/abs/2603.04417
- Norman, Rivera, Hughes. "Reliability without Validity." 2026. https://arxiv.org/abs/2606.19544
- Schroeder K, Wood-Doughty Z. "Can You Trust LLM Judgments? Reliability of LLM-as-a-Judge." 2024. https://arxiv.org/abs/2412.12509
- Tam et al. "Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models." 2024. https://arxiv.org/abs/2408.02442
- Zrnic T, Candès EJ. "Active Statistical Inference." ICML 2024. https://arxiv.org/abs/2403.03208
