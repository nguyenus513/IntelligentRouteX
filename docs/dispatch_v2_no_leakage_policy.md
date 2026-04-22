# Dispatch V2 No Leakage Policy

- Observation-time rows must not contain realized outcome labels.
- Teacher-time rows must not contain outcome-time facts.
- Outcome-time rows must not be reused as observation features without an explicit offline join step.
- Replay logs, raw prompts, provider prose, secrets, headers, and raw tile images are forbidden from Gold datasets.
- Validators must fail on:
  - missing `rowType`
  - missing `candidateId` on candidate rows
  - missing time-layer classification
  - outcome fields present in observation or teacher rows
