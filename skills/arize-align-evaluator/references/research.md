# Where the defaults come from

Each default in this skill either rests on a published source or is an Arize heuristic. This page says which. Heuristics are starting points: change them when a user has a reason, and state the new value in the report.

Some sources were only partly checked. The tag after each one says how far: **[read]** means the source itself was read, **[abstract]** only its abstract or summary page, **[secondary]** a citation or summary of it elsewhere, and **[computed]** a number worked out here. Practitioner pages were read through a summarizing tool, so paraphrase them; check the live page before quoting one word for word.

## Sample size and the two tiers

| Default | Basis |
|---|---|
| DIRECTIONAL needs ≥ 10 gold records, ≥ 2 classes with ≥ 3 each | **Arize heuristic.** It is a floor for starting alignment, not for a claim. At 10 records, 9/10 agreement has a 95% Wilson interval of about 60–98% **[computed]**, so every target in the table below fits inside one interval. |
| VALIDATED needs ≥ 50 gold records and ≥ 2 classes with ≥ 30 each | Arize's alignment guide asks for 50–100 labeled examples before trusting the metrics **[read]**. Husain recommends 30–50 examples of each outcome in each of the dev and test sets, and warns that intervals are too wide below about 60 examples **[read]**. Telling 80% from 90% agreement takes roughly 83–108 records **[computed]**. |
| Print a 95% interval next to every rate | Wilson (1927) score interval, as recommended over the normal approximation by Brown, Cai & DasGupta (2001) **[secondary]**; see the NIST/SEMATECH e-Handbook. |

## Agreement between annotators

| Default | Basis |
|---|---|
| Cohen's κ ≥ 0.6 per annotator pair | McHugh (2012) treats κ below 0.60 as inadequate agreement **[read]**, and 0.61 is where Landis & Koch's "substantial" band starts **[secondary]**. It is a lenient floor: Krippendorff accepts α ≥ 0.667 only for tentative conclusions and wants 0.80 for firm ones **[secondary]**, and Artstein & Poesio (2008) recommend 0.8 **[secondary]**. |
| κ bands | Landis & Koch (1977): below 0 poor, 0.00–0.20 slight, 0.21–0.40 fair, 0.41–0.60 moderate, 0.61–0.80 substantial, 0.81–1.00 almost perfect **[secondary, cut-points confirmed via McHugh]**. |
| Accept AC1 ≥ 0.6 when one label holds ≥ 80% of a pair's votes | The kappa paradox: with one dominant class, κ is low even when raw agreement is high (Feinstein & Cicchetti 1990; Byrt, Bishop & Carlin 1993) **[secondary]**. Gwet's AC1 (Gwet 2008) **[secondary]** and PABAK (Byrt et al. 1993) **[secondary]** correct for it. Worked example: 20 shared records, 18 agree, 90% one label gives κ = 0.44, AC1 = 0.88, PABAK = 0.80 **[computed]**. The 80% cut-off is an Arize heuristic. |
| Note when a pair shares fewer than 20 records | κ from 10 records has a very wide interval, roughly 0.26–1.0 at moderate agreement **[computed]**; see Sim & Wright (2005) on κ sample sizes **[secondary]**. The 20 is an Arize heuristic. |
| A single annotator is allowed | Husain recommends one domain expert ("benevolent dictator") as the source of truth for most teams **[read]**. The report still says that each gold label rests on one person. |
| Adjudicate disputes and keep both original votes | The MATTER annotation cycle (Pustejovsky & Stubbs) revises guidelines and adjudicates instead of discarding disagreement **[read]**. "Majority vote only with 3+ annotators" is an Arize heuristic. |

## Measuring the evaluator

| Default | Basis |
|---|---|
| Report recall per human label (TPR and TNR) and balanced accuracy, not only exact agreement | A judge that always passes scores 95% agreement when 5% of outputs fail, and catches nothing (Husain) **[read]**. Thakur et al. (2024) show percent agreement hides large differences between judges **[read]**. Yan (2024) recommends precision, recall and κ **[read]**. |
| Agreement targets by evaluator type (85–90%, 80–85%, 70–80%, 70–75%) | **Arize heuristic**, kept from the original version of this skill. Anchors: McHugh's 80% minimum for percent agreement **[read]**; Arize's 75–85% guidance **[read]**. For crisp binary tasks the bar may be too low: humans agreed 98.5% on TriviaQA grading in Thakur et al. **[read]**. |
| The evaluator is held to measured human-human agreement, not a fixed ceiling | A judge can match or slightly exceed humans: GPT-4 agreed with humans 85% of the time against 81% between humans, ties excluded (Zheng et al. 2023) **[read]**. Agreement varies widely by task (Bavaresco et al. 2025, JUDGE-BENCH) **[read]**, so measure it on this queue. |
| Train / dev / test split by human label (15% / 42.5% / 42.5%), test scored once | Husain uses 10–20% train, 40–45% dev, 40–45% test, and keeps dev and test examples out of the prompt **[read]**. Yan (AlignEval) warns that a judge overfits the examples it is tuned on **[read]**. |
| Few-shot examples only from the train split | Husain **[read]**. |

## Workflow

| Default | Basis |
|---|---|
| Check the human labels fit the evaluator (unit, rubric, input) | Arize names a judge scoring a different dimension than the annotation as the most common mismatch, and says to check the variable mappings **[read]**. Husain: the human and the judge must see the same information **[read]**. Span-vs-session matching is an Arize addition. |
| Read every disagreement; sometimes the human is wrong | Husain inspects disagreements by hand before tuning a prompt **[read]**. People's grading criteria change as they label ("criteria drift", Shankar et al. 2024) **[abstract]**. |
| Iterate on a candidate copy against a fixed baseline | Arize saves an aligned evaluator as a new version **[read]**; LangSmith Align Evals compares against a saved baseline **[read]**. |
| Compare before and after with intervals, flipped records and the label mix | Yan: metrics fluctuate a lot on small samples **[read]**. Thakur et al.: judges are sensitive to prompt length and tend to be lenient, so a revision can shift the overall pass rate **[read]**. |
| Stop for approval; stop after 3–4 iterations or on a plateau | **Arize heuristics.** No published source covers them. |
| Flag results scored before a session ended | **Arize heuristic** with adjacent support: LangSmith waits for a thread to go idle (10 minutes by default) before scoring it **[read]**. |
| Prefer a judge model different from the one that generated the output | Judges favor their own outputs (Panickssery, Bowman & Feng 2024) **[read]**; Anthropic's evaluation guide recommends grading with a different model **[read]**. |
| Exclusion cap 30%; join and stored-output coverage 90% | **Arize heuristics.** Risk: if the excluded records are the hard ones, excluding them inflates agreement, as excluding ties did in Zheng et al. **[read]**. |

## Sources

- Arize AX. "Align evals to human feedback." https://arize.com/docs/ax/evaluate/align-evals-to-human-feedback.md
- Artstein R, Poesio M. "Inter-Coder Agreement for Computational Linguistics." *Computational Linguistics* 34(4), 2008. https://aclanthology.org/J08-4004/
- Bavaresco A et al. "LLMs instead of Human Judges? A Large Scale Empirical Study across 20 NLP Evaluation Tasks." ACL 2025. https://arxiv.org/abs/2406.18403
- Byrt T, Bishop J, Carlin JB. "Bias, prevalence and kappa." *J Clin Epidemiol* 46(5), 1993. https://pmc.ncbi.nlm.nih.gov/articles/PMC2636838
- Feinstein AR, Cicchetti DV. "High agreement but low kappa: I." *J Clin Epidemiol* 43(6), 1990.
- Gwet KL. "Computing inter-rater reliability and its variance in the presence of high agreement." *BJMSP* 61, 2008. https://agreestat.com/papers/bjmsp2008_interrater.pdf
- Husain H. "Using LLM-as-a-Judge For Evaluation: A Complete Guide." https://hamel.dev/blog/posts/llm-judge/
- Husain H. "AI Evals FAQ." https://hamel.dev/blog/posts/evals-faq/
- Krippendorff K. *Content Analysis*, 2nd ed., Sage, 2004. https://en.wikipedia.org/wiki/Krippendorff%27s_alpha
- LangChain. "Introducing Align Evals," 2025. https://www.langchain.com/blog/introducing-align-evals
- LangSmith. Multi-turn online evaluations. https://docs.langchain.com/langsmith/online-evaluations-multi-turn
- Landis JR, Koch GG. "The Measurement of Observer Agreement for Categorical Data." *Biometrics* 33(1), 1977. https://pubmed.ncbi.nlm.nih.gov/843571/
- McHugh ML. "Interrater reliability: the kappa statistic." *Biochemia Medica* 22(3), 2012. https://www.biochemia-medica.com/en/journal/22/3/10.11613/BM.2012.031
- NIST/SEMATECH e-Handbook, confidence intervals for proportions. https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm
- Panickssery A, Bowman SR, Feng S. "LLM Evaluators Recognize and Favor Their Own Generations." NeurIPS 2024. https://arxiv.org/abs/2404.13076
- Pustejovsky J, Stubbs A. MATTER cycle overview. https://arxiv.org/pdf/1602.05753
- Shankar S et al. "Who Validates the Validators? Aligning LLM-Assisted Evaluation of LLM Outputs with Human Preferences." UIST 2024. https://arxiv.org/abs/2404.12272
- Sim J, Wright CC. "The Kappa Statistic in Reliability Studies." *Physical Therapy* 85(3), 2005. https://academic.oup.com/ptj/article/85/3/257/2805933
- Thakur AS et al. "Judging the Judges: Evaluating Alignment and Vulnerabilities in LLMs-as-Judges." 2024. https://arxiv.org/abs/2406.12624
- Yan E. "Evaluating the Effectiveness of LLM-Evaluators (aka LLM-as-Judge)," 2024. https://eugeneyan.com/writing/llm-evaluators/
- Yan E. "AlignEval," 2024. https://eugeneyan.com/writing/aligneval/
- Zheng L et al. "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena." NeurIPS 2023. https://arxiv.org/abs/2306.05685
