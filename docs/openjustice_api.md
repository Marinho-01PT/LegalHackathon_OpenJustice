# OpenJustice API – what we use (from https://api.openjustice.ai/api/docs, read 2026-11-07)

Auth: `Authorization: Bearer <API key>` (key from https://openjustice.ai/api-keys/new, acts as you).

## Protocol Graph – `GET /reasoning-protocols/{id}`
`{id, name, description[], version, visibility, startNodeId[], nodes[], edges[]}`
- node types: `start`, `fact` (`factDefinitions[]`: id, label, question, instructions, dataType, required),
  `reasoning` (question, instructions, dataType, customEnumValues, annotations[] with sources),
  `switch`, `outcome` (responseType, instructions, template)
- edges: `{from, to, kind}`; kind = `next` | `branch` | `sub_reasoning`
  - `branch.conditions[]`: `{sourceNodeId, operator (== != > >= < <= contains starts_with ends_with), compareValue, conditionOperator (AND|OR)}`, plus `isDefault`
  - `sub_reasoning`: child reasoning node that runs first and feeds its parent (**direction to verify**)
- `GET /reasoning-protocols?scope=own|community|all` lists protocols.

## Baseline engine – `POST /reasoning-protocol/v1/responses` (OpenAI Responses format)
Body: `{reasoning_protocol_id, model, input}`; default model `gpt-5.4-mini`; models: `GET /reasoning-protocol/v1/models`.
Output items in run order: `node_result` (node_id, node_type, output, usage), `fact` (prediction, probability,
rationale), assistant `message` per Outcome. `status`: completed | incomplete (`awaiting_input` → `pending_input`
item; resume with `previous_response_id` + answer) | failed. Exact LLM calls per node:
`GET /reasoning-protocol/v1/responses/{id}/node_results/{nr_id}/trace` (`call_count`, `calls[]`).
Not allowed: `instructions`, `tools`, `temperature`, ... (400).

## Agent – `POST /agent/v1/responses` (OpenAI Responses format, stateless)
Body: `{model, instructions, input, tools, text.format, max_tool_calls}`; models: `GET /agent/v1/models`.
Tools run server-side: file_search, read_file (+cite), list_files, list_tags, web_search, web_fetch, todo_write,
agent (subagent). Omit `tools` = all enabled; `[]` = none. `text.format` json_schema (strict) is validated.
Limits: max 3 agent requests in flight per user; daily token budget (429).
