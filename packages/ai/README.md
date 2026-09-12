# packages/ai

Agents, tools, prompts, schemas, memory, and the `AIProvider` abstraction
(Anthropic, OpenAI, ... interchangeable behind one interface).

Empty scaffold. The tool system (Phase 7) lands before any agent, since
agents may only act through explicitly defined, permissioned tools — never
via `execute_sql` or an arbitrary HTTP request tool.
