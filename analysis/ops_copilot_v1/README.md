# Operations Copilot V1

This folder defines the interface contract for the manicure operations copilot.

## Files

- `ops_copilot_schema.json`
  Input/output schema for a strategy generation call

- `ops_copilot_system_prompt.md`
  System prompt template for an LLM-backed operations assistant

- `ops_copilot_example_request.json`
  Example request payload

- `ops_copilot_example_response.json`
  Example response payload

## Intended usage

1. Load the strategy rules from `analysis/ops_strategy_v1/ops_strategy_rules_v1.json`
2. Build a request payload matching `ops_copilot_schema.json`
3. Use `ops_copilot_system_prompt.md` as the system instruction
4. Ask the LLM to return JSON only
5. Render the response in the operations UI or recommendation backend

## Scope

This contract is intended for:

- campaign recommendation generation
- persona-specific style recommendation
- occasion-based promotion planning
- operator decision support

It is not intended for:

- image generation
- direct inventory write-back
- autonomous budget execution
