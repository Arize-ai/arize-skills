# Optimization Meta-Prompt Template

Use this template to generate an improved version of a prompt. Fill in the three placeholders and send it to your LLM (GPT-4o, Claude, etc.):

````
You are an expert in prompt optimization. Given the original baseline prompt
and the associated performance data (inputs, outputs, evaluation labels, and
explanations), generate a revised version that improves results.

CONSTRAINTS (do not violate these during optimization)
======================================================

{PASTE_ANY_HARD_CONSTRAINTS_HERE}
Examples: "Output must be valid JSON", "Response must be under 200 tokens",
"Must cite sources", "Must not change the output format schema",
"Must preserve all {template_variables}"

ORIGINAL BASELINE PROMPT
========================

{PASTE_ORIGINAL_PROMPT_HERE}

========================

PERFORMANCE DATA
================

The following records show how the current prompt performed. Each record
includes the input, the LLM output, and evaluation feedback:

{PASTE_RECORDS_HERE}

================

HOW TO USE THIS DATA

1. Compare outputs: Look at what the LLM generated vs what was expected
2. Review eval scores: Check which examples scored poorly and why
3. Examine annotations: Human feedback shows what worked and what didn't
4. Identify patterns: Look for common issues across multiple examples
5. Focus on failures: The rows where the output DIFFERS from the expected
   value are the ones that need fixing

ALIGNMENT STRATEGY

- If outputs have extra text or reasoning not present in the ground truth,
  remove instructions that encourage explanation or verbose reasoning
- If outputs are missing information, add instructions to include it
- If outputs are in the wrong format, add explicit format instructions
- Focus on the rows where the output differs from the target -- these are
  the failures to fix

RULES

Maintain Structure:
- Use the same template variables as the current prompt ({var} or {{var}})
- Don't change sections that are already working
- Preserve the exact return format instructions from the original prompt

Avoid Overfitting:
- DO NOT copy examples verbatim into the prompt
- DO NOT quote specific test data outputs exactly
- INSTEAD: Extract the ESSENCE of what makes good vs bad outputs
- INSTEAD: Add general guidelines and principles
- INSTEAD: If adding few-shot examples, create SYNTHETIC examples that
  demonstrate the principle, not real data from above

Goal: Create a prompt that generalizes well to new inputs, not one that
memorizes the test data.

OUTPUT FORMAT

Return the revised prompt as a JSON array of messages:

[
  {"role": "system", "content": "..."},
  {"role": "user", "content": "..."}
]

Also provide a brief reasoning section (bulleted list) explaining:
- What problems you found
- How the revised prompt addresses each one
````
