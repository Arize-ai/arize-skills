# Prompt Optimization Workflows

## Optimize a prompt from a failing trace

1. Find failing traces:
   ```bash
   ax spans export PROJECT_ID --filter "status_code = 'ERROR' AND attributes.openinference.span.kind = 'LLM'" -l 5 --output-dir .arize-tmp-traces
   ```
2. Export the trace:
   ```bash
   ax spans export PROJECT_ID --trace-id TRACE_ID --output-dir .arize-tmp-traces
   ```
3. Extract the prompt from the LLM span:
   ```bash
   jq '[.[] | select(.attributes.openinference.span.kind == "LLM")][0] | {
     messages: .attributes.llm.input_messages,
     template: .attributes.llm.prompt_template,
     output: .attributes.output.value,
     error: .attributes.exception.message
   }' trace_*/spans.json
   ```
4. Identify what failed from the error message or output
5. Fill in the optimization meta-prompt (see `meta-prompt.md` in this skill directory) with the prompt and error context
6. Apply the revised prompt

## Optimize using a dataset and experiment

1. Find the dataset and experiment:
   ```bash
   ax datasets list
   ax experiments list --dataset-id DATASET_ID
   ```
2. Export both:
   ```bash
   ax datasets export DATASET_ID
   ax experiments export EXPERIMENT_ID
   ```
3. Prepare the joined data for the meta-prompt
4. Run the optimization meta-prompt (see `meta-prompt.md` in this skill directory)
5. Create a new experiment with the revised prompt to measure improvement

## Debug a prompt that produces wrong format

1. Export spans where the output format is wrong:
   ```bash
   ax spans export PROJECT_ID \
     --filter "attributes.openinference.span.kind = 'LLM' AND annotation.format.label = 'incorrect'" \
     -l 10 --output-dir .arize-tmp-traces
   ```
2. Look at what the LLM is producing vs what was expected
3. Add explicit format instructions to the prompt (JSON schema, examples, delimiters)
4. Common fix: add a few-shot example showing the exact desired output format

## Reduce hallucination in a RAG prompt

1. Find traces where the model hallucinated:
   ```bash
   ax spans export PROJECT_ID \
     --filter "annotation.faithfulness.label = 'unfaithful'" \
     -l 20 --output-dir .arize-tmp-traces
   ```
2. Export and inspect the retriever + LLM spans together:
   ```bash
   ax spans export PROJECT_ID --trace-id TRACE_ID --output-dir .arize-tmp-traces
   jq '[.[] | {kind: .attributes.openinference.span.kind, name, input: .attributes.input.value, output: .attributes.output.value}]' trace_*/spans.json
   ```
3. Check if the retrieved context actually contained the answer
4. Add grounding instructions to the system prompt: "Only use information from the provided context. If the answer is not in the context, say so."
