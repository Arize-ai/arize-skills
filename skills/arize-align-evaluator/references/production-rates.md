# Production rates (SOP step 8)

A judge's raw pass rate is biased whenever it errs: too high when the true rate is low, and too low when it's high (Lee). The report corrects it with human labels. Source names refer to [sources.md](sources.md).

## What the report computes

Pass `--plan plan.json` from **arize-align-queue-builder**. For each label, the report shows:

- **Judge only:** the judge's share of that label over every scored unit in the plan's window. It's biased.
- **Corrected (PPI++):** the judge's rate, corrected with the human labels from the plan's **random stream**, with λ tuned per label (Angelopoulos; PPI++). For binary labels this is the efficient estimator (Chen).
- **Human only:** the rate among the random-stream human labels alone.

Use whichever of the corrected and human-only intervals is narrower. The judge doesn't always earn its keep: on one benchmark, human-only estimates beat every judge-assisted one (Lee §6).

## What it assumes

- **The labeled records are a random sample of the same traffic** (Angelopoulos p.3 L11–13). Only random-stream records are used. Gold-queue records never are (SOP rule 5).
- **The labeled records' label mix matches production.** It does for a uniform random stream. If the random stream was stratified and its weights are missing, PPI is biased (Lee §8). Fix the weights, or use the Rogan–Gladen sensitivity/specificity correction, which stays unbiased while the judge's error rate per true label holds.
- **The same judge version on both sets.** Re-collect random-stream labels after any judge version change. Drift also degrades the correction over time (Divekar).

## The gold queue

Production-weighted agreement and recall on the targeted queue are a secondary estimate. Label-dependent selection supports estimates when each stratum's selection probability is known and used (Egami p.4 L41–43; Zrnic & Candès; Fisch et al.). They also assume uniform sampling inside each stratum. The queue builder rotates across entry points inside a label without recording it, so take measurement from the calibration queue.

## With few labels

With fewer than 30 random-stream labels, the normal-approximation intervals are rough, and the report says so. Report the interval, not the point estimate.
